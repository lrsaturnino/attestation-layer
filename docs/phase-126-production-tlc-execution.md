# Phase 126 - Production TLC Execution

## Status

Implemented.

## Purpose

Add TLC as an explicit-state TLA+ backend path independent from Apalache. TLC
evidence is bounded or configuration-scoped explicit-state evidence and must be
distinguishable from symbolic bounded evidence.

## Implementation

Primary modules:

- `src/nlreq/formal_backend.py`
- `src/nlreq/model_checker_runner.py`

Relevant backend:

- `TlcProductionBackend`

CLI:

```bash
uv run nlreq formal-backend-check requirement.ir.json \
  --backend tlc \
  --artifact-dir .nlreq-formal-artifacts/REQ/tlc
```

## Contracts

- Default command is `tlc2.TLC -config {config} {module}`.
- Backend result details include `evidence_flavor: explicit_state_bounded`.
- TLC success markers produce `valid`.
- TLC invariant, temporal property, assertion, and counterexample markers
  produce `counterexample`.
- Output hashes and bounded tails are retained.
- Timeout and missing tool outcomes are non-approving.

## Backend Disagreement

TLC responses are compatible with `backend-agreement`. Overlapping Apalache/TLC
responses can report disagreement when status, evidence level, or overlap
metadata differ.

## Verification

`tests/test_milestone_group11.py` verifies TLC counterexample parsing and
explicit-state bounded profile metadata.
