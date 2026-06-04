from __future__ import annotations

from .formal_claim import FormalClaim, FormalClaimFragment
from .models import BackendResult, EvidenceLevel

# Evidence honesty: "unsupported" results carry no evidence level.
# _producer_blockers skips results with evidence_level=None, preventing spurious
# producer-mapping blockers for fragments that are intentionally not checked at this layer.
_UNSUPPORTED_EVIDENCE: EvidenceLevel | None = None


FORMAL_CLAIM_SMT_VERSION = "0.1"


def smt_check_formal_claim_predicate_fragments(claim: FormalClaim) -> list[BackendResult]:
    """SMT-check FormalClaim fragments, returning explicit results for every kind.

    Evidence honesty contract:
      - Predicate fragments: named uninterpreted predicates require model-level
        checking (Apalache/Pillar B). Emits "unsupported" so their routes become
        "blocked" in the proof object (explicit reason) rather than silently "open".
      - Comparison fragments, both operands concrete numbers: evaluates ground
        truth and emits SMT_CHECKED. This is a real check.
      - Comparison fragments, at least one symbolic operand: satisfiability-in-
        isolation of a symbolic constraint proves nothing (x > rhs is always SAT).
        Emits CONSISTENCY_CHECKED with needs_review so the route stays open.
      - Membership fragments: not implemented; emits CONSISTENCY_CHECKED /
        needs_review so routes stay open.
      - rejection_order fragments: bounded-reachability ordering requires a model
        checker (Apalache). Emits "unsupported" so routes become "blocked".

    covered_fragment_ids is set on every result so proof_closure can match
    formal_claim-routed premises by fragment ID.
    """
    return [
        _check_fragment(fragment)
        for fragment in [*claim.premises, *claim.obligations]
        if fragment.kind in {"comparison", "membership", "predicate", "rejection_order"}
    ]


def _check_fragment(fragment: FormalClaimFragment) -> BackendResult:
    if fragment.kind == "comparison":
        status, evidence = _check_comparison(fragment)
        check_label = "fragment_satisfiability:comparison"
        extra: dict[str, str] = {}
    elif fragment.kind == "predicate":
        # Named uninterpreted predicates require Apalache/Pillar B model-level checking.
        # Returning "unsupported" causes proof_closure to set the premise status to
        # "blocked" with an explicit reason rather than leaving it silently "open".
        # evidence_level=None so _producer_blockers skips this result and emits no spurious
        # producer-mapping blocker (core_smt is only registered for SMT_CHECKED).
        status, evidence = "unsupported", _UNSUPPORTED_EVIDENCE
        check_label = "fragment_satisfiability:predicate"
        span_text = fragment.source_spans[0].text if fragment.source_spans else fragment.canonical
        extra = {"reason": (
            f"uninterpreted predicate '{span_text}' has no fragment-level SMT content "
            "(a free boolean is trivially SAT); checkable only at the requirement level "
            "via S∧R composition in system_checker — not a fragment-level Z3 query"
        )}
    elif fragment.kind == "rejection_order":
        # Bounded-reachability ordering requires a model checker (Apalache).
        # Return with backend="apalache" to match the routed_backend so proof_closure can
        # find this result and set the premise to "blocked" (not silently "open").
        span_text = fragment.source_spans[0].text if fragment.source_spans else fragment.canonical
        return BackendResult(
            backend="apalache",
            status="unsupported",
            evidence_level=_UNSUPPORTED_EVIDENCE,
            details={
                "covered_fragment_ids": [fragment.fragment_id],
                "check": "fragment_satisfiability:rejection_order",
                "tool_version": FORMAL_CLAIM_SMT_VERSION,
                "reason": f"rejection_order '{span_text}' bounded-reachability requires Apalache binary; not available",
            },
        )
    else:
        # membership — encode not yet implemented
        status, evidence = "needs_review", EvidenceLevel.CONSISTENCY_CHECKED
        check_label = f"fragment_satisfiability:{fragment.kind}"
        extra = {}

    return BackendResult(
        backend="core_smt",
        status=status,
        evidence_level=evidence,
        details={
            "covered_fragment_ids": [fragment.fragment_id],
            "check": check_label,
            "tool_version": FORMAL_CLAIM_SMT_VERSION,
            **extra,
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
