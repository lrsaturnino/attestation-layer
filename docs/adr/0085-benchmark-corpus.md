# ADR 0085: Benchmark Evaluation Methodology And Regression Policy

## Status

Accepted

## Context

The public seed corpus is useful for examples, but release claims need metrics
that identify false closure, false refusal, category regressions, and runtime.
False closure is especially important because accepting a requirement that
should have been blocked undermines the gate.

## Decision

Add `nlreq.benchmark_reporting` as an evaluation layer over the existing
benchmark corpus and observed-results format.

The evaluation report tracks:

- closure rate;
- false-closure rate;
- false-refusal rate;
- total runtime;
- tag-based category counts;
- per-metric budgets;
- hash of the base benchmark run report.

The CLI command `nlreq benchmark-evaluate` fails when the evaluation result is
failed, including when a configured false-closure budget is exceeded.

## Rationale

Keeping the corpus shape stable avoids churn while still giving release
certification a stronger metrics object. Category counts let benchmark owners
attribute regressions to translation, formal checking, trace replay, drift,
adapter behavior, backend disagreement, or other tagged dimensions.

## Consequences

Positive:

- False closure can be budgeted at zero for hard-gated release cases.
- Public benchmark reports can separate correctness and runtime signals.
- Release certification can hash-link evaluation reports to base observations.

Negative:

- A metric report is only as strong as the corpus behind it.
- Tag quality becomes important for meaningful regression diagnosis.

## Alternatives Considered

- Replace the corpus format immediately. Rejected because the seed corpus is
  already schema-backed and can be extended incrementally.
- Track only aggregate pass/fail. Rejected because it hides false closure and
  category-specific regressions.

## Validation

`tests/test_milestone_group6.py` covers tag category counts and zero-budget
false-closure failure.
