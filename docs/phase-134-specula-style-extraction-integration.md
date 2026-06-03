# Phase 134 - Specula-Style Extraction Integration

## Status

Implemented.

## Purpose

Generate candidate formal specs for uncovered brownfield modules without
letting generated specs satisfy coverage or freshness gates by themselves.

## Implementation

Primary module:

- `src/nlreq/spec_extraction.py`

Primary artifacts:

- `SpeculaExtractionIntegrationReport`
- `CandidateSpec`
- `CandidateSpecStructuralValidation`

Schema:

- `schemas/specula-extraction-integration-report.schema.json`

CLI:

```bash
uv run nlreq specula-extract \
  --requirement-ir requirement.ir.json \
  --impact impact.json \
  --registry system-spec-registry.json \
  --trace-replay trace-replay.json \
  --out specula-extraction.json
```

## Contracts

- Generated specs are labeled `draft` with `freshness=unknown`.
- Integration reports have `trust_boundary=candidate_only`.
- Structural validation checks candidate hash integrity and TLA module envelope.
- Trace validation is required before candidate output is considered usable for
  review.
- Candidate specs cannot satisfy coverage until phase 135 review promotes them.

## Failure Behavior

- Missing trace grounding is recorded as a blocker.
- Failed structural validation is recorded per candidate.
- Existing fresh reviewed modules are skipped.
- Blocked extraction still retains candidates for audit and review.

## Verification

`tests/test_milestone_group12.py` verifies candidate-only status, structural
validation, missing-trace blocking, and grounded candidate output.
