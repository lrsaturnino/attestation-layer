# ADR 0134: Apalache Execution And Result Normalization

## Status

Accepted

## Context

Apalache is the first production symbolic bounded-checking backend. The project
must retain enough metadata to replay and audit a run while avoiding false
success when Apalache is missing, times out, or fails to parse a model.

## Decision

Use `ApalacheBackend` in `nlreq.formal_backend` as the Apalache execution
boundary. It projects IR to TLA+, writes module/config artifacts, runs through
`nlreq.model_checker_runner`, and normalizes the result into
`FormalBackendResponse`.

Apalache responses record `evidence_flavor: symbolic_bounded`.

## Outcome Mapping

- success markers -> `valid`;
- violation/counterexample markers -> `counterexample`;
- timeout markers or process timeout -> `timeout`;
- missing executable -> `unsupported`;
- unclassified non-zero tool failures -> `invalid`.

`valid` and `counterexample` can carry `BOUNDED_CHECKED`. No Apalache result can
claim `PROVEN_INDUCTIVE`.

## Consequences

Release gates can distinguish symbolic bounded evidence from explicit-state and
proof-assistant evidence. Missing local tools no longer masquerade as failed
proofs or successful closure.

## Validation

Group 11 tests exercise Apalache through deterministic fixture commands and
assert symbolic bounded metadata, timeout classification, and missing-tool
handling.
