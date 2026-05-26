from __future__ import annotations

from .adapter import Adapter
from .models import RequirementIR, SymbolBinding, SymbolRef


def refs_for_ir(ir: RequirementIR) -> list[SymbolRef]:
    refs: dict[str, SymbolRef] = {ir.claim.action: SymbolRef(name=ir.claim.action, expected_type="action")}
    for predicate in ir.claim.condition:
        for arg in predicate.args:
            if arg.kind == "identifier":
                refs.setdefault(str(arg.value), SymbolRef(name=str(arg.value)))
    if ir.claim.expected.target:
        refs.setdefault(ir.claim.expected.target, SymbolRef(name=ir.claim.expected.target))
    if ir.claim.expected.value and ir.claim.expected.value.kind == "identifier":
        refs.setdefault(
            str(ir.claim.expected.value.value),
            SymbolRef(name=str(ir.claim.expected.value.value)),
        )
    return list(refs.values())


def bind_ir(ir: RequirementIR, adapter: Adapter) -> tuple[RequirementIR, list[str]]:
    missing: list[str] = []
    bindings: dict[str, SymbolBinding] = {}
    for resolution in adapter.resolve_symbols(refs_for_ir(ir)):
        if resolution.status != "resolved" or not resolution.symbols:
            missing.append(resolution.ref.name)
            continue
        symbol = resolution.symbols[0]
        bindings[resolution.ref.name] = SymbolBinding(
            adapter=adapter.adapter_id,
            symbol=symbol.name,
            symbol_type=symbol.symbol_type,
            confidence="generic_symbol_table" if adapter.adapter_id == "generic" else "adapter_resolved",
        )
    return ir.model_copy(update={"bindings": bindings}), missing
