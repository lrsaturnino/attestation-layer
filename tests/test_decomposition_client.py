"""Tests for PA-5: DecompositionClient interface and ensemble check wired into
translate_controlled_requirement_to_formal_claim.
"""
from __future__ import annotations

from pathlib import Path

from nlreq.decomposition_client import (
    DecompositionClient,
    RecordedDecompositionClient,
    UnavailableDecompositionClient,
)
from nlreq.dsl_v3 import DslV3Parser
from nlreq.models import RequirementIRV2
from nlreq.semantic_translation import translate_controlled_requirement_to_formal_claim


FIXTURES = Path(__file__).parent / "fixtures" / "requirements"

_CONTROLLED_TEXT = (FIXTURES / "authorization_precondition_v3.nlreq").read_text()
_REQUIREMENT_ID = "REQ-DECOMP-001"
_TITLE = "PA-5 decomposition ensemble test"


def _parse_ir(requirement_id: str = _REQUIREMENT_ID) -> RequirementIRV2:
    return DslV3Parser().parse_ir(
        _CONTROLLED_TEXT, requirement_id=requirement_id, title=_TITLE
    )


def _parse_ir_variant() -> RequirementIRV2:
    """Return an IR that differs in its FormalClaim signature from the base IR.

    Mutates the predicate name in the premise so the formal-claim signature
    (alpha-renamed, commutative) differs from the unmodified base IR.
    """
    data = _parse_ir().model_dump(mode="json")
    # Change the predicate name in the premise children to produce a different
    # formal-claim signature (verified empirically — the base predicate is
    # 'not_authorized'; changing it produces a distinct FormalClaim signature).
    data["semantic_ir"]["premise"]["children"][0]["name"] = "alternative_predicate"
    return RequirementIRV2.model_validate(data)


# ---------------------------------------------------------------------------
# RecordedDecompositionClient
# ---------------------------------------------------------------------------


def test_recorded_decomposition_client_returns_fixture() -> None:
    """RecordedDecompositionClient returns the fixture IR regardless of inputs."""
    ir = _parse_ir()
    client = RecordedDecompositionClient(fixture=ir)

    result = client.decompose_controlled_to_ir(
        "any text", "any-id", "any title"
    )

    assert result == ir


def test_recorded_decomposition_client_satisfies_protocol() -> None:
    """RecordedDecompositionClient satisfies the DecompositionClient Protocol."""
    client = RecordedDecompositionClient(fixture=_parse_ir())
    assert isinstance(client, DecompositionClient)


# ---------------------------------------------------------------------------
# UnavailableDecompositionClient
# ---------------------------------------------------------------------------


def test_unavailable_decomposition_client_raises() -> None:
    """UnavailableDecompositionClient raises NotImplementedError with a useful message."""
    import pytest

    client = UnavailableDecompositionClient()
    with pytest.raises(NotImplementedError, match="PA-5"):
        client.decompose_controlled_to_ir("text", "id", "title")


# ---------------------------------------------------------------------------
# PA-5 ensemble check: agreed → accepted, disagreed → REFUSED_AMBIGUOUS
# ---------------------------------------------------------------------------


def test_ensemble_agreed_clients_produce_accepted() -> None:
    """Two RecordedDecompositionClients returning the same IR yield an accepted translation."""
    ir = _parse_ir()
    clients = [
        RecordedDecompositionClient(fixture=ir),
        RecordedDecompositionClient(fixture=ir),
    ]

    report = translate_controlled_requirement_to_formal_claim(
        controlled_text=_CONTROLLED_TEXT,
        requirement_id=_REQUIREMENT_ID,
        title=_TITLE,
        decomposition_clients=clients,
    )

    assert report.result in {"accepted", "needs_review"}, (
        f"Agreeing ensemble must not be refused, got {report.result!r}: "
        f"refusal_code={report.refusal_code}"
    )
    assert report.refusal_code != "NLR-REFUSED-AMBIGUOUS", (
        "Agreeing ensemble must not produce NLR-REFUSED-AMBIGUOUS"
    )


def test_ensemble_disagreed_clients_produce_refused_ambiguous() -> None:
    """Two RecordedDecompositionClients with different IRs produce NLR-REFUSED-AMBIGUOUS."""
    ir_a = _parse_ir()
    ir_b = _parse_ir_variant()  # different predicate → different formal-claim signature
    clients = [
        RecordedDecompositionClient(fixture=ir_a),
        RecordedDecompositionClient(fixture=ir_b),
    ]

    report = translate_controlled_requirement_to_formal_claim(
        controlled_text=_CONTROLLED_TEXT,
        requirement_id=_REQUIREMENT_ID,
        title=_TITLE,
        decomposition_clients=clients,
    )

    assert report.result == "refused", (
        f"Disagreeing ensemble must produce refused, got {report.result!r}"
    )
    assert report.refusal_code == "NLR-REFUSED-AMBIGUOUS", (
        f"Expected NLR-REFUSED-AMBIGUOUS, got {report.refusal_code!r}"
    )
    assert len(report.ambiguity_findings) >= 1, (
        "Must carry at least one ambiguity finding with the disagreement"
    )
    assert any(
        "ensemble-decomposition-0" in f.clarification_question
        or "ensemble-decomposition-1" in f.clarification_question
        for f in report.ambiguity_findings
    ), "Ambiguity findings must reference the ensemble candidate IDs"


def test_no_ensemble_clients_skips_check() -> None:
    """Omitting decomposition_clients does not trigger the ensemble check."""
    report = translate_controlled_requirement_to_formal_claim(
        controlled_text=_CONTROLLED_TEXT,
        requirement_id=_REQUIREMENT_ID,
        title=_TITLE,
        decomposition_clients=None,
    )

    assert report.result != "refused" or report.refusal_code != "NLR-REFUSED-AMBIGUOUS", (
        "No ensemble clients must not produce NLR-REFUSED-AMBIGUOUS"
    )


def test_single_ensemble_client_skips_check() -> None:
    """A list with only one client does not trigger the ensemble check (need ≥2)."""
    ir = _parse_ir()
    clients = [RecordedDecompositionClient(fixture=ir)]

    report = translate_controlled_requirement_to_formal_claim(
        controlled_text=_CONTROLLED_TEXT,
        requirement_id=_REQUIREMENT_ID,
        title=_TITLE,
        decomposition_clients=clients,
    )

    assert report.refusal_code != "NLR-REFUSED-AMBIGUOUS", (
        "Single-client list must not produce NLR-REFUSED-AMBIGUOUS"
    )
