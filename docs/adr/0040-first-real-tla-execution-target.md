# ADR 0040: First Real TLA+ Execution Target

## Status

Proposed

## Context

The Attestation Layer already had a TLA+ lowering skeleton and a reviewed TLA
model adapter, but the formal backend boundary did not yet execute a checker
over IR-lowered artifacts. The roadmap requires the first real formal target to
emit runnable artifacts, execute a local checker, and map the result to bounded
evidence semantics.

TLC is the narrowest first target because it can consume a `.tla` module and a
`.cfg` file with explicit-state semantics. The implementation still permits an
explicit local command so tests and deployments are not coupled to one installed
binary path.

## Decision

Introduce the `tla-runner` formal backend.

The backend:

- lowers supported compositional IR with the deterministic TLA+ lowerer;
- refuses unsupported fragments before execution;
- writes a module and config artifact;
- runs the selected checker command through the model-checker runner;
- records module/config hashes, command metadata, runner result hash, checker
  id, and budget details;
- maps runner outcomes into formal backend statuses.

The supported MVP fragment is intentionally small. Predicate and event nodes are
given deterministic total definitions so the generated module is runnable, while
the backend metadata makes clear that the result is bounded checker evidence,
not inductive proof or full semantic equivalence.

## Consequences

TLA+ becomes the first formal backend that can produce `BOUNDED_CHECKED` from an
actual checker run over emitted artifacts. Later phases can reuse this path for
requirement self-consistency and solver-backed system composition.

The MVP lowerer is deliberately conservative. Unsupported IR nodes refuse
before execution, and richer TLA+ semantics will need explicit translation rules
and agreement checks before they can increase assurance.
