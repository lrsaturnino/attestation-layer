from __future__ import annotations

from dataclasses import dataclass

from .adapter import Adapter
from .jsonutil import canonical_json
from .models import (
    EvidenceCapability,
    RequirementIR,
    SymbolBinding,
    SymbolRef,
    SymbolResolution,
    ValidationResult,
    VerificationTask,
)


@dataclass(frozen=True)
class AdapterConformanceFixture:
    resolved_ref: SymbolRef
    unresolved_ref: SymbolRef
    ambiguous_ref: SymbolRef
    sample_ir: RequirementIR


@dataclass(frozen=True)
class AdapterConformanceReport:
    adapter_id: str
    target_kind: str
    checks: tuple[str, ...]


class AdapterConformanceError(AssertionError):
    pass


def assert_adapter_conforms(
    adapter: Adapter, fixture: AdapterConformanceFixture
) -> AdapterConformanceReport:
    failures = run_adapter_conformance(adapter, fixture)
    if failures:
        joined = "\n".join(f"- {failure}" for failure in failures)
        raise AdapterConformanceError(f"Adapter conformance failed:\n{joined}")
    return AdapterConformanceReport(
        adapter_id=adapter.adapter_id,
        target_kind=adapter.target_kind,
        checks=(
            "interface_methods",
            "stable_resolution",
            "resolution_statuses",
            "binding_validation",
            "evidence_capabilities",
            "verification_tasks",
            "evidence_collection",
        ),
    )


def run_adapter_conformance(adapter: Adapter, fixture: AdapterConformanceFixture) -> list[str]:
    failures: list[str] = []
    failures.extend(_check_interface(adapter))

    refs = [fixture.resolved_ref, fixture.unresolved_ref, fixture.ambiguous_ref]
    first = _safe_resolve(adapter, refs, failures)
    second = _safe_resolve(adapter, refs, failures)
    if first is None or second is None:
        return failures

    try:
        stable = canonical_json(first) == canonical_json(second)
    except TypeError as exc:
        failures.append(f"resolve_symbols returned non-JSON-serializable results: {exc}")
        stable = True
    if not stable:
        failures.append("resolve_symbols must return byte-stable results for the same input")

    by_name = {resolution.ref.name: resolution for resolution in first}
    resolved = by_name.get(fixture.resolved_ref.name)
    unresolved = by_name.get(fixture.unresolved_ref.name)
    ambiguous = by_name.get(fixture.ambiguous_ref.name)

    if not resolved or resolved.status != "resolved" or not resolved.symbols:
        failures.append(f"{fixture.resolved_ref.name} must resolve to at least one symbol")
    if not unresolved or unresolved.status != "unresolved":
        failures.append(f"{fixture.unresolved_ref.name} must be reported as unresolved")
    if not ambiguous or ambiguous.status != "ambiguous" or len(ambiguous.symbols) < 2:
        failures.append(f"{fixture.ambiguous_ref.name} must be reported as ambiguous")

    if resolved and resolved.symbols:
        _check_binding_validation(adapter, resolved, failures)
        _check_capabilities(adapter, resolved, failures)
    _check_tasks(adapter, fixture.sample_ir, failures)
    _check_evidence_collection(adapter, failures)
    return failures


def _check_interface(adapter: Adapter) -> list[str]:
    failures: list[str] = []
    if not isinstance(adapter.adapter_id, str) or not adapter.adapter_id:
        failures.append("adapter_id must be a non-empty string")
    if not isinstance(adapter.target_kind, str) or not adapter.target_kind:
        failures.append("target_kind must be a non-empty string")
    for method in (
        "resolve_symbols",
        "validate_binding",
        "available_evidence",
        "generate_tasks",
        "collect_evidence",
    ):
        if not callable(getattr(adapter, method, None)):
            failures.append(f"{method} must be callable")
    return failures


def _safe_resolve(
    adapter: Adapter, refs: list[SymbolRef], failures: list[str]
) -> list[SymbolResolution] | None:
    try:
        resolutions = adapter.resolve_symbols(refs)
    except Exception as exc:  # pragma: no cover - defensive conformance boundary
        failures.append(f"resolve_symbols raised {type(exc).__name__}: {exc}")
        return None
    if len(resolutions) != len(refs):
        failures.append("resolve_symbols must return one result for each requested ref")
        return None
    if not all(isinstance(resolution, SymbolResolution) for resolution in resolutions):
        failures.append("resolve_symbols must return SymbolResolution objects")
        return None
    return resolutions


def _check_binding_validation(
    adapter: Adapter, resolution: SymbolResolution, failures: list[str]
) -> None:
    symbol = resolution.symbols[0]
    binding = SymbolBinding(
        adapter=adapter.adapter_id,
        symbol=symbol.name,
        symbol_type=symbol.symbol_type,
        confidence="generic_symbol_table" if adapter.adapter_id == "generic" else "adapter_resolved",
    )
    result = adapter.validate_binding(binding)
    if not isinstance(result, ValidationResult):
        failures.append("validate_binding must return a ValidationResult")
        return
    if not result.valid:
        failures.append(f"validate_binding rejected a resolved symbol: {result.reason}")


def _check_capabilities(
    adapter: Adapter, resolution: SymbolResolution, failures: list[str]
) -> None:
    capabilities = adapter.available_evidence(resolution.symbols)
    if not isinstance(capabilities, list):
        failures.append("available_evidence must return a list")
        return
    if not capabilities:
        failures.append("available_evidence must report at least one capability for resolved symbols")
    if not all(isinstance(capability, EvidenceCapability) for capability in capabilities):
        failures.append("available_evidence must return EvidenceCapability objects")


def _check_tasks(adapter: Adapter, ir: RequirementIR, failures: list[str]) -> None:
    tasks = adapter.generate_tasks(ir)
    if not isinstance(tasks, list):
        failures.append("generate_tasks must return a list")
        return
    if not tasks:
        failures.append("generate_tasks must return at least one task for the sample IR")
    if not all(isinstance(task, VerificationTask) for task in tasks):
        failures.append("generate_tasks must return VerificationTask objects")


def _check_evidence_collection(adapter: Adapter, failures: list[str]) -> None:
    collected = adapter.collect_evidence([])
    if not isinstance(collected, list):
        failures.append("collect_evidence must return a list")
