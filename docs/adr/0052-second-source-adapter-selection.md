# ADR 0052: Second Source Adapter Selection

## Status

Proposed

## Context

The agnostic wedge requires the requirement and proof spine to avoid depending
on one implementation language. Python provides the first real source adapter,
but a single ecosystem is not enough to validate the source-language boundary.

## Decision

Select JavaScript/TypeScript as the second production source ecosystem.

The JavaScript adapter must implement the same `SourceLanguageAdapter` protocol
as Python:

- parse a shared `SourceManifest`;
- resolve symbols into normalized source symbols;
- emit a normalized call graph;
- validate source bindings;
- present bounded snippets for review and LLM context;
- extract normalized traces.

Add a shared source-adapter conformance harness and require both Python and
JavaScript to pass it.

Language-specific extraction remains inside the adapter. The semantic IR and
proof closure APIs only consume normalized artifacts.

## Consequences

The source boundary is now exercised by two real ecosystems, making it harder
for Python-specific assumptions to leak into the proof model.

The initial JavaScript implementation is lexical and dependency-free. It is
stable for common top-level function, exported arrow function, and class
declarations, but it is not a full compiler frontend. A future parser-backed
implementation can improve precision without changing the artifact contract.
