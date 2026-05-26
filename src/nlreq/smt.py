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
        details={
            "checked": "supported_phase_0_claim_shape",
            "query_hash": sha256_text(smt2_for_ir(ir)),
        },
    )


def static_resolution_result(ir: RequirementIR, missing_symbols: list[str]) -> BackendResult:
    if missing_symbols:
        return BackendResult(
            backend="generic_adapter",
            status="invalid",
            evidence_level=EvidenceLevel.STATICALLY_RESOLVED,
            details={"missing_symbols": missing_symbols},
        )
    return BackendResult(
        backend="generic_adapter",
        status="valid",
        evidence_level=EvidenceLevel.STATICALLY_RESOLVED,
        details={"resolved_symbols": sorted(ir.bindings)},
    )


def evidence_for_ir(ir: RequirementIR, *, ir_hash: str, missing_symbols: list[str]) -> EvidenceObject:
    static = static_resolution_result(ir, missing_symbols)
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
        unbound_symbols=missing_symbols,
        failed_checks=failed,
    )


def smt2_for_ir(ir: RequirementIR) -> str:
    declarations: list[str] = []
    assertions: list[str] = []
    declared: set[str] = set()
    for predicate in ir.claim.condition:
        if predicate.op not in {"authorized", "not_authorized", "approved", "not_approved"}:
            continue
        name = _smt_atom_name(predicate)
        if name not in declared:
            declarations.append(f"(declare-const {name} Bool)")
            declared.add(name)
        assertions.append(f"(assert {'(not ' + name + ')' if predicate.op.startswith('not_') else name})")

    body = "\n".join(declarations + assertions + ["(check-sat)"])
    return f"; Phase 0 SMT query for {ir.requirement_id}\n{body}\n"


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
