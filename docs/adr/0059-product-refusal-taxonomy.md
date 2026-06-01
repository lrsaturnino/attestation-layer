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

Operational rules:

- Refusal codes are stable product API values.
- Unknown evidence remains `unknown` and does not become refusal by wording.
- Every finding must explain source span availability.
- Stage-level blockers may use `no_span_reason` until provenance can attach a
  fragment span.
- Markdown renderers must consume the JSON report object rather than
  reclassifying blockers.

Rejected alternatives:

- Free-form blocker strings were rejected because they cannot be benchmarked or
  routed to owners.
- A single failure code was rejected because intake, translation, formal,
  coverage, trace, producer, and closure failures require different next
  actions.

Validation:

- Gate blockers map through deterministic stage/status rules.
- Benchmark cases can assert expected refusal codes.

## Consequences

Refusals become actionable and benchmarkable. Unknown results are not blurred
into failed checks.
