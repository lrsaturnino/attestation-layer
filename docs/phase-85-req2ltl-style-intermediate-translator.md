# Phase 85 Req2LTL-Style Intermediate Translator

Phase 85 adds a deterministic two-stage translation pipeline:

```text
controlled text -> semantic IR -> formal claim IR
```

## Purpose

The previous translator workbench produced requirement IR candidates. This
phase adds a formal-claim translation report that records the semantic tree,
formal claim lowering, hashes, stages, refusal codes, and clarification prompts.

## Contracts

`src/nlreq/semantic_translation.py` defines:

- `SemanticTranslationReport`
- `SemanticTranslationStage`
- `SemanticAmbiguityFinding`

Schema:

- `schemas/semantic-translation-report.schema.json`

CLI:

```bash
uv run nlreq semantic-translate requirement.nlreq3 \
  --requirement-id REQ-001 \
  --title "Requirement title" \
  --out semantic-translation.json
```

## Pipeline

Stage 1 canonicalizes and hash-binds the controlled text.

Stage 2 parses controlled DSL v3 into `RequirementIRV2`.

Stage 3 lowers the semantic tree into `FormalClaimLoweringReport`.

The report includes:

- `translation_id`;
- `requirement_id`;
- final result: `accepted`, `refused`, or `needs_review`;
- syntactic validity;
- semantic-tree hash;
- formal-claim hash when present;
- stable refusal code when refused;
- optional `RequirementIRV2`;
- optional formal claim lowering report;
- stage records;
- input hashes.

## Refusal Behavior

Parser failures produce `NLR-PARSE-UNSUPPORTED` and a repair question. Formal
claim lowering failures propagate their refusal code, such as
`NLR-SEMANTIC-UNSUPPORTED`.

The translator does not silently repair unsupported text. A user must submit a
corrected controlled requirement or a reviewed controlled rewrite.

## Exit Criteria

This phase exits when:

- accepted controlled text produces semantic IR and formal claim IR;
- unsupported text produces structured refusal;
- stage records and hashes are deterministic;
- repair questions are available for refused translation;
- tests cover accepted and refused translation.

## Tests

`tests/test_milestone_group5.py` verifies accepted translation and unsupported
text refusal through the CLI and direct API.

## Out Of Scope

This phase does not trust free-form natural language directly. Free-form intake
still requires the existing controlled rewrite approval path.

