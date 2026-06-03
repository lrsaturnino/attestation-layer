# ADR 0186: Rust Or Java Adapter Production Hardening

## Status

Accepted

## Context

Phase 177 is part of milestone 18, Production Adapter And Trace Closure. The roadmap requires closure for second compiled ecosystem evidence without relying on shallow fixtures or implicit review assumptions.

## Decision

Represent the phase as a schema-backed real-evidence phase report. The required artifact types are: rust_or_java_adapter_selection, compiled_adapter_v3_report, compiled_call_graph_report, compiled_trace_producer_report. Each artifact must be accepted, reviewed, replayable, and explicitly marked as real evidence before the phase can pass.

## Alternatives Considered

- Treat generated fixtures as sufficient release evidence. Rejected because the final roadmap is specifically about hostile real-evidence closure.
- Keep the phase as prose-only documentation. Rejected because milestone aggregation and final gap assessment need machine-checkable blockers.

## Consequences

The release path becomes stricter: incomplete, unreviewed, blocked, or scaffold evidence blocks the phase instead of allowing a fixture-complete claim. The tradeoff is that projects must retain more evidence before claiming closure.

## Validation

`tests/test_milestone_groups_15_to_20.py` validates the phase through the real-evidence registry, milestone aggregation, and final Claude-conversation gap assessment.
