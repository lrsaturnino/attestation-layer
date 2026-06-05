from __future__ import annotations

from z3 import Bool, Solver, unsat

from .jsonutil import sha256_text
from .models import (
    BackendResult,
    EvidenceClaim,
    EvidenceLevel,
    EvidenceObject,
    Predicate,
    RequirementIR,
    SourceSpan,
)


# The Phase 0 SMT encoder (``smt2_for_ir`` and the ``check_self_consistency`` solver) is
# propositional: it represents only these authorization/approval boolean predicate ops. Comparison
# (eq/neq/gt/lt/gte/lte) and set-membership (in) predicates are NOT theory-encoded here — the
# theory-aware encoder lives on the FormalClaim path (``formal_claim_smt``). Naming the encodable set
# once lets both the query writer and the check refuse to over-claim for the predicates they drop.
_SMT_ENCODABLE_OPS = frozenset({"authorized", "not_authorized", "approved", "not_approved"})


def check_self_consistency(ir: RequirementIR) -> BackendResult:
    contradictions = _direct_contradictions(ir.claim.condition)
    if contradictions:
        return BackendResult(
            backend="core_smt",
            status="invalid",
            evidence_level=EvidenceLevel.CONSISTENCY_CHECKED,
            details={"contradictions": contradictions},
        )

    solver = Solver()
    for predicate in ir.claim.condition:
        if predicate.op in {"authorized", "not_authorized", "approved", "not_approved"}:
            atom = Bool(_atom_name(predicate))
            solver.add(atom if predicate.op in {"authorized", "approved"} else ~atom)
    result = solver.check()
    return BackendResult(
        backend="core_smt",
        status="invalid" if result == unsat else "valid",
        evidence_level=EvidenceLevel.CONSISTENCY_CHECKED,
        details={"solver_result": str(result)},
    )


def smt_check_requirement(ir: RequirementIR) -> BackendResult:
    """Phase 0 check: supported claim shape is encodable and conditions are satisfiable."""
    unencoded = _unencoded_predicate_ops(ir)
    if unencoded:
        # The Phase 0 query (smt2_for_ir) and the self-consistency solver encode only
        # authorization/approval booleans, so any comparison, numeric, or set-membership predicate
        # is silently dropped. This refusal is checked BEFORE consulting self-consistency on
        # purpose: _direct_contradictions flags eq/neq opposites *syntactically* (e.g. `counter is
        # limit` plus `counter is not limit`), so an invalid consistency verdict can rest entirely on
        # ops smt2_for_ir never encoded. Upgrading that verdict to SMT_CHECKED would label a check
        # the query did not run. Gating the level on the whole condition being propositionally
        # encodable keeps SMT_CHECKED honest: emit an explicit non-checked result (no evidence level)
        # naming the unencoded ops so the evidence builders treat C-smt as undischarged rather than a
        # false pass. The theory-aware encoder on the FormalClaim path (formal_claim_smt) is where
        # comparison/membership predicates are actually checked.
        return BackendResult(
            backend="core_smt",
            status="unsupported",
            evidence_level=None,
            details={
                "checked": "supported_phase_0_claim_shape",
                "unencoded_predicate_ops": unencoded,
                "reason": "Phase 0 SMT encodes only authorization/approval booleans",
                "query_hash": sha256_text(smt2_for_ir(ir)),
            },
        )
    consistency = check_self_consistency(ir)
    if consistency.status != "valid":
        # Every condition predicate is propositionally encodable here (the unencoded guard above
        # already returned), so an invalid verdict — including an authorization/approval
        # contradiction — was genuinely represented in the SMT query: SMT_CHECKED is honest.
        return consistency.model_copy(update={"evidence_level": EvidenceLevel.SMT_CHECKED})
    return BackendResult(
        backend="core_smt",
        status="valid",
        evidence_level=EvidenceLevel.SMT_CHECKED,
        details={
            "checked": "supported_phase_0_claim_shape",
            "query_hash": sha256_text(smt2_for_ir(ir)),
        },
    )


def static_resolution_result(
    ir: RequirementIR, missing_symbols: list[str], ambiguous_symbols: list[str]
) -> BackendResult:
    if missing_symbols or ambiguous_symbols:
        return BackendResult(
            backend="generic_adapter",
            status="invalid",
            evidence_level=EvidenceLevel.STATICALLY_RESOLVED,
            details={
                "ambiguous_symbols": ambiguous_symbols,
                "missing_symbols": missing_symbols,
            },
        )
    return BackendResult(
        backend="generic_adapter",
        status="valid",
        evidence_level=EvidenceLevel.STATICALLY_RESOLVED,
        details={"resolved_symbols": sorted(ir.bindings)},
    )


def evidence_for_ir(
    ir: RequirementIR,
    *,
    ir_hash: str,
    missing_symbols: list[str],
    ambiguous_symbols: list[str] | None = None,
    ambiguous_symbol_spans: dict[str, SourceSpan] | None = None,
    unbound_symbol_spans: dict[str, SourceSpan] | None = None,
) -> EvidenceObject:
    ambiguous_symbols = ambiguous_symbols or []
    static = static_resolution_result(ir, missing_symbols, ambiguous_symbols)
    consistency = check_self_consistency(ir)
    smt = smt_check_requirement(ir)
    failed = []
    if static.status != "valid":
        failed.append("C-static")
    if consistency.status != "valid":
        failed.append("C-consistency")
    if smt.status != "valid":
        failed.append("C-smt")

    claims = [
        EvidenceClaim(
            id="C-static",
            description="Symbols are statically resolved by the generic adapter.",
            required_evidence=EvidenceLevel.STATICALLY_RESOLVED,
            achieved_evidence=EvidenceLevel.STATICALLY_RESOLVED if static.status == "valid" else None,
            backend_results=[static],
        ),
        EvidenceClaim(
            id="C-consistency",
            description="Supported claims are internally consistent.",
            required_evidence=EvidenceLevel.CONSISTENCY_CHECKED,
            achieved_evidence=EvidenceLevel.CONSISTENCY_CHECKED
            if consistency.status == "valid"
            else None,
            backend_results=[consistency],
        ),
        EvidenceClaim(
            id="C-smt",
            description="Supported claim shape is SMT-checked under declared assumptions.",
            required_evidence=EvidenceLevel.SMT_CHECKED,
            achieved_evidence=EvidenceLevel.SMT_CHECKED if smt.status == "valid" else None,
            backend_results=[smt],
        ),
    ]

    return EvidenceObject(
        requirement_id=ir.requirement_id,
        ir_hash=ir_hash,
        claims=claims,
        ambiguous=bool(ambiguous_symbols),
        ambiguous_symbols=ambiguous_symbols,
        ambiguous_symbol_spans=ambiguous_symbol_spans or {},
        unbound_symbols=missing_symbols,
        unbound_symbol_spans=unbound_symbol_spans or {},
        failed_checks=failed,
    )


def smt2_for_ir(ir: RequirementIR) -> str:
    declarations: list[str] = []
    assertions: list[str] = []
    declared: set[str] = set()
    for predicate in ir.claim.condition:
        if predicate.op not in _SMT_ENCODABLE_OPS:
            continue
        name = _smt_atom_name(predicate)
        if name not in declared:
            declarations.append(f"(declare-const {name} Bool)")
            declared.add(name)
        assertions.append(f"(assert {'(not ' + name + ')' if predicate.op.startswith('not_') else name})")

    header = [f"; Phase 0 SMT query for {ir.requirement_id}"]
    unencoded = _unencoded_predicate_ops(ir)
    if unencoded:
        # Keep the .smt2 file honest: the propositional Phase 0 encoder does not represent these
        # predicates, so name them rather than presenting an empty (check-sat) as a complete query.
        header.append(
            "; UNENCODED by Phase 0 (propositional only; not represented in this query): "
            + ", ".join(unencoded)
        )
    body = "\n".join([*declarations, *assertions, "(check-sat)"])
    return "\n".join([*header, body]) + "\n"


def _unencoded_predicate_ops(ir: RequirementIR) -> list[str]:
    """Distinct condition predicate ops the Phase 0 SMT encoder cannot represent, in first-seen order.

    These are the comparison and set-membership ops ``smt2_for_ir`` and the self-consistency solver
    silently drop; naming them is what lets the check refuse to over-claim SMT_CHECKED and the query
    file disclose what it omits.
    """
    unencoded: list[str] = []
    for predicate in ir.claim.condition:
        if predicate.op not in _SMT_ENCODABLE_OPS and predicate.op not in unencoded:
            unencoded.append(predicate.op)
    return unencoded


def _direct_contradictions(predicates: list[Predicate]) -> list[str]:
    seen: set[tuple[str, tuple[str, ...]]] = set()
    contradictions: list[str] = []
    opposites = {
        "authorized": "not_authorized",
        "not_authorized": "authorized",
        "approved": "not_approved",
        "not_approved": "approved",
        "eq": "neq",
        "neq": "eq",
    }
    for predicate in predicates:
        key = (predicate.op, tuple(str(arg.value) for arg in predicate.args))
        opposite = (opposites.get(predicate.op, ""), key[1])
        if opposite in seen:
            contradictions.append(predicate.source_span.text)
        seen.add(key)
    return contradictions


def _atom_name(predicate: Predicate) -> str:
    return f"{predicate.op.replace('not_', '')}:{':'.join(str(arg.value) for arg in predicate.args)}"


def _smt_atom_name(predicate: Predicate) -> str:
    base = predicate.op.replace("not_", "")
    args = "_".join(str(arg.value).replace("-", "_") for arg in predicate.args)
    return f"{base}_{args}"
