# ADR 0056: Free-Form Intake, Controlled Rewrite, And Approval Semantics

## Status

Proposed

## Context

Free-form natural language is useful product input, but it cannot be trusted as
the direct source of formal artifacts. Silent semantic rewrite would move the
human review point without consent.

## Decision

Represent intake as three artifacts:

- original free-form intake;
- controlled rewrite proposal with diff and producer metadata;
- hash-bound approval or rejection.

Parsing a rewrite requires an approval whose controlled-text hash and diff hash
match the proposal.

## Consequences

LLM rewrites can be used as suggestions without becoming trusted evidence.
Reviewers can audit exactly what text was approved.
