# ADR 0067: IR-To-TLA Projection Semantics

## Status

Proposed

## Context

Generated TLA must be auditable before model checkers consume it.

## Decision

Add a projection report that records projected fragments, unsupported fragments,
temporal bounds, input hashes, and semantic rules.

## Consequences

Lowering is no longer an opaque file-generation step. Unsupported fragments can
be benchmarked and refused consistently.

## Validation

`nlreq tla-projection` emits a schema-backed report.
