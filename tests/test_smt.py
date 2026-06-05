from __future__ import annotations

from nlreq.models import (
    Claim,
    EvidenceLevel,
    ExpectedResult,
    Predicate,
    RequirementIR,
    RequirementSource,
    SourceSpan,
    ValueRef,
)
from nlreq.smt import smt2_for_ir, smt_check_requirement


def _span(text: str) -> SourceSpan:
    return SourceSpan(document="controlled_requirement", start_char=0, end_char=len(text), text=text)


def _ident(name: str) -> ValueRef:
    return ValueRef(kind="identifier", value=name)


def _ir(condition: list[Predicate], *, kind: str = "numeric_invariant") -> RequirementIR:
    return RequirementIR(
        requirement_id="REQ-SMT-T",
        title="SMT honesty regression",
        source=RequirementSource(controlled_text="controlled requirement"),
        claim=Claim(
            kind=kind,
            action="finalize",
            forall=[],
            condition=condition,
            expected=ExpectedResult(kind="succeed", source_span=_span("succeeds")),
        ),
    )


def test_eq_neq_contradiction_does_not_emit_smt_checked() -> None:
    # `counter is limit` plus `counter is not limit` is a syntactic eq/neq contradiction that
    # _direct_contradictions catches — but smt2_for_ir never encodes eq/neq, so the .smt2 query
    # discloses them as UNENCODED. The result must not upgrade that verdict to SMT_CHECKED: it
    # would label a check the query did not run.
    ir = _ir(
        [
            Predicate(op="eq", args=[_ident("counter"), _ident("limit")], source_span=_span("counter is limit")),
            Predicate(op="neq", args=[_ident("counter"), _ident("limit")], source_span=_span("counter is not limit")),
        ]
    )
    result = smt_check_requirement(ir)
    assert "UNENCODED" in smt2_for_ir(ir)
    assert result.evidence_level is None
    assert result.status == "unsupported"
    assert result.details["unencoded_predicate_ops"] == ["eq", "neq"]


def test_lte_comparison_does_not_emit_smt_checked() -> None:
    ir = _ir(
        [Predicate(op="lte", args=[_ident("counter"), _ident("limit")], source_span=_span("counter is at most limit"))]
    )
    result = smt_check_requirement(ir)
    assert "UNENCODED" in smt2_for_ir(ir)
    assert result.evidence_level is None
    assert result.status == "unsupported"
    assert result.details["unencoded_predicate_ops"] == ["lte"]


def test_membership_in_does_not_emit_smt_checked() -> None:
    ir = _ir(
        [Predicate(op="in", args=[_ident("operation_status"), _ident("allowed")], source_span=_span("status is in allowed"))]
    )
    result = smt_check_requirement(ir)
    assert "UNENCODED" in smt2_for_ir(ir)
    assert result.evidence_level is None
    assert result.status == "unsupported"
    assert result.details["unencoded_predicate_ops"] == ["in"]


def test_authorization_contradiction_still_emits_smt_checked() -> None:
    # An authorization/approval contradiction IS propositionally encoded by smt2_for_ir, so the
    # invalid verdict is a genuine SMT result: SMT_CHECKED stays honest. Only the unencodable
    # comparison/membership ops are refused — encodable contradictions are not.
    ir = _ir(
        [
            Predicate(op="authorized", args=[_ident("wallet")], source_span=_span("wallet is authorized")),
            Predicate(op="not_authorized", args=[_ident("wallet")], source_span=_span("wallet is not authorized")),
        ],
        kind="authorization_precondition",
    )
    result = smt_check_requirement(ir)
    assert "UNENCODED" not in smt2_for_ir(ir)
    assert result.status == "invalid"
    assert result.evidence_level == EvidenceLevel.SMT_CHECKED


def test_supported_authorization_claim_emits_smt_checked_valid() -> None:
    ir = _ir(
        [Predicate(op="authorized", args=[_ident("wallet")], source_span=_span("wallet is authorized"))],
        kind="authorization_precondition",
    )
    result = smt_check_requirement(ir)
    assert "UNENCODED" not in smt2_for_ir(ir)
    assert result.status == "valid"
    assert result.evidence_level == EvidenceLevel.SMT_CHECKED
