# ADR 0142: Spec Freshness And Drift CI

## Status

Accepted

## Context

Formal checks are misleading when the spec was validated against old source or
when the spec file itself changed after validation. Freshness must be enforced
as a CI gate, not only reported as metadata.

## Decision

Add timestamped freshness lockfiles and CI drift reports in
`nlreq.spec_freshness`.

`SpecFreshnessLockfileV2` records source hashes, spec hashes, dependency module
ids, manifest-entry hash, validation timestamp, and optional validation artifact
hashes. `SpecFreshnessDriftCiReport` blocks changed source hashes, changed spec
hashes, missing locks, missing files, expired validation age, and propagated
dependency drift.

## Consequences

Changing source or formal specs invalidates brownfield closure until validation
reruns and a new lock is committed. Release gates can map freshness blockers to
stale-spec refusal.

## Validation

Group 12 tests verify spec hash drift and validation age blockers.
