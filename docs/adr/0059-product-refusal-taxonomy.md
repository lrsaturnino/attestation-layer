# ADR 0059: Product Refusal Taxonomy, Source-Span Mapping, And Iteration Loop

## Status

Proposed

## Context

Current reports expose blockers, but product users need stable codes, owners,
and next actions.

## Decision

Introduce `ProductRefusalReport` with stable `NLR-*` codes, refused versus
unknown category, source spans or no-span reasons, next actions, and likely
owner.

The end-to-end gate can emit Markdown from the same report shape used for JSON.

## Consequences

Refusals become actionable and benchmarkable. Unknown results are not blurred
into failed checks.
