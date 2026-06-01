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
text artifact with old and new hashes.

## Consequences

Ambiguity resolution becomes auditable. Previous controlled versions remain
available for comparison.
