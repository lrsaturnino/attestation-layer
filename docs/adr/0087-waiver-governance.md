# ADR 0087: Gate Policy, Waiver Governance, And Exception Audit Semantics

## Status

Accepted

## Context

Real adoption needs exceptions for staged rollout, tool availability, and
temporary unknown outcomes. At the same time, waivers can destroy the value of a
hard gate if they silently convert blocked proof closure into success.

## Decision

Use gate policy and waiver schemas as the governance source of truth, and add
`nlreq.policy_governance` for waiver audit reports.

The audit blocks waivers when:

- the waiver is expired;
- policy does not allow waivers;
- expiration exceeds `max_duration_days`;
- policy requires reviewed hashes and none are supplied;
- the waiver is marked unsafe for hard-gate satisfaction.

Active waivers remain visible findings.

## Rationale

Waiver governance belongs beside policy evaluation rather than inside proof
closure. A proof object should remain blocked or open when evidence is missing;
a waiver records an external governance exception around that state.

## Consequences

Positive:

- Expired and out-of-policy waivers are first-class blockers.
- Hard-gate unsafe waivers cannot satisfy enforcement.
- Review hashes make waiver approval auditable.
- Waiver-dependent outcomes can be counted by benchmarks and release reports.

Negative:

- Current duration enforcement uses remaining duration from the audit timestamp;
  future schemas may add `created_at` for exact lifetime checks.
- Active waivers still require downstream reporting discipline to avoid being
  interpreted as proof closure.

## Alternatives Considered

- Let waivers directly change proof status. Rejected because that would hide
  missing evidence.
- Keep waivers as unstructured comments. Rejected because expiration, reviewer,
  and hash review need machine-readable audit.

## Validation

`tests/test_milestone_group6.py` covers active, expired, unsafe, over-duration,
and missing-reviewed-hash waiver outcomes.
