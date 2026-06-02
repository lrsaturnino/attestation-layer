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

## Implementation Specification

### Inputs

The semantics reference has no external input. It is generated from
`build_controlled_requirement_semantics_reference()` so docs, CLI output,
formal-claim lowering, and schema generation share one source of truth.

### Outputs

The output is `ControlledRequirementSemanticsReference`, with:

- `schema_version`;
- `dsl_version`;
- generated tool metadata;
- claim-class semantics;
- construct semantics;
- global refusal rules.

The CLI emits the same artifact through:

```bash
uv run nlreq controlled-semantics --out controlled-semantics.json
```

### Claim-Class Requirements

Every supported claim class must declare:

- `supported == true`;
- a canonical rule written in backend-neutral language;
- minimum evidence levels needed by later closure phases;
- limitations when the claim has bounded, trace, or cross-module semantics.

No claim class may imply `PROVEN_INDUCTIVE`. Inductive proof remains available
only from a proof-producing backend classified by the evidence boundary.

### Construct Requirements

Every construct entry must declare:

- the DSL fragment shape;
- the formal role it plays in a formal claim;
- its canonical meaning;
- allowed claim classes;
- required evidence when the construct introduces a stronger obligation;
- refusal behavior when syntax or semantics are unsupported.

The reference deliberately names unsupported behavior. Parser acceptance,
semantic lowering, and repair UX must be able to explain why a construct cannot
be accepted without inventing policy at runtime.

### Compatibility Rules

Changing a construct meaning is a semantics change, not a formatting change.
Such changes require updating this phase spec, ADR 0093, the generated schema
if needed, and golden tests that assert the new rule.

## Exit Criteria

This phase exits when:

- the semantics reference is executable and schema-backed;
- every supported DSL v3 claim class has a canonical rule;
- every construct documents evidence requirements and refusal behavior;
- tests assert the reference is populated and names refusal rules.

## Tests

`tests/test_milestone_group8.py` verifies the semantics reference covers all
claim classes and includes refusal rules.

## Out Of Scope

This phase does not make unsupported natural language acceptable. It documents
the controlled subset only.
