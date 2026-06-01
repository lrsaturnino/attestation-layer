# ADR 0062: Logical Translator Agreement And Equivalence-Method Hierarchy

## Status

Proposed

## Context

Structural comparison catches many translator disagreements but also rejects
equivalent rewrites, such as reordered commutative predicates.

## Decision

Add a logical agreement report with an explicit method hierarchy:
normalized equality, alpha-renaming, commutative predicate equivalence, simple
SMT predicate equivalence, and bounded trace equivalence when witnesses exist.

Unsupported equivalence remains `needs_review` or `conflict`.

## Consequences

Simple equivalent translations can proceed without manual clarification, while
unsupported semantic claims remain explicit.
