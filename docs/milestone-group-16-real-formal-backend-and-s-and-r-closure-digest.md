# Milestone Group 16 Real Formal Backend And S-and-R Closure Digest

Milestone group 16 implements phases 157 through 163 from `docs/conclusion-real-evidence-final-gap-roadmap.md`.

## Phase Map

| Phase | Name | ADR |
|---:|---|---|
| 157 | Formal Claim Semantics Exhaustion | ADR 0166 |
| 158 | Production Apalache Runner Hardening | ADR 0167 |
| 159 | Production TLC Runner Hardening | ADR 0168 |
| 160 | Reviewed System Spec Package Format | ADR 0169 |
| 161 | Production S-and-R Compatibility Checker | ADR 0170 |
| 162 | Counterexample Explanation And Replay | ADR 0171 |
| 163 | Verification Budget And Abstraction Profiles | ADR 0172 |

## Implementation

The milestone is implemented through `nlreq.real_evidence`, which records phase plans, required artifact types, phase evidence reports, milestone aggregation, and the final Claude-conversation gap assessment. The reports block missing, scaffold, blocked, or unreviewed evidence.

## Schemas

- `schemas/real-evidence-phase-plan.schema.json`
- `schemas/real-evidence-phase-report.schema.json`
- `schemas/real-evidence-milestone-report.schema.json`
- `schemas/claude-convo-gap-assessment.schema.json`

## Verification

`tests/test_milestone_groups_15_to_20.py` covers all phases in this milestone and schema drift is enforced by `scripts/check_schema_drift.py`.
