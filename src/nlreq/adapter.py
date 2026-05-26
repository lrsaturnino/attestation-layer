from __future__ import annotations

from abc import ABC, abstractmethod

from .models import (
    EvidenceCapability,
    EvidenceLevel,
    RequirementIR,
    Symbol,
    SymbolBinding,
    SymbolRef,
    SymbolResolution,
    ValidationResult,
    VerificationTask,
)


class Adapter(ABC):
    adapter_id: str
    target_kind: str

    @abstractmethod
    def resolve_symbols(self, refs: list[SymbolRef]) -> list[SymbolResolution]:
        raise NotImplementedError

    @abstractmethod
    def validate_binding(self, binding: SymbolBinding) -> ValidationResult:
        raise NotImplementedError

    @abstractmethod
    def available_evidence(self, symbols: list[Symbol]) -> list[EvidenceCapability]:
        raise NotImplementedError

    @abstractmethod
    def generate_tasks(self, ir: RequirementIR) -> list[VerificationTask]:
        raise NotImplementedError

    @abstractmethod
    def collect_evidence(self, task_results: list[object]) -> list[object]:
        raise NotImplementedError


class GenericAdapter(Adapter):
    adapter_id = "generic"
    target_kind = "static_symbol_table"

    def __init__(self, symbols: dict[str, dict[str, object]]):
        self._symbols = symbols

    def resolve_symbols(self, refs: list[SymbolRef]) -> list[SymbolResolution]:
        resolutions: list[SymbolResolution] = []
        for ref in refs:
            raw = self._symbols.get(ref.name)
            if raw is None:
                resolutions.append(
                    SymbolResolution(ref=ref, status="unresolved", reason="symbol not found")
                )
                continue
            symbol_type = str(raw.get("type", "unknown"))
            if ref.expected_type and ref.expected_type != symbol_type:
                resolutions.append(
                    SymbolResolution(
                        ref=ref,
                        status="unresolved",
                        reason=f"expected {ref.expected_type}, found {symbol_type}",
                    )
                )
                continue
            resolutions.append(
                SymbolResolution(
                    ref=ref,
                    status="resolved",
                    symbols=[
                        Symbol(
                            name=ref.name,
                            symbol_type=symbol_type,
                            metadata={key: value for key, value in raw.items() if key != "type"},
                        )
                    ],
                )
            )
        return resolutions

    def validate_binding(self, binding: SymbolBinding) -> ValidationResult:
        raw = self._symbols.get(binding.symbol)
        if raw is None:
            return ValidationResult(valid=False, reason="binding symbol not found")
        symbol_type = str(raw.get("type", "unknown"))
        if symbol_type != binding.symbol_type:
            return ValidationResult(
                valid=False,
                reason=f"binding type mismatch: expected {binding.symbol_type}, found {symbol_type}",
            )
        return ValidationResult(valid=True)

    def available_evidence(self, symbols: list[Symbol]) -> list[EvidenceCapability]:
        if not symbols:
            return []
        return [
            EvidenceCapability(
                evidence_level=EvidenceLevel.STATICALLY_RESOLVED,
                description="Symbol exists in the generic static symbol table.",
            )
        ]

    def generate_tasks(self, ir: RequirementIR) -> list[VerificationTask]:
        return [
            VerificationTask(
                id="C1",
                backend="core_smt",
                description=f"SMT consistency and supported-claim check for {ir.requirement_id}.",
                payload={"requirement_id": ir.requirement_id, "claim_kind": ir.claim.kind},
            )
        ]

    def collect_evidence(self, task_results: list[object]) -> list[object]:
        return task_results


def default_generic_adapter() -> GenericAdapter:
    return GenericAdapter(
        {
            "operation": {"type": "action"},
            "actor": {"type": "principal"},
            "authorized": {"type": "predicate"},
            "state_change": {"type": "state_transition"},
            "operation_status": {"type": "state"},
            "counter": {"type": "quantity"},
            "limit": {"type": "quantity"},
        }
    )
