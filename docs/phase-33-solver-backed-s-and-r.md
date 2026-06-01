# Phase 33 Solver-Backed `S and R`

Phase 33 adds a solver-backed system consistency path. It keeps the existing
deterministic marker checker available, but introduces a real checker execution
over a composed artifact built from the requirement `R` and the selected fresh
reviewed system specs `S`.

## Purpose

The phase lets the Attestation Layer say:

```text
Fresh reviewed system specs were selected for the impacted modules, composed
with R, checked by a local model checker under recorded bounds, and returned as
valid, counterexample, timeout, unsupported, or invalid.
```

It does not say:

```text
All system specs are semantically complete.
All TLA+ system modules are imported with full TLC semantics.
The result is inductive proof.
```

## Implementation Scope

Phase 33 implementation includes:

- solver-backed system consistency function;
- fresh/reviewed spec gate before checker execution;
- composed TLA+ module and config artifact;
- spec hash recording for the selected `S` context;
- checker execution through the Phase 30 runner;
- backend result mapping with `BOUNDED_CHECKED` only on valid bounded runs;
- normalized counterexample objects with runner metadata;
- CLI command for `solver-system-consistency-check`;
- tests for valid execution, counterexample preservation, stale-spec blocking,
  and CLI output.

## Evidence Semantics

The solver-backed checker emits `BOUNDED_CHECKED` when the composed artifact
checks valid under recorded bounds. Counterexample, timeout, unsupported, and
invalid outcomes never approve.

The old marker-based checker remains as a deterministic boundary path, but the
new solver-backed path is the one that future proof closure and delta extraction
should prefer for system compatibility evidence.

## Success Criterion

Phase 33 succeeds when:

- system compatibility is backed by a real checker run;
- stale, missing, or unreviewed specs block before execution;
- counterexamples are preserved as actionable artifacts;
- result metadata records selected specs, hashes, command, checker id, runner
  result hash, bounds, and emitted artifacts.

## Boundary

This phase does not solve full semantic import of arbitrary TLA+ system specs.
The composed artifact records and checks the selected `S` context through the
MVP formal path. Stronger composition semantics and richer counterexample
projection remain later work.
