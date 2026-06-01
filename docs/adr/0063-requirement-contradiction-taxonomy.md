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

Operational rules:

- Deterministic contradiction checks run before backend execution.
- Contradictions include stable codes, node IDs, and source spans when
  available.
- Backend timeout, unsupported, and tool-error outcomes remain explicit and do
  not approve a requirement.
- Backend counterexamples are represented as contradiction records without
  converting bounded evidence into proof.

Rejected alternatives:

- A generic invalid status was rejected because reviewers need actionable
  contradiction classes.
- Running the formal backend before cheap deterministic contradictions was
  rejected because deterministic blockers are clearer and faster.

Validation:

- The self-consistency report schema captures deterministic and backend
  outcomes in one artifact.
- Benchmarks can assert contradiction codes independently from backend
  availability.

## Consequences

Contradictions become explainable and benchmarkable. Unknown classes remain
unsupported rather than being accepted.
