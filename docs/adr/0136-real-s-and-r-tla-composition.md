# ADR 0136: Real S And R TLA Composition

## Status

Accepted

## Context

The system must check requirement claim `R` against reviewed system spec `S`,
not only against itself. Earlier reports could hash a system-consistency result,
but release evidence needs composed artifact references, namespace policy, and
spec freshness blockers.

## Decision

Keep solver-backed composition in `nlreq.system_checker` and extend
`nlreq.system_composition.SandRCompositionReport` with:

- backend-checkable composed TLA/config artifact references;
- preserved invariant/property names;
- namespace policy;
- blockers for stale/unreviewed specs and non-approving backend outcomes.

The `nlreq s-and-r-composition` command packages requirement, lowered artifact,
impact, registry, and system-consistency inputs into one hash-bound report.

## Invariants

- Draft, stale, missing, and unreviewed specs block before backend execution.
- Existing spec hashes and requirement hashes are retained.
- Composition results can be valid, counterexample, timeout, unsupported, or
  invalid.
- Bounded composition remains bounded evidence unless a proof-producing backend
  separately proves it.

## Consequences

Release reports can inspect actual composed artifacts and cannot hide stale spec
state behind a backend status.

## Validation

Group 11 tests verify generated artifact references and blockers.
