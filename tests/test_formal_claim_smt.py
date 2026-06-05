from __future__ import annotations

from pathlib import Path

import pytest

from nlreq.cvc5_backend import cvc5_available, cvc5_check_formal_claim_premises
from nlreq.dsl_v3 import DslV3Parser
from nlreq.formal_claim import build_formal_claim, build_proof_dispatch_plan_from_formal_claim
from nlreq.formal_claim_smt import (
    FORMAL_CLAIM_SMT_VERSION,
    _premise_consistency,
    smt_check_formal_claim_predicate_fragments,
)
from nlreq.formal_claim import FormalClaimFragment, FormalClaimOperand
from nlreq.models import EvidenceLevel
from nlreq.proof_closure import build_proof_object


FIXTURES = Path(__file__).parent / "fixtures" / "requirements"

requires_cvc5 = pytest.mark.skipif(
    not cvc5_available(),
    reason="cvc5 optional dependency not installed (run under `uv run --extra formal`)",
)


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


def test_predicate_fragments_are_unsupported_with_covered_ids() -> None:
    """Predicate fragments must produce status='unsupported' with covered_fragment_ids.

    Named uninterpreted predicates have no fragment-level SMT content — a free boolean is
    trivially SAT regardless of the predicate's meaning. They can only be checked via S∧R
    composition in system_checker (Apalache/Pillar B). Returning 'unsupported' causes
    proof_closure to set the premise to 'blocked' with an explicit reason, rather than
    silently leaving it 'open' or falsely 'discharged'.
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
            f"predicate fragment BackendResult must have status='unsupported' "
            f"(requires Apalache/Pillar B), got {r.status!r}"
        )
        assert r.evidence_level is None, (
            f"predicate BackendResult must have evidence_level=None to avoid spurious "
            f"producer-mapping blockers, got {r.evidence_level!r}"
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


def test_ground_true_comparison_discharges_at_smt_checked() -> None:
    """A satisfiable (here ground-true) premise comparison discharges at valid/SMT_CHECKED."""
    frag = _make_comparison_fragment("number", 5, "number", 10, "lt")
    results = _premise_consistency([frag])
    assert [r.status for r in results] == ["valid"]
    assert results[0].evidence_level == EvidenceLevel.SMT_CHECKED
    assert results[0].details["covered_fragment_ids"] == [frag.fragment_id]


def test_ground_false_comparison_is_invalid_smt_checked() -> None:
    """A ground-false premise comparison is an unsatisfiable antecedent: invalid/SMT_CHECKED."""
    frag = _make_comparison_fragment("number", 10, "number", 5, "lt")
    results = _premise_consistency([frag])
    assert [r.status for r in results] == ["invalid"]
    assert results[0].evidence_level == EvidenceLevel.SMT_CHECKED


def test_lone_symbolic_comparison_is_consistent_smt_checked() -> None:
    """A single symbolic comparison is a satisfiable (encodable, non-contradictory) antecedent, so
    it discharges at SMT_CHECKED — unlike the old per-fragment path it is a real Z3 check, and a
    ground contradiction in the same position would instead be invalid."""
    frag = _make_comparison_fragment("identifier", "balance", "identifier", "threshold", "lt")
    results = _premise_consistency([frag])
    assert [r.status for r in results] == ["valid"]
    assert results[0].evidence_level == EvidenceLevel.SMT_CHECKED
    assert results[0].details["smt_logic"] == "QF_LRA"


def test_consistent_symbolic_premises_discharge_at_smt_checked() -> None:
    """Two satisfiable bounds on the same variable (>=10, <=50) both discharge at SMT_CHECKED."""
    low = _make_comparison_fragment("identifier", "collateral", "number", 10, "gte")
    high = _make_comparison_fragment("identifier", "collateral", "number", 50, "lte")
    high.fragment_id = "test.frag.cmp.high"
    results = _premise_consistency([low, high])
    assert {r.status for r in results} == {"valid"}
    assert all(r.evidence_level == EvidenceLevel.SMT_CHECKED for r in results)
    covered = {r.details["covered_fragment_ids"][0] for r in results}
    assert covered == {low.fragment_id, high.fragment_id}


def test_contradictory_symbolic_premises_are_invalid_smt_checked() -> None:
    """Two unsatisfiable bounds on the same variable (>=10, <=5) make the antecedent contradictory:
    every contributing premise is invalid/SMT_CHECKED. The negation of the consistent sibling above
    yields the opposite verdict — the discrimination Z3-with-theories provides."""
    low = _make_comparison_fragment("identifier", "collateral", "number", 10, "gte")
    high = _make_comparison_fragment("identifier", "collateral", "number", 5, "lte")
    high.fragment_id = "test.frag.cmp.high"
    results = _premise_consistency([low, high])
    assert {r.status for r in results} == {"invalid"}
    assert all(r.evidence_level == EvidenceLevel.SMT_CHECKED for r in results)


def test_cross_variable_contradiction_caught_by_z3() -> None:
    """`x > y` AND `y > x` is unsatisfiable. The deterministic interval heuristic groups by the
    first operand and so puts these in different buckets — it cannot see the conflict; the Z3
    linear-arithmetic check does, returning invalid for both premises."""
    a = _make_comparison_fragment("identifier", "x", "identifier", "y", "gt")
    b = _make_comparison_fragment("identifier", "y", "identifier", "x", "gt")
    b.fragment_id = "test.frag.cmp.b"
    results = _premise_consistency([a, b])
    assert {r.status for r in results} == {"invalid"}


def test_membership_fragment_returns_needs_review_no_evidence_level() -> None:
    """An opaque named-set membership needs a concrete finite set to encode (the set operand is a
    single opaque identifier). It was not checked here, so it emits needs_review with NO evidence
    level — claiming CONSISTENCY_CHECKED for a premise the solver never saw would overstate it, and
    None keeps the route open without tripping the SMT_CHECKED-only producer mapping."""
    from nlreq.formal_claim_smt import _check_fragment
    frag = _make_membership_fragment()
    result = _check_fragment(frag)
    assert result.status == "needs_review"
    assert result.evidence_level is None


def _make_set_membership_fragment(
    element: str, members: list[str], fragment_id: str = "test.frag.setmem"
) -> FormalClaimFragment:
    return FormalClaimFragment(
        fragment_id=fragment_id,
        source_node_id="n3",
        role="premise",
        kind="membership",
        canonical=f"in({element},{{{','.join(members)}}})",
        operator="in",
        operands=[
            FormalClaimOperand(kind="identifier", value=element),
            *[FormalClaimOperand(kind="identifier", value=member) for member in members],
        ],
        metadata={"membership": "set_literal"},
    )


def test_set_literal_membership_discharges_at_smt_checked() -> None:
    """A satisfiable set-literal membership (`x in {A, B}`) discharges at valid/SMT_CHECKED — it is
    enumerated into the joint premise query, not left review-only like an opaque named set."""
    frag = _make_set_membership_fragment("status", ["APPROVED", "REJECTED"])
    results = _premise_consistency([frag])
    assert [r.status for r in results] == ["valid"]
    assert results[0].evidence_level == EvidenceLevel.SMT_CHECKED
    assert results[0].details["smt_logic"] == "QF_UF"
    assert results[0].details["covered_fragment_ids"] == [frag.fragment_id]


def test_disjoint_set_membership_is_invalid_smt_checked() -> None:
    """`x in {A}` AND `x in {B}` with distinct members is an unsatisfiable antecedent: every
    contributing membership premise is invalid/SMT_CHECKED. This is the natural set contradiction a
    per-fragment check (which sees each membership as trivially satisfiable) cannot catch."""
    approved = _make_set_membership_fragment("status", ["APPROVED"], "test.frag.setmem.a")
    rejected = _make_set_membership_fragment("status", ["REJECTED"], "test.frag.setmem.b")
    results = _premise_consistency([approved, rejected])
    assert {r.status for r in results} == {"invalid"}
    assert all(r.evidence_level == EvidenceLevel.SMT_CHECKED for r in results)
    covered = {r.details["covered_fragment_ids"][0] for r in results}
    assert covered == {approved.fragment_id, rejected.fragment_id}


def test_overlapping_set_membership_is_consistent_smt_checked() -> None:
    """Two memberships whose sets share a member (`{A, B}` and `{B, C}`) are jointly satisfiable
    (the element is B): valid/SMT_CHECKED — the encoding does not over-constrain to a contradiction."""
    left = _make_set_membership_fragment("status", ["APPROVED", "PENDING"], "test.frag.setmem.l")
    right = _make_set_membership_fragment("status", ["PENDING", "REJECTED"], "test.frag.setmem.r")
    results = _premise_consistency([left, right])
    assert {r.status for r in results} == {"valid"}


def test_membership_and_comparison_share_one_joint_query() -> None:
    """A set-literal membership and a numeric comparison over independent identifiers are checked in
    one joint query (logic QF_UFLRA) and are mutually consistent: both discharge at SMT_CHECKED."""
    membership = _make_set_membership_fragment("status", ["APPROVED"], "test.frag.setmem")
    comparison = _make_comparison_fragment("identifier", "collateral", "number", 10, "gte")
    results = _premise_consistency([membership, comparison])
    assert {r.status for r in results} == {"valid"}
    assert all(r.evidence_level == EvidenceLevel.SMT_CHECKED for r in results)
    assert {r.details["smt_logic"] for r in results} == {"QF_UFLRA"}


def test_membership_element_also_used_as_numeric_operand_needs_review() -> None:
    """An identifier used as both a membership element and a numeric operand cannot be both a real
    and a member value in one model, so the membership fragment stays needs_review (route open)
    while the encodable comparison still discharges — the sort clash is not forced."""
    membership = _make_set_membership_fragment("amount", ["APPROVED"], "test.frag.setmem")
    comparison = _make_comparison_fragment("identifier", "amount", "number", 5, "gte")
    comparison.fragment_id = "test.frag.cmp.amount"
    results = _premise_consistency([membership, comparison])
    by_id = {r.details["covered_fragment_ids"][0]: r for r in results}
    assert by_id[membership.fragment_id].status == "needs_review"
    # Not encoded -> not checked -> no evidence level (route stays open without a producer blocker).
    assert by_id[membership.fragment_id].evidence_level is None
    assert by_id[comparison.fragment_id].status == "valid"


def test_set_literal_membership_lowers_with_concrete_members_and_marker() -> None:
    """`x is in {A, B}` lowers to a membership fragment carrying its members as concrete operands
    and the set_literal marker, distinguishing it from an opaque named-set membership."""
    ir = DslV3Parser().parse_ir(
        "requirement numeric_invariant:\n"
        "scope reserve\n"
        "when status is in {APPROVED, REJECTED}\n"
        "then keep collateral >= 1\n",
        requirement_id="MEM-LOWER",
        title="Membership lowering",
    )
    report = build_formal_claim(ir)
    assert report.formal_claim is not None
    membership = [f for f in report.formal_claim.premises if f.kind == "membership"]
    assert len(membership) == 1
    assert [operand.value for operand in membership[0].operands] == [
        "status",
        "APPROVED",
        "REJECTED",
    ]
    assert membership[0].metadata == {"membership": "set_literal"}


def test_numeric_invariant_with_set_membership_premise_smt_checked_end_to_end() -> None:
    """End to end through the public projection: a numeric_invariant whose antecedent is a
    set-literal membership produces a real SMT_CHECKED result for that premise — closing the
    'membership remains review-only' gap for a concrete enumerable set."""
    ir = DslV3Parser().parse_ir(
        "requirement numeric_invariant:\n"
        "scope reserve\n"
        "when status is in {APPROVED, REJECTED}\n"
        "then keep collateral >= 1\n",
        requirement_id="MEM-E2E",
        title="Membership end to end",
    )
    report = build_formal_claim(ir)
    assert report.formal_claim is not None
    membership = next(f for f in report.formal_claim.premises if f.kind == "membership")

    results = smt_check_formal_claim_predicate_fragments(report.formal_claim)

    membership_results = [
        r for r in results if membership.fragment_id in r.details.get("covered_fragment_ids", [])
    ]
    assert membership_results, "membership premise must produce a backend result"
    assert all(r.status == "valid" for r in membership_results)
    assert all(r.evidence_level == EvidenceLevel.SMT_CHECKED for r in membership_results)


def _numeric_invariant_proof(premise_clause: str):
    """Build the proof object for a numeric_invariant requirement whose antecedent is
    ``premise_clause``, dispatching the FormalClaim fragments and feeding only the SMT results."""
    ir = DslV3Parser().parse_ir(
        "requirement numeric_invariant:\n"
        "scope reserve\n"
        f"when {premise_clause}\n"
        "then keep collateral >= 1\n",
        requirement_id="NUMERIC-PREMISE",
        title="Numeric premise",
    )
    report = build_formal_claim(ir)
    assert report.formal_claim is not None
    plan = build_proof_dispatch_plan_from_formal_claim(report.formal_claim)
    # Feed both theory backends, mirroring the production gate: comparison premises route to and are
    # discharged by smt-theories (z3), set-membership premises by cvc5. cvc5 results are inert for
    # comparison-only claims (comparison routes to smt-theories), so comparison tests need no cvc5.
    results = [
        *smt_check_formal_claim_predicate_fragments(report.formal_claim),
        *cvc5_check_formal_claim_premises(report.formal_claim),
    ]
    return build_proof_object(requirement=ir, backend_results=results, dispatch=plan)


def test_consistent_comparison_premises_discharge_through_proof_object() -> None:
    """Wiring: the claim-level SMT result actually discharges the comparison premise routes in the
    proof object (not a unit-tested island). Consistent bounds discharge; the state_invariant
    obligation stays open for the S ∧ R model check — Z3 never claims an invariant it cannot prove."""
    proof = _numeric_invariant_proof("collateral >= 10 and collateral <= 50")
    by_kind = {(p.node_kind, p.premise_id): p.status for p in proof.premises}
    comparison_statuses = {s for (kind, _), s in by_kind.items() if kind == "comparison"}
    invariant_statuses = {s for (kind, _), s in by_kind.items() if kind == "state_invariant"}
    assert comparison_statuses == {"discharged"}
    assert invariant_statuses == {"open"}  # routes to Apalache S∧R, not discharged by Z3


def test_contradictory_comparison_premises_block_through_proof_object() -> None:
    """The negation: contradictory bounds block the comparison premises (backend status invalid),
    so the proof cannot close on a vacuously-true antecedent — the discrimination Z3 provides."""
    proof = _numeric_invariant_proof("collateral >= 10 and collateral <= 5")
    comparison = [p for p in proof.premises if p.node_kind == "comparison"]
    assert comparison, "requirement must have comparison premises"
    assert all(p.status == "blocked" and p.backend_status == "invalid" for p in comparison)


def test_large_integer_contradiction_survives_exact_encoding() -> None:
    """Two premises pin one variable to consecutive integers past 2**53. They contradict, so Z3 must
    block the comparison premises. Encoding the literals through ``float()`` rounds both to the same
    value, makes the antecedent look satisfiable, and the contradiction vanishes — the exact-rational
    encoding catches it."""
    proof = _numeric_invariant_proof(
        "collateral == 9007199254740992 and collateral == 9007199254740993"
    )
    comparison = [p for p in proof.premises if p.node_kind == "comparison"]
    assert comparison, "requirement must have comparison premises"
    assert all(p.status == "blocked" and p.backend_status == "invalid" for p in comparison)


@requires_cvc5
def test_set_membership_premise_discharges_through_proof_object() -> None:
    """Wiring: a consistent set-literal membership premise is actually discharged at SMT_CHECKED in
    the proof object — the producer is wired behind the proof contract, not a unit-tested island.
    This is what closes 'membership remains review-only' where the producer is observed. Membership
    routes to cvc5 (its native finite-set theory, PB-7), so the discharge is by the cvc5 producer."""
    proof = _numeric_invariant_proof("status is in {APPROVED, REJECTED}")
    membership = [p for p in proof.premises if p.node_kind == "membership"]
    assert membership, "requirement must have a membership premise"
    assert all(p.status == "discharged" and p.backend_status == "valid" for p in membership)
    assert all(p.routed_backend == "cvc5" and p.producer_id == "cvc5" for p in membership)


@requires_cvc5
def test_disjoint_set_membership_premises_block_through_proof_object() -> None:
    """The negation: a disjoint-set antecedent (`x in {A}` and `x in {B}`) blocks the membership
    premises (backend status invalid), so the proof cannot close on a vacuously-true antecedent."""
    proof = _numeric_invariant_proof("status is in {APPROVED} and status is in {REJECTED}")
    membership = [p for p in proof.premises if p.node_kind == "membership"]
    assert membership, "requirement must have membership premises"
    assert all(p.status == "blocked" and p.backend_status == "invalid" for p in membership)


def test_set_membership_member_also_used_as_numeric_operand_needs_review() -> None:
    """An identifier used as both a set member and a numeric operand (`status in {APPROVED}` and
    `APPROVED >= 5`) cannot be both a real and a member value in one model. The membership stays
    needs_review rather than encoding the two occurrences as unrelated and falsely discharging."""
    membership = _make_set_membership_fragment("status", ["APPROVED"], "test.frag.setmem")
    comparison = _make_comparison_fragment("identifier", "APPROVED", "number", 5, "gte")
    comparison.fragment_id = "test.frag.cmp.approved"
    results = _premise_consistency([membership, comparison])
    by_id = {r.details["covered_fragment_ids"][0]: r for r in results}
    assert by_id[membership.fragment_id].status == "needs_review"
    # Not encoded -> not checked -> no evidence level (route stays open without a producer blocker).
    assert by_id[membership.fragment_id].evidence_level is None
    assert by_id[comparison.fragment_id].status == "valid"


def test_large_integer_consistent_premise_still_discharges() -> None:
    """Discrimination control: a satisfiable large-integer premise stays discharged — the exact
    encoding flags genuine contradictions without flipping every big-integer comparison to invalid."""
    proof = _numeric_invariant_proof("collateral == 9007199254740993")
    comparison_statuses = {p.status for p in proof.premises if p.node_kind == "comparison"}
    assert comparison_statuses == {"discharged"}


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
