# ADR 0007: Gate Policy And Waiver Model

## Status

Accepted

## Context

Phase 4 introduced a soft gate that can report whether implementation work
references accepted requirement packages. Phase 5 needs a hard-gate path, but
hard gating must be scoped and reversible. The system should not globally block
work because one adapter, directory, or evidence backend is still noisy.

The status decision remains a pure function over evidence. Gate enforcement is a
Layer 7 concern: it reads package status, package evidence, policy, references,
and waiver artifacts, then decides whether CI should fail.

## Decision

Phase 5 will introduce explicit gate policy and waiver artifacts.

A gate policy defines:

- policy schema version,
- gate mode,
- scoped package roots or requirement id patterns,
- scoped adapters,
- optional changed-path patterns,
- allowed final statuses,
- required review state,
- minimum evidence levels by claim or package,
- findings that block CI,
- findings that remain report-only,
- and waiver rules.

A waiver records:

- waiver id,
- requirement ids or package paths covered,
- reviewer,
- reason,
- expiration timestamp,
- reviewed package hashes,
- linked issue or PR,
- and whether the waiver may satisfy hard-gate enforcement.

Hard gates must:

- default to opt-in policy files,
- fail only scoped findings,
- include waiver decisions in the gate report,
- reject expired or stale waivers,
- never mutate package status,
- never bypass `validate` or adapter-specific package validation,
- and never add side effects to `decide_status`.

Example artifacts live in:

- `docs/examples/gate-policy.example.json`
- `docs/examples/waiver.example.json`

## Consequences

Phase 5 can introduce blocking CI without changing the package/evidence/status
contract. Teams can roll out hard gates by adapter, directory, or requirement
scope after observing soft-gate noise. Waivers are auditable and temporary, not
silent bypasses.
