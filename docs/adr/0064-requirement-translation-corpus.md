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

## Consequences

Translator changes can be evaluated quickly and independently. The seed corpus
is small and must grow before beta release claims.
