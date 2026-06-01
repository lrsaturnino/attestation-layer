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
