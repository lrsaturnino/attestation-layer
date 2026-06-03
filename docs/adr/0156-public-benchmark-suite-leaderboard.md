# ADR 0156: Public Benchmark Suite And Leaderboard

## Status

Accepted

## Context

Internal benchmark reports are not enough for a public conclusion claim. The
project needs a report that names dimensions, thresholds, false-closure budget,
and leaderboard inputs.

## Decision

Introduce public benchmark suite, leaderboard entry, and release report
schemas. Publication requires passing base and extended benchmark reports,
complete dimensions, no failed dimensions, false closure within budget, and at
least one retained leaderboard entry.

## Consequences

Benchmark accountability is now schema-backed and false closure is explicitly
release-blocking. The tradeoff is that publication is blocked until leaderboard
metadata exists, even for local reference runs.

## Validation

Group 14 tests verify publishable results and blocking behavior for false
closure and missing leaderboard entries.
