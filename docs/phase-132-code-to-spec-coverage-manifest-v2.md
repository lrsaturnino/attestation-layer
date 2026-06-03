# Phase 132 - Code-To-Spec Coverage Manifest v2

## Status

Implemented.

## Purpose

Make brownfield formal spec coverage precise enough to gate requirements that
touch existing code.

## Implementation

Primary module:

- `src/nlreq/coverage_alignment.py`

Primary artifacts:

- `CodeSpecCoverageManifestV2`
- `CodeSpecCoverageGateReportV2`
- `CoverageGateModuleStatusV2`

Schemas:

- `schemas/code-spec-coverage-manifest-v2.schema.json`
- `schemas/code-spec-coverage-gate-report-v2.schema.json`

CLI:

```bash
uv run nlreq coverage-manifest-v2-migrate \
  --manifest code-spec-manifest.json \
  --registry system-spec-registry.json \
  --out coverage-manifest-v2.json

uv run nlreq coverage-gate-v2 \
  --impact impact.json \
  --manifest coverage-manifest-v2.json \
  --threshold 1.0 \
  --out coverage-gate.json
```

## Contracts

- Only reviewed, full, fresh coverage above threshold allows closure.
- Candidate, draft, rejected, missing, stale, partial, and unsupported coverage
  blocks closure.
- Dependency gaps propagate to dependent affected modules.
- Trace coverage links are retained on manifest entries for downstream trace
  validation.
- The v1 code/spec manifest can be migrated into v2 using the system spec
  registry review and freshness state.

## Failure Behavior

- Missing affected module: status `missing`, closure `block`.
- Candidate or draft coverage: status `candidate`, closure `block`.
- Freshness stale: status `stale`, closure `block`.
- Below threshold: status `partial`, closure `block`.
- Dependency gap: status `dependency_gap`, closure `block`.

## Verification

`tests/test_milestone_group12.py` verifies candidate coverage blocking and
dependency-gap propagation.
