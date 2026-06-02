# Phase 87 Translation Repair And Clarification UX

Phase 87 turns translation failures and agreement blockers into actionable
repair reports.

## Purpose

Refusal is useful only if it tells a user what to change. This phase adds a
source-span-aware repair artifact for parse refusals, formal-claim lowering
refusals, and semantic agreement disagreements.

## Contracts

`src/nlreq/translation_repair.py` defines:

- `TranslationRepairReport`
- `TranslationRepairHighlight`
- `TranslationRepairPrompt`

Schema:

- `schemas/translation-repair-report.schema.json`

CLI:

```bash
uv run nlreq translation-repair \
  --translation-report semantic-translation.json \
  --agreement-report semantic-agreement.json \
  --out translation-repair.json
```

## Report Shape

The report records:

- requirement ID;
- decision: `no_repair_needed`, `repair_required`, or `review_required`;
- refusal code;
- highlights with source spans or no-span reasons;
- prompts;
- next actions.

## Repair Decisions

`repair_required` is used for parse or lowering refusals that require corrected
controlled text.

`review_required` is used for semantic agreement blockers that require a
reviewer decision.

`no_repair_needed` is used when translation is accepted or disagreement has
already been resolved by review.

## Source-Span Policy

When source spans exist, prompts carry them. Parser-level failures may not have
stable spans; those findings include `no_span_reason` instead of fabricating a
span.

## Implementation Specification

### Inputs

Repair reports may consume:

- `SemanticTranslationReport`;
- `SemanticAgreementReport`;
- or both.

At least one input is required. The repair module does not call a translator,
parser, model, or backend; it renders actionable follow-up from existing
reports.

### Outputs

The output is `TranslationRepairReport`, with:

- requirement ID;
- decision;
- refusal code when one is available;
- highlights;
- prompts;
- next actions.

Highlights name the failing stage and affected source spans when available.
Prompts are UI-ready clarification or review questions.

### Decision Rules

`repair_required` is emitted when a translation failure can be addressed by
submitting corrected controlled text or a reviewed controlled rewrite.

`review_required` is emitted when semantic agreement cannot accept the
candidate set without reviewer selection.

`no_repair_needed` is emitted when translation is accepted, no failing input is
present, or agreement was resolved by review.

### Prompt Semantics

Parser refusals ask the user to rewrite into supported DSL v3 form.

Formal-claim unsupported fragments ask which supported controlled construct
should replace the fragment and carry fragment-level next actions.

Semantic-agreement conflicts ask which candidate preserves the controlled
requirement intent and require hash-bound reviewer selection.

### Non-Silent-Rewrite Rule

The repair phase never edits controlled text. Any corrected text must re-enter
intake, review, translation, and agreement as a new auditable artifact.

## Exit Criteria

This phase exits when:

- parse refusals produce repair prompts;
- unsupported formal fragments produce source-span highlights;
- semantic disagreement produces review prompts;
- resolved disagreement requires no further repair.

## Tests

`tests/test_milestone_group8.py` verifies repair prompts for unsupported text
and no-op repair after reviewed agreement resolution.

## Out Of Scope

This phase does not apply the repair automatically. It emits the artifact a
review or clarification workflow can consume.
