# Phase 147 - Public Benchmark Suite And Leaderboard

## Status

Implemented.

## Purpose

Make benchmark results externally accountable by publishing the benchmark
dimensions, release thresholds, false-closure accounting, and leaderboard input
format.

## Implementation

Primary module:

- `src/nlreq/benchmark_reporting.py`

Primary artifacts:

- `PublicBenchmarkSuite`
- `PublicLeaderboardEntry`
- `PublicBenchmarkReleaseReport`
- existing `ExtendedBenchmarkEvaluationReport`

Schemas:

- `schemas/public-benchmark-suite.schema.json`
- `schemas/public-leaderboard-entry.schema.json`
- `schemas/public-benchmark-release-report.schema.json`

## Contract

The public suite records:

- suite id and version;
- required benchmark dimensions;
- case ids by dimension;
- release thresholds;
- optional expected-results hash.

The public release report records:

- named dimensions;
- missing and failed dimensions;
- false closure and false refusal rates;
- false closure budget;
- leaderboard entries;
- blocking findings.

Publication requires:

- the base benchmark report passed;
- the extended benchmark report passed;
- every public suite dimension is present;
- no dimension failed its release threshold;
- false closure rate is within budget;
- at least one leaderboard entry is retained.

## Failure Behavior

- Base or extended benchmark failure blocks publication.
- Missing dimensions block publication.
- Failed dimensions block publication.
- False closure over budget blocks publication.
- Empty leaderboard blocks publication.

## Verification

`tests/test_milestone_group14.py` verifies publishable benchmark output,
dimension naming, false-closure blocking, and missing-leaderboard blocking.
