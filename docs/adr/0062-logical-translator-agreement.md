# ADR 0062: Logical Translator Agreement And Equivalence-Method Hierarchy

## Status

Proposed

## Context

Structural comparison catches many translator disagreements but also rejects
equivalent rewrites, such as reordered commutative predicates.

## Decision

Add a logical agreement report with an explicit method hierarchy:
normalized equality, alpha-renaming, commutative predicate equivalence, simple
SMT predicate equivalence, and bounded trace equivalence when witnesses exist.

Unsupported equivalence remains `needs_review` or `conflict`.

Operational rules:

- Candidate hashes are included in every logical agreement report.
- Comparisons are pairwise against the first candidate in the run.
- Any conflict makes the report conflict.
- Temporal equivalence without trace witnesses remains needs-review.
- Method limitations are reported with the artifact.

Rejected alternatives:

- Pure structural equality was rejected because it creates noisy manual review
  for equivalent reordered predicates and renamed scopes.
- General semantic equivalence was rejected for this phase because it would
  overclaim beyond supported fragments.

Validation:

- Supported equivalence methods are deterministic.
- Unsupported methods cannot return agreed.

## Consequences

Simple equivalent translations can proceed without manual clarification, while
unsupported semantic claims remain explicit.
