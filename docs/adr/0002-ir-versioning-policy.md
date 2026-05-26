# ADR 0002: IR Versioning Policy

## Status

Accepted

## Context

Requirement packages must remain auditable after the IR schema evolves. Silent upgrades would make old evidence ambiguous because the checked artifact would no longer match the representation used by current tooling.

## Decision

Every IR document includes `ir_version`. Phase 0 starts at `0.1`.

- Patch versions may add optional fields only.
- Minor versions may add claim kinds or evidence fields.
- Existing packages are never silently upgraded.
- Migration commands must preserve the old IR hash, migration tool version, and migration diff.
- Validators reject unsupported `ir_version` values.

## Consequences

Schema evolution requires explicit migration work, but old packages remain reproducible and auditable.
