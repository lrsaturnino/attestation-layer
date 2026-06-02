# ADR 0097: Semantic Translation Benchmark Methodology

## Status

Proposed

## Context

The existing translation benchmark measures syntax, semantic match,
clarification, refusal, and runtime. Milestone 5 needs to measure ambiguity,
needs-review, formal-claim output, and false acceptance.

## Decision

Extend the existing requirement translation benchmark schemas compatibly.

Add outcome `needs_review` and result fields for ambiguity, false acceptance,
review reason, formal claim hash, and semantic profile. Add aggregate ambiguity,
needs-review, and false-acceptance rates.

Any false acceptance fails the benchmark report.

## Rejected Alternatives

Creating a separate milestone-5 benchmark runner was rejected because the
existing translation benchmark already owns this measurement surface.

Ignoring false acceptance until release benchmarking was rejected because
semantic translation changes need early regression signal.

## Consequences

Existing seed benchmark files remain valid. Future corpus growth can track
semantic translation quality without changing the runner again.

## Validation

`nlreq benchmark-translation` emits the expanded report. Tests verify new
metrics and false-acceptance failure behavior.

