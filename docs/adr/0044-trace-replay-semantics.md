# ADR 0044: Trace Replay Semantics

## Status

Proposed

## Context

Phase 27 aligned normalized traces by checking whether the requirement action
appeared. That was enough for a coverage-style gate, but not enough to ground a
formalized requirement against observed behavior. The roadmap requires replay of
real traces against `R` and selected `S` context, with explicit limits for lossy
normalization.

## Decision

Introduce a trace replay report.

The replay engine consumes:

- compositional requirement IR;
- normalized trace artifact;
- spec coverage report.

It refuses replay as unsupported when spec coverage failed. Otherwise it finds
the requirement action and replays supported obligations in order:

- required event after the action;
- numeric state comparisons over event post-state fragments.

Each trace receives one of four statuses:

- `satisfied`;
- `violating`;
- `uncovered`;
- `unsupported`.

Violations include event ids, expected fragments, actual fragments, and
counterexample metadata. Lossy-normalization warnings from trace or event
metadata are preserved in the observation.

## Consequences

Trace grounding can now block proof closure on real behavioral mismatches
instead of only reporting action-name alignment. The evidence remains contextual:
trace replay does not produce formal proof and cannot emit `PROVEN_INDUCTIVE`.

The first replay semantics are deliberately limited to the DSL v2 MVP fragment.
Future phases can add richer temporal windows, cross-trace state machines, and
adapter-specific replay semantics while preserving the satisfied/violating/
uncovered/unsupported contract.
