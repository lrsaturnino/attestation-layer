# ADR 0034: Spec Freshness Invariant And CI Thresholds

## Status

Proposed

## Context

System specs can drift from source code. Phase 25 records freshness, and Phase
27 needs a CI-facing threshold for when coverage is sufficient.

## Decision

Spec freshness is a gating invariant for covered modules.

Coverage reports compute a covered/total ratio over affected modules and compare
it to a threshold. Fresh reviewed specs count as covered. Missing, stale, and
unreviewed specs do not.

The first default threshold is 1.0 for affected modules.

## Consequences

CI can block requirements touching under-specified or stale modules while the
project still keeps extraction and proof closure in later phases.
