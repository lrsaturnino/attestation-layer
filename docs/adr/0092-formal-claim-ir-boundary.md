# ADR 0092: Formal Claim IR Boundary

## Status

Proposed

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

## Validation

`nlreq formal-claim` emits `FormalClaimLoweringReport`. Tests verify accepted
lowering for multiple claim classes and refused lowering for unsupported
semantics.

