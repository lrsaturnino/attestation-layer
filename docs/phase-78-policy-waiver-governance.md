# Phase 78 - Policy And Waiver Governance

## Status

Implemented.

## Purpose

Support staged adoption without allowing exceptions to become silent proof
closure. Waivers must remain visible, bounded, reviewed, and auditable.

## Scope

The phase builds on the existing gate policy and waiver schemas. It audits
waivers against policy allowance, expiration, maximum duration, reviewed-hash
requirements, and hard-gate safety.

## Data Contracts

- `GatePolicy` defines allowed statuses, minimum evidence, scope, and waiver
  rules.
- `GateWaiver` records covered requirements or packages, reviewer, reason,
  expiration, reviewed hashes, linked issue, and whether it may satisfy hard
  gate.
- `WaiverAuditReport` records policy id, pass/block result, and findings.
- `WaiverAuditFinding` records waiver id, status, blocking flag, and reason.

The implemented schemas are:

- `schemas/gate-policy.schema.json`
- `schemas/waiver.schema.json`
- `schemas/waiver-audit-report.schema.json`

## API And CLI

Implementation module: `nlreq.policy_governance`.

Core function:

- `build_waiver_audit_report(...)` audits waivers against a policy and a stable
  timestamp.

CLI:

- `nlreq waiver-audit --policy <policy> --waiver <waiver>`
- multiple waiver files can be supplied and audited together.

## Governance Rules

- Expired waivers block.
- Waivers block when policy does not allow waivers.
- Waivers block when expiration exceeds `max_duration_days`.
- Waivers block when policy requires reviewed hashes and none are supplied.
- Waivers marked unsafe for hard gate block.
- Active waivers remain visible findings; they do not erase the original gate
  blocker.

## Verification

`tests/test_milestone_group6.py` verifies active, expired, unsafe, over-duration,
and missing-reviewed-hash waiver outcomes.

## Exit Criteria

- Waivers cannot silently make a blocked proof appear closed.
- Expired waivers fail.
- Waivers outside policy fail.
- Closure and audit reports show every waiver used or rejected.
- Benchmark and release reporting can measure waiver-dependent outcomes.
