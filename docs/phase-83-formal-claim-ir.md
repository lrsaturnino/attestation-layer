# Phase 83 Formal Claim IR

Phase 83 introduces the backend-neutral formal-claim layer between
compositional requirement IR and backend-specific projections.

## Purpose

The existing `RequirementIRV2` semantic tree preserves controlled-language
structure, but backend projection code needs a narrower artifact with explicit
claim semantics. Formal claim IR is that artifact. It names the supported claim
class, canonical formula, source-node mapping, required evidence, and
unsupported fragments before any TLA, SMT, or trace-specific projection runs.

## Contracts

`src/nlreq/formal_claim.py` defines:

- `FormalClaim`
- `FormalClaimFragment`
- `FormalClaimLoweringReport`
- `FormalClaimUnsupportedFragment`
- `FormalClaimSemanticsRule`

Schemas:

- `schemas/formal-claim.schema.json`
- `schemas/formal-claim-lowering-report.schema.json`

CLI:

```bash
uv run nlreq formal-claim requirement.ir.json --out formal-claim.json
```

## Formal Claim Shape

Each formal claim records:

- `claim_id` and `requirement_id`;
- `source_ir_version` and `source_ir_hash`;
- `claim_class` from the controlled DSL v3 requirement class;
- `semantics_profile`, for example `dsl-v3/state_precondition`;
- scope fragments;
- premise fragments;
- one action fragment;
- obligation fragments;
- a deterministic `canonical_formula`;
- source spans from controlled text;
- `node_map` from semantic IR nodes to formal fragments;
- required evidence levels.

Fragments are intentionally small. They cover scope, predicates, comparisons,
membership, action, success, rejection ordering, post-state equality, event
emission, numeric invariants, and causal transitions.

## Lowering Rules

Formal claim lowering accepts only supported semantic-node kinds. Unsupported
nodes produce a `refused` lowering report with `NLR-SEMANTIC-UNSUPPORTED`.
There is no partial formal claim for unsupported semantics.

Supported premise nodes:

- `predicate`
- `membership`
- `eq`
- `neq`
- `lt`
- `lte`
- `gt`
- `gte`

Supported obligation nodes:

- `predicate` with `succeeds`
- `before` containing rejection ordering
- `post_state`
- `within` containing event emission
- `within` containing causal transition
- comparison nodes for invariants

## Evidence Rules

Required evidence is derived from controlled claim-class semantics:

- authorization preconditions require `CONSISTENCY_CHECKED` and
  `STATICALLY_RESOLVED`;
- state preconditions require `CONSISTENCY_CHECKED`;
- state postconditions require `CONSISTENCY_CHECKED` and `TRACE_VALIDATED`;
- numeric invariants require `CONSISTENCY_CHECKED` and `SMT_CHECKED`;
- temporal/event claims require `BOUNDED_CHECKED` and `TRACE_VALIDATED`.

No formal claim lowering emits backend evidence. It only states what evidence
must later be produced.

## Implementation Specification

### Inputs

The lowering input is a validated `RequirementIRV2` artifact with
`ir_version == "0.2"` and a semantic root that declares a DSL v3
`requirement_class` in `semantic_ir.metadata`.

The lowering path is deterministic. It must not inspect source files, backend
state, benchmark results, or reviewer comments. Those artifacts are consumed by
later phases.

### Outputs

The output is always `FormalClaimLoweringReport`.

When `result == "lowered"`, the report includes exactly one `FormalClaim`.
When `result == "refused"`, `formal_claim` is absent and
`unsupported_fragments` explains why no backend-neutral claim can be trusted.

The report records:

- the source IR hash;
- input hashes for source IR and, when lowered, the formal claim;
- semantics rules used during lowering;
- stable refusal code `NLR-SEMANTIC-UNSUPPORTED` for unsupported semantics.

### Fragment Mapping

Fragment identifiers use `formal.<semantic_node_id>` so source-node mapping is
stable across schema generation and CLI output. `node_map` maps semantic-node
IDs to formal fragment IDs and must include scope, premise, action, and
obligation fragments.

The canonical formula is a display and comparison artifact. It is not a proof
term and must not be used to bypass typed fragment checks.

### Decision Rules

Lowering succeeds only when:

- the requirement class is one of the controlled semantics claim classes;
- every traversed semantic node is in the supported kind set;
- premises lower to predicate, comparison, or membership fragments;
- obligations lower to success, rejection order, post-state, event emission,
  invariant, or causal transition fragments;
- temporal obligations carry explicit bounds.

Lowering refuses before constructing a formal claim when any semantic node is
unsupported. There is no partially lowered formal claim because downstream
agreement could otherwise compare incomplete formulas.

## Failure Behavior

Failure modes are stable:

- missing or unknown `requirement_class` refuses lowering;
- unsupported semantic-node kinds refuse lowering;
- unsupported obligation or premise shapes raise deterministic validation
  errors during lowering;
- refused lowering includes source spans when available and next actions.

## Exit Criteria

This phase exits when:

- at least three controlled claim classes lower to formal claim IR;
- formal fragments retain source spans and node mappings;
- unsupported fragments refuse without partial formal claims;
- schemas are generated and committed;
- tests cover accepted and refused outcomes.

## Tests

`tests/test_milestone_group8.py` verifies lowering for authorization,
state-precondition, numeric-invariant, and event-state claim classes.
It also verifies unsupported semantic nodes are refused without partial formal
claims.

## Out Of Scope

This phase does not project to TLA or SMT. It also does not claim formal
compatibility with system specs; those are Milestone 6 concerns.
