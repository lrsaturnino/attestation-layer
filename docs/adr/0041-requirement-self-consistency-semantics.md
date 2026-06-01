# ADR 0041: Requirement Self-Consistency Semantics

## Status

Proposed

## Context

The roadmap requires each formalized requirement `R` to be checked before it is
composed with system specs `S`. Without this gate, an impossible or unsupported
requirement can create misleading `S and R` failures, or worse, pass through as
a proof-context artifact whose own contradiction was never isolated.

Phase 31 introduced a runnable TLA+ backend. Phase 32 uses that backend path,
while still allowing deterministic prechecks for contradictions that are cheaper
and clearer to report before tool execution.

## Decision

Introduce a requirement self-consistency report.

The report first runs deterministic checks for:

- impossible numeric comparisons over literal values;
- directly opposite fragments in conjunctions, such as a predicate and its
  negation or mutually exclusive comparisons.

If the deterministic precheck passes, the report builds a formal backend request
for `R` alone and records the backend response. Backend statuses are mapped as:

- `valid` -> self-consistency valid;
- `counterexample` -> contradiction;
- `unsupported` -> unsupported;
- `timeout` -> timeout;
- `tool_error` -> tool error.

Only a valid bounded backend run may carry `BOUNDED_CHECKED`. No
self-consistency result may emit `PROVEN_INDUCTIVE`.

## Consequences

Contradictions and unsupported fragments now fail before system composition.
The `S and R` checker can assume that incoming requirements have already passed
their own gate, and later delta extraction can distinguish requirement-local
fixes from system compatibility fixes.

The deterministic contradiction taxonomy is deliberately small. It prevents
obvious false progress, while preserving the need for real solver-backed checks
as the supported formal fragment grows.
