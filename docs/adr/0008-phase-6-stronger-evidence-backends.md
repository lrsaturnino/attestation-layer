# ADR 0008: Phase 6 Stronger Evidence Backends

## Status

Accepted

## Context

Phase 5 introduced scoped hard-gate enforcement over already-computed package
artifacts. Phase 6 needs stronger evidence sources without weakening the
existing status contract or treating generated artifacts as proof by default.

The first real adapter is the Python package adapter. It can already resolve
symbols, validate Python symbol shape, and run scoped pytest. The next slice
should prove that stronger adapter-generated evidence can be represented,
validated for freshness, and reported deterministically before adding broader
trace or model-checking backends.

## Decision

Phase 6 will introduce stronger evidence artifacts and a narrow generated
property-check backend for the Python package adapter.

The first Phase 6 slice will:

- define shared counterexample and normalized-trace schemas,
- add deterministic generated Python property tasks for supported claim shapes,
- record generated-test provenance and source hashes in task payloads,
- validate freshness by recomputing source-sensitive task inputs,
- report property failures as backend counterexamples,
- keep generated property evidence at `TEST_VALIDATED`,
- and keep `decide_status` unchanged.

The first generated property shape is intentionally narrow:

```text
if actor is approved
then operation must succeed
```

For Python packages, this maps only to a resolved zero-argument callable action
that returns `True` for the generated sample case. Other claim shapes remain
unsupported until they have explicit adapters, generators, and review rules.

Trace schemas may be introduced before trace validation is gateable. A backend
may claim `TRACE_VALIDATED` only when it points at a normalized trace artifact or
a documented adapter-specific exception.

## Consequences

Phase 6 gains stronger, source-fresh evidence without introducing broad
free-form test generation. Generated property checks are auditable task
artifacts, not hidden code. Counterexamples become structured backend output
that later tools can render in CI reports or agent retry payloads.

The system remains conservative: generated checks can satisfy only the evidence
level they actually exercise, and hard gates can opt into minimum evidence
requirements without changing package status calculation.
