# ADR 0049: Verification Budgets And Unknown Semantics

## Status

Proposed

## Context

Bounded verification is useful only when its bounds are explicit. Earlier phases
recorded some runner budgets, but proof consumers need a shared model for
requirement-class budgets, finite domains, abstraction levels, assumptions, and
the distinction between timeout, unknown, and inconclusive outcomes.

## Decision

Introduce verification budget policy, report, and budgeted outcome artifacts.

Budget reports record:

- requirement class;
- timeout;
- max depth;
- max states;
- finite domains;
- abstraction level;
- abstraction assumptions;
- assumptions hash;
- review blockers.

Outcome classification is explicit:

- valid under a ready budget approves;
- counterexample does not approve;
- timeout means budget exhaustion;
- unsupported or unreviewed assumptions are inconclusive;
- invalid or unrecognized backend status is unknown.

## Consequences

Bounded checks can be audited without hiding state-space limits. Reviewers can
see which abstractions were assumed and whether they were reviewed.

Future proof objects can link to these reports to preserve budget semantics
across closure and reproduction.
