# ADR 0024: Verification-Grade NormalizedTrace Schema

## Status

Proposed

## Context

The existing `NormalizedTraceArtifact` supports Phase 11 runtime trace
validation. It records trace id, adapter id, source hash, events, and metadata.
Events record timestamp, actor, action, pre-state, post-state, and metadata.

GAP-C3 requires a verification-grade trace shape for source-language adapters.
Future Solidity, Go, Python, or other adapters need a common projection target
for execution traces even when their native trace semantics differ.

## Decision

Extend the existing trace schema in a backward-compatible way.

`NormalizedTrace` keeps:

- trace id;
- adapter id;
- source hash;
- events;
- metadata.

It also gains optional:

- language;
- runtime.

`TraceEvent` keeps:

- event id;
- timestamp;
- actor;
- action;
- pre-state;
- post-state;
- metadata.

It also gains optional:

- causal predecessor event id;
- language override;
- runtime override.

Adapters must not fabricate missing trace data. Lossy normalization is recorded
in metadata, including omitted fields, redaction, sampling, clock source, and
runtime-specific limitations when applicable.

## Consequences

Existing trace artifacts remain valid because new fields are optional. Future
source adapters can emit richer traces without inventing per-language artifact
formats.

The tradeoff is that `NormalizedTrace` is still a projection, not a complete
native trace. Code/spec trace alignment in Phase 27 must account for lossy
normalization rather than treating every omitted field as proof of absence.
