# ADR 0144: Candidate Spec Review And Promotion

## Status

Accepted

## Context

Candidate specs need a safe path into the reviewed system spec registry. The
promotion must bind to exact generated content and reviewer identity.

## Decision

Add `CandidateSpecReviewReport` in `nlreq.spec_extraction`.

Promotion requires:

- reviewer id;
- review timestamp;
- approved candidate content hash;
- passing structural validation;
- passed trace grounding;
- no rejected checklist item.

Rejections are first-class reports with reviewer identity and rejection reasons.

## Consequences

Generated specs remain auditable whether promoted, rejected, or blocked. A
changed candidate cannot be promoted using an old approval hash.

## Validation

Group 12 tests verify hash-bound promotion, blocked stale promotion, and
rejection audit records.
