# ADR 0124: Threat Model And TCB Review

## Status

Accepted

## Context

The threat model names TCB categories and threat scenarios. The extended
conclusion release needs that model converted into concrete release evidence:
artifact hashes and accepted residual risks.

## Decision

Add `ExtendedTcbReviewReport`.

The report consumes a `ThreatModelReport`, required release artifact hashes,
and accepted residual risks. It blocks when required release artifacts are
missing or when residual risks remain unaccepted.

## Rationale

Security review should not be a prose-only assertion. Binding TCB review to
release artifact hashes and residual-risk acceptance makes the release claim
auditable.

## Consequences

Positive:

- Release certification can require concrete TCB evidence.
- Evidence attack scenarios are represented in machine-readable output.
- Residual risk acceptance is explicit.

Negative:

- Release managers must keep artifact hashes and risk acceptance current.

## Validation

`tests/test_milestone_group9.py` verifies complete TCB review and blocking for
missing release artifacts or unaccepted residual risks.
