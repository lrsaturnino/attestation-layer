# Phase 76 - Benchmark Corpus v2

## Status

Implemented as a v2 metrics layer over the existing corpus format.

## Purpose

Track public evaluation metrics that matter for release claims, especially false
closure.

## Implementation

- `nlreq.benchmark_v2`
- `nlreq benchmark-v2`
- `schemas/benchmark-v2-report.schema.json`

The v2 report includes category counts, closure rate, false-closure rate,
false-refusal rate, runtime, and budget pass/fail status.

## Exit Criteria

- False closure can be budgeted at zero.
- Corpus tags produce category counts.
- Benchmark v2 preserves the base benchmark report hash.
