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


def test_predicate_fragments_produce_unsupported_results_with_covered_ids() -> None:
    """Predicate fragments must produce BackendResult(status='unsupported') with covered_fragment_ids.

    Named uninterpreted predicates require Apalache/Pillar B model-level checking. Rather
    than silently excluding them (which left proof_closure routes as 'open' with no reason),
    the SMT checker now emits an explicit 'unsupported' result. proof_closure maps
    'unsupported' → premise status 'blocked', making the gap visible and auditable.
    """
    report = build_formal_claim(_auth_ir())
    assert report.formal_claim is not None
    predicate_fragments = [
        f for f in [*report.formal_claim.premises, *report.formal_claim.obligations]
        if f.kind == "predicate"
    ]
    assert predicate_fragments, "auth fixture must have predicate fragments"

    results = smt_check_formal_claim_predicate_fragments(report.formal_claim)

    predicate_results = [
        r for r in results
        if any(
            fid in r.details.get("covered_fragment_ids", [])
            for fid in {f.fragment_id for f in predicate_fragments}
        )
    ]
    assert len(predicate_results) == len(predicate_fragments), (
        f"expected one BackendResult per predicate fragment, got {predicate_results}"
    )
    for r in predicate_results:
        assert r.status == "unsupported", (
            f"predicate fragment BackendResult must have status='unsupported', got {r.status!r}"
        )
        assert "reason" in r.details, (
            f"predicate BackendResult must carry a reason in details: {r.details}"
        )


def test_unsupported_fragment_results_carry_no_evidence_level() -> None:
    """Unsupported fragment results must have evidence_level=None.

    Predicate and rejection_order fragments are intentionally unsupported at the
    fragment-level SMT layer (they require Apalache/Pillar B). Setting evidence_level=None
    prevents _producer_blockers in proof_closure from emitting spurious producer-mapping
    blockers — core_smt is only registered for SMT_CHECKED and apalache only for
    BOUNDED_CHECKED; claiming CONSISTENCY_CHECKED from either backend would violate the
    evidence honesty contract.
    """
    report = build_formal_claim(_auth_ir())
    assert report.formal_claim is not None

    results = smt_check_formal_claim_predicate_fragments(report.formal_claim)

    unsupported_results = [r for r in results if r.status == "unsupported"]
    assert unsupported_results, "auth fixture must produce at least one unsupported result"
    for r in unsupported_results:
        assert r.evidence_level is None, (
            f"unsupported BackendResult must have evidence_level=None to avoid "
            f"spurious producer-mapping blockers, got evidence_level={r.evidence_level!r} "
            f"for backend={r.backend!r}"
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
