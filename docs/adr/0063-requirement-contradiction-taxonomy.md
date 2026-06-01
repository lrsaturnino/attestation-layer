# ADR 0063: Requirement Contradiction Taxonomy And Self-Consistency Semantics

## Status

Proposed

## Context

Self-consistency needs stable contradiction categories. A generic invalid result
does not give reviewers enough information to fix the requirement.

## Decision

Extend self-consistency with contradiction codes for direct opposite
predicates, impossible comparisons, mutually exclusive states, overlapping
opposite obligations, temporal impossibility, numeric bound conflicts, and
duplicate obligation conflicts.

Formal backend counterexamples remain a separate contradiction source.

## Consequences

Contradictions become explainable and benchmarkable. Unknown classes remain
unsupported rather than being accepted.
