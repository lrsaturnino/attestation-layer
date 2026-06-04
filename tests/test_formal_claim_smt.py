from __future__ import annotations

from pathlib import Path

from nlreq.dsl_v3 import DslV3Parser
from nlreq.formal_claim import build_formal_claim
from nlreq.formal_claim_smt import (
    FORMAL_CLAIM_SMT_VERSION,
    _check_comparison,
    smt_check_formal_claim_predicate_fragments,
)
from nlreq.formal_claim import FormalClaimFragment, FormalClaimOperand
from nlreq.models import EvidenceLevel


FIXTURES = Path(__file__).parent / "fixtures" / "requirements"


def _auth_ir():
    return DslV3Parser().parse_ir(
        FIXTURES.joinpath("authorization_precondition_v3.nlreq").read_text(),
        requirement_id="SMT-AUTH-001",
        title="Authorization precondition",
    )


def _make_comparison_fragment(lhs_kind: str, lhs_val, rhs_kind: str, rhs_val, operator: str) -> FormalClaimFragment:
    return FormalClaimFragment(
        fragment_id="test.frag.cmp",
        source_node_id="n1",
        role="premise",
        kind="comparison",
        canonical=f"{lhs_val} {operator} {rhs_val}",
        operator=operator,
        operands=[
            FormalClaimOperand(kind=lhs_kind, value=lhs_val),
            FormalClaimOperand(kind=rhs_kind, value=rhs_val),
        ],
    )


def _make_membership_fragment() -> FormalClaimFragment:
    return FormalClaimFragment(
        fragment_id="test.frag.mem",
        source_node_id="n2",
        role="premise",
        kind="membership",
        canonical="role in allowed_roles",
        operator="in",
        operands=[
            FormalClaimOperand(kind="identifier", value="role"),
            FormalClaimOperand(kind="identifier", value="allowed_roles"),
        ],
    )


def test_predicate_fragments_are_excluded_from_smt_results() -> None:
    """Predicate fragments must not produce BackendResults — they require model-level checking."""
    report = build_formal_claim(_auth_ir())
    assert report.formal_claim is not None
    predicate_fragments = [
        f for f in [*report.formal_claim.premises, *report.formal_claim.obligations]
        if f.kind == "predicate"
    ]
    assert predicate_fragments, "auth fixture must have predicate fragments"

    results = smt_check_formal_claim_predicate_fragments(report.formal_claim)

    covered_ids = {fid for r in results for fid in r.details.get("covered_fragment_ids", [])}
    for frag in predicate_fragments:
        assert frag.fragment_id not in covered_ids, (
            f"predicate fragment {frag.fragment_id!r} must not be SMT-checked"
        )


def test_ground_true_comparison_returns_valid_smt_checked() -> None:
    """Concrete-number comparison that is true must emit valid/SMT_CHECKED."""
    frag = _make_comparison_fragment("number", 5, "number", 10, "lt")
    status, evidence = _check_comparison(frag)
    assert status == "valid"
    assert evidence == EvidenceLevel.SMT_CHECKED


def test_ground_false_comparison_returns_invalid_smt_checked() -> None:
    """Concrete-number comparison that is false must emit invalid/SMT_CHECKED."""
    frag = _make_comparison_fragment("number", 10, "number", 5, "lt")
    status, evidence = _check_comparison(frag)
    assert status == "invalid"
    assert evidence == EvidenceLevel.SMT_CHECKED


def test_symbolic_comparison_returns_needs_review_consistency_checked() -> None:
    """Symbolic comparison must emit needs_review/CONSISTENCY_CHECKED — satisfiability proves nothing."""
    frag = _make_comparison_fragment("identifier", "balance", "identifier", "threshold", "lt")
    status, evidence = _check_comparison(frag)
    assert status == "needs_review"
    assert evidence == EvidenceLevel.CONSISTENCY_CHECKED


def test_membership_fragment_returns_needs_review_consistency_checked() -> None:
    """Membership fragments are not yet implemented — must emit needs_review/CONSISTENCY_CHECKED."""
    from nlreq.formal_claim_smt import _check_fragment
    frag = _make_membership_fragment()
    result = _check_fragment(frag)
    assert result.status == "needs_review"
    assert result.evidence_level == EvidenceLevel.CONSISTENCY_CHECKED


def test_smt_results_include_covered_fragment_ids() -> None:
    """Every BackendResult must carry covered_fragment_ids for proof_closure matching."""
    report = build_formal_claim(_auth_ir())
    if report.formal_claim is None:
        return

    results = smt_check_formal_claim_predicate_fragments(report.formal_claim)

    for r in results:
        assert "covered_fragment_ids" in r.details
        assert isinstance(r.details["covered_fragment_ids"], list)
        assert len(r.details["covered_fragment_ids"]) == 1
