# Phase 76 - Benchmark Evaluation

## Status

Implemented as a release metrics layer over the benchmark corpus format.

## Purpose

Move from illustrative seed cases to release-accountability metrics. The system
must track when it closes a case that should not close, refuses a case that
should close, regresses by category, or exceeds runtime expectations.

## Scope

This phase does not replace the corpus format from phase 45. It adds an
evaluation report that consumes the existing corpus and observed results, then
derives release metrics and configurable budgets.

## Data Contracts

`BenchmarkEvaluationReport` records:

- corpus id, version, total case count, and pass/fail result;
- metrics with values, optional budgets, and per-metric pass flags;
- tag-based category counts;
- hash of the base benchmark run report;
- input hashes for corpus and results.

The implemented schema is `schemas/benchmark-evaluation-report.schema.json`.

## API And CLI

Implementation module: `nlreq.benchmark_reporting`.

Core function:

- `build_benchmark_evaluation_report(...)` computes closure rate,
  false-closure rate, false-refusal rate, total runtime, category counts, and
  budget status.

CLI:

- `nlreq benchmark-evaluate --corpus <corpus> --results <results>`
- `nlreq benchmark-evaluate ... --false-closure-budget 0`

## Evaluation Rules

- False closure is any observed `accepted` decision for a case whose expected
  decision is not `accepted`.
- False refusal is any observed `refused` decision for a case expected to be
  `accepted`.
- The false-closure budget can be zero for hard-gated release claims.
- Category counts are derived from corpus tags so regressions can be attributed
  to translation, formal checking, traces, adapters, drift, backend
  disagreement, or other public benchmark dimensions.
- The report preserves the hash of the base benchmark run report so release
  metrics remain tied to the lower-level observations.

## Verification

`tests/test_milestone_group6.py` verifies category counting and false-closure
budget failure.

## Exit Criteria

- False closure is measured and budgeted explicitly.
- Benchmark reports can distinguish category regressions.
- Runtime is included in release metrics.
- Public docs can explain what the benchmark does and does not prove.
