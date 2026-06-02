# Phase 58 - TLA Projection Semantics v2

## Status

Implemented.

## Purpose

Make IR-to-TLA lowering auditable as a semantic projection report instead of an
opaque generated file.

## Implementation

- `nlreq.tla_projection_v2`
- `nlreq tla-projection-v2`
- `schemas/tla-projection-v2-report.schema.json`

The report records projected and unsupported fragments, temporal bounds, input
hashes, and rules stating that generated TLA is not evidence until a backend
executes it.

## Exit Criteria

- Supported DSL v2 fragments lower to a TLA artifact and projection report.
- Unsupported fragments remain explicit diagnostics.
- Temporal bounds are represented as bounded checking metadata, not unbounded
  proof claims.
