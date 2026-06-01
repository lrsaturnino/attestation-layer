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

## Consequences

Review state can be consumed by gates and CI. Teams can distinguish a current
approval from a stale or self-audit approval.
