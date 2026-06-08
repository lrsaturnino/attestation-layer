from __future__ import annotations

import os
from pathlib import Path
from typing import Protocol, runtime_checkable


NLREQ_API_KEY_ENV = "NLREQ_ANTHROPIC_API_KEY"

# Model used for controlled-rewrite drafting. Temperature=0 for best-effort
# reproducibility; callers must still treat output as untrusted.
_DEFAULT_MODEL = "claude-haiku-4-5-20251001"

# Sentinel a drafting model emits in place of controlled text when it is NOT confident
# it can faithfully translate a (typically non-English) fragment. The intake layer turns
# this into a clarification refusal instead of letting a guessed rewrite reach the parser
# (PA-11: low-confidence cross-language fragments refuse rather than guess). The text after
# the sentinel is the model's stated reason / the fragment it could not map.
CROSS_LANGUAGE_CLARIFY_SENTINEL = "[[NLR-CLARIFY]]"


def language_prompt_addendum(language: str) -> str:
    """Extra prompt guidance for non-English prose; empty for English.

    The IR and controlled DSL are language-neutral (symbols normalise to snake_case), so
    the model is asked to translate MEANING while keeping merchant names, identifiers, and
    quoted string literals VERBATIM in the original language. Returns "" for ``en`` so the
    English prompt — and therefore its pinned prompt_hash — is unchanged.
    """
    if language == "en":
        return ""
    return (
        f"\nThe PROSE is written in the language with code '{language}'. Translate its MEANING "
        "into the controlled DSL, not its words. Keep merchant names, identifiers, and quoted "
        "string literals VERBATIM in their original language — do not translate or transliterate "
        "them. If you cannot confidently map a fragment to the controlled grammar, reply with "
        f"'{CROSS_LANGUAGE_CLARIFY_SENTINEL} <the untranslatable fragment>' and nothing else.\n"
    )


def _find_dot_claude_env(start_dir: Path | None = None) -> Path | None:
    """Walk up from start_dir (default: cwd) looking for a .claude/.env file.

    This is a module-level function so tests can monkeypatch it to prevent
    coupling to the ambient .claude/.env file on the developer's machine.
    """
    base = start_dir if start_dir is not None else Path.cwd()
    for parent in [base, *base.parents]:
        candidate = parent / ".claude" / ".env"
        if candidate.is_file():
            return candidate
    return None


def _parse_env_file(path: Path) -> dict[str, str]:
    """Parse KEY=VALUE lines from a .env file; skip blank lines and # comments."""
    result: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if "=" in stripped:
            key, _, rest = stripped.partition("=")
            # Trim inline comment (e.g., "KEY=val #alias: ...")
            value = rest.split(" #")[0].strip()
            result[key.strip()] = value
    return result


def load_api_key() -> str:
    """Load the Anthropic API key.

    Lookup order:
    1. NLREQ_ANTHROPIC_API_KEY environment variable.
    2. .claude/.env file (walked up from cwd), key NLREQ_ANTHROPIC_API_KEY.

    Raises EnvironmentError with a clear message if neither source yields a
    key, so callers get actionable guidance rather than an opaque SDK failure.
    Patch _find_dot_claude_env to return None in tests that must not read the
    ambient .claude/.env file.
    """
    key = os.environ.get(NLREQ_API_KEY_ENV, "").strip()
    if key:
        return key
    dot_claude = _find_dot_claude_env()
    if dot_claude is not None:
        env_vars = _parse_env_file(dot_claude)
        key = env_vars.get(NLREQ_API_KEY_ENV, "").strip()
        if key:
            return key
    raise EnvironmentError(
        f"Real LLM drafting requires {NLREQ_API_KEY_ENV} to be set. "
        "Lookup order: (1) environment variable, "
        "(2) .claude/.env file (walked up from cwd). "
        "Set it to an Anthropic API key or pass --fixture for offline use."
    )


@runtime_checkable
class LlmClient(Protocol):
    """Synchronous interface for proposing controlled rewrites from prose.

    The returned text is UNTRUSTED — callers must route it through the
    human approval and hash-binding gate before the parser sees it.
    RecordedLlmClient is deterministic; real clients set temperature=0 for
    best-effort reproducibility but are not guaranteed to be deterministic.
    """

    def propose_controlled_rewrite(
        self, prose: str, grammar_summary: str, *, language: str = "en"
    ) -> str:
        """Return proposed DSL v3 controlled text for the given prose.

        Args:
            prose: The free-form natural-language requirement text.
            grammar_summary: A compact description of the target DSL grammar.
            language: BCP-47-ish source-language code of ``prose`` (e.g. "en", "pt").
                The IR is language-neutral; this only steers the drafting prompt and is
                recorded in provenance. Keyword-only with an "en" default so existing
                English call sites and their pinned prompt hashes are unchanged.

        Returns:
            The proposed controlled text.  Not yet verified or approved.
        """
        ...


class RecordedLlmClient:
    """Replays a pre-recorded fixture; never contacts a real model.

    Use for offline/golden tests and CI.  The fixture is returned verbatim
    regardless of the prose or grammar_summary inputs — this is intentional:
    golden tests pin the rewrite, not the translation path.
    """

    def __init__(self, fixture: str) -> None:
        self._fixture = fixture

    def propose_controlled_rewrite(
        self, prose: str, grammar_summary: str, *, language: str = "en"
    ) -> str:
        # Deterministic replay: the recorded fixture already encodes the model's output for
        # this prose in this language (including any cross-language clarify sentinel), so
        # language only steers a live model — here it is accepted and ignored.
        return self._fixture


def _extract_text(message: object) -> str:
    """Return the first text block's text from a Messages API response.

    The Anthropic Messages API returns ``message.content`` as a LIST of content
    blocks (``text``, ``thinking``, ``tool_use``, ...) — not a guaranteed
    text-first array. ``message.content[0].text`` assumes the first block is a
    text block and fails opaquely otherwise: an ``IndexError`` on empty content,
    or an ``AttributeError`` when the leading block is a non-text block (e.g. a
    thinking block). Walk the blocks, return the first ``type == "text"`` block's
    ``.text``, and raise a clear ``ValueError`` naming the observed block types
    when none is present, so the caller gets an actionable message rather than a
    structural crash.

    Duck-typed over the block objects (``.type`` / ``.text``) so it needs no
    import of the ``anthropic`` package and is unit-testable offline.
    """
    content = getattr(message, "content", None)
    if not content:
        raise ValueError(
            "Anthropic response carried no content blocks; expected a text block "
            "with the proposed controlled rewrite."
        )
    for block in content:
        if getattr(block, "type", None) == "text":
            return block.text
    observed = ", ".join(sorted({str(getattr(b, "type", "<unknown>")) for b in content}))
    raise ValueError(
        "Anthropic response contained no text block; got block types: "
        f"{observed}. Expected a text block with the proposed controlled rewrite."
    )


class AnthropicLlmClient:
    """Real Anthropic SDK client for controlled-rewrite drafting.

    Constructs lazily — the 'anthropic' package is imported inside
    propose_controlled_rewrite, not at module load time, so the absence of the
    package raises a clear error only when a live call is attempted.

    Credentials are loaded from NLREQ_ANTHROPIC_API_KEY via load_api_key().
    Never hardcode keys; the key is read fresh on each call so rotating the
    environment variable takes effect without a process restart.
    """

    def __init__(self, model: str = _DEFAULT_MODEL) -> None:
        self._model = model

    def propose_controlled_rewrite(
        self, prose: str, grammar_summary: str, *, language: str = "en"
    ) -> str:
        # Credential check first so a missing key surfaces as EnvironmentError
        # even when the 'anthropic' package is not installed.
        api_key = load_api_key()

        try:
            import anthropic
        except ImportError as exc:
            raise ImportError(
                "Real LLM drafting requires the 'anthropic' package. "
                "Install it via: pip install anthropic  (or uv add anthropic)"
            ) from exc
        client = anthropic.Anthropic(api_key=api_key)
        message = client.messages.create(
            model=self._model,
            max_tokens=1024,
            temperature=0,
            messages=[
                {
                    "role": "user",
                    "content": (
                        "You are a precise technical writer converting free-form requirement prose "
                        "into a controlled DSL v3 requirement.\n\n"
                        "GRAMMAR:\n"
                        + grammar_summary
                        + language_prompt_addendum(language)
                        + "\nPROSE:\n"
                        + prose.strip()
                        + "\n\nProduce ONLY the controlled DSL v3 text, no explanation or commentary."
                    ),
                }
            ],
        )
        # Extract the proposed text defensively: the response content is a list of
        # content blocks and the first one is not guaranteed to be a text block.
        return _extract_text(message)


class UnavailableLlmClient:
    """Raises a clear error when the real SDK is not installed.

    Installed in place of the real SDK client when the 'anthropic' package is
    absent.  Surfaces a helpful error rather than an import-time failure.
    """

    def propose_controlled_rewrite(
        self, prose: str, grammar_summary: str, *, language: str = "en"
    ) -> str:
        raise NotImplementedError(
            "Real LLM drafting requires the 'anthropic' package. "
            "Install it or supply --fixture for offline use."
        )
