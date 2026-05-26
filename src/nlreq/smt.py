from __future__ import annotations

from z3 import Bool, Solver, unsat

from .models import (
    BackendResult,
    EvidenceClaim,
    EvidenceLevel,
    EvidenceObject,
    Predicate,
    RequirementIR,
)


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
    consistency = check_self_consistency(ir)
    if consistency.status != "valid":
        return consistency.model_copy(update={"evidence_level": EvidenceLevel.SMT_CHECKED})
    return BackendResult(
        backend="core_smt",
        status="valid",
        evidence_level=EvidenceLevel.SMT_CHECKED,
        details={"checked": "supported_phase_0_claim_shape"},
    )


def evidence_for_ir(ir: RequirementIR, *, ir_hash: str, missing_symbols: list[str]) -> EvidenceObject:
    consistency = check_self_consistency(ir)
    smt = smt_check_requirement(ir)
    failed = []
    if consistency.status != "valid":
        failed.append("C-consistency")
    if smt.status != "valid":
        failed.append("C-smt")

    claims = [
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
        unbound_symbols=missing_symbols,
        failed_checks=failed,
    )


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
