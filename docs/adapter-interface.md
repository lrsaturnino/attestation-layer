# Adapter Interface

Adapters connect the system-neutral NL Requirement Attestation Layer core to a concrete target ecosystem.

The core owns:

- controlled-language parsing,
- IR validation,
- package layout,
- evidence levels,
- status decision,
- and generic verification task schemas.

Adapters own:

- target symbol resolution,
- binding validation,
- target capability reporting,
- target-specific task generation,
- and evidence collection.

## Interface

```text
Adapter:
  adapter_id: string
  target_kind: string

  resolve_symbols(refs: SymbolRef[]) -> SymbolResolution[]
  validate_binding(binding: Binding) -> ValidationResult
  available_evidence(symbols: Symbol[]) -> EvidenceCapability[]
  generate_tasks(ir: RequirementIR) -> VerificationTask[]
  collect_evidence(task_results: TaskResult[]) -> BackendEvidence[]
```

## Conformance

An adapter is valid only if it passes the conformance suite. The suite verifies that the adapter:

- implements every interface method,
- returns stable symbol-resolution results for the same input,
- distinguishes unresolved, ambiguous, and resolved symbols,
- reports evidence capabilities honestly,
- produces verification tasks in the core task schema,
- and returns evidence in the core evidence schema.

Phase 0 provides a generic static-symbol adapter as the reference implementation.
