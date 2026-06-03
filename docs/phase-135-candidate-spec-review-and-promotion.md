# Phase 135 - Candidate Spec Review And Promotion

## Status

Implemented.

## Purpose

Promote generated candidate specs into reviewed system spec coverage only after
explicit hash-bound human review.

## Implementation

Primary module:

- `src/nlreq/spec_extraction.py`

Primary artifacts:

- `CandidateSpecReviewReport`
- `CandidateSpecReviewChecklistItem`

Schema:

- `schemas/candidate-spec-review-report.schema.json`

CLI:

```bash
uv run nlreq candidate-spec-review candidate.json \
  --decision promote \
  --reviewer-id reviewer-a \
  --approved-hash sha256:... \
  --version 1 \
  --out candidate-review.json
```

## Contracts

- Promotion requires reviewer identity and review timestamp.
- Promotion binds to the exact candidate content hash.
- Candidate structural validation must pass before promotion.
- Candidate trace grounding must have passed before promotion.
- Review checklist rejection blocks promotion.
- Rejection reports retain reviewer identity and rejection reasons.

## Failure Behavior

- Approved hash mismatch: decision `blocked`.
- Trace grounding missing or blocked: decision `blocked`.
- Rejected checklist item: decision `blocked`.
- Reviewer rejection: decision `rejected`, candidate remains auditable.

## Verification

`tests/test_milestone_group12.py` verifies stale hash blocking, successful
promotion to reviewed fresh spec entry, and rejection audit retention.
