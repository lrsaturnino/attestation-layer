# ADR 0094: Two-Stage Semantic Translation Pipeline

## Status

Proposed

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

## Rejected Alternatives

Direct natural-language-to-backend output was rejected because it bypasses
controlled semantics and source-span provenance.

Direct semantic-tree-to-backend projection was rejected because Milestone 5
needs backend-neutral semantic agreement.

## Consequences

Translation reports become auditable and can fail before backend work starts.
Free-form requirements still need the existing controlled rewrite approval
path.

## Validation

`nlreq semantic-translate` emits the report. Tests verify accepted controlled
translation and refused unsupported text.

