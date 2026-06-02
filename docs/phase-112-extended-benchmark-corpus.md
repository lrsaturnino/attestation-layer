# Phase 112 Extended Benchmark Corpus

Phase 112 upgrades release benchmarks from generic closure rate tracking to
dimension-specific release evidence.

## Purpose

The conclusion roadmap warns against demo success being mistaken for broad
correctness. The extended benchmark report requires public release dimensions
that cover translation quality, formal closure, trace grounding, adapter
evidence, action gating, error rates, runtime, and counterexample quality.

## Contracts

Implementation:

- `ExtendedBenchmarkDimensionResult`
- `ExtendedBenchmarkEvaluationReport`
- `build_extended_benchmark_evaluation_report`
- CLI command `nlreq benchmark-extended`

Schema:

- `schemas/extended-benchmark-evaluation-report.schema.json`

## Required Dimensions

The default required dimensions are:

- `semantic_translation`
- `formal_system`
- `trace_grounding`
- `adapter_evidence`
- `release_gate`
- `false_closure`
- `false_refusal`
- `runtime`
- `counterexample_quality`

Each dimension records total cases, passed cases, failed cases, score,
threshold, pass/fail status, and findings.

## Decision Rules

The extended benchmark passes only when:

- the base `BenchmarkEvaluationReport` passed;
- every required dimension is present;
- every dimension passes its configured release threshold.

Missing dimensions fail the report even when the base benchmark passed.

## Exit Criteria

- Required release dimensions are machine-readable.
- Threshold failures produce findings.
- Missing dimensions fail release readiness.
- Tests cover passing, missing-dimension, and failed-threshold cases.
