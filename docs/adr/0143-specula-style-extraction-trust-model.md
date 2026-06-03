# ADR 0143: Specula-Style Extraction Trust Model

## Status

Accepted

## Context

Spec extraction helps cover brownfield gaps, but generated specs are not trusted
evidence. They can suggest a formal model for review, not close coverage.

## Decision

Add `SpeculaExtractionIntegrationReport` in `nlreq.spec_extraction`.

Generated specs are candidate-only artifacts with `review_status=draft` and
`freshness=unknown`. The integration report performs structural validation and
records whether trace validation has passed. Missing trace grounding or
structural failure blocks the integration report while retaining candidates for
review.

## Consequences

The project can generate candidate formal specs for uncovered modules without
confusing draft output with reviewed system specification evidence.

## Validation

Group 12 tests verify candidate-only reports, structural validation, and
missing trace blocking.
