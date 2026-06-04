from __future__ import annotations

from z3 import Bool, Int, Solver, unsat

from .formal_claim import FormalClaim, FormalClaimFragment
from .models import BackendResult, EvidenceLevel


FORMAL_CLAIM_SMT_VERSION = "0.1"


def smt_check_formal_claim_predicate_fragments(claim: FormalClaim) -> list[BackendResult]:
    """SMT-check ground (concrete-number) comparison FormalClaim fragments.

    Evidence honesty contract:
      - Predicate fragments: excluded. Named uninterpreted predicates require
        model-level checking (Pillar B/system_checker), not SMT well-formedness.
        Their routes remain open pending that evidence.
      - Comparison fragments, both operands concrete numbers: evaluates ground
        truth and emits SMT_CHECKED. This is a real check.
      - Comparison fragments, at least one symbolic operand: satisfiability-in-
        isolation of a symbolic constraint proves nothing (x > rhs is always SAT).
        Emits CONSISTENCY_CHECKED with needs_review so the route stays open.
      - Membership fragments: not implemented; emits CONSISTENCY_CHECKED /
        needs_review so routes stay open.

    covered_fragment_ids is set on every result so proof_closure can match
    formal_claim-routed premises by fragment ID.
    """
    return [
        _check_fragment(fragment)
        for fragment in [*claim.premises, *claim.obligations]
        if fragment.kind in {"comparison", "membership"}
    ]


def _check_fragment(fragment: FormalClaimFragment) -> BackendResult:
    if fragment.kind == "comparison":
        status, evidence = _check_comparison(fragment)
    else:
        # membership — encode not yet implemented
        status, evidence = "needs_review", EvidenceLevel.CONSISTENCY_CHECKED

    return BackendResult(
        backend="core_smt",
        status=status,
        evidence_level=evidence,
        details={
            "covered_fragment_ids": [fragment.fragment_id],
            "check": f"fragment_satisfiability:{fragment.kind}",
            "tool_version": FORMAL_CLAIM_SMT_VERSION,
        },
    )


def _check_comparison(fragment: FormalClaimFragment) -> tuple[str, EvidenceLevel]:
    if fragment.operator is None or len(fragment.operands) < 2:
        return "needs_review", EvidenceLevel.CONSISTENCY_CHECKED

    lhs = fragment.operands[0]
    rhs = fragment.operands[1]

    # Ground evaluation — both operands are concrete numbers: real SMT_CHECKED result.
    if lhs.kind == "number" and rhs.kind == "number":
        try:
            lv = float(lhs.value)
            rv = float(rhs.value)
        except (TypeError, ValueError):
            return "needs_review", EvidenceLevel.CONSISTENCY_CHECKED
        ops: dict[str, bool] = {
            "lt": lv < rv,
            "lte": lv <= rv,
            "gt": lv > rv,
            "gte": lv >= rv,
            "eq": lv == rv,
            "neq": lv != rv,
        }
        if fragment.operator not in ops:
            return "needs_review", EvidenceLevel.CONSISTENCY_CHECKED
        result = "valid" if ops[fragment.operator] else "invalid"
        return result, EvidenceLevel.SMT_CHECKED

    # Symbolic operand — satisfiability-in-isolation is trivially true for most
    # operators and proves nothing meaningful about the fragment's semantics.
    # Return needs_review so the route stays open pending a real encoding.
    return "needs_review", EvidenceLevel.CONSISTENCY_CHECKED
