# Phase 40 Verification Budget And Abstraction

Phase 40 makes bounded verification limits explicit. Requirement classes now map
to concrete timeout, depth, state, finite-domain, and abstraction settings, and
abstraction assumptions are hash-addressed and review-gated.

## Purpose

The phase lets the Attestation Layer say:

```text
This requirement was checked under this budget and these reviewed assumptions;
timeout, unknown, and inconclusive outcomes are not approval.
```

It does not say:

```text
Bounded checking is inductive proof.
Unreviewed abstraction assumptions are trusted.
Budget exhaustion can pass.
```

## Implementation Scope

Phase 40 implementation includes:

- verification budget policy, report, and outcome schemas;
- default budgets by requirement class;
- finite domain and abstraction-level metadata;
- review-gated abstraction assumptions;
- assumptions hash;
- outcome classifier for valid, counterexample, timeout, unknown, and
  inconclusive statuses;
- CLI command for `verification-budget`;
- tests for reviewed assumptions, unreviewed blockers, timeout/unknown
  classification, and CLI output.

## Evidence Semantics

Only a valid backend result under a ready budget is approving. Timeout,
counterexample, unknown, and inconclusive outcomes are non-approving. Unreviewed
assumptions force `needs_review`.

## Success Criterion

Phase 40 succeeds when:

- every budget report records bounds, finite domains, abstraction level, and
  assumptions;
- timeout and unknown are distinct;
- abstraction assumptions are reviewable and hash-addressed;
- budget exhaustion cannot approve.

## Boundary

This phase does not choose better abstractions automatically. It makes the
chosen budget and assumptions explicit so later proof objects can preserve them.
