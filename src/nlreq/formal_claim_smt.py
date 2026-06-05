from __future__ import annotations

from z3 import ArithRef, BoolRef, Real, RealVal, Solver, sat

from .formal_claim import FormalClaim, FormalClaimFragment, FormalClaimOperand
from .jsonutil import sha256_text
from .models import BackendResult, EvidenceLevel

# Evidence honesty: "unsupported" results carry no evidence level.
# _producer_blockers skips results with evidence_level=None, preventing spurious
# producer-mapping blockers for fragments that are intentionally not checked at this layer.
_UNSUPPORTED_EVIDENCE: EvidenceLevel | None = None


FORMAL_CLAIM_SMT_VERSION = "0.1"

# The Z3 logic the premise consistency check runs in: quantifier-free linear real arithmetic.
# The IR declares no sorts for identifiers, so the reals are the honest (most permissive) domain —
# an UNSAT over the reals is a genuine contradiction in any numeric interpretation, and the
# satisfiability claim is reported as "consistent over QF_LRA", never as a stronger integer result.
_SMT_LOGIC = "QF_LRA"

# Comparison operators the linear-arithmetic encoder understands (membership "in" is not one of
# them — set semantics need a concrete finite collection, which the IR's opaque set operand does
# not provide, so membership is left to a model-level check).
_COMPARISON_OPS = frozenset({"eq", "neq", "lt", "lte", "gt", "gte"})


def smt_check_formal_claim_predicate_fragments(claim: FormalClaim) -> list[BackendResult]:
    """SMT-check FormalClaim fragments, returning explicit results for every checkable kind.

    Evidence honesty contract:
      - Comparison fragments (premises): checked together by a claim-level Z3 linear-arithmetic
        consistency query — see ``_premise_numeric_consistency``. The conjunction of the numeric
        premises being satisfiable discharges each at SMT_CHECKED (the antecedent is realizable and
        internally consistent); being unsatisfiable marks them invalid (a contradictory antecedent
        a single boolean-only or per-fragment query cannot detect). A lone symbolic comparison is
        vacuous in isolation, so the check is deliberately claim-level, not per-fragment.
      - Comparison obligations lower to ``state_invariant`` (invariance over S's transitions), not
        ``comparison``; proving them needs the system model S, so they are NOT discharged here —
        they route to the S ∧ R model check (Apalache). Z3 only checks the premise antecedent.
      - Predicate fragments: named uninterpreted predicates require model-level checking
        (Apalache/Pillar B). Emits "unsupported" so their routes become "blocked" in the proof
        object (explicit reason) rather than silently "open".
      - Membership fragments: a set membership needs a concrete finite collection to encode
        (a disjunction of equalities); the IR's set operand is opaque, so emits CONSISTENCY_CHECKED
        / needs_review and the route stays open.
      - rejection_order fragments: bounded-reachability ordering requires a model checker
        (Apalache). Emits "unsupported" so routes become "blocked".

    covered_fragment_ids is set on every result so proof_closure can match formal_claim-routed
    premises by fragment ID.
    """
    results = list(_premise_numeric_consistency(claim.premises))
    for fragment in [*claim.premises, *claim.obligations]:
        if fragment.kind in {"predicate", "rejection_order", "membership"}:
            results.append(_check_fragment(fragment))
    return results


def _premise_numeric_consistency(premises: list[FormalClaimFragment]) -> list[BackendResult]:
    """Discharge premise comparison fragments by a claim-level Z3 linear-arithmetic check.

    A lone symbolic comparison proves nothing (``x > rhs`` is trivially satisfiable), but the
    *conjunction* of the premises does: it is the requirement's antecedent. Checking that
    conjunction for satisfiability over QF_LRA gives a real, non-vacuous SMT result:

      - SAT  -> every contributing premise is an encodable, mutually-consistent constraint and the
                antecedent is realizable: status "valid", SMT_CHECKED.
      - UNSAT -> the premises contradict one another, so the antecedent can never hold (a modeling
                error): status "invalid", SMT_CHECKED. Z3 catches cross-variable and mixed
                equality/inequality contradictions the deterministic interval heuristic in
                requirement_self_consistency misses (e.g. ``x > y`` AND ``y > x``).

    One result is emitted per contributing fragment (each covering exactly its own fragment_id) so
    proof_closure can discharge or block each premise route individually while the verdict comes
    from the joint model. A comparison whose operands are not numerically encodable (a string
    operand, or fewer than two operands) cannot enter linear arithmetic; it is returned
    needs_review so its route stays open rather than being forced into the reals.
    """
    comparisons = [fragment for fragment in premises if fragment.kind == "comparison"]
    if not comparisons:
        return []

    solver = Solver()
    variables: dict[str, ArithRef] = {}
    encoded: list[FormalClaimFragment] = []
    unencodable: list[FormalClaimFragment] = []
    constraint_texts: list[str] = []
    for fragment in comparisons:
        constraint = _encode_comparison(fragment, variables)
        if constraint is None:
            unencodable.append(fragment)
            continue
        solver.add(constraint)
        encoded.append(fragment)
        constraint_texts.append(str(constraint))

    results: list[BackendResult] = []
    if encoded:
        outcome = solver.check()
        status = "valid" if outcome == sat else "invalid"
        # Order-independent reproducibility key for the joint query the verdict came from.
        query_hash = sha256_text(f"{_SMT_LOGIC}\n" + "\n".join(sorted(constraint_texts)))
        participating = sorted(fragment.fragment_id for fragment in encoded)
        for fragment in encoded:
            results.append(
                BackendResult(
                    backend="core_smt",
                    status=status,
                    evidence_level=EvidenceLevel.SMT_CHECKED,
                    details={
                        "covered_fragment_ids": [fragment.fragment_id],
                        "check": "premise_numeric_consistency",
                        "tool_version": FORMAL_CLAIM_SMT_VERSION,
                        "smt_logic": _SMT_LOGIC,
                        "z3_result": str(outcome),
                        "premise_constraint_fragment_ids": participating,
                        "query_hash": query_hash,
                    },
                )
            )
    for fragment in unencodable:
        results.append(
            BackendResult(
                backend="core_smt",
                status="needs_review",
                evidence_level=EvidenceLevel.CONSISTENCY_CHECKED,
                details={
                    "covered_fragment_ids": [fragment.fragment_id],
                    "check": "premise_numeric_consistency:unencodable",
                    "tool_version": FORMAL_CLAIM_SMT_VERSION,
                    "reason": (
                        "comparison operand is not encodable into linear arithmetic "
                        "(a string operand or fewer than two operands); route stays open"
                    ),
                },
            )
        )
    return results


def _encode_comparison(
    fragment: FormalClaimFragment, variables: dict[str, ArithRef]
) -> BoolRef | None:
    """A Z3 linear-arithmetic constraint for a comparison fragment, or None if not encodable.

    Numbers map to real literals and identifiers to shared real variables, so the same identifier
    in two fragments is the same variable and a cross-fragment contradiction is caught. A string
    operand, an unknown operator, or fewer than two operands makes the comparison non-arithmetic
    (returns None), and the caller keeps that route open rather than forcing it into the reals.
    """
    if fragment.operator not in _COMPARISON_OPS or len(fragment.operands) < 2:
        return None
    lhs = _encode_operand(fragment.operands[0], variables)
    rhs = _encode_operand(fragment.operands[1], variables)
    if lhs is None or rhs is None:
        return None
    operator = fragment.operator
    if operator == "eq":
        return lhs == rhs
    if operator == "neq":
        return lhs != rhs
    if operator == "lt":
        return lhs < rhs
    if operator == "lte":
        return lhs <= rhs
    if operator == "gt":
        return lhs > rhs
    return lhs >= rhs  # gte


def _encode_operand(
    operand: FormalClaimOperand, variables: dict[str, ArithRef]
) -> ArithRef | None:
    """A real literal for a number, a shared real variable for an identifier, or None otherwise.

    String operands are not linear arithmetic, so they return None and make the whole comparison
    unencodable — encoding them as reals would invent an ordering the requirement never stated.
    """
    if operand.kind == "number":
        try:
            return RealVal(float(operand.value))
        except (TypeError, ValueError):
            return None
    if operand.kind == "identifier":
        name = str(operand.value)
        if name not in variables:
            variables[name] = Real(f"v_{name}")
        return variables[name]
    return None


def _check_fragment(fragment: FormalClaimFragment) -> BackendResult:
    if fragment.kind == "predicate":
        # Named uninterpreted predicates require Apalache/Pillar B model-level checking.
        # Returning "unsupported" causes proof_closure to set the premise status to
        # "blocked" with an explicit reason rather than leaving it silently "open".
        # evidence_level=None so _producer_blockers skips this result and emits no spurious
        # producer-mapping blocker (core_smt is only registered for SMT_CHECKED).
        span_text = fragment.source_spans[0].text if fragment.source_spans else fragment.canonical
        return BackendResult(
            backend="core_smt",
            status="unsupported",
            evidence_level=_UNSUPPORTED_EVIDENCE,
            details={
                "covered_fragment_ids": [fragment.fragment_id],
                "check": "fragment_satisfiability:predicate",
                "tool_version": FORMAL_CLAIM_SMT_VERSION,
                "reason": (
                    f"uninterpreted predicate '{span_text}' has no fragment-level SMT content "
                    "(a free boolean is trivially SAT); checkable only at the requirement level "
                    "via S∧R composition in system_checker — not a fragment-level Z3 query"
                ),
            },
        )
    if fragment.kind == "rejection_order":
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
    # membership — a set membership needs a concrete finite collection to encode (a disjunction of
    # equalities); the IR's set operand is an opaque identifier, so a fragment-level query is
    # vacuous. needs_review keeps the route open rather than discharging it falsely.
    return BackendResult(
        backend="core_smt",
        status="needs_review",
        evidence_level=EvidenceLevel.CONSISTENCY_CHECKED,
        details={
            "covered_fragment_ids": [fragment.fragment_id],
            "check": f"fragment_satisfiability:{fragment.kind}",
            "tool_version": FORMAL_CLAIM_SMT_VERSION,
        },
    )
