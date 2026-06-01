# Phase 35 Trace Replay Grounding

Phase 35 upgrades trace grounding from action-name alignment to semantic replay
over compositional requirement obligations. Runtime traces can now satisfy,
violate, leave uncovered, or be unsupported for the requirement under review.

## Purpose

The phase lets the Attestation Layer say:

```text
This trace was replayed against R, the relevant action and obligations were
observed, and any violation names the event ids plus expected and actual state
fragments.
```

It does not say:

```text
Trace observations are formal proof.
Lossy normalized traces are complete.
All temporal semantics are fully replayed.
```

## Implementation Scope

Phase 35 implementation includes:

- trace replay report model and schema;
- replay of DSL v2 action obligations against normalized trace events;
- status classification: satisfied, violating, uncovered, unsupported;
- event-id preservation for action, required event, and state comparison
  observations;
- expected/actual fragments for missing events and state mismatches;
- lossy-normalization warning propagation from traces and events;
- coverage gate integration so failed spec coverage blocks replay;
- CLI command for `trace-replay`;
- tests for satisfied traces, missing event violations, state mismatches,
  uncovered actions, coverage blocking, warnings, and CLI output.

## Evidence Semantics

Trace replay is proof context, not proof. A satisfied replay can support closure
as grounding context, but it never emits `PROVEN_INDUCTIVE` and does not replace
solver-backed formal checks.

Violating, uncovered, and unsupported replay statuses block closure unless a
future policy explicitly waives them.

## Success Criterion

Phase 35 succeeds when:

- real normalized traces replay against a compositional requirement;
- violations include event ids and expected/actual fragments;
- uncovered behavior blocks the replay report;
- lossy-normalization warnings remain visible;
- the report is schema-backed and CLI-addressable.

## Boundary

This phase handles the current DSL v2 MVP obligations. Rich temporal replay,
cross-trace causality, and adapter-specific state semantics remain later
extensions.
