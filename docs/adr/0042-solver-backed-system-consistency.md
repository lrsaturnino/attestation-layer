# ADR 0042: Solver-Backed System Consistency

## Status

Proposed

## Context

The Phase 26 system checker was intentionally marker-based. It proved the
registry, impact, freshness, and refusal boundaries, but it did not execute a
solver over a composition of system specs `S` and requirement `R`.

Phase 30 introduced the model-checker runner, Phase 31 introduced runnable TLA+
backend artifacts, and Phase 32 added requirement self-consistency. The next
step is a system consistency path that refuses stale or unreviewed specs before
execution, then checks a composed `S and R` artifact with reproducible bounds.

## Decision

Introduce a solver-backed system consistency function and CLI command.

The checker:

- selects specs through the existing impact and registry logic;
- blocks missing, stale, or unreviewed specs before execution;
- refuses if the requirement lowering is already refused;
- writes a composed TLA+ module and config;
- records selected spec ids and content hashes;
- executes the configured checker command through the model-checker runner;
- maps runner outcomes to `SystemConsistencyResult`;
- emits normalized `Counterexample` objects from runner counterexamples.

A valid run emits `BOUNDED_CHECKED`. Counterexample, timeout, unsupported, and
invalid outcomes emit no approving evidence.

## Consequences

System compatibility can now be backed by an actual checker run instead of a
deterministic marker. Proof closure can distinguish legacy
`CONSISTENCY_CHECKED` marker evidence from bounded solver-backed compatibility
evidence.

The MVP composition is conservative. It records the selected system context and
checks the requirement in a composed artifact, but does not yet import arbitrary
TLA+ modules with complete semantic linking. Later phases can strengthen the
composition contract without changing the refusal semantics introduced here.
