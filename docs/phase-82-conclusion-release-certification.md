# Phase 82 - Conclusion Release Certification

## Status

Implemented.

## Purpose

Produce the final readiness decision for the conclusion release from
machine-readable release evidence.

Certification is a report over evidence. It is not a global correctness claim
for arbitrary natural language or arbitrary programs.

## Scope

Certification consumes:

- benchmark evaluation report;
- threat model report;
- reference demo report;
- public documentation index;
- schema-freeze evidence.

It emits a release-level `certified` or `blocked` decision, criterion statuses,
blocking findings, evidence label claims, and known limitations.

## Data Contracts

Implementation module: `nlreq.conclusion_certification`.

Schema:

- `schemas/conclusion-certification-report.schema.json`

Primary models:

- `ConclusionCertificationReport`
- `ConclusionCriterionStatus`

Required criteria:

- `benchmark-evaluation`
- `threat-model`
- `reference-demo`
- `public-docs`
- `schema-freeze`

## API And CLI

Core function:

- `build_conclusion_certification_report(...)`

CLI:

```bash
uv run nlreq conclusion-certify \
  --release-id conclusion-0.1 \
  --benchmark-report /tmp/benchmark-evaluation.json \
  --threat-model /tmp/threat-model.json \
  --reference-demo-report /tmp/reference-demo-report.json \
  --docs-index /tmp/public-docs.json \
  --schemas-frozen \
  --out /tmp/conclusion-certification.json
```

The command exits non-zero when the report is `blocked`.

## Invariants

- Any failed required criterion blocks certification.
- Benchmark evidence must pass and include at least one case.
- Threat model evidence must be complete under Phase 79 release checks.
- Reference demo evidence must be reproducible, include accepted and refused
  requirements, declare commands, and have no missing artifacts or decision
  mismatches.
- Public docs must cover required audiences and include schema references and
  example coverage tags.
- Schema-freeze evidence is required for certification.
- Bounded checks, trace replay, adapter certification, and signed evidence keep
  their original evidence-label boundaries.

## Verification

`tests/test_milestone_group7.py` verifies a fully certified release path and
blocking behavior for incomplete threat-model evidence and missing schema-freeze
evidence.

## Exit Criteria

- Certification is reproducible from machine-readable inputs.
- Failed criteria explain their blocking findings.
- Evidence-label claims and known limitations ship with the report.
- Public release claims remain scoped to the released evidence set.
