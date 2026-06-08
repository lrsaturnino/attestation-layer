"""PB-6.T2 — the independent cvc5 second backend over the FormalClaim premise question.

The headline acceptance ("the same FormalClaim projects into ≥2 backends") is
``test_cvc5_matches_z3_verdict_on_same_formal_claim``: z3 (smt-theories) and cvc5 encode the same
premise-consistency question through independent encoders and decide the same verdict. The
remaining tests pin the honest-degradation and producer-registration contracts, and run whether or
not cvc5 is installed (cvc5 is an optional dependency; the real-run tests skip cleanly when absent).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from nlreq.cvc5_backend import (
    CVC5_BACKEND_ID,
    cvc5_available,
    cvc5_check_formal_claim_premises,
    cvc5_tool_version,
)
from nlreq.dsl_v3 import DslV3Parser
from nlreq.formal_claim import build_formal_claim
from nlreq.formal_claim_smt import smt_check_formal_claim_predicate_fragments
from nlreq.models import BackendResult, EvidenceLevel
from nlreq.premise_consistency import is_set_literal_membership
from nlreq.proof_closure import _producer_blockers, default_evidence_producer_mapping


FIXTURES = Path(__file__).parent / "fixtures" / "requirements"

requires_cvc5 = pytest.mark.skipif(
    not cvc5_available(),
    reason="cvc5 optional dependency not installed (run under `uv run --with cvc5` / `--extra formal`)",
)


def _claim(premise_clause: str):
    ir = DslV3Parser().parse_ir(
        "requirement numeric_invariant:\n"
        "scope reserve\n"
        f"when {premise_clause}\n"
        "then keep collateral >= 1\n",
        requirement_id="CVC5-BACKEND",
        title="cvc5 backend",
    )
    report = build_formal_claim(ir)
    assert report.formal_claim is not None
    return report.formal_claim


def _auth_claim():
    ir = DslV3Parser().parse_ir(
        FIXTURES.joinpath("authorization_precondition_v3.nlreq").read_text(),
        requirement_id="CVC5-AUTH",
        title="cvc5 auth",
    )
    report = build_formal_claim(ir)
    assert report.formal_claim is not None
    return report.formal_claim


def _by_fragment(results: list[BackendResult]) -> dict[str, BackendResult]:
    return {
        fragment_id: result
        for result in results
        for fragment_id in result.details.get("covered_fragment_ids", [])
    }


# (premise clause, the verdict every contributing premise of that clause should reach)
_PARITY_CASES = [
    ("collateral >= 10 and collateral <= 50", "valid"),  # satisfiable numeric bounds
    ("collateral >= 10 and collateral <= 5", "invalid"),  # contradictory numeric bounds
    ("status is in {APPROVED, REJECTED}", "valid"),  # satisfiable set-literal membership
    ("status is in {APPROVED} and status is in {REJECTED}", "invalid"),  # disjoint singletons
    ("status is in {APPROVED, PENDING} and collateral >= 10", "valid"),  # mixed, independent vars
    ("collateral > threshold and threshold > collateral", "invalid"),  # cross-variable contradiction
]


@requires_cvc5
@pytest.mark.parametrize("clause, expected", _PARITY_CASES)
def test_cvc5_matches_z3_verdict_on_same_formal_claim(clause: str, expected: str) -> None:
    """The same FormalClaim projects into two backends and they agree on every premise verdict.

    z3 (smt-theories) encodes set membership as DeclareSort + Distinct + a disjunction of equalities;
    cvc5 encodes it through the native finite-set theory (set.member / set.insert). The two encoders
    share only the FormalClaim, yet decide the same sat/unsat verdict for every contributing
    premise — the '≥2 backends, same question' acceptance, and the substrate a non-vacuous agreement
    check (PB-6.T3) compares.
    """
    claim = _claim(clause)
    z3_by_fragment = _by_fragment(smt_check_formal_claim_predicate_fragments(claim))
    cvc5_by_fragment = _by_fragment(cvc5_check_formal_claim_premises(claim))

    assert cvc5_by_fragment, "cvc5 must check at least one premise fragment"
    for fragment_id, cvc5_result in cvc5_by_fragment.items():
        assert cvc5_result.backend == CVC5_BACKEND_ID
        assert fragment_id in z3_by_fragment, f"z3 must cover the same premise {fragment_id}"
        z3_result = z3_by_fragment[fragment_id]
        assert cvc5_result.status == z3_result.status == expected, (
            f"verdict mismatch on {fragment_id}: expected {expected}, "
            f"z3={z3_result.status}, cvc5={cvc5_result.status}"
        )
        assert cvc5_result.evidence_level == z3_result.evidence_level == EvidenceLevel.SMT_CHECKED


@requires_cvc5
def test_cvc5_results_carry_covered_ids_and_recorded_version() -> None:
    """Every cvc5 result carries exactly one covered fragment id and the run-recorded cvc5 version."""
    results = cvc5_check_formal_claim_premises(_claim("collateral >= 10 and collateral <= 50"))
    assert results
    for result in results:
        assert result.backend == CVC5_BACKEND_ID
        assert len(result.details["covered_fragment_ids"]) == 1
        assert result.details["tool"] == "cvc5"
        # cvc5 present -> the real installed version is recorded, never None or a placeholder.
        assert cvc5_tool_version() is not None
        assert result.details["tool_version"] == cvc5_tool_version()


def test_cvc5_emits_one_result_per_contributing_premise() -> None:
    """Per-fragment emission holds whether cvc5 checks or reports unavailable.

    proof closure matches premise routes by covered fragment id, so each contributing premise must
    produce exactly one result — a real verdict when cvc5 is present, an honest 'unavailable' result
    when absent — and never silently vanish.
    """
    claim = _claim("collateral >= 10 and collateral <= 50")
    results = cvc5_check_formal_claim_premises(claim)
    covered = {fragment_id for r in results for fragment_id in r.details["covered_fragment_ids"]}
    comparison_ids = {f.fragment_id for f in claim.premises if f.kind == "comparison"}
    assert covered == comparison_ids


@requires_cvc5
def test_cvc5_discharges_concrete_set_literal_membership() -> None:
    """A CONCRETE set-literal membership (``x is in {A, B}``) is discharged by cvc5 at SMT_CHECKED.

    This is the surface where a real finite set reaches cvc5: the v3 grammar's ``membership_set`` form
    carries enumerable members and the ``set_literal`` marker, so cvc5's native finite-set theory
    encodes it and decides a verdict — unlike an OPAQUE v1 membership (``value is in value``), which
    has no concrete members and stays open (the generic v1 adapter emits that case ``unsupported``;
    see ``tests/test_adapter.py::test_generate_tasks_routes_opaque_v1_membership_to_unsupported``).
    """
    claim = _claim("status is in {APPROVED, REJECTED}")
    set_literal_premises = [
        fragment
        for fragment in claim.premises
        if fragment.kind == "membership" and is_set_literal_membership(fragment)
    ]
    assert set_literal_premises, "the v3 set-literal membership must lower to a concrete-member fragment"

    results = cvc5_check_formal_claim_premises(claim)
    membership_results = [
        result
        for result in results
        for fragment in set_literal_premises
        if fragment.fragment_id in result.details.get("covered_fragment_ids", [])
    ]
    assert membership_results, "cvc5 must contribute a result for the concrete set-literal membership"
    for result in membership_results:
        assert result.backend == CVC5_BACKEND_ID
        # Two distinct named members in one set -> the membership is satisfiable -> a real SMT verdict.
        assert result.status == "valid"
        assert result.evidence_level == EvidenceLevel.SMT_CHECKED


@requires_cvc5
def test_cvc5_membership_requirement_and_negation_discriminate() -> None:
    """PA-1 membership discrimination: a concrete set-membership question and its negation reach
    OPPOSITE cvc5 verdicts — the cvc5 analogue of the Apalache 'one valid / one counterexample' pair.

    `actor is in {alice, bob}` with the witness `actor is in {alice}` (the element IS in the set) is
    satisfiable -> cvc5 valid; the same base set with the witness `actor is in {carol}` (the element
    is OUTSIDE the set — the realizable negation of membership) is unsatisfiable -> cvc5 invalid,
    because the three named members are encoded as pairwise-distinct constants. cvc5's native
    finite-set theory is a real decision procedure here, not a rubber stamp: it discriminates a member
    from a non-member.

    This is cvc5's surface: a membership constraint as a FormalClaim theory fragment, and the route
    for an OPAQUE set reference (`NAME is in NAME`) that names no finite literal Apalache could decide.
    It is NOT the only membership surface — a membership PREMISE whose variable a reviewed S declares
    (`tier is in {gold, silver}` over S's own `tier`) IS Apalache-discriminable: the
    state_postcondition narrowing keeps it as a finite-set guard so a set change flips valid vs
    counterexample (see
    test_system_checker.test_state_postcondition_membership_premise_apalache_discriminates_on_set).
    The v3 grammar admits membership only as a premise (never a `keep` obligation), so unlike
    comparison it has no Apalache OBLIGATION form — but the S-declared premise above and this cvc5
    fragment/opaque-set route are both real producers. This is the cvc5 discrimination test (member ->
    valid, non-member -> invalid)."""

    def membership_verdicts(premise_clause: str) -> set[str]:
        claim = _claim(premise_clause)
        membership = [
            fragment
            for fragment in claim.premises
            if fragment.kind == "membership" and is_set_literal_membership(fragment)
        ]
        assert membership, "the premise must contribute concrete set-literal membership fragments"
        results = cvc5_check_formal_claim_premises(claim)
        return {
            result.status
            for result in results
            for fragment in membership
            if fragment.fragment_id in result.details.get("covered_fragment_ids", [])
        }

    # Witness IN the set -> satisfiable -> cvc5 discharges the membership (valid).
    assert membership_verdicts("actor is in {alice, bob} and actor is in {alice}") == {"valid"}
    # Witness OUTSIDE the set (the negation) -> unsatisfiable -> cvc5 refutes it (invalid).
    assert membership_verdicts("actor is in {alice, bob} and actor is in {carol}") == {"invalid"}


def test_cvc5_degrades_honestly_when_absent(monkeypatch: pytest.MonkeyPatch) -> None:
    """With cvc5 forced absent, the check emits 'unsupported' results with no evidence level.

    Never an SMT_CHECKED claim without a real cvc5 run: the absent path discharges nothing, keeps the
    routes open under an explicit reason, and records no tool version.
    """
    monkeypatch.setattr("nlreq.cvc5_backend.cvc5", None)
    assert not cvc5_available()

    results = cvc5_check_formal_claim_premises(_claim("collateral >= 10 and collateral <= 50"))
    assert results, "must still emit one result per premise so the routes are explicitly unsupported"
    for result in results:
        assert result.backend == CVC5_BACKEND_ID
        assert result.status == "unsupported"
        assert result.evidence_level is None
        assert result.details["tool_version"] is None
        assert "reason" in result.details


def test_cvc5_returns_no_results_without_a_premise_consistency_question() -> None:
    """An authorization predicate premise poses no comparison/membership question — cvc5 returns []."""
    claim = _auth_claim()
    contributing = [
        fragment
        for fragment in claim.premises
        if fragment.kind == "comparison"
        or (fragment.kind == "membership" and fragment.metadata.get("membership") == "set_literal")
    ]
    if contributing:
        pytest.skip("auth fixture has contributing premises; empty-case not applicable")
    assert cvc5_check_formal_claim_premises(claim) == []


def test_cvc5_producer_registered_for_smt_checked() -> None:
    """The cvc5 producer is registered and allowed to emit SMT_CHECKED as a real producer."""
    mapping = default_evidence_producer_mapping()
    producer = next((p for p in mapping.producers if p.producer_id == CVC5_BACKEND_ID), None)
    assert producer is not None, "cvc5 must be registered in the default producer mapping"
    assert producer.real_producer is True
    assert producer.allowed_evidence_levels == [EvidenceLevel.SMT_CHECKED]


def test_cvc5_smt_checked_result_accepted_by_producer_mapping() -> None:
    """A cvc5 SMT_CHECKED result raises no producer-mapping blocker in proof closure.

    Without registration, an SMT_CHECKED result from backend 'cvc5' would trip _producer_blockers
    ("producer is not registered"); this asserts the registration is effective end to end.
    """
    result = BackendResult(
        backend=CVC5_BACKEND_ID,
        status="valid",
        evidence_level=EvidenceLevel.SMT_CHECKED,
        details={"covered_fragment_ids": ["frag.cmp"], "check": "premise_consistency"},
    )
    blockers = _producer_blockers([result], default_evidence_producer_mapping())
    assert blockers == [], f"cvc5 SMT_CHECKED must be accepted by the producer mapping, got {blockers}"
