# ADR 0146: Trace Validation Closure Policy

## Status

Accepted

## Context

Trace validation must ground current code behavior without overstating trace
evidence as proof. It also must distinguish contradictions from missing
coverage, stale specs, lossy traces, and unsupported predicates.

## Decision

Add `TraceValidationGateReport` in `nlreq.trace_validation`.

Gate outcomes are:

- `satisfied`: trace predicate satisfied; evidence label is `trace_grounding`;
- `violation`: observed trace contradicts the requirement;
- `coverage_gap`: trace coverage or affected action is missing;
- `lossy`: trace is lossy under high-assurance policy;
- `stale`: freshness CI blocks grounding;
- `unsupported`: no supported trace predicate exists.

Only satisfied outcomes allow closure. Trace grounding is not formal proof.

## Consequences

Product refusal can distinguish "current behavior contradicts the requirement"
from "we do not have enough trace coverage" and "the spec is stale".

## Validation

Group 12 tests verify satisfied grounding, lossy blocking, stale blocking, and
CLI output.
