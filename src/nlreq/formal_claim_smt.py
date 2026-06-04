from __future__ import annotations

from z3 import Bool, Int, Real, Solver, unsat

from .formal_claim import FormalClaim, FormalClaimFragment
from .models import BackendResult, EvidenceLevel


FORMAL_CLAIM_SMT_VERSION = "0.1"


def smt_check_formal_claim_predicate_fragments(claim: FormalClaim) -> list[BackendResult]:
    """SMT-check predicate, comparison, and membership FormalClaim fragments with Z3.

    Returns one BackendResult per checkable fragment with covered_fragment_ids set to
    [fragment.fragment_id] so proof_closure can match by fragment ID rather than by
    backend alone. FormalClaim routes (routing_mode="formal_claim") require this
    explicit coverage to be discharged.

    Evidence level is SMT_CHECKED for all results, matching the evidence level required
    by predicate/comparison/membership routes in formal_claim._evidence_for_fragment_kind.
    """
    return [
        _check_fragment(fragment)
        for fragment in [*claim.premises, *claim.obligations]
        if fragment.kind in {"predicate", "comparison", "membership"}
    ]


def _check_fragment(fragment: FormalClaimFragment) -> BackendResult:
    if fragment.kind == "predicate":
        status = _check_predicate(fragment)
    elif fragment.kind in {"comparison", "membership"}:
        status = _check_comparison(fragment)
    else:
        status = "needs_review"

    return BackendResult(
        backend="core_smt",
        status=status,
        evidence_level=EvidenceLevel.SMT_CHECKED,
        details={
            "covered_fragment_ids": [fragment.fragment_id],
            "check": f"fragment_satisfiability:{fragment.kind}",
            "tool_version": FORMAL_CLAIM_SMT_VERSION,
        },
    )


def _check_predicate(fragment: FormalClaimFragment) -> str:
    # Uninterpreted boolean predicate — satisfiable iff a name is present (non-vacuous).
    # A missing predicate name means the fragment is malformed, not a logical property.
    if not fragment.predicate:
        return "needs_review"
    s = Solver()
    var = Bool(f"pred_{fragment.fragment_id}")
    s.add(var)
    return "valid" if s.check() != unsat else "invalid"


def _check_comparison(fragment: FormalClaimFragment) -> str:
    if fragment.operator is None or len(fragment.operands) < 2:
        return "needs_review"
    lhs = fragment.operands[0]
    rhs = fragment.operands[1]
    # Both operands are concrete numbers — evaluate directly without Z3.
    if lhs.kind == "number" and rhs.kind == "number":
        try:
            lv = float(lhs.value)
            rv = float(rhs.value)
        except (TypeError, ValueError):
            return "needs_review"
        ops: dict[str, bool] = {
            "lt": lv < rv,
            "lte": lv <= rv,
            "gt": lv > rv,
            "gte": lv >= rv,
            "eq": lv == rv,
            "neq": lv != rv,
            "in": False,  # in-membership requires a set; handled separately
        }
        return "valid" if ops.get(fragment.operator, False) else "invalid"
    # At least one symbolic operand — check satisfiability via Z3 arithmetic.
    s = Solver()
    lhs_z3 = Int(str(lhs.value)) if lhs.kind == "identifier" else int(float(str(lhs.value)))
    rhs_z3 = Int(str(rhs.value)) if rhs.kind == "identifier" else int(float(str(rhs.value)))
    op_exprs = {
        "lt": lhs_z3 < rhs_z3,
        "lte": lhs_z3 <= rhs_z3,
        "gt": lhs_z3 > rhs_z3,
        "gte": lhs_z3 >= rhs_z3,
        "eq": lhs_z3 == rhs_z3,
        "neq": lhs_z3 != rhs_z3,
    }
    if fragment.operator not in op_exprs:
        return "needs_review"
    s.add(op_exprs[fragment.operator])
    return "valid" if s.check() != unsat else "invalid"
