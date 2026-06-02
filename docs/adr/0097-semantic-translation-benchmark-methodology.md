# ADR 0097: Semantic Translation Benchmark Methodology

## Status

Accepted

## Context

The existing translation benchmark measures syntax, semantic match,
clarification, refusal, and runtime. Milestone group 8 needs to measure
ambiguity, needs-review, formal-claim output, and false acceptance.

## Decision

Extend the existing requirement translation benchmark schemas compatibly.

Add outcome `needs_review` and result fields for ambiguity, false acceptance,
review reason, formal claim hash, and semantic profile. Add aggregate ambiguity,
needs-review, and false-acceptance rates.

Any false acceptance fails the benchmark report.

The expanded methodology remains exposed by `nlreq benchmark-translation`.

## Decision Details

The corpus remains the authoritative evaluation set. Observed results for case
IDs outside the corpus are ignored for aggregate metrics.

New per-result fields are:

- `ambiguous`;
- `false_acceptance`;
- `needs_review_reason`;
- `formal_claim_hash`;
- `semantic_profile`.

New aggregate fields are:

- ambiguity rate;
- needs-review rate;
- false-acceptance rate.

Clarification quality requires observed questions to include the expected
questions. Missing clarification results score zero quality. Refusal correctness
requires exact refusal-code match.

## Invariants

- Aggregate rates divide by corpus size.
- Extra observed results cannot inflate syntax, semantic, runtime, or
  false-acceptance metrics.
- Any false acceptance fails the report.
- Accepted cases require semantic match.
- Needs-review cases require a review reason.

## Rejected Alternatives

Creating a separate milestone-5 benchmark runner was rejected because the
existing translation benchmark already owns this measurement surface.

Ignoring false acceptance until release benchmarking was rejected because
semantic translation changes need early regression signal.

## Consequences

Existing seed benchmark files remain valid. Future corpus growth can track
semantic translation quality without changing the runner again.

False acceptance becomes visible before release certification. Runtime metrics
also stay corpus-scoped, which prevents unrelated observed results from hiding
translation regressions.

## Compatibility

The schema changes are backward-compatible because new fields have defaults and
the existing CLI command is unchanged.

## Validation

`nlreq benchmark-translation` emits the expanded report. Tests verify new
metrics, false-acceptance failure behavior, missing clarification scoring, and
extra-result exclusion from aggregate metrics.
