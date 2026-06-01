# ADR 0058: Requirement Review, Approval Hash Binding, And Self-Audit Policy

## Status

Proposed

## Context

Review comments are insufficient for a gate. Approvals must become explicit
state transitions and must not survive artifact changes.

## Decision

Introduce a review workflow artifact with roles, checklist, decision, reviewer,
timestamp, self-audit metadata, and reviewed artifact hashes.

Review status is stale when current artifact hashes differ from approved
hashes. Solo mode is represented explicitly with `self_audit` and optional
delay.

Operational rules:

- Approved decisions cannot include failed checklist items.
- Required review roles are configurable; the default required role is
  `requirement_reviewer`.
- Each role approval replaces the previous approval for that role.
- Review status reports stale artifacts and missing roles separately.
- Checklist schema is emitted separately so UI and CI surfaces can validate it
  before submitting approval.

Rejected alternatives:

- Treating review comments as approval was rejected because comments do not bind
  artifact hashes.
- Letting failed checklist items coexist with approved status was rejected
  because the gate would have to infer reviewer intent.

Validation:

- `nlreq review-approve --checklist` validates checklist JSON and records it on
  the approval.
- `nlreq review-status --required-role` checks role completeness without
  mutating the workflow.

## Consequences

Review state can be consumed by gates and CI. Teams can distinguish a current
approval from a stale or self-audit approval.
