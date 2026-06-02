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

## Exit Criteria

This phase exits when:

- parse refusals produce repair prompts;
- unsupported formal fragments produce source-span highlights;
- semantic disagreement produces review prompts;
- resolved disagreement requires no further repair.

## Tests

`tests/test_milestone_group5.py` verifies repair prompts for unsupported text.

## Out Of Scope

This phase does not apply the repair automatically. It emits the artifact a
review or clarification workflow can consume.

