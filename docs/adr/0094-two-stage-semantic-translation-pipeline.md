# ADR 0094: Two-Stage Semantic Translation Pipeline

## Status

Accepted

## Context

The translator workbench can produce requirement IR candidates, but the
extended conclusion target needs a formal claim artifact before backend
projection.

## Decision

Adopt a two-stage deterministic pipeline:

```text
controlled DSL v3 text -> RequirementIRV2 semantic tree -> FormalClaim
```

Record the process in `SemanticTranslationReport` with stage status, hashes,
syntax validity, formal claim hash, refusal code, and clarification questions.

The pipeline is exposed by `nlreq semantic-translate`.

## Decision Details

The pipeline stages are:

1. Canonicalize approved controlled DSL v3 text.
2. Parse canonical text into `RequirementIRV2`.
3. Lower semantic IR into `FormalClaimLoweringReport`.

Each stage records status, message, and artifact hash when an artifact exists.
Accepted translation requires successful semantic parsing and successful
formal-claim lowering.

Parser failures produce `NLR-PARSE-UNSUPPORTED`. Formal-claim lowering failures
propagate the lowering refusal code. The report includes clarification questions
for refused translation so repair UX can work without parsing stderr.

## Invariants

- Raw free-form prose is not accepted by this pipeline.
- The pipeline does not silently repair controlled text.
- The same input text, requirement ID, and title produce stable stage hashes.
- LLM or workbench candidates remain untrusted until deterministic parsing,
  formal-claim lowering, agreement, and review policy allow selection.

## Rejected Alternatives

Direct natural-language-to-backend output was rejected because it bypasses
controlled semantics and source-span provenance.

Direct semantic-tree-to-backend projection was rejected because milestone group 8
needs backend-neutral semantic agreement.

## Consequences

Translation reports become auditable and can fail before backend work starts.
Free-form requirements still need the existing controlled rewrite approval
path.

The system gains an explicit artifact for measuring translation quality before
formal backend execution. It also means downstream gates can block on
translation refusal without invoking source adapters or model checkers.

## Compatibility

The decision is additive. Existing DSL v2 and structural translator workbench
commands remain available. Group-8 semantic translation consumes DSL v3 text and
emits newer schema-backed reports.

## Validation

`nlreq semantic-translate` emits the report. Tests verify accepted controlled
translation, refused unsupported text, and deterministic stage hashes.
