# ADR 0129: Translator Ensemble Calibration

## Status

Accepted

## Context

Semantic agreement previously compared formal claim candidates under named
equivalence profiles. The roadmap requires calibration against semantic labels
so agreement quality is measured by meaning, not only shape.

## Decision

Add semantic agreement calibration cases and reports. A calibration case pairs a
`SemanticAgreementReport` with an expected same-meaning label. Calibration emits
matched cases, semantic accuracy, false acceptance count, false refusal count,
and budget blockers.

## Invariants

- High-assurance agreement still requires at least two lowered candidates.
- Unreviewed disagreement blocks acceptance.
- Reviewer resolution remains hash-bound to the selected candidate.
- False semantic acceptance budget defaults to zero.

## Consequences

Release checks can fail when the agreement method accepts candidates that the
benchmark labels as semantically different.

## Rejected Alternatives

Using only canonical formal claim equality was rejected because it cannot
measure missed semantic errors.

Allowing confidence scores without labeled calibration was rejected because it
would not create a reproducible release signal.

## Validation

`tests/test_milestone_group10.py` verifies a labeled false agreement fails
calibration.
