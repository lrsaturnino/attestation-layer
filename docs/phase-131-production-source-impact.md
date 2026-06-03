# Phase 131 - Production Source Impact

## Status

Implemented.

## Purpose

Identify which source modules a requirement touches using adapter-owned source
facts before coverage, freshness, and trace gates run.

## Implementation

Primary module:

- `src/nlreq/source_impact.py`

Primary artifacts:

- `ProductionSourceImpactReport`
- `ImpactConfidencePolicy`
- `ProductionImpactedModule`
- `SourceImpactFinding`

Schema:

- `schemas/production-source-impact-report.schema.json`

CLI:

```bash
uv run nlreq python-source-impact-production \
  --manifest source-manifest.json \
  --symbol finalize_redemption \
  --trace-artifact traces.json \
  --semantic-suggestion wallet:semantic-hint:llm \
  --out impact.json
```

## Contracts

- Adapter symbol resolution is authoritative for deterministic impact.
- Unresolved and ambiguous input symbols are blocking findings.
- Call graph dependencies are expanded from resolved symbols and marked as
  deterministic dependency impact.
- Runtime trace touchpoints are included as affected modules, but trace-only
  disagreements require review.
- Semantic suggestions are retained as non-gateable hints unless policy
  explicitly allows them.
- `closure_effect` is `block`, `review`, or `allow`; downstream gates must not
  treat review or block as closure.

## Failure Behavior

- Missing symbol: `closure_effect=block`, category `unresolved_symbol`.
- Ambiguous symbol: `closure_effect=block`, category `ambiguous_symbol`.
- Trace-only module outside deterministic impact: `closure_effect=review`.
- Semantic-only module: recorded but not gateable.

## Verification

`tests/test_milestone_group12.py` verifies deterministic modules, trace
touchpoints, semantic hints, review findings, and unresolved-symbol blocking.
