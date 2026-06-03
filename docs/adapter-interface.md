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

## Source Adapter v2 Capability Contract

Production source adapters also expose:

```text
SourceLanguageAdapter:
  parse_manifest(path) -> SourceManifest
  resolve_symbol(ref, manifest) -> SourceSymbolResolution
  validate_binding(binding) -> SourceBindingValidation
  call_graph(manifest) -> SourceCallGraph
  present_to_llm(refs, manifest) -> CodePresentation
  extract_traces(manifest) -> NormalizedTraceArtifact
  capability_contract() -> AdapterCapabilityContract
```

The v2 contract is schema-backed by
`schemas/adapter-capability-contract.schema.json`. It records:

- `interface_version=2.0`,
- adapter identity, language, runtime, and ecosystem,
- capability claims such as `static_symbol_resolution`, `call_graph`,
  `code_presentation`, and `normalized_trace`,
- evidence labels backed by those claims,
- supported symbol types and trace runtimes,
- and limitations with closure effects.

Certification can require capability ids:

```bash
uv run nlreq adapter-certify \
  --language go \
  --manifest source-manifest.json \
  --symbol Redeem \
  --required-capability static_symbol_resolution \
  --required-capability normalized_trace
```

## Conformance

An adapter is valid only if it passes the conformance suite. The suite verifies that the adapter:

- implements every interface method,
- returns stable symbol-resolution results for the same input,
- distinguishes unresolved, ambiguous, and resolved symbols,
- reports evidence capabilities honestly,
- produces verification tasks in the core task schema,
- and returns evidence in the core evidence schema.

Phase 0 provides a generic static-symbol adapter as the reference implementation. In code,
future adapters should run `nlreq.conformance.assert_adapter_conforms` with an
adapter-specific fixture before their evidence is allowed to satisfy gates.

The CLI command `nlreq conformance` runs the suite against the generic adapter.

For production source adapters, `nlreq adapter-capabilities` emits the v2
capability contract and `nlreq adapter-certify` emits a v2 certification report.
Certification is contract evidence. It is not proof that the target program
satisfies a requirement.
