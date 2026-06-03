# Milestone Group 20 External Review And Conclusion Publication Digest

Milestone group 20 implements phases 187 through 192 from `docs/conclusion-real-evidence-final-gap-roadmap.md`.

## Phase Map

| Phase | Name | ADR |
|---:|---|---|
| 187 | Threat Model And TCB Re-Review | ADR 0196 |
| 188 | External Reproduction And Red-Team Review | ADR 0197 |
| 189 | Public Documentation And Schema Freeze v2 | ADR 0198 |
| 190 | Release Bundle Signing And Publication | ADR 0199 |
| 191 | Conclusion Claim Language And Limitations | ADR 0200 |
| 192 | Final Real-Evidence Conclusion Decision | ADR 0201 |

## Implementation

The milestone is implemented through `nlreq.real_evidence`, which records phase plans, required artifact types, phase evidence reports, milestone aggregation, and the final Claude-conversation gap assessment. The reports block missing, scaffold, blocked, or unreviewed evidence.

## Schemas

- `schemas/real-evidence-phase-plan.schema.json`
- `schemas/real-evidence-phase-report.schema.json`
- `schemas/real-evidence-milestone-report.schema.json`
- `schemas/claude-convo-gap-assessment.schema.json`

## Verification

`tests/test_milestone_groups_15_to_20.py` covers all phases in this milestone and schema drift is enforced by `scripts/check_schema_drift.py`.
