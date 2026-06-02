# ADR 0065: Apalache Production Backend And Evidence Mapping

## Status

Proposed

## Context

The roadmap requires a real symbolic bounded-checking path. The existing TLA
runner can execute commands, but Apalache needs an explicit backend identity and
evidence mapping.

## Decision

Introduce `ApalacheBackend` with backend ID `apalache`. It lowers IR v2 to TLA,
writes artifacts, invokes a command through the model-checker runner, and maps
valid/counterexample outcomes to `BOUNDED_CHECKED`. Missing tools map to
`unsupported` with `tool_missing: true`.

## Consequences

Apalache can be used in CI when installed, while local environments without the
tool do not get false success. Bounded evidence remains bounded.

## Validation

Tests cover backend registration and missing-tool refusal semantics.
