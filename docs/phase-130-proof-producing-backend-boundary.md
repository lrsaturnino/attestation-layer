# Phase 130 - Proof-Producing Backend Boundary

## Status

Implemented.

## Purpose

Define the boundary for true proof evidence without requiring inductive proofs
for every bounded release claim. `PROVEN_INDUCTIVE` must be impossible to fake
with model-checker evidence.

## Implementation

Primary module:

- `src/nlreq/evidence_boundary.py`

Schemas:

- `schemas/proof-evidence-boundary-report.schema.json`
- `schemas/proof-producing-backend-boundary-report.schema.json`

CLI:

```bash
uv run nlreq proof-backend-boundary \
  --backend-result backend-result.json \
  --proof-artifact checked:checked_proof:sha256:abc123@proof.out \
  --checker-command tlapm Proof.tla
```

## Contracts

`PROVEN_INDUCTIVE` requires all of:

- backend status `valid`;
- registered producer kind `proof_assistant`;
- retained `checked_proof` artifact;
- proof checker command metadata.

Bounded model-checker evidence may support bounded closure but is reported as
non-inductive. Missing proof-producing backends do not block bounded release
claims when evidence labels are honest.

## Failure Behavior

- A non-proof-assistant producer claiming `PROVEN_INDUCTIVE` blocks.
- A valid proof-assistant result without checked proof artifact blocks.
- A checked proof artifact without checker command metadata blocks.
- Bounded evidence produces an informational finding and remains accepted as
  bounded, not inductive.

## Verification

`tests/test_milestone_group11.py` verifies blocked fake inductive evidence and
accepted checked proof-assistant evidence.
