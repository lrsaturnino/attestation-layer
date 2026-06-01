# Phase 49 Requirement Review And Approval Workflow

Phase 49 makes review a hash-bound state transition.

## Roles

- `author`
- `requirement_reviewer`
- `formal_reviewer`
- `adapter_evidence_reviewer`
- `self_audit_reviewer`

## Contracts

`src/nlreq/review_workflow.py` defines:

- `ApprovalWorkflowArtifact`
- `ReviewApprovalRecord`
- `ReviewChecklistV2`
- `ReviewStatusReport`

CLI:

```bash
uv run nlreq review-open --review-id REVIEW-1 --requirement-id REQ-1 \
  --artifact controlled=requirement.nlreq3 --out review.json
uv run nlreq review-approve review.json --role requirement_reviewer \
  --reviewer reviewer@example.invalid --out review.approved.json
uv run nlreq review-status review.approved.json --artifact controlled=requirement.nlreq3
```

## Invariants

- Approval records bind role, reviewer, decision, checklist, timestamp, and
  artifact hashes.
- Artifact changes make approval status `stale`.
- Solo mode is represented by `self_audit` and an optional delay.

## Exit Criteria

Tests cover approved and stale states.

## Implementation Spec

Input artifacts:

- One or more named artifact references created with `artifact_ref_from_path`.
- Optional `ReviewChecklistV2` JSON supplied to `nlreq review-approve`.
- Required role list supplied to `review_status` or `nlreq review-status`.

Output artifacts:

- `ApprovalWorkflowArtifact` records review ID, requirement ID, current status,
  reviewed artifact refs, and role-scoped approvals.
- `ReviewApprovalRecord` binds reviewer, decision, timestamp, role, checklist,
  self-audit metadata, and the artifact hashes reviewed at approval time.
- `ReviewStatusReport` names stale artifacts and missing required roles.
- `schemas/review-checklist-v2.schema.json` exposes the checklist shape for
  product and CI surfaces.

Validation behavior:

- An approved decision cannot include any checklist item marked `fail`.
- Artifact content changes make the approval stale.
- Required roles are configurable. The default required role is
  `requirement_reviewer`.
- Self-audit status and optional delay are recorded on the approval rather than
  inferred from reviewer identity.

CLI behavior:

- `nlreq review-open` records named artifacts and hashes.
- `nlreq review-approve --checklist checklist.json` records a hash-bound role
  decision.
- `nlreq review-status --required-role formal_reviewer` reports missing role
  approvals without mutating the workflow.

Failure modes:

- Failed checklist with an approved decision raises before a stale approval can
  be written.
- Changed artifact hashes return `stale`.
- Missing required roles return `open` or `needs_review`.

Tests:

- `tests/test_milestone_group1.py` covers stale approvals, failed checklist
  rejection, CLI checklist ingestion, and required-role status reporting.
