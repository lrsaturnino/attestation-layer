# Phase 43 Second Real Source Adapter

Phase 43 adds JavaScript/TypeScript source support as a second production source
language adapter alongside Python.

## Purpose

The phase lets the Attestation Layer say:

```text
The source-language boundary is operational for more than one real ecosystem,
and both adapters satisfy the same manifest, symbol, call graph, presentation,
and trace extraction contract.
```

It does not say:

```text
JavaScript parsing is a complete compiler frontend.
Adapter-specific facts may enter the semantic IR spine.
Cross-language evidence proves equivalent implementations by itself.
```

## Implementation Scope

Phase 43 implementation includes:

- JavaScript/TypeScript source language adapter;
- manifest parsing through the shared `SourceManifest` artifact;
- deterministic symbol resolution for functions, exported arrow functions, and
  classes;
- lexical call graph extraction across manifest modules;
- source binding validation;
- code presentation snippets for LLM/reviewer context;
- normalized trace extraction with adapter, language, and runtime grounding;
- CLI commands for `javascript-source-impact` and
  `javascript-source-impact-context`;
- shared source-adapter conformance harness used by Python and JavaScript;
- tests for resolution, call graph, bindings, traces, impact CLI, trace replay,
  proof closure, and cross-language wedge reporting.

## Adapter Contract

The JavaScript adapter uses the same `SourceLanguageAdapter` protocol as the
Python adapter. It keeps language-specific parsing behind the adapter boundary
and emits shared artifacts:

- `SourceSymbolResolution`;
- `SourceCallGraph`;
- `CodePresentation`;
- `NormalizedTraceArtifact`;
- impact analysis artifacts.

The adapter is intentionally deterministic and dependency-free. It recognizes
common top-level JavaScript and TypeScript declaration forms, then exposes
normalized source facts without adding language-specific fields to IR v2.

## Success Criterion

Phase 43 succeeds when:

- Python and JavaScript pass the same source-adapter conformance suite;
- JavaScript source impact can drive the generic coverage and trace replay
  path;
- a proof object and agnostic wedge can close over cross-language source
  evidence;
- adapter-specific details remain outside the semantic IR.

## Boundary

This phase adds a production adapter boundary, not a complete ECMAScript parser.
Future work can replace the lexical extraction internals with a typed parser
while preserving the same normalized artifacts.
