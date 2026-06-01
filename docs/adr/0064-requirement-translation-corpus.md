# ADR 0064: Requirement Translation Corpus, Semantic Accuracy, And Clarification Metrics

## Status

Proposed

## Context

The verification benchmark measures gate outcomes. Translation quality needs a
separate corpus that can run without formal backends.

## Decision

Introduce `benchmarks/requirements-translation` with cases for controlled text,
ambiguous prose, incomplete or adversarial prose, expected IR fixtures,
expected clarification questions, and expected refusal codes.

Add a benchmark report with syntactic validity, semantic match, clarification
quality, refusal correctness, and runtime.

Operational rules:

- Corpus case IDs must be unique.
- Expected IR fixture paths must be corpus-root-relative.
- Accepted cases require semantic match.
- Clarification cases measure expected questions separately from accepted IR.
- Refusal cases measure expected stable refusal codes.

Rejected alternatives:

- Measuring translation only through full gate outcome was rejected because
  backend failures can hide translation regressions.
- A prose-only benchmark table was rejected because CI and public reporting need
  machine-readable cases and observations.

Validation:

- `nlreq benchmark-translation` emits a report with aggregate metrics and
  per-case observation statuses.
- Missing, outcome mismatch, semantic mismatch, clarification mismatch, and
  refusal mismatch are distinct.

## Consequences

Translator changes can be evaluated quickly and independently. The seed corpus
is small and must grow before beta release claims.
