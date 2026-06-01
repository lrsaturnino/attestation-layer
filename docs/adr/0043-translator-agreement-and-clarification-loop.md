# ADR 0043: Translator Agreement And Clarification Loop

## Status

Proposed

## Context

The verification pipeline depends on a formalized requirement `R`, but
translation from controlled or natural language is not itself proof. A single
translator can choose the wrong action, predicate, temporal bound, or obligation
shape and still emit a syntactically valid IR. Downstream solvers would then
verify the wrong claim.

The roadmap requires multiple translation strategies, structural comparison,
deterministic refusal on material disagreement, and clarification output for
reviewers.

## Decision

Introduce a translator agreement report.

Each candidate records:

- translator id;
- translation method: deterministic, manual, or LLM;
- compositional IR candidate;
- optional approval;
- provenance metadata.

The agreement gate compares structural signatures of semantic IR, excluding
provenance and source-span noise. The report:

- passes as `agreed` only when at least two candidates structurally match and no
  trust blocker exists;
- returns `disagreed` when the first material structural difference is found;
- emits a clarification question for each disagreement;
- returns `needs_review` when agreement exists but trust requirements are not
  met, such as an unapproved LLM candidate.

LLM-originated candidates cannot auto-approve. Review approval is required
before they can participate in an agreed report.

## Consequences

Downstream verification now has a deterministic translation gate. Solver-backed
checks can fail because of formal artifacts rather than silently inheriting a
single untrusted translation.

The comparison is structural, not a complete semantic equivalence proof. Future
phases can add richer equivalence checks, but the refusal and clarification
contract remains stable.
