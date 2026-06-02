# Phase 78 - Policy And Waiver Governance v2

## Status

Implemented.

## Purpose

Allow staged adoption without allowing waivers to silently turn blocked proof
closure into closed proof closure.

## Implementation

- `nlreq.policy_v2`
- `nlreq waiver-audit`
- `schemas/waiver-audit-report.schema.json`

The audit report checks expiration, policy allowance, and hard-gate safety flags
for existing gate waivers.

## Exit Criteria

- Expired waivers block.
- Waivers outside policy block.
- Unsafe hard-gate waivers block and remain visible.
