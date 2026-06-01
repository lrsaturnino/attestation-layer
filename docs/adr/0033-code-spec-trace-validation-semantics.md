# ADR 0033: Code/Spec Trace Validation Semantics

## Status

Proposed

## Context

The existing trace validator checks normalized runtime traces against supported
requirement shapes. The roadmap also needs code/spec trace alignment: observed
code traces should be classified against the requirement/spec context.

## Decision

Introduce a trace alignment report.

Trace alignment statuses are:

- `aligned` when the requirement action is observed and relevant specs are
  fresh;
- `violating` when a trace declares an alignment violation marker;
- `uncovered` when the requirement action is absent;
- `unsupported` when specs are missing, stale, or unreviewed.

These statuses are review/gating context, not proof.

## Consequences

Trace alignment becomes explicit without conflating observations with formal
verification.
