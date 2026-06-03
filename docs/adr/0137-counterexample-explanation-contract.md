# ADR 0137: Counterexample Explanation Contract

## Status

Accepted

## Context

Formal backend failures need to be actionable. A raw model-checker excerpt is
not enough for product refusal, review, or PR feedback. The system needs a
stable JSON and Markdown explanation contract.

## Decision

Add `CounterexampleExplanationReport` in
`nlreq.counterexample_normalization`.

The report is built from a normalized counterexample report, optional formal
claim, and optional backend responses. It records backend, violated property,
retained bounds, shortest known trace steps, source mappings, next actions, and
Markdown text derived from the JSON report.

## Invariants

- No counterexamples produce `result: none`.
- Missing formal claim does not block explanation, but source mappings are
  absent.
- Missing backend response does not block explanation, but backend bounds are
  absent.
- Markdown is generated from structured fields.

## Consequences

Counterexample quality can be benchmarked over structured fields, and refusal
reports can present backend failures without hand-written interpretation.

## Validation

Group 11 tests verify source-span mapping and Markdown rendering.
