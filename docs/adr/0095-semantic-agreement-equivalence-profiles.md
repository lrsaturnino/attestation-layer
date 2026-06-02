# ADR 0095: Semantic Agreement And Equivalence Profiles

## Status

Proposed

## Context

Structural translator agreement is useful but insufficient. Equivalent
translations can differ in premise order, while conflicting translations can be
structurally plausible.

## Decision

Compare formal claim candidates with explicit semantic agreement profiles:

1. canonical formal claim equality;
2. alpha identifier equivalence;
3. commutative claim equivalence;
4. unsupported.

Acceptance is allowed only when candidates agree under a supported profile or
when a reviewer resolves a disagreement with a hash-bound selected candidate.

## Rejected Alternatives

Using only structural IR comparison was rejected because it cannot express
formal-claim-level profiles.

Claiming general formula equivalence was rejected because Milestone 5 does not
include a proof engine for arbitrary formulas.

## Consequences

Translator disagreement now blocks at the formal claim layer. Reviewer
resolution is explicit and auditable.

## Validation

`nlreq semantic-agreement` emits `SemanticAgreementReport`. Tests verify
commutative agreement, conflict blocking, and reviewer resolution.

