# ADR 0069: S And R Composition Semantics And Invariant Preservation

## Status

Proposed

## Context

Requirement `R` must be checked against reviewed system specs `S`, not only
against itself.

## Decision

Represent composition as a report over requirement hash, lowered hash, impact
hash, system spec hashes, and backend result hash.

## Consequences

Composition evidence is reproducible and can distinguish valid,
counterexample, timeout, unsupported, and invalid outcomes.

## Validation

The composition model is schema-backed and builds from system consistency
results.
