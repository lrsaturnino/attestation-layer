"""PB-6.T3 — the cross-backend premise-consistency agreement gate over the FormalClaim backends.

The two SMT backends (z3 as ``core_smt``, cvc5) answer the same premise-consistency question through
independent encoders. These tests pin the verdict-first agreement gate that judges them: they share a
solver-independent ``overlap_key`` for the question, agreement is decided on the verdict alone, an
opposite-verdict divergence blocks (a planted encoder disagreement), and a backend that cannot decide
(or is absent) is non-overlap rather than a false block. Evidence honesty is checked too: a
non-encodable premise emits no evidence level, so it raises no spurious producer-mapping blocker.
"""

from __future__ import annotations

import pytest

from nlreq.cvc5_backend import CVC5_BACKEND_ID, cvc5_available, cvc5_check_formal_claim_premises
from nlreq.dsl_v3 import DslV3Parser
from nlreq.formal_claim import build_formal_claim
from nlreq.formal_claim_backend import (
    CORE_SMT_BACKEND_ID,
    Cvc5ConsistencyBackend,
    CoreSmtConsistencyBackend,
    _collapse_backend_verdict,
    build_premise_consistency_agreement,
    formal_claim_consistency_backend_for_id,
    formal_claim_consistency_backends,
)
from nlreq.formal_claim_smt import smt_check_formal_claim_premise_consistency
from nlreq.models import BackendResult, EvidenceLevel
from nlreq.premise_consistency import contributing_premises, premise_consistency_overlap_key
from nlreq.proof_closure import _producer_blockers, default_evidence_producer_mapping


requires_cvc5 = pytest.mark.skipif(
    not cvc5_available(),
    reason="cvc5 optional dependency not installed (run under `uv run --extra formal`)",
)


def _claim(premise_clause: str):
    ir = DslV3Parser().parse_ir(
        "requirement numeric_invariant:\n"
        "scope reserve\n"
        f"when {premise_clause}\n"
        "then keep collateral >= 1\n",
        requirement_id="PC-AGREE",
        title="premise consistency agreement",
    )
    report = build_formal_claim(ir)
    assert report.formal_claim is not None
    return report.formal_claim


class _StubBackend:
    """A FormalClaim consistency backend that returns canned results (planted scenarios)."""

    def __init__(self, backend_id: str, results: list[BackendResult]) -> None:
        self.backend_id = backend_id
        self._results = results

    def check(self, claim) -> list[BackendResult]:  # noqa: ANN001 - structural protocol
        return list(self._results)


def _contributing_ids(claim) -> list[str]:  # noqa: ANN001 - structural FormalClaim
    """The fragment IDs of the claim's contributing premises (comparisons + set-literal memberships).

    A planted stub standing in for a backend that fully decided the question must cover these *real*
    IDs: the collapse cross-references this authoritative contributing set, so a synthetic ID would
    read as undecided coverage and the stub would (correctly) collapse to non-deciding."""
    return [fragment.fragment_id for fragment in contributing_premises(claim.premises)]


def _checked_all(backend_id: str, status: str, fragment_ids: list[str]) -> list[BackendResult]:
    """One SMT_CHECKED result per contributing fragment carrying the joint verdict — what a backend
    that fully decided the premise-consistency question emits."""
    return [
        BackendResult(
            backend=backend_id,
            status=status,  # type: ignore[arg-type]
            evidence_level=EvidenceLevel.SMT_CHECKED,
            details={"covered_fragment_ids": [fragment_id], "check": "premise_consistency"},
        )
        for fragment_id in fragment_ids
    ]


# --- registry discoverability (PB-6.T2/T1) ---------------------------------------------------------


def test_backends_discoverable_via_registry() -> None:
    """Both SMT backends are discoverable through the shared FormalClaim backend registry."""
    backends = formal_claim_consistency_backends()
    ids = {backend.backend_id for backend in backends}
    assert ids == {CORE_SMT_BACKEND_ID, CVC5_BACKEND_ID}
    assert isinstance(formal_claim_consistency_backend_for_id(CORE_SMT_BACKEND_ID), CoreSmtConsistencyBackend)
    assert isinstance(formal_claim_consistency_backend_for_id(CVC5_BACKEND_ID), Cvc5ConsistencyBackend)
    with pytest.raises(ValueError):
        formal_claim_consistency_backend_for_id("does-not-exist")


@requires_cvc5
def test_both_backends_emit_shared_overlap_key() -> None:
    """z3 and cvc5 emit the same solver-independent overlap_key for the same question.

    This is the pairing identity the agreement check needs: derived from the FormalClaim alone, so
    the two independent encoders cannot drift apart on *what* they were asked."""
    claim = _claim("collateral >= 10 and collateral <= 50")
    canonical = premise_consistency_overlap_key(claim.premises)
    assert canonical is not None

    z3_keys = {
        result.details.get("overlap_key")
        for result in smt_check_formal_claim_premise_consistency(claim)
        if result.evidence_level is not None
    }
    cvc5_keys = {
        result.details.get("overlap_key")
        for result in cvc5_check_formal_claim_premises(claim)
        if result.evidence_level is not None
    }
    assert z3_keys == cvc5_keys == {canonical}


# --- the gate over the real backends (PB-6.T3) -----------------------------------------------------


@requires_cvc5
def test_builder_allows_when_real_backends_agree_consistent() -> None:
    """A satisfiable antecedent: both backends decide valid, so the gate agrees and allows."""
    report = build_premise_consistency_agreement(_claim("collateral >= 10 and collateral <= 50"))
    assert report.status == "agreed"
    assert report.closure_effect == "allow"
    assert all(comparison.status == "agreed" for comparison in report.comparisons)


@requires_cvc5
def test_builder_allows_when_real_backends_agree_contradictory() -> None:
    """A contradictory antecedent: both backends decide invalid — they still agree, so the gate
    allows (agreement is about the backends concurring, not about the premises being satisfiable)."""
    report = build_premise_consistency_agreement(_claim("collateral >= 10 and collateral <= 5"))
    assert report.status == "agreed"
    assert report.closure_effect == "allow"


def test_builder_blocks_planted_verdict_disagreement() -> None:
    """The headline PB-6.T3 acceptance: a planted opposite-verdict divergence between two backends
    on the same question blocks the gate, naming the verdict mismatch.

    Two complete solvers never disagree on identical formulas, so a real divergence can only come
    from an encoder bug — exactly what the agreement is meant to catch. The planted stubs simulate
    that: each fully decides every contributing premise, but on opposite verdicts."""
    claim = _claim("collateral >= 10 and collateral <= 50")
    ids = _contributing_ids(claim)
    left = _StubBackend("backend_a", _checked_all("backend_a", "valid", ids))
    right = _StubBackend("backend_b", _checked_all("backend_b", "invalid", ids))

    report = build_premise_consistency_agreement(claim, backends=[left, right])

    assert report.status == "disagreed"
    assert report.closure_effect == "block"
    assert report.comparisons[0].status == "disagreed"
    assert "verdict differs" in report.comparisons[0].reasons[0]
    # The block is on the verdict, not on evidence level or bounds.
    assert report.comparisons[0].compared_fields == ["status"]


def test_builder_non_overlap_when_a_backend_cannot_decide() -> None:
    """A backend that cannot decide the question (needs_review, no evidence level) is not a
    disagreement — the gate reports non_overlap rather than a false block. The other backend fully
    decides the question, covering every contributing premise at SMT_CHECKED."""
    claim = _claim("collateral >= 10 and collateral <= 50")
    ids = _contributing_ids(claim)
    decided = _StubBackend("backend_a", _checked_all("backend_a", "valid", ids))
    undecided = _StubBackend(
        "backend_b",
        [
            BackendResult(
                backend="backend_b",
                status="needs_review",
                evidence_level=None,
                details={"covered_fragment_ids": ids, "check": "premise_consistency:unencodable"},
            )
        ],
    )

    report = build_premise_consistency_agreement(claim, backends=[decided, undecided])
    assert report.comparisons[0].status == "non_overlap"


# --- evidence honesty: non-encodable premises raise no producer blocker (PB-6.T3 / GAP-X4) ---------


def test_core_smt_unencodable_premise_raises_no_producer_blocker() -> None:
    """A core_smt premise that could not be encoded (sort clash) emits no evidence level, so it
    raises no spurious producer-mapping blocker — the route stays cleanly open."""
    claim = _claim("amount is in {APPROVED} and amount >= 5")
    results = smt_check_formal_claim_premise_consistency(claim)
    unencodable = [r for r in results if r.status == "needs_review"]
    assert unencodable, "the sort clash must yield a needs_review premise"
    assert all(r.evidence_level is None for r in unencodable)
    assert _producer_blockers(results, default_evidence_producer_mapping()) == []


@requires_cvc5
def test_cvc5_unencodable_premise_raises_no_producer_blocker() -> None:
    """The same honesty for cvc5: a sort-clash premise emits no evidence level, so feeding cvc5
    results into proof closure produces a clean open route, not a producer-mapping blocker."""
    claim = _claim("amount is in {APPROVED} and amount >= 5")
    results = cvc5_check_formal_claim_premises(claim)
    unencodable = [r for r in results if r.status == "needs_review"]
    assert unencodable, "the sort clash must yield a needs_review premise"
    assert all(r.evidence_level is None for r in unencodable)
    assert _producer_blockers(results, default_evidence_producer_mapping()) == []


# --- partial encoding must never become a false whole-question agreement --------------------------
# A backend that decides only PART of the shared question (one premise checked, another unencodable)
# must collapse to a non-deciding observation, not the partial verdict. Otherwise two backends that
# each answered only half the antecedent identically would be paired as a false "agreed/allow".


def test_partial_encoding_collapses_to_non_deciding() -> None:
    """The headline regression: a backend that decided only part of the question collapses to a
    non-deciding observation that lists the undecided premise — never the partial verdict.

    In ``amount is in {APPROVED} and amount >= 5`` the identifier ``amount`` is both a numeric
    operand and a set element, so the membership is an unencodable sort clash while the comparison
    checks ``valid``. The backend answered only half the antecedent, so its collapsed observation
    must carry no evidence level, no valid/invalid verdict, and must name the undecided membership.
    Runs on z3 alone (no cvc5), so it always guards the collapse in CI."""
    claim = _claim("amount is in {APPROVED} and amount >= 5")
    overlap_key = premise_consistency_overlap_key(claim.premises)

    collapsed = _collapse_backend_verdict(CoreSmtConsistencyBackend(), claim, overlap_key)

    assert collapsed.evidence_level is None
    assert collapsed.status not in {"valid", "invalid"}
    assert collapsed.details["decided"] is False
    assert collapsed.details["undecided_fragment_ids"], (
        "the unencodable membership must be reported as an undecided contributing premise"
    )
    # Covered (discharged) and undecided premises are disjoint, and together they are exactly the
    # contributing set: partial coverage is reported as such, never inflated to the whole question.
    covered = set(collapsed.details["covered_fragment_ids"])
    undecided = set(collapsed.details["undecided_fragment_ids"])
    assert covered.isdisjoint(undecided)
    assert covered | undecided == set(_contributing_ids(claim))


@requires_cvc5
def test_builder_partial_encoding_is_not_a_false_agreement() -> None:
    """End-to-end: with BOTH real backends each deciding only the comparison and leaving the
    membership unencodable, the agreement report must NOT be a false ``agreed``.

    Collapsing each backend's partial coverage to a whole-question verdict would let two backends
    that each answered only half the antecedent be paired as a false ``agreed``. Each backend's
    partial result is instead non-deciding, so the pair is non_overlap — an honest "the question was
    not fully answered". A non_overlap is non-blocking (closure_effect="allow") because the agreement
    is additive: these premises are discharged independently by the per-premise SMT path. The guard
    that matters is that the status is non_overlap, never ``agreed`` — so the agreement provides no
    false confirmation the proof could close on."""
    report = build_premise_consistency_agreement(_claim("amount is in {APPROVED} and amount >= 5"))
    assert report.status == "non_overlap"
    assert all(comparison.status == "non_overlap" for comparison in report.comparisons)
    assert report.closure_effect == "allow"
