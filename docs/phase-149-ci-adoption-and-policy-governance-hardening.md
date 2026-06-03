# Phase 149 - CI Adoption And Policy Governance Hardening

## Status

Implemented.

## Purpose

Make action gating branch-protection ready by connecting hard-gate CI output,
waiver audit, branch protection required checks, and reviewed policy changes.

## Implementation

Primary module:

- `src/nlreq/policy_governance.py`

Primary artifacts:

- `PolicyChangeRecord`
- `CiPolicyGovernanceReportV2`
- existing `ExtendedCiPrGateReport`
- existing `WaiverAuditReport`

Schemas:

- `schemas/policy-change-record.schema.json`
- `schemas/ci-policy-governance-report-v2.schema.json`
- `schemas/extended-ci-pr-gate-report.schema.json`
- `schemas/waiver-audit-report.schema.json`

## Contract

Governance passes only when:

- the host branch protection list contains the required check name;
- CI ran in `hard_gate` mode;
- CI enforcement is `blocking`;
- CI result is `passed`;
- stable JSON hash is present;
- waiver audit passed;
- every CI waiver id has an audit entry;
- policy changes are reviewed when review is required.

## Failure Behavior

- Missing branch protection required check blocks governance.
- Report-only or soft-gate CI blocks governance.
- Non-blocking enforcement blocks governance.
- Failed or blocked CI result blocks governance.
- Failed waiver audit blocks governance.
- Unreviewed policy changes block governance.

## Verification

`tests/test_milestone_group14.py` verifies branch protection readiness and
reviewed policy change enforcement.
