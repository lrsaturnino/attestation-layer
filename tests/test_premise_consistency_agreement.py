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
    build_premise_consistency_agreement,
    formal_claim_consistency_backend_for_id,
    formal_claim_consistency_backends,
)
from nlreq.formal_claim_smt import smt_check_formal_claim_premise_consistency
from nlreq.models import BackendResult, EvidenceLevel
from nlreq.premise_consistency import premise_consistency_overlap_key
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


def _checked(backend_id: str, status: str) -> BackendResult:
    return BackendResult(
        backend=backend_id,
        status=status,  # type: ignore[arg-type]
        evidence_level=EvidenceLevel.SMT_CHECKED,
        details={"covered_fragment_ids": ["frag.cmp"], "check": "premise_consistency"},
    )


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
    that: same claim, opposite decided verdicts."""
    claim = _claim("collateral >= 10 and collateral <= 50")
    left = _StubBackend("backend_a", [_checked("backend_a", "valid")])
    right = _StubBackend("backend_b", [_checked("backend_b", "invalid")])

    report = build_premise_consistency_agreement(claim, backends=[left, right])

    assert report.status == "disagreed"
    assert report.closure_effect == "block"
    assert report.comparisons[0].status == "disagreed"
    assert "verdict differs" in report.comparisons[0].reasons[0]
    # The block is on the verdict, not on evidence level or bounds.
    assert report.comparisons[0].compared_fields == ["status"]


def test_builder_non_overlap_when_a_backend_cannot_decide() -> None:
    """A backend that cannot decide the question (needs_review, no evidence level) is not a
    disagreement — the gate reports non_overlap rather than a false block."""
    claim = _claim("collateral >= 10 and collateral <= 50")
    decided = _StubBackend("backend_a", [_checked("backend_a", "valid")])
    undecided = _StubBackend(
        "backend_b",
        [
            BackendResult(
                backend="backend_b",
                status="needs_review",
                evidence_level=None,
                details={"covered_fragment_ids": ["frag.cmp"], "check": "premise_consistency:unencodable"},
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
