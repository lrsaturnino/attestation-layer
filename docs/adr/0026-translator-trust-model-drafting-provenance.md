# ADR 0026: Translator Trust Model, Drafting Provenance, And Deterministic Lowering

## Status

Proposed

## Context

The roadmap needs a bridge from human prose to controlled DSL v2 and then into a
formal target. The risk is letting a rewrite model, translator, or lowering
step silently become authoritative.

Existing package artifacts already reserve space for original text,
source-diff, controlled-text approval, and review records. Phase 23 turns that
trust model into executable artifacts for the DSL v2 path.

## Decision

Drafting is advisory. A draft artifact records original text, suggested
controlled text, diff, prompt/model metadata, timestamp, and approval state.
Unapproved drafts cannot be parsed into IR.

Approval is explicit and recorded with reviewer and timestamp. Only approved
controlled text may enter the DSL v2 parser.

Lowering is deterministic. The first lowering target is a TLA-oriented skeleton
artifact from `RequirementIRV2`. Unsupported semantic nodes refuse with node id,
kind, source span, and reason. The translator must not silently drop nodes or
invent missing semantics.

## Consequences

The project gains a safe front-door MVP without introducing a network LLM
dependency or trusting model output. Teams can preserve prose intent, review a
controlled rewrite, and lower approved compositional IR into a reviewable formal
artifact.

The tradeoff is that the first lowering artifact is narrow and review-oriented.
It is not model-checked proof.
