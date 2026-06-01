# ADR 0035: Multi-Backend Proof Object

## Status

Proposed

## Context

By Phase 28 the system can parse compositional requirements, lower selected
forms, check `S ∧ R`, evaluate spec coverage, and align traces. These artifacts
need one closure record so downstream tools do not interpret individual checks
in isolation.

## Decision

Introduce a versioned proof object with:

- a dispatch plan from compositional IR proof fragments to backend ids;
- premise-level discharge records;
- normalized backend results;
- evidence producer mapping;
- spec coverage and trace-alignment status;
- closure blockers;
- and reproducibility input hashes.

The first dispatch policy routes proof fragments to `system_checker` and
requires `CONSISTENCY_CHECKED`. Future backend policies may route specific
fragments to SMT, model checking, or proof-assistant producers.

## Consequences

The proof object becomes the downstream closure unit. Individual backend
results remain useful evidence, but they do not close a requirement unless the
aggregated proof object is closed.
