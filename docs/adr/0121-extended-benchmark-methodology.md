# ADR 0121: Extended Benchmark Methodology

## Status

Accepted

## Context

The benchmark evaluation report tracks closure and false-closure metrics, but
the extended conclusion release must show coverage across translation, formal
checking, trace grounding, adapter evidence, release gating, error rates,
runtime, and counterexample quality.

## Decision

Add `ExtendedBenchmarkEvaluationReport` and dimension-level benchmark results.

The default required dimensions are:

- semantic translation;
- formal system closure;
- trace grounding;
- adapter evidence;
- release gate behavior;
- false closure;
- false refusal;
- runtime;
- counterexample quality.

Missing required dimensions or failed release thresholds block the extended
benchmark report.

## Rationale

Aggregate closure rate can hide important gaps. Dimension-level scoring makes
benchmark coverage and release thresholds explicit.

## Consequences

Positive:

- Release benchmarks cannot pass by testing only happy paths.
- Threshold failures are represented with findings.
- Public benchmark reports can grow by dimension.

Negative:

- Maintainers must curate benchmark labels and dimension scores.

## Validation

`tests/test_milestone_group9.py` verifies passing dimensions, missing dimension
failure, and threshold failure.
