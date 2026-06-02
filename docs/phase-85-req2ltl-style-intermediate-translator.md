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

## Implementation Specification

### Inputs

The translator consumes approved or otherwise trusted controlled DSL v3 text,
plus a requirement ID and title. It does not consume raw free-form prose
directly. Free-form intake remains the responsibility of the phase 47-49 intake
and approval workflow.

### Outputs

The output is `SemanticTranslationReport`.

For accepted translations, the report includes:

- validated `RequirementIRV2`;
- `FormalClaimLoweringReport`;
- semantic-tree hash;
- formal-claim hash;
- stage records for canonicalization, semantic parsing, and formal-claim
  lowering.

For refused translations, the report includes:

- stable refusal code;
- syntactic validity flag;
- ambiguity or repair findings;
- clarification questions;
- stage records showing where the pipeline stopped.

### Stage Semantics

`canonicalize` records the hash of controlled text after deterministic DSL v3
canonicalization.

`parse_semantic_tree` records the hash of the semantic IR tree when parsing
succeeds. Parser failures become `NLR-PARSE-UNSUPPORTED`.

`lower_formal_claim` records the formal-claim hash when lowering succeeds and
propagates formal-claim refusal codes when it does not.

### Decision Rules

`result == "accepted"` only when parsing succeeds and formal-claim lowering
returns `lowered`.

`result == "refused"` when parsing fails or formal-claim lowering refuses.

`result == "needs_review"` is reserved for future semantic steps that can
produce a reviewed-but-not-refused artifact. It must not be used as a silent
fallback for parser failures.

### Determinism Rules

Running the pipeline twice over the same controlled text, requirement ID, and
title must produce the same stage hashes, semantic-tree hash, and formal-claim
hash. Tool timestamps or environment metadata must not enter those hashes.

## Exit Criteria

This phase exits when:

- accepted controlled text produces semantic IR and formal claim IR;
- unsupported text produces structured refusal;
- stage records and hashes are deterministic;
- repair questions are available for refused translation;
- tests cover accepted and refused translation.

## Tests

`tests/test_milestone_group8.py` verifies accepted translation and unsupported
text refusal through the CLI and direct API.

## Out Of Scope

This phase does not trust free-form natural language directly. Free-form intake
still requires the existing controlled rewrite approval path.
