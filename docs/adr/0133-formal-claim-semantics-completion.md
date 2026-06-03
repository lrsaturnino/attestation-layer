# ADR 0133: Formal Claim Semantics Completion

## Status

Accepted

## Context

Group 11 requires exact semantics for every supported formal claim class before
real backend execution. Earlier formal-claim IR recorded fragments and required
evidence, but the release path needed a machine-readable completion reference
that proves all supported classes have explicit semantics and unsupported
behavior.

## Decision

Add `FormalClaimSemanticsCompletionReference` in `nlreq.formal_claim` and expose
it through `nlreq formal-claim-semantics`.

The reference covers all DSL v3 claim classes:

- authorization precondition;
- state precondition;
- state postcondition;
- numeric invariant;
- event/state correspondence;
- bounded temporal property;
- cross-module causal obligation.

Each entry records exact semantics, supported fragment kinds, required evidence,
backend projection obligations, trace validation obligations, limitations, and
unsupported behavior.

## Invariants

- Unsupported fragments refuse before backend dispatch.
- Required evidence is declared, not produced, by formal-claim semantics.
- Bounded temporal semantics must retain explicit bounds.
- Missing claim-class coverage makes the reference `incomplete`.

## Consequences

Backends and release gates can reason over a stable semantics matrix. Any new
claim class must update the semantics reference, schema, docs, and tests.

## Validation

`tests/test_milestone_group11.py` validates reference completeness and CLI
emission.
