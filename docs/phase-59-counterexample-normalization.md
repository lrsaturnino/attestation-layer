# Phase 59 - Counterexample Normalization

## Status

Implemented.

## Purpose

Normalize backend counterexamples into a stable report that downstream refusal,
benchmark, and PR-rendering paths can consume.

## Implementation

- `nlreq.counterexample_normalization`
- `nlreq counterexample-normalize`
- `schemas/counterexample-normalization-report.schema.json`

Formal backend responses with `counterexample` status are converted into
normalized counterexample records with backend, source hash, steps, excerpt, and
metadata.

## Exit Criteria

- Backend counterexamples are hash-linked to their source response.
- Empty counterexample details still produce an explicit backend counterexample
  summary.
- Non-counterexample responses produce `result: none`.
