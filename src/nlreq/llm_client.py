from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class LlmClient(Protocol):
    """Synchronous interface for proposing controlled rewrites from prose.

    The returned text is UNTRUSTED — callers must route it through the
    human approval and hash-binding gate before the parser sees it.
    Implementations must be pure and deterministic for a fixed input (i.e.
    not call time(), random(), or maintain mutable state across calls) so
    that offline golden tests are reproducible.
    """

    def propose_controlled_rewrite(self, prose: str, grammar_summary: str) -> str:
        """Return proposed DSL v3 controlled text for the given prose.

        Args:
            prose: The free-form natural-language requirement text.
            grammar_summary: A compact description of the target DSL grammar.

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

    def propose_controlled_rewrite(self, prose: str, grammar_summary: str) -> str:
        return self._fixture


class UnavailableLlmClient:
    """Raises a clear error when the real SDK is not installed.

    Installed in place of the real SDK client when the 'anthropic' package is
    absent.  Surfaces a helpful error rather than an import-time failure.
    """

    def propose_controlled_rewrite(self, prose: str, grammar_summary: str) -> str:
        raise NotImplementedError(
            "Real LLM drafting requires the 'anthropic' package. "
            "Install it or supply --fixture for offline use."
        )
