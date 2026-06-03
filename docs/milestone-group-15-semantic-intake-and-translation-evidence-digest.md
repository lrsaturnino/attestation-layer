# Milestone Group 15 Semantic Intake And Translation Evidence Digest

Milestone group 15 implements phases 151 through 156 from `docs/conclusion-real-evidence-final-gap-roadmap.md`.

## Phase Map

| Phase | Name | ADR |
|---:|---|---|
| 151 | Product Free-Form Intake Evidence Runtime | ADR 0160 |
| 152 | Controlled Rewrite Replay Corpus | ADR 0161 |
| 153 | Semantic Decomposition IR v2 | ADR 0162 |
| 154 | Semantic Equivalence And Translator Calibration | ADR 0163 |
| 155 | ALICE-Grade Contradiction Engine | ADR 0164 |
| 156 | Translation Release Corpus And Thresholds | ADR 0165 |

## Implementation

The milestone is implemented through `nlreq.real_evidence`, which records phase plans, required artifact types, phase evidence reports, milestone aggregation, and the final Claude-conversation gap assessment. The reports block missing, scaffold, blocked, or unreviewed evidence.

## Schemas

- `schemas/real-evidence-phase-plan.schema.json`
- `schemas/real-evidence-phase-report.schema.json`
- `schemas/real-evidence-milestone-report.schema.json`
- `schemas/claude-convo-gap-assessment.schema.json`

## Verification

`tests/test_milestone_groups_15_to_20.py` covers all phases in this milestone and schema drift is enforced by `scripts/check_schema_drift.py`.
