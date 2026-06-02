# ADR 0096: Clarification And Repair Protocol

## Status

Accepted

## Context

Structured refusal without next actions makes requirement iteration slow and
encourages users to bypass the gate. Translation and agreement failures need a
source-span-aware repair artifact.

## Decision

Introduce `TranslationRepairReport` with highlights, prompts, refusal code,
decision, and next actions.

Repair reports can consume semantic translation reports, semantic agreement
reports, or both.

The repair artifact is exposed by `nlreq translation-repair`.

## Decision Details

Repair reports turn existing failures into UI-ready next actions. They do not
run translation, comparison, or backend verification.

The report records:

- requirement ID;
- decision;
- refusal code;
- highlights;
- prompts;
- next actions.

Highlights carry source spans when the upstream report provides them. When no
stable span exists, the highlight records `no_span_reason` instead of inventing
a location.

Parser failures create rewrite prompts. Formal-claim unsupported fragments
create construct-replacement prompts. Semantic-agreement conflicts create
review-selection prompts.

## Invariants

- Repair reports never automatically edit controlled text.
- Corrected text must re-enter intake, review, translation, and agreement.
- Agreement that is already resolved by review produces `no_repair_needed`.
- Agreement blockers produce `review_required`, not `repair_required`.

## Rejected Alternatives

Returning only exceptions or CLI stderr was rejected because CI and product
surfaces need stable JSON.

Automatically rewriting controlled text was rejected because it can silently
change meaning without review.

## Consequences

Users get actionable repair prompts. The system still requires corrected
controlled text or reviewer approval before acceptance.

Product surfaces can render repair reports without coupling to parser
exceptions, formal-claim internals, or agreement comparison implementation.

## Compatibility

The repair report is additive. Existing refusal reports remain valid; group-8
translation repair adds a more specialized artifact for semantic translation
failure modes.

## Validation

`nlreq translation-repair` emits the repair report. Tests verify parse-refusal
repair prompts and no-op behavior after reviewed agreement resolution.
