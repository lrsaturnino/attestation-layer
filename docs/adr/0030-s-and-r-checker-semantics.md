# ADR 0030: `S ∧ R` Checker Semantics

## Status

Proposed

## Context

Phase 25 made system spec `S` addressable through a reviewed registry. Phase 23
made requirement `R` lowerable into a first formal artifact. The roadmap now
needs the checker boundary that composes `S` and `R` and returns normalized
states without overstating proof.

## Decision

Introduce a deterministic `S ∧ R` checker artifact and API.

The first checker consumes reviewed/fresh registry entries, affected module ids,
`RequirementIRV2`, and a lowered formal artifact. It returns a normalized
`BackendResult` and structured counterexamples where available.

Statuses are:

- `valid` when all selected specs are fresh/reviewed, lowering succeeded, and no
  checker marker indicates failure;
- `counterexample` when a selected spec declares a counterexample marker for the
  requirement;
- `timeout` when a selected spec declares a timeout marker;
- `unsupported` when specs are missing/stale/unreviewed or lowering refused.

This first implementation is a deterministic boundary, not full model checking.
Future phases may replace marker-backed execution with Apalache/TLC while
preserving the status semantics.

## Consequences

The project gets the core `S ∧ R` result shape and non-approving timeout/
unsupported semantics before full backend execution.

The tradeoff is limited checking strength. `CONSISTENCY_CHECKED` here means the
deterministic checker boundary completed; it is not bounded model checking or
inductive proof.
