# ADR 0135: TLC Execution And Result Normalization

## Status

Accepted

## Context

TLC provides an explicit-state TLA+ checking path that is independent from
Apalache. Its results must normalize into the same backend response shape while
remaining distinguishable from symbolic bounded evidence.

## Decision

Use `TlcProductionBackend` in `nlreq.formal_backend` as the TLC execution
boundary. TLC responses record `evidence_flavor: explicit_state_bounded`.

TLC runs through the shared model-checker runner so command metadata, output
hashes, timeout behavior, artifact hashes, and bounded tails are retained.

## Outcome Mapping

- "No error has been found" and equivalent success markers -> `valid`;
- invariant, property, assertion, or counterexample markers -> `counterexample`;
- timeout markers or process timeout -> `timeout`;
- missing executable -> `unsupported`;
- unclassified non-zero tool failures -> `invalid`.

## Consequences

Backend agreement can compare Apalache and TLC over the same requirement while
preserving evidence flavor. Explicit-state evidence remains bounded evidence.

## Validation

Group 11 tests verify TLC counterexample parsing and evidence-flavor metadata.
