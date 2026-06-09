from __future__ import annotations

import json
import os
import re
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

    def estimate_impacted_modules(
        self, *, prose: str, symbols: list[str], candidate_modules: list[str]
    ) -> str:
        """Return a JSON array of module ids the model estimates the requirement impacts.

        This is the SEMANTIC impact estimate cross-validated against the deterministic
        call-graph-reachable set (PC-9). The model reads the requirement prose, its bound symbols,
        and the universe of candidate modules, and returns the modules it believes are impacted.

        The returned text is UNTRUSTED — like ``propose_controlled_rewrite`` it is never gateable
        on its own. The cross-validation derives the AUTHORITATIVE affected set from the call graph
        and uses this estimate only to surface agreement/disagreement as review flags; a module the
        model names but the call graph never reaches does not enter the gateable impact set. Parse
        the returned text with :func:`parse_impact_estimate`, which tolerates malformed output.

        Args:
            prose: The free-form requirement text (or controlled text) the estimate is over.
            symbols: The requirement's bound symbols (the call-graph roots).
            candidate_modules: The universe of module ids the model may choose from.

        Returns:
            A JSON array of module-id strings. Not yet verified.
        """
        ...

    def extract_spec_invariants(
        self, *, module_id: str, code_presentation: str, language: str = "en"
    ) -> str:
        """Return a JSON Specula-style spec-extraction proposal read from a module's SOURCE (PC-8).

        The model reads the module's presented source and proposes candidate ``S`` invariants
        (formal safety properties) plus the trace-observable obligations those invariants imply —
        operations the spec asserts the code performs. The proposal is derived from the CODE, never
        from the trace: the trace is the independent validator.

        The returned text is UNTRUSTED and never promotable on its own. A candidate ``S`` is
        promotable to ``reviewed`` only if its trace-observable obligations are REPRODUCED by the
        module's real traces (PC-7) — a paper-only candidate, asserting an operation the code never
        runs, is rejected by that guard. Parse the returned text with
        :func:`nlreq.spec_extraction.parse_spec_extraction`, which tolerates malformed output.

        Args:
            module_id: The source module the spec is extracted for.
            code_presentation: The presented source the model reads (the adapter's code presentation).
            language: The source language (e.g. "go"); steers a live model and is recorded.

        Returns:
            A JSON object with ``invariants`` and ``trace_expectations``. Not yet verified.
        """
        ...


def parse_impact_estimate(text: str) -> list[str]:
    """Parse an UNTRUSTED LLM impact estimate into a sorted, de-duplicated list of module ids.

    The model is asked for a JSON array of module-id strings. This parse is defensive because the
    output is untrusted: it accepts a JSON array of strings (optionally wrapped in a ```json code
    fence), ignores non-string entries, and falls back to comma/newline splitting when the text is
    not valid JSON (a model may wrap the array in prose). It NEVER raises on malformed output — an
    unparseable estimate yields an empty list, which the cross-validation reads as "the semantic
    estimate named no modules" (surfaced as a disagreement against every call-graph module), not a
    crash. The result is sorted + de-duplicated so cross-validation is order-insensitive.
    """
    stripped = text.strip()
    # Strip a surrounding markdown code fence (```json ... ``` or ``` ... ```) if present.
    fence = re.match(r"^```(?:json)?\s*(.*?)\s*```$", stripped, re.DOTALL)
    if fence:
        stripped = fence.group(1).strip()
    try:
        parsed = json.loads(stripped)
    except (ValueError, TypeError):
        parsed = None
    else:
        # Valid JSON: a list of strings is the estimate; any other JSON value (object, number,
        # bare string) is treated as "named no modules" rather than re-split as loose text.
        if isinstance(parsed, list):
            return sorted({item.strip() for item in parsed if isinstance(item, str) and item.strip()})
        return []
    # Not JSON at all: a bare or prose-wrapped list — split on commas/newlines, strip brackets/quotes.
    tokens = re.split(r"[,\n]", stripped.strip("[]"))
    return sorted({token.strip().strip("\"'") for token in tokens if token.strip().strip("\"'")})


class RecordedLlmClient:
    """Replays a pre-recorded fixture; never contacts a real model.

    Use for offline/golden tests and CI.  The fixture is returned verbatim
    regardless of the prose or grammar_summary inputs — this is intentional:
    golden tests pin the rewrite, not the translation path.
    """

    def __init__(
        self,
        fixture: str,
        *,
        impact_fixture: str | None = None,
        spec_fixture: str | None = None,
    ) -> None:
        self._fixture = fixture
        # The recorded semantic-impact estimate (a JSON array of module ids). Optional and separate
        # from the controlled-rewrite fixture so one client can replay BOTH the rewrite and the
        # PC-9 impact estimate; when omitted, estimate_impacted_modules replays the main fixture
        # (so a client constructed solely with the JSON list still serves an impact estimate).
        self._impact_fixture = impact_fixture
        # The recorded Specula spec-extraction proposal (a JSON object of invariants +
        # trace_expectations). Optional and separate so one client can replay the rewrite, the impact
        # estimate, AND the PC-8 spec extraction; when omitted, extract_spec_invariants replays the
        # main fixture.
        self._spec_fixture = spec_fixture

    def propose_controlled_rewrite(
        self, prose: str, grammar_summary: str, *, language: str = "en"
    ) -> str:
        # Deterministic replay: the recorded fixture already encodes the model's output for
        # this prose in this language (including any cross-language clarify sentinel), so
        # language only steers a live model — here it is accepted and ignored.
        return self._fixture

    def estimate_impacted_modules(
        self, *, prose: str, symbols: list[str], candidate_modules: list[str]
    ) -> str:
        # Deterministic replay: the recorded estimate already encodes the model's chosen modules,
        # so prose/symbols/candidate_modules only steer a live model — here they are accepted and
        # ignored. Falls back to the rewrite fixture when no dedicated impact fixture was recorded.
        return self._impact_fixture if self._impact_fixture is not None else self._fixture

    def extract_spec_invariants(
        self, *, module_id: str, code_presentation: str, language: str = "en"
    ) -> str:
        # Deterministic replay: the recorded proposal already encodes the model's extracted
        # invariants + trace expectations, so module_id/code_presentation/language only steer a live
        # model — here they are accepted and ignored. Falls back to the rewrite fixture when no
        # dedicated spec fixture was recorded.
        return self._spec_fixture if self._spec_fixture is not None else self._fixture


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

    def estimate_impacted_modules(
        self, *, prose: str, symbols: list[str], candidate_modules: list[str]
    ) -> str:
        # Credential check first so a missing key surfaces as EnvironmentError even when the
        # 'anthropic' package is not installed (mirrors propose_controlled_rewrite).
        api_key = load_api_key()

        try:
            import anthropic
        except ImportError as exc:
            raise ImportError(
                "Real LLM impact estimation requires the 'anthropic' package. "
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
                        "You estimate which source modules a software requirement impacts. You are "
                        "given the requirement prose, its bound symbols, and the universe of "
                        "candidate module ids. Reply with ONLY a JSON array of the module ids you "
                        "believe are impacted (a subset of the candidates), no prose.\n\n"
                        "BOUND SYMBOLS: " + ", ".join(symbols) + "\n"
                        "CANDIDATE MODULES: " + ", ".join(candidate_modules) + "\n\n"
                        "REQUIREMENT:\n" + prose.strip()
                    ),
                }
            ],
        )
        return _extract_text(message)

    def extract_spec_invariants(
        self, *, module_id: str, code_presentation: str, language: str = "en"
    ) -> str:
        # Credential check first so a missing key surfaces as EnvironmentError even when the
        # 'anthropic' package is not installed (mirrors propose_controlled_rewrite).
        api_key = load_api_key()

        try:
            import anthropic
        except ImportError as exc:
            raise ImportError(
                "Real LLM spec extraction requires the 'anthropic' package. "
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
                        "You extract candidate formal invariants from source code. Read the "
                        f"presented {language} source of module '{module_id}' and propose candidate "
                        "safety invariants AND the trace-observable operations those invariants imply "
                        "(operations the code performs at runtime). Derive everything from the CODE, "
                        "not from any external description. Reply with ONLY a JSON object of the form "
                        '{"invariants": [{"name": "...", "tla": "..."}], "trace_expectations": '
                        '[{"expectation_id": "...", "kind": "event_emitted", "target": "...", '
                        '"description": "..."}]} where kind is "event_emitted" (the operation runs) '
                        'or "action_never" (the operation must never run). No prose.\n\n'
                        "SOURCE:\n" + code_presentation.strip()
                    ),
                }
            ],
        )
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

    def estimate_impacted_modules(
        self, *, prose: str, symbols: list[str], candidate_modules: list[str]
    ) -> str:
        raise NotImplementedError(
            "Real LLM impact estimation requires the 'anthropic' package. "
            "Install it or supply a RecordedLlmClient for offline use."
        )

    def extract_spec_invariants(
        self, *, module_id: str, code_presentation: str, language: str = "en"
    ) -> str:
        raise NotImplementedError(
            "Real LLM spec extraction requires the 'anthropic' package. "
            "Install it or supply a RecordedLlmClient for offline use."
        )
