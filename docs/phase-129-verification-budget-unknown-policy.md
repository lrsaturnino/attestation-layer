# Phase 129 - Verification Budget And Unknown Policy

## Status

Implemented.

## Purpose

Prevent false confidence when verification exhausts time, depth, state, memory,
or abstraction budgets. Budget exhaustion and invalid backend outcomes must be
non-approving and distinct from semantic refusal.

## Implementation

Primary module:

- `src/nlreq/verification_budget.py`

Schemas:

- `schemas/verification-budget-policy.schema.json`
- `schemas/verification-budget-report.schema.json`
- `schemas/budgeted-verification-outcome.schema.json`

CLI:

```bash
uv run nlreq verification-budget \
  --requirement-ir requirement.ir.json \
  --requirement-class system_compatibility \
  --assumption A1:wallet:finite-wallet-set:reviewed \
  --out budget.json
```

## Contracts

- Reviewed assumptions are required before a budget is `ready`.
- Unreviewed assumptions produce `needs_review`.
- `valid` can approve only when the budget report is ready.
- `counterexample`, `timeout`, `unknown`, and `inconclusive` never approve.
- The budgeted outcome records `closure_effect` as `allow`, `block`, or
  `review`.
- Timeout is not a semantic refusal; it is a non-approving budget outcome.

## Unknown Policy

Invalid backend statuses are classified as `unknown`. Unsupported and
review-bound cases classify as `inconclusive` with `closure_effect: review`.
Timeout remains its own outcome so release reports can distinguish exhausted
budget from malformed backend execution.

## Verification

`tests/test_milestone_group11.py` verifies closure effects for valid, timeout,
unknown, and review-bound cases.
