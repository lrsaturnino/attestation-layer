# ADR 0095: Semantic Agreement And Equivalence Profiles

## Status

Accepted

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

The agreement gate is exposed by `nlreq semantic-agreement`.

## Decision Details

The gate consumes `FormalClaimLoweringReport` candidates. Candidate hashes are
recorded in the report and used to bind reviewer resolution to the exact
candidate artifact selected.

Profiles are evaluated in this order:

1. canonical formal claim equality;
2. alpha identifier equivalence;
3. commutative claim equivalence.

If no profile proves equivalence, the comparison is a conflict. `unsupported`
is a failure profile, not a permissive fallback.

Reviewer resolution may select one candidate after disagreement. If the
resolution supplies a selected candidate hash, it must match the report's
candidate hash. If omitted, the report derives the selected hash from the
candidate artifact and records it.

## Invariants

- Agreement requires at least two candidates.
- Every candidate must target the same requirement ID.
- Every candidate must have lowered to formal claim IR.
- Conflicts block acceptance unless a valid approved resolution is present.
- Reviewer resolution records a human choice; it does not prove equivalence.

## Rejected Alternatives

Using only structural IR comparison was rejected because it cannot express
formal-claim-level profiles.

Claiming general formula equivalence was rejected because milestone group 8 does not
include a proof engine for arbitrary formulas.

## Consequences

Translator disagreement now blocks at the formal claim layer. Reviewer
resolution is explicit and auditable.

Hash binding makes resolution stable across artifact updates: if a selected
candidate changes, the old resolution no longer matches the candidate hash.

## Compatibility

Existing callers that provide only `selected_candidate_id` continue to work; the
report derives and records the selected hash. Callers that provide an explicit
incorrect hash remain blocked.

## Validation

`nlreq semantic-agreement` emits `SemanticAgreementReport`. Tests verify
commutative agreement, missing-candidate blockers, conflict blocking, reviewer
resolution, and incorrect-hash rejection.
