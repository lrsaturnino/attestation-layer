# Phase 133 - Spec Freshness And Drift CI

## Status

Implemented.

## Purpose

Prevent requirements from being checked against stale formal specs after source
or spec files change.

## Implementation

Primary module:

- `src/nlreq/spec_freshness.py`

Primary artifacts:

- `SpecFreshnessLockfileV2`
- `SpecFreshnessDriftCiReport`
- `SpecFreshnessDriftStatusV2`

Schemas:

- `schemas/spec-freshness-lockfile-v2.schema.json`
- `schemas/spec-freshness-drift-ci-report.schema.json`

CLI:

```bash
uv run nlreq spec-freshness-lock-v2 \
  --manifest code-spec-manifest.json \
  --registry system-spec-registry.json \
  --validated-at 2026-06-03T00:00:00Z \
  --out freshness-lock.json

uv run nlreq spec-freshness-ci \
  --manifest code-spec-manifest.json \
  --registry system-spec-registry.json \
  --lockfile freshness-lock.json \
  --now 2026-06-03T12:00:00Z \
  --max-validation-age-hours 24 \
  --out freshness-ci.json
```

## Contracts

- Lock entries include source hashes, spec hashes, dependency modules,
  manifest-entry hash, validation timestamp, and optional validation artifact
  hashes.
- Source drift and spec drift both produce stale statuses.
- Locked modules missing from the current manifest block closure.
- Current modules missing from the lockfile block closure.
- Validation age can be policy-gated.
- Freshness drift propagates through dependency edges.

## Failure Behavior

- Changed source hash: status `stale`, closure `block`.
- Changed spec hash: status `stale`, closure `block`.
- Missing lock or file: closure `block`.
- Validation older than policy allows: status `validation_expired`, closure
  `block`.

## Verification

`tests/test_milestone_group12.py` verifies changed spec blocking and validation
age blocking.
