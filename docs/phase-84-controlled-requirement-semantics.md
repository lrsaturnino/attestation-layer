# Phase 84 Controlled Requirement Semantics

Phase 84 makes the supported DSL v3 constructs explicit and machine-readable.

## Purpose

Controlled requirements are only useful if every accepted phrase has a named
meaning. This phase publishes a semantics reference for supported claim classes,
constructs, required evidence, limitations, and refusal behavior.

## Contracts

`src/nlreq/controlled_semantics.py` defines:

- `ControlledRequirementSemanticsReference`
- `ControlledClaimClassSemantics`
- `ControlledConstructSemantics`

Schema:

- `schemas/controlled-requirement-semantics.schema.json`

CLI:

```bash
uv run nlreq controlled-semantics --out controlled-semantics.json
```

## Claim Classes

The semantics reference covers:

- `authorization_precondition`
- `state_precondition`
- `state_postcondition`
- `numeric_invariant`
- `event_state_correspondence`
- `bounded_temporal`
- `cross_module_causal_obligation`

Each class records whether it is supported, its canonical rule, required
evidence levels, and limitations.

## Construct Semantics

Constructs are classified by formal role:

- `scope NAME` is universal scope;
- authorization predicates are boolean premises;
- approval and confirmation predicates are workflow-state premises;
- comparisons are typed comparison premises or invariants;
- `NAME must succeed` is a success obligation;
- `NAME must reject before NAME` is rejection ordering;
- `state NAME must be value` is a post-state obligation;
- `emit NAME within NUMBER TIME_UNIT` is bounded event emission;
- `keep NAME COMP value` is a numeric invariant;
- cross-module causal text is bounded causal transition semantics.

## Refusal Rules

The reference declares refusal behavior:

- unsupported grammar is refused before semantic-tree construction;
- unsupported semantic-node kinds are refused before backend projection;
- ambiguous or review-bound constructs cannot be accepted without hash-bound
  review;
- bounded temporal semantics carry explicit bounds and cannot be labeled
  `PROVEN_INDUCTIVE`.

## Exit Criteria

This phase exits when:

- the semantics reference is executable and schema-backed;
- every supported DSL v3 claim class has a canonical rule;
- every construct documents evidence requirements and refusal behavior;
- tests assert the reference is populated and names refusal rules.

## Tests

`tests/test_milestone_group5.py` verifies the semantics reference covers all
claim classes and includes refusal rules.

## Out Of Scope

This phase does not make unsupported natural language acceptable. It documents
the controlled subset only.

