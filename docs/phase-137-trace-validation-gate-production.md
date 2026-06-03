# Phase 137 - Trace Validation Gate Production

## Status

Implemented.

## Purpose

Use runtime traces as grounding evidence for current behavior while preserving
the boundary between trace satisfaction and formal proof.

## Implementation

Primary module:

- `src/nlreq/trace_validation.py`

Primary artifacts:

- `TraceValidationGateReport`
- `TraceValidationGateOutcome`

Schema:

- `schemas/trace-validation-gate-report.schema.json`

CLI:

```bash
uv run nlreq trace-validation-gate \
  --requirement-ir requirement.ir.json \
  --trace-artifact traces.json \
  --coverage spec-coverage.json \
  --freshness freshness-ci.json \
  --out trace-validation-gate.json
```

## Contracts

- Trace replay outcomes are normalized into gate outcomes.
- Supported outcomes are `satisfied`, `violation`, `coverage_gap`, `lossy`,
  `stale`, and `unsupported`.
- Trace satisfaction yields `evidence_label=trace_grounding`, not formal proof.
- Trace violations block closure.
- Missing trace coverage is distinct from contradiction.
- Stale freshness blocks trace grounding even when traces satisfy the predicate.
- Lossy traces block high-assurance closure unless policy explicitly allows
  lossy evidence.

## Failure Behavior

- Requirement violation in traces: status `violation`, closure `block`.
- Missing action or failed coverage: status `coverage_gap`, closure `block`.
- Freshness CI blocker: status `stale`, closure `block`.
- Loss records in high-assurance mode: status `lossy`, closure `block`.
- Unsupported trace predicate: status `unsupported`, closure `review`.

## Verification

`tests/test_milestone_group12.py` verifies satisfied grounding evidence, lossy
blocking, stale blocking, and CLI output.
