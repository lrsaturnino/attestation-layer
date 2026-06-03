# ADR 0149: Go Adapter Graduation

## Status

Accepted

## Context

The adapter abstraction needs a compiled service ecosystem that is not shaped
like Solidity or JavaScript. Go is a good pressure test because it has package
structure, call graphs, runtime traces, and common OpenTelemetry integration.

## Decision

Graduate `GoSourceAdapter` under the v2 adapter contract.

The adapter declares `ecosystem=compiled_service`, resolves Go functions,
methods, and types, emits static call graph edges through `SourceCallGraph`,
records package metadata, and consumes normalized runtime/trace or
OpenTelemetry artifacts. Build tags, generated files, and generic
instantiation are explicit review-depth limitations.

Specula-style extraction is not claimed as adapter proof. It remains a
candidate-generation path that requires human review and trace grounding.

## Consequences

Go can be certified with static and trace-backed evidence through the same
surface used by other ecosystems. Package graph facts become adapter metadata,
not requirement IR semantics.

The tradeoff is that the bundled adapter slice remains lexical. Deeper gopls or
go-callgraph integration can replace the extraction internals without changing
the core contract.

## Validation

Group 13 tests verify Go call graph edges, package metadata, normalized trace
consumption, and production-candidate certification.
