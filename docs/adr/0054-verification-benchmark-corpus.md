# ADR 0054: Verification Benchmark Corpus

## Status

Proposed

## Context

The roadmap has added stronger verification checks, but progress needs stable
measurement. Without a benchmark corpus, closure improvements can hide false
closures, weaker refusals, missing counterexamples, or worse runtime behavior.

## Decision

Introduce a public benchmark corpus under `benchmarks/verification-power`.

The corpus records stable cases with relative artifact paths and expected
outcomes. Observed results are supplied separately and evaluated into a
benchmark run report.

The benchmark report tracks:

- total and matched cases;
- closure rate;
- false closure rate;
- false refusal rate;
- counterexample quality;
- total runtime.

The initial corpus includes:

- positive closure;
- system counterexample;
- parser disagreement;
- stale spec;
- trace mismatch;
- timeout;
- backend disagreement.

## Consequences

Future verification changes can be evaluated against fixed examples. A change
that raises closure rate while introducing false closures will fail the benchmark
report.

The initial corpus is intentionally compact. New cases should be added with
stable ids and versioned expectations so historical comparisons remain
meaningful.
