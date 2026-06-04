"""Tests for PA-5: DecompositionClient interface and ensemble check wired into
translate_controlled_requirement_to_formal_claim.
"""
from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from nlreq.decomposition_client import (
    AnthropicDecompositionClient,
    DecompositionClient,
    DecompositionResult,
    RecordedDecompositionClient,
)
from nlreq.dsl_v3 import DslV3Parser
from nlreq.models import Approval, RequirementIRV2
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


def _approved_approval() -> Approval:
    return Approval(status="approved", approved_by="test-suite", approved_at="test")


# ---------------------------------------------------------------------------
# RecordedDecompositionClient
# ---------------------------------------------------------------------------


def test_recorded_decomposition_client_returns_fixture() -> None:
    """RecordedDecompositionClient returns a DecompositionResult whose .requirement is the fixture."""
    ir = _parse_ir()
    client = RecordedDecompositionClient(fixture=ir)

    result = client.decompose_controlled_to_ir("any text", "any-id", "any title")

    assert isinstance(result, DecompositionResult)
    assert result.requirement == ir


def test_recorded_decomposition_client_carries_trust_metadata() -> None:
    """RecordedDecompositionClient propagates approval, is_audited, model_id, and prompt_hash."""
    ir = _parse_ir()
    approval = _approved_approval()
    client = RecordedDecompositionClient(
        fixture=ir,
        candidate_id="my-candidate",
        approval=approval,
        is_audited=True,
        model_id="test-model",
        prompt_hash="abc123",
    )

    result = client.decompose_controlled_to_ir(_CONTROLLED_TEXT, _REQUIREMENT_ID, _TITLE)

    assert result.candidate_id == "my-candidate"
    assert result.approval == approval
    assert result.is_audited is True
    assert result.model_id == "test-model"
    assert result.prompt_hash == "abc123"
    assert result.source_text_hash  # non-empty hash of the controlled text


def test_recorded_decomposition_client_defaults_to_unapproved_unaudited() -> None:
    """RecordedDecompositionClient without explicit trust metadata is unapproved and unaudited."""
    client = RecordedDecompositionClient(fixture=_parse_ir())
    result = client.decompose_controlled_to_ir(_CONTROLLED_TEXT, _REQUIREMENT_ID, _TITLE)

    assert result.approval is None
    assert result.is_audited is False


def test_recorded_decomposition_client_satisfies_protocol() -> None:
    """RecordedDecompositionClient satisfies the DecompositionClient Protocol."""
    client = RecordedDecompositionClient(fixture=_parse_ir())
    assert isinstance(client, DecompositionClient)


# ---------------------------------------------------------------------------
# AnthropicDecompositionClient
# ---------------------------------------------------------------------------


def test_anthropic_decomposition_client_raises_on_missing_key() -> None:
    """AnthropicDecompositionClient raises EnvironmentError when no API key is configured."""
    client = AnthropicDecompositionClient()
    # Patch both the env variable and the .claude/.env file lookup so neither
    # source yields a key, ensuring the test is hermetic.
    with patch("nlreq.llm_client._find_dot_claude_env", return_value=None):
        with patch.dict("os.environ", {"NLREQ_ANTHROPIC_API_KEY": ""}, clear=False):
            with pytest.raises(EnvironmentError, match="NLREQ_ANTHROPIC_API_KEY"):
                client.decompose_controlled_to_ir(_CONTROLLED_TEXT, _REQUIREMENT_ID, _TITLE)


def test_anthropic_decomposition_client_satisfies_protocol() -> None:
    """AnthropicDecompositionClient satisfies the DecompositionClient Protocol."""
    client = AnthropicDecompositionClient()
    assert isinstance(client, DecompositionClient)


def test_anthropic_decomposition_client_defaults_unaudited() -> None:
    """AnthropicDecompositionClient never produces an audited result (PA-6 not yet implemented)."""
    # Verifying the class-level invariant without making a live call.
    # The is_audited=False / approval=None defaults are asserted on a RecordedDecompositionClient
    # acting as a proxy; the live-call path is integration-tested separately.
    client = RecordedDecompositionClient(fixture=_parse_ir())  # stand-in for the live client
    result = client.decompose_controlled_to_ir(_CONTROLLED_TEXT, _REQUIREMENT_ID, _TITLE)
    assert result.is_audited is False
    assert result.approval is None


# ---------------------------------------------------------------------------
# PA-5 ensemble check: agreed + audited → accepted; disagreed + audited → REFUSED_AMBIGUOUS
# ---------------------------------------------------------------------------


def test_ensemble_agreed_audited_clients_produce_accepted() -> None:
    """Two approved+audited clients with the same IR yield an accepted translation."""
    approval = _approved_approval()
    ir = _parse_ir()
    clients = [
        RecordedDecompositionClient(fixture=ir, approval=approval, is_audited=True),
        RecordedDecompositionClient(fixture=ir, approval=approval, is_audited=True),
    ]

    report = translate_controlled_requirement_to_formal_claim(
        controlled_text=_CONTROLLED_TEXT,
        requirement_id=_REQUIREMENT_ID,
        title=_TITLE,
        decomposition_clients=clients,
    )

    assert report.result in {"accepted", "needs_review"}, (
        f"Agreeing audited ensemble must not be refused, got {report.result!r}: "
        f"refusal_code={report.refusal_code}"
    )
    assert report.refusal_code != "NLR-REFUSED-AMBIGUOUS", (
        "Agreeing ensemble must not produce NLR-REFUSED-AMBIGUOUS"
    )


def test_ensemble_agreed_clients_produce_accepted() -> None:
    """Two RecordedDecompositionClients with default (unapproved) trust produce needs_review."""
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


def test_ensemble_disagreed_audited_clients_produce_refused_ambiguous() -> None:
    """Two approved+audited clients with different IRs produce NLR-REFUSED-AMBIGUOUS.

    Approval must be supplied explicitly — the ensemble never synthesises it.
    """
    approval = _approved_approval()
    ir_a = _parse_ir()
    ir_b = _parse_ir_variant()  # different predicate → different formal-claim signature
    clients = [
        RecordedDecompositionClient(fixture=ir_a, approval=approval, is_audited=True),
        RecordedDecompositionClient(fixture=ir_b, approval=approval, is_audited=True),
    ]

    report = translate_controlled_requirement_to_formal_claim(
        controlled_text=_CONTROLLED_TEXT,
        requirement_id=_REQUIREMENT_ID,
        title=_TITLE,
        decomposition_clients=clients,
    )

    assert report.result == "refused", (
        f"Disagreeing audited ensemble must produce refused, got {report.result!r}"
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


# Backward-compat alias so existing callers of the old test name still pass.
test_ensemble_disagreed_clients_produce_refused_ambiguous = (
    test_ensemble_disagreed_audited_clients_produce_refused_ambiguous
)


# ---------------------------------------------------------------------------
# PA-5 trust boundary: unaudited candidates → needs_review, not refused-ambiguous
# ---------------------------------------------------------------------------


def test_ensemble_unaudited_clients_produce_needs_review() -> None:
    """Unaudited clients (no approval, is_audited=False) produce needs_review, not refused-ambiguous.

    Even when the two candidates disagree, the trust boundary must win: the
    correct output is needs_review with NLR-UNAUDITED-DECOMPOSITION, not
    NLR-REFUSED-AMBIGUOUS.  An ambiguity refusal requires both candidates to be
    explicitly approved and audited — reflecting that PA-6 audit is a prerequisite.
    """
    ir_a = _parse_ir()
    ir_b = _parse_ir_variant()
    clients = [
        RecordedDecompositionClient(fixture=ir_a),  # unapproved, unaudited
        RecordedDecompositionClient(fixture=ir_b),  # unapproved, unaudited
    ]

    report = translate_controlled_requirement_to_formal_claim(
        controlled_text=_CONTROLLED_TEXT,
        requirement_id=_REQUIREMENT_ID,
        title=_TITLE,
        decomposition_clients=clients,
    )

    assert report.result == "needs_review", (
        f"Unaudited ensemble must yield needs_review, got {report.result!r}"
    )
    assert report.refusal_code == "NLR-UNAUDITED-DECOMPOSITION", (
        f"Expected NLR-UNAUDITED-DECOMPOSITION, got {report.refusal_code!r}"
    )
    assert report.refusal_code != "NLR-REFUSED-AMBIGUOUS", (
        "Unaudited candidates must not produce NLR-REFUSED-AMBIGUOUS"
    )


def test_ensemble_unaudited_carries_prior_provenance() -> None:
    """needs_review from unaudited ensemble carries controlled-text hash and prior stages."""
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

    assert "controlled_text" in report.input_hashes, (
        "input_hashes must include controlled_text hash"
    )
    stage_names = [s.stage for s in report.stages]
    assert "canonicalize" in stage_names, "canonicalize stage must be preserved in refusal"
    assert "parse_semantic_tree" in stage_names, "parse_semantic_tree stage must be preserved"


def test_ensemble_refused_ambiguous_carries_prior_provenance() -> None:
    """NLR-REFUSED-AMBIGUOUS carries controlled-text hash, prior stages, and tree hashes."""
    approval = _approved_approval()
    ir_a = _parse_ir()
    ir_b = _parse_ir_variant()
    clients = [
        RecordedDecompositionClient(fixture=ir_a, approval=approval, is_audited=True),
        RecordedDecompositionClient(fixture=ir_b, approval=approval, is_audited=True),
    ]

    report = translate_controlled_requirement_to_formal_claim(
        controlled_text=_CONTROLLED_TEXT,
        requirement_id=_REQUIREMENT_ID,
        title=_TITLE,
        decomposition_clients=clients,
    )

    assert report.refusal_code == "NLR-REFUSED-AMBIGUOUS"
    assert "controlled_text" in report.input_hashes, "input_hashes must include controlled_text"
    assert report.semantic_tree_hash is not None, "semantic_tree_hash must be set"
    assert report.semantic_decomposition_hash is not None, "semantic_decomposition_hash must be set"
    assert report.requirement_ir is not None, "requirement_ir must be present in refusal"
    stage_names = [s.stage for s in report.stages]
    assert "canonicalize" in stage_names, "canonicalize stage must be preserved"
    assert "parse_semantic_tree" in stage_names, "parse_semantic_tree stage must be preserved"
    assert "lower_formal_claim" in stage_names, "lower_formal_claim failure stage must be present"


# ---------------------------------------------------------------------------
# Ensemble skip conditions
# ---------------------------------------------------------------------------


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
