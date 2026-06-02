# Phase 76 - Benchmark Evaluation

## Status

Implemented as a release metrics layer over the existing corpus format.

## Purpose

Track public evaluation metrics that matter for release claims, especially false
closure.

## Implementation

- `nlreq.benchmark_reporting`
- `nlreq benchmark-evaluate`
- `schemas/benchmark-evaluation-report.schema.json`

The evaluation report includes category counts, closure rate, false-closure rate,
false-refusal rate, runtime, and budget pass/fail status.

## Exit Criteria

- False closure can be budgeted at zero.
- Corpus tags produce category counts.
- Benchmark evaluation preserves the base benchmark report hash.
