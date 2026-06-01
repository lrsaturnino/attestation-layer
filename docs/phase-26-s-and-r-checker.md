# Phase 26 `S ∧ R` Checker

Phase 26 introduces the first system-consistency checker shape: compose a new
requirement `R` with the relevant reviewed system specs `S`, return normalized
checker status, and never approve unsupported or timed-out checks.

This phase also adds the first requirement-set contradiction pass.

## Purpose

The phase lets the Attestation Layer say:

```text
Relevant system specs S were selected for affected modules, composed with a
lowered requirement R through a checker boundary, and the result was valid,
counterexample, timeout, or unsupported.
```

It does not say:

```text
Apalache integration is complete.
All TLA+ semantics are checked.
The proof object is closed.
Spec coverage and trace alignment are complete.
```

## Checker Semantics

The first checker is deterministic and conservative. It consumes:

- `RequirementIRV2`;
- lowered formal artifact;
- system spec registry;
- affected module ids.

It returns a `BackendResult` with:

- `valid`;
- `counterexample`;
- `timeout`;
- or `unsupported`.

Missing, stale, or unreviewed specs are unsupported. Refused lowering artifacts
are unsupported. Timeout markers are timeout. Counterexample markers are
counterexample. Otherwise the first deterministic checker returns valid for the
composed reviewed inputs.

## Requirement-Set Consistency

The first requirement-set check targets current flat `0.1` claims and detects
direct contradictory predicates across requirements, such as `approved(actor)`
and `not_approved(actor)` in the same checked set.

This is a first taxonomy slice, not the final ALICE-style contradiction system.

## Implementation Scope

Phase 26 implementation should include:

- system-consistency request/result models and schemas;
- deterministic `S ∧ R` checker boundary;
- counterexample and timeout semantics;
- unsupported handling for stale/missing specs and refused lowering;
- requirement-set contradiction report model and schema;
- tests for valid, counterexample, timeout, unsupported, and cross-requirement
  contradiction cases.

## Evidence Semantics

The first checker may produce `CONSISTENCY_CHECKED` for deterministic composition
results. It must not produce `BOUNDED_CHECKED` or `PROVEN_INDUCTIVE`.

Timeout and unsupported are non-approving states.

## Success Criterion

Phase 26 succeeds when:

- formal `R` can be composed with relevant reviewed `S`;
- checker returns valid, counterexample, timeout, or unsupported;
- counterexamples identify the relevant spec marker and requirement id;
- timeout and unsupported never approve;
- requirement-set contradictions are detected for the first supported scope.

## Boundary

This phase is not full Apalache/TLC execution from compositional IR, spec
coverage, Specula extraction, trace alignment, proof closure, or PR gating.
