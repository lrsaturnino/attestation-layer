from __future__ import annotations

from typing import Protocol, runtime_checkable

from .models import RequirementIRV2


@runtime_checkable
class DecompositionClient(Protocol):
    """Synchronous interface for decomposing controlled DSL v3 text into a RequirementIRV2.

    Used by the PA-5 ensemble: two independent clients receive the same approved
    controlled text and each returns its interpretation as an IR.  The caller
    compares FormalClaim signatures; divergence triggers REFUSED_AMBIGUOUS.

    Implementations:
    - RecordedDecompositionClient — replays a fixture IR (offline/golden tests).
    - UnavailableDecompositionClient — raises NotImplementedError (placeholder until
      the live LLM decomposition path is fully implemented).

    The returned IR is UNTRUSTED from a semantic standpoint: the ensemble check
    determines whether it agrees with other independent decompositions.
    """

    def decompose_controlled_to_ir(
        self,
        controlled_text: str,
        requirement_id: str,
        title: str,
    ) -> RequirementIRV2:
        """Return a RequirementIRV2 for the given controlled DSL v3 text.

        Args:
            controlled_text: Approved DSL v3 controlled text.
            requirement_id: Requirement identifier to embed in the returned IR.
            title: Human-readable title to embed in the returned IR.

        Returns:
            A RequirementIRV2 representing this client's interpretation.
        """
        ...


class RecordedDecompositionClient:
    """Replays a pre-recorded fixture IR; never contacts a real model.

    Use for offline/golden tests and CI.  The fixture is returned verbatim
    regardless of the controlled_text, requirement_id, or title — golden tests
    pin the decomposition result, not the input routing.
    """

    def __init__(self, fixture: RequirementIRV2) -> None:
        self._fixture = fixture

    def decompose_controlled_to_ir(
        self,
        controlled_text: str,
        requirement_id: str,
        title: str,
    ) -> RequirementIRV2:
        return self._fixture


class UnavailableDecompositionClient:
    """Raises NotImplementedError; installed until the live LLM path is complete.

    The live Anthropic-backed decomposition client (PA-5 full impl) is not yet
    available.  This placeholder surfaces a clear error rather than silently
    skipping the ensemble check.  Replace with the real implementation once the
    LLM prompt + IR-extraction path is validated on the spike corpus (PA-9).
    """

    def decompose_controlled_to_ir(
        self,
        controlled_text: str,
        requirement_id: str,
        title: str,
    ) -> RequirementIRV2:
        raise NotImplementedError(
            "Live LLM decomposition is not yet implemented (PA-5 full impl pending). "
            "Supply RecordedDecompositionClient instances for offline testing, "
            "or omit decomposition_clients to skip the ensemble check."
        )
