# ADR 0080: Adapter Certification Levels And Conformance Suite

## Status

Proposed

## Context

Adapters need a stable public certification output.

## Decision

Introduce certification levels: `manifest_only`, `static_resolution`,
`trace_capable`, and `production_candidate`.

## Consequences

Adapters can be compared without pretending every adapter has equal depth.

## Validation

`nlreq adapter-certify` emits a schema-backed report.
