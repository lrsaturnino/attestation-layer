# Phase 45 Public Benchmark Corpus

Phase 45 adds a stable benchmark corpus and metric report for tracking
verification power over time.

## Purpose

The phase lets the Attestation Layer say:

```text
Verification changes are measured against stable examples for closure, refusal,
unknown outcomes, counterexamples, timeouts, stale specs, trace mismatches, and
backend disagreement.
```

It does not say:

```text
The corpus is exhaustive.
A benchmark pass proves all real requirements are safe.
Runtime and quality metrics can be ignored when closure rate improves.
```

## Implementation Scope

Phase 45 implementation includes:

- benchmark corpus model and schema;
- benchmark results model and schema;
- benchmark run report model and schema;
- public `benchmarks/verification-power` corpus;
- cases for positive closure, system counterexample, parser disagreement, stale
  specs, trace mismatch, timeout, and backend disagreement;
- example observed results;
- CLI command for `benchmark-corpus`;
- metrics for closure rate, false closure rate, false refusal rate,
  counterexample quality, and runtime total;
- tests validating corpus paths, metrics, false closure detection, and CLI
  output.

## Corpus Contract

Each benchmark case declares:

- stable case id and title;
- short description;
- relative artifact paths;
- tags;
- expected decision;
- optional failure mode;
- whether a counterexample is expected.

The corpus is static input. Observed benchmark results are separate artifacts so
CI, local runs, and future runners can compare outputs without rewriting the
corpus itself.

## Metrics

The benchmark report computes:

- `closure_rate`: observed accepted cases divided by total cases;
- `false_closure_rate`: cases accepted when expected to refuse or remain
  unknown;
- `false_refusal_rate`: cases refused when expected to accept;
- `counterexample_quality`: expected counterexample cases with at least one
  observed counterexample;
- `runtime_ms_total`: total observed runtime.

## Success Criterion

Phase 45 succeeds when:

- future phases can run against stable examples;
- regressions in refusal, closure, and unknown behavior are visible;
- benchmark output is schema-backed and publishable as progress evidence.

## Boundary

The corpus is intentionally small and representative. Future benchmark updates
should append cases or version the corpus rather than mutating existing case
semantics silently.
