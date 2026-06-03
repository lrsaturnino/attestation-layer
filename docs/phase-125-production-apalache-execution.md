# Phase 125 - Production Apalache Execution

## Status

Implemented.

## Purpose

Make Apalache the symbolic bounded-checking path for formal claims projected to
TLA+. The path must retain command metadata, bounds, output hashes, artifacts,
counterexamples, and missing-tool behavior.

## Implementation

Primary modules:

- `src/nlreq/formal_backend.py`
- `src/nlreq/model_checker_runner.py`

Relevant backend:

- `ApalacheBackend`

CLI:

```bash
uv run nlreq formal-backend-check requirement.ir.json \
  --backend apalache \
  --artifact-dir .nlreq-formal-artifacts/REQ/apalache \
  --max-depth 20
```

## Contracts

- Default command is `apalache-mc check --length={max_depth} {module}`.
- Backend result details include `evidence_flavor: symbolic_bounded`.
- Bounds and solver options are retained in the normalized response.
- Generated TLA module and config hashes are retained.
- Counterexamples are retained from normalized model-checker output.
- Missing executable maps to `unsupported`, not `valid`.
- Timeout maps to `timeout`, not `valid`.
- Non-zero unclassified tool errors map to `invalid`.

## Evidence Labels

`valid` and `counterexample` outcomes may carry `BOUNDED_CHECKED`. They are not
inductive proof evidence.

## Failure Behavior

- Lowering refusal blocks command execution.
- Missing Apalache is non-approving `unsupported`.
- Timeout is non-approving and handled by the budget policy.
- Parse/tool failures are non-approving `invalid`.

## Verification

`tests/test_milestone_group11.py` runs Apalache through a deterministic fixture
command and verifies symbolic bounded metadata, timeout/missing-tool behavior,
and output parsing.
