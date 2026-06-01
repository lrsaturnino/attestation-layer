# Phase 21 Source LanguageAdapter Boundary

Phase 21 defines how real source code enters the Attestation Layer without
binding the core to Solidity, Go, Python, or any one runtime.

This phase introduces the source-language adapter contract and tightens
`NormalizedTrace` for verification-grade traces. It does not implement a real
Solidity, Go, or other production source adapter.

## Purpose

The phase lets the Attestation Layer say:

```text
A source adapter has a stable interface for symbol resolution, call graphs,
binding validation, code presentation, trace extraction, and manifest parsing;
and execution traces have the fields needed for cross-language reasoning.
```

It does not say:

```text
Solidity or Go source analysis is implemented.
Impact analysis is complete.
Spec coverage is checked.
Traces are aligned with system spec S.
```

## Why This Comes After Phase 20

Phase 19 defined the compositional IR. Phase 20 defined the formal backend edge.
Phase 21 defines the code edge. Later phases can combine these edges for impact
analysis, source verticals, system specs, and trace alignment.

## Source Adapter Interface

The source adapter family is separate from the existing declaration-level
`Adapter` family. Declaration adapters resolve reviewed contracts and schemas.
Source adapters reason about implementation code.

The first interface is:

```text
SourceLanguageAdapter:
  adapter_id
  language
  runtime

  resolve_symbol(ref) -> SourceSymbolResolution
  call_graph(manifest) -> SourceCallGraph
  validate_binding(binding) -> SourceBindingValidation
  present_to_llm(refs) -> CodePresentation
  extract_traces(manifest) -> NormalizedTraceArtifact
  parse_manifest(path) -> SourceManifest
```

Phase 21 includes a null adapter so the interface can be exercised end to end
without claiming language support.

## Manifest Shape

The first manifest binds source modules to files, symbols, optional spec ids,
and optional trace sources:

```json
{
  "schema_version": "0.1",
  "adapter": "null-source",
  "language": "null",
  "modules": [
    {
      "module_id": "example",
      "path": "src/example.null",
      "symbols": ["operation"],
      "spec_refs": ["spec:example"],
      "trace_sources": []
    }
  ]
}
```

The manifest is intentionally small. Phase 24 can extend it when the first real
source vertical chooses concrete tooling.

## Verification-Grade Trace Fields

`NormalizedTrace` and `TraceEvent` remain backward compatible but gain optional
fields needed by source adapters:

- trace `language`;
- trace `runtime`;
- trace `source_hash`;
- event timestamp;
- event actor;
- event action;
- event pre-state;
- event post-state;
- event causal predecessor;
- event language/runtime override;
- event source span or symbol metadata through `metadata`.

Lossy normalization must be explicit. If a source runtime cannot provide a
field, the adapter records the omission in metadata rather than fabricating it.

## Relationship To Existing Trace Validation

The Phase 11 runtime-trace validator already consumes `NormalizedTraceArtifact`
for requirement-shaped trace checks. Phase 21 extends that artifact for future
source adapters but keeps existing trace-validation behavior compatible.

Code/spec trace alignment belongs to Phase 27.

## Implementation Scope

Phase 21 implementation should include:

- source adapter protocol and Pydantic artifact models;
- null source adapter implementation;
- source manifest JSON schema;
- optional verification trace fields on existing trace models;
- tests for null adapter conformance behavior;
- tests that old trace artifacts still validate;
- tests for causal predecessor and language/runtime fields;
- documentation for declaration-adapter coexistence.

## Evidence Semantics

Phase 21 adds no new approving evidence.

The null adapter cannot satisfy implementation evidence. It may produce empty
call graphs and empty trace artifacts for interface testing only. Real evidence
requires a future source adapter and downstream checks.

## Success Criterion

Phase 21 succeeds when:

- the source adapter interface covers symbol resolution, call graph, binding
  validation, code presentation, trace extraction, and manifest parsing;
- a null adapter exercises the interface end to end;
- trace schema records timestamp, actor, action, pre/post state, causal
  predecessor, language/runtime, source hash, and metadata;
- existing runtime trace validation remains compatible;
- and source adapters remain separate from declaration adapters.

## Boundary

This phase is not the first real source vertical, impact analysis, spec coverage,
Specula integration, code/spec trace alignment, or system consistency checking.
