# ADR 0061: Bidirectional Provenance Graph And Clarification Protocol

## Status

Proposed

## Context

Users need to understand which text produced which IR node, formal fragment, or
refusal. Clarification should target exact spans rather than rewrite whole
requirements opaquely.

## Decision

Introduce a provenance graph with text-span, IR-node, formal-fragment, and
refusal-reason nodes. Clarification requests target paths or nodes.
Clarification responses apply span replacements and produce a new controlled
text artifact with old and new hashes, target range, and replacement text.

Operational rules:

- Text-to-IR edges use `parsed_to`.
- IR-to-formal edges use `lowered_to`.
- IR-to-refusal edges use `refuses`.
- Clarification responses are patch-like artifacts over explicit character
  spans.
- Clarification requests copy disagreement source spans when upstream
  translation agreement can identify them.
- Previous controlled text versions remain hash-addressed after clarification.

Rejected alternatives:

- Whole-document clarification rewrites were rejected because they obscure the
  exact ambiguity being resolved.
- One-way provenance was rejected because product surfaces need both "why did
  this formal node exist?" and "where did this text go?" queries.

Validation:

- Provenance graph construction walks every semantic IR node.
- Clarification application validates target ranges before producing new text.
- A clarification target that exceeds the controlled text length is rejected.

## Consequences

Ambiguity resolution becomes auditable. Previous controlled versions remain
available for comparison.
