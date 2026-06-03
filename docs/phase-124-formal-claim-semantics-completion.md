# Phase 124 - Formal Claim Semantics Completion

## Status

Implemented.

## Purpose

Complete the formal semantics table for every supported DSL v3 claim class
before backend dispatch. A backend must receive typed formal fragments with
declared evidence requirements, never raw prose or partially lowered semantics.

## Scope

Supported claim classes:

- `authorization_precondition`
- `state_precondition`
- `state_postcondition`
- `numeric_invariant`
- `event_state_correspondence`
- `bounded_temporal`
- `cross_module_causal_obligation`

Each class declares exact canonical semantics, supported formal fragment kinds,
required evidence labels, backend projection obligations, trace validation
obligations, limitations, and unsupported behavior.

## Implementation

Primary module:

- `src/nlreq/formal_claim.py`

Schema:

- `schemas/formal-claim-semantics-completion.schema.json`

CLI:

```bash
uv run nlreq formal-claim-semantics --out formal-claim-semantics.json
```

The implementation exposes
`build_formal_claim_semantics_completion_reference()`. It derives the evidence
matrix from the controlled-semantics reference and augments it with backend and
trace obligations required by real formal closure.

## Contracts

- The semantics reference result is `complete` only when all supported claim
  classes are present.
- Unsupported semantic nodes refuse before backend dispatch with stable
  unsupported-fragment records.
- Temporal and cross-module claims must carry explicit bounds.
- The reference records evidence requirements but does not emit backend
  evidence.
- Formal fragment IDs remain stable over semantic-node IDs.

## Failure Behavior

- Unknown claim classes produce incomplete semantics or refused lowering.
- Unsupported node kinds refuse before any backend command is constructed.
- Missing temporal bounds refuse temporal lowering.
- Required evidence labels cannot be strengthened by the semantics reference.

## Verification

`tests/test_milestone_group11.py` verifies that the completion reference covers
all seven claim classes, includes required evidence, and is emitted by the CLI.
