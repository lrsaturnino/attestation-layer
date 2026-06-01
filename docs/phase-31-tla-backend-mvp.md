# Phase 31 TLA+ Backend MVP

Phase 31 turns the TLA+ path from a lowering boundary into the first runnable
formal backend. It keeps the supported fragment narrow and records bounded
evidence only when a local checker command actually runs.

## Purpose

The phase lets the Attestation Layer say:

```text
This supported compositional IR fragment lowered to TLA+, emitted module/config
artifacts, ran through a checker command, and produced a normalized backend
result with recorded bounds.
```

It does not say:

```text
The TLA+ fragment is semantically complete for all IR nodes.
The result is inductive proof.
TLC or any other checker is always installed locally.
```

## Implementation Scope

Phase 31 implementation includes:

- a `tla-runner` formal backend id;
- runnable TLA+ skeleton support for the current DSL v2 MVP fragment;
- emitted `.tla` module and `.cfg` config artifacts;
- checker execution through the Phase 30 model-checker runner;
- command-token replacement for `{module}`, `{config}`, and `{module_name}`;
- backend result mapping for valid, counterexample, timeout, unsupported, and
  tool-error outcomes;
- bounded-evidence metadata with module/config hashes, runner result hash,
  command, checker id, and verification budget;
- CLI support through `formal-backend-check`;
- tests for valid runs, counterexamples, unsupported fragments, and CLI usage.

## Evidence Semantics

Successful `tla-runner` checks may emit `BOUNDED_CHECKED`. They never emit
`PROVEN_INDUCTIVE`.

The backend records the checker id and command that actually ran. The default
target is TLC-style execution, but tests and local deployments can pass an
explicit checker command while preserving the same metadata contract.

Unsupported lowering refuses before execution. Timeout and tool-error outcomes
remain non-approving backend statuses.

## Success Criterion

Phase 31 succeeds when:

- a supported DSL v2 fixture lowers to a runnable TLA+ module;
- `.tla` and `.cfg` artifacts are written deterministically;
- checker execution is delegated to the Phase 30 runner;
- valid and counterexample outcomes are represented as backend results;
- bounded runs record budgets and reproducibility metadata.

## Boundary

This phase is not full semantic equivalence from NL to TLA+, not solver-backed
system/spec composition, and not multi-backend agreement. It is the first real
formal target that later phases can compose with requirement self-consistency
and `S and R` checks.
