# Milestone Group 17 Brownfield Spec Grounding And Drift Closure Digest

Milestone group 17 implements phases 164 through 171 from `docs/conclusion-real-evidence-final-gap-roadmap.md`.

## Phase Map

| Phase | Name | ADR |
|---:|---|---|
| 164 | Multi-Language Impact Analysis v2 | ADR 0173 |
| 165 | Code-To-Spec Coverage Manifest v3 | ADR 0174 |
| 166 | Specula-Style Extraction Runner Production | ADR 0175 |
| 167 | Candidate Spec Review Workbench | ADR 0176 |
| 168 | Continuous Spec Freshness CI | ADR 0177 |
| 169 | Trace Producer SDK v2 | ADR 0178 |
| 170 | Trace Validation Against Formal Claims v2 | ADR 0179 |
| 171 | Brownfield Delta And Remediation Reports | ADR 0180 |

## Implementation

The milestone is implemented through `nlreq.real_evidence`, which records phase plans, required artifact types, phase evidence reports, milestone aggregation, and the final Claude-conversation gap assessment. The reports block missing, scaffold, blocked, or unreviewed evidence.

## Schemas

- `schemas/real-evidence-phase-plan.schema.json`
- `schemas/real-evidence-phase-report.schema.json`
- `schemas/real-evidence-milestone-report.schema.json`
- `schemas/claude-convo-gap-assessment.schema.json`

## Verification

`tests/test_milestone_groups_15_to_20.py` covers all phases in this milestone and schema drift is enforced by `scripts/check_schema_drift.py`.
