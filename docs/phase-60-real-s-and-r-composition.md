# Phase 60 - Real S And R Composition

## Status

Implemented as a composition report over existing deterministic and solver-backed
system consistency checks.

## Purpose

Represent the checked conjunction of reviewed system specs `S` and requirement
`R` as an auditable artifact.

## Implementation

- `nlreq.system_composition`
- `schemas/s-and-r-composition-report.schema.json`
- Existing `system-consistency-check-fixture` (offline marker check)
- Existing `solver-system-consistency-check`

The composition report records requirement hash, lowered artifact hash, impact
hash, spec hashes, backend result hash, and the resulting valid, counterexample,
timeout, unsupported, or invalid status.

## Exit Criteria

- Composition cannot hide draft or stale specs.
- The report distinguishes bounded/backend-scoped evidence from proof.
- Counterexample and timeout outcomes remain non-approving.
