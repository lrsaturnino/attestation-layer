# ADR 0092: Formal Claim IR Boundary

## Status

Accepted

## Context

`RequirementIRV2` preserves controlled-language structure. Backend projections
need a narrower artifact with explicit formal semantics, deterministic hashes,
evidence requirements, and refusal behavior.

## Decision

Introduce backend-neutral formal claim IR in `src/nlreq/formal_claim.py`.

Formal claim IR is a sibling artifact derived from `RequirementIRV2`; it does
not replace compositional IR. It records scope, premises, action, obligations,
canonical formula, source spans, node mapping, required evidence, and semantic
profile.

Unsupported semantic fragments refuse lowering with
`NLR-SEMANTIC-UNSUPPORTED`. No partial formal claim is emitted for unsupported
semantics.

The formal claim artifact exposes:

- `FormalClaim`;
- `FormalClaimFragment`;
- `FormalClaimLoweringReport`;
- `FormalClaimUnsupportedFragment`;
- `FormalClaimSemanticsRule`;
- `nlreq formal-claim`.

## Decision Details

Formal claim IR is a backend-neutral semantic contract. It is narrower than
`RequirementIRV2` and more explicit than backend-specific TLA, SMT, or trace
artifacts.

Every lowered claim records:

- claim class and semantics profile;
- source IR hash;
- scope, premise, action, and obligation fragments;
- canonical formula;
- source spans;
- semantic-node-to-fragment map;
- required evidence labels;
- canonical signature hash metadata.

The lowering code may derive required evidence from the controlled semantics
reference, but it must not create backend evidence. Later proof and evidence
boundary phases decide whether required evidence has actually been produced.

## Invariants

- Unsupported semantic nodes produce refusal before formal claim creation.
- Fragment IDs are stable over semantic-node IDs.
- Source spans are preserved when supplied by the parser.
- Required evidence cannot include `PROVEN_INDUCTIVE` unless a later
  proof-producing backend emits that evidence.
- Formal-claim canonical strings are comparison aids, not proof terms.

## Rejected Alternatives

Embedding formal claim fields directly inside `RequirementIRV2` was rejected
because requirement IR should remain a controlled-language semantic tree.

Projecting directly from requirement IR to TLA or SMT was rejected because it
couples translation semantics to backend syntax and makes semantic agreement
harder to evaluate.

## Consequences

Backends consume a smaller, canonical artifact. Evidence policies can refer to
formal claim fragments before any backend runs. The project now has another
schema-backed artifact to keep stable.

The additional artifact also creates a stricter compatibility boundary: changes
to fragment roles, kinds, operators, or evidence derivation require schema
regeneration and group-8 tests.

## Compatibility

The decision is additive. Existing `RequirementIRV2` artifacts remain valid and
can still be consumed by older projection paths. New group-8 translation and
agreement paths consume formal claim reports.

## Validation

`nlreq formal-claim` emits `FormalClaimLoweringReport`. Tests verify accepted
lowering for multiple claim classes, refused lowering for unsupported
semantics, and absence of partial formal claims on refusal.
