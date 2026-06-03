# ADR 0132: Semantic Translation Benchmark Release Bar

## Status

Accepted

## Context

The translation benchmark reported semantic match, ambiguity, needs-review, and
false acceptance rates. The roadmap requires release thresholds that block
publication when semantic translation quality is unsafe.

## Decision

Add `RequirementTranslationReleaseThresholds` and
`RequirementTranslationReleaseBarReport`. Release evaluation hashes the
underlying benchmark report, checks false acceptance/refusal budgets, checks
semantic match and optional clarification/refusal thresholds, and verifies
required expected outcomes are present.

## Invariants

- False semantic acceptance budget defaults to zero.
- Benchmark scoring remains corpus-scoped.
- Extra observed results cannot improve required-case metrics.
- Release-bar reports fail when the underlying benchmark report failed.

## Consequences

Semantic translation quality becomes an explicit release gate instead of an
informational metric.

## Rejected Alternatives

Using only aggregate pass/fail from benchmark observations was rejected because
release policy needs separately configurable blockers.

Allowing extra cases to compensate for missing required outcomes was rejected
because it enables benchmark gaming.

## Validation

`tests/test_milestone_group10.py` verifies release-bar failure on false semantic
acceptance.
