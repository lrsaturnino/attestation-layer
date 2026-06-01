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
match the proposal. The approval also binds the original intake hash, so a
controlled rewrite approved for one human request cannot be replayed against a
different request.

Operational rules:

- Free-form intake is not parser input.
- Proposals may come from manual, rule-based, or LLM producers, but all remain
  untrusted until approval.
- Approvals bind proposal ID, original text hash, controlled text hash, and
  diff hash.
- Rejection is a first-class decision and cannot be parsed.

Rejected alternatives:

- Directly parsing free-form text was rejected because it makes semantic rewrite
  invisible.
- Storing only the final controlled text was rejected because reviewers need the
  original text and diff to audit semantic movement.

Validation:

- `controlled_text_for_parsing` is the parser-facing guard.
- The CLI creates proposal, approval, and diff artifacts without invoking a
  trusted parser path.

## Consequences

LLM rewrites can be used as suggestions without becoming trusted evidence.
Reviewers can audit exactly what text was approved.
