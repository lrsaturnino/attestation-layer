# Phase 128 - Counterexample Explanation Contract

## Status

Implemented.

## Purpose

Turn backend counterexamples into product-grade refusal evidence. The report
must name the backend, violated property, retained bounds, shortest known trace,
source mappings, and next actions.

## Implementation

Primary module:

- `src/nlreq/counterexample_normalization.py`

Schemas:

- `schemas/counterexample-normalization-report.schema.json`
- `schemas/counterexample-explanation-report.schema.json`

CLI:

```bash
uv run nlreq counterexample-normalize \
  --formal-backend-response apalache-response.json \
  --out normalized-counterexamples.json

uv run nlreq counterexample-explain \
  --normalization normalized-counterexamples.json \
  --formal-claim formal-claim.json \
  --formal-backend-response apalache-response.json \
  --out counterexample-explanation.json \
  --markdown-out counterexample-explanation.md
```

## Contracts

- Every explanation names backend and counterexample ID.
- Backend bounds are copied from the backend response when present.
- The violated property maps to a formal claim fragment when a formal claim is
  supplied.
- Source spans are retained through formal claim fragments.
- Markdown output is derived from the JSON report, not hand-authored text.
- Next actions distinguish requirement repair, spec update, and implementation
  fix paths.

## Failure Behavior

- No counterexamples produce `result: none`.
- Missing formal claim still yields an explanation without source mappings.
- Missing backend response still yields an explanation without bound metadata.

## Verification

`tests/test_milestone_group11.py` verifies source-span mapping and Markdown
rendering for a normalized backend counterexample.
