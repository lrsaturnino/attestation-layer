# ADR 0072: Code-To-Spec Manifest v2 And Brownfield Coverage Semantics

## Status

Proposed

## Context

Brownfield gating needs a stable map from source modules to specs.

## Decision

Use the code-spec manifest as the module-to-source/spec/dependency map and use
drift plus freshness lockfiles to enforce coverage.

## Consequences

Coverage and freshness become reproducible from files and hashes.

## Validation

Spec drift tests cover changed source, missing source, and dependency
propagation.
