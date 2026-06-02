# ADR 0096: Clarification And Repair Protocol

## Status

Proposed

## Context

Structured refusal without next actions makes requirement iteration slow and
encourages users to bypass the gate. Translation and agreement failures need a
source-span-aware repair artifact.

## Decision

Introduce `TranslationRepairReport` with highlights, prompts, refusal code,
decision, and next actions.

Repair reports can consume semantic translation reports, semantic agreement
reports, or both.

## Rejected Alternatives

Returning only exceptions or CLI stderr was rejected because CI and product
surfaces need stable JSON.

Automatically rewriting controlled text was rejected because it can silently
change meaning without review.

## Consequences

Users get actionable repair prompts. The system still requires corrected
controlled text or reviewer approval before acceptance.

## Validation

`nlreq translation-repair` emits the repair report. Tests verify parse-refusal
repair prompts.

