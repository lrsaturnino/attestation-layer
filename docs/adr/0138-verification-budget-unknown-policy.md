# ADR 0138: Verification Budget And Unknown Policy

## Status

Accepted

## Context

Model checking can exhaust time, depth, state, memory, or abstraction budgets.
Those outcomes are not proof failures and not semantic refusals, but they must
not approve closure.

## Decision

Extend `BudgetedVerificationOutcome` with `closure_effect` and an explicit
unknown policy string while preserving existing outcomes.

Outcome policy:

- ready budget + valid backend -> `valid`, `closure_effect: allow`;
- counterexample -> `counterexample`, `closure_effect: block`;
- timeout -> `timeout`, `closure_effect: block`;
- unsupported, needs-review, or unreviewed assumptions -> `inconclusive`,
  `closure_effect: review`;
- invalid backend status -> `unknown`, `closure_effect: block`.

## Consequences

Release gates can distinguish exhausted budget from semantic refusal and can
choose policies such as "no unknowns" for selected release claims.

## Validation

Group 11 tests verify closure effects across valid, timeout, unknown, and
review-bound cases.
