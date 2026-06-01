# ADR 0028: First Source Adapter Selection And Manifest Format

## Status

Proposed

## Context

Phase 21 defined the source adapter interface but intentionally shipped only a
null adapter. Phase 24 needs one real source vertical to prove the abstraction
before adding heavier target ecosystems.

Solidity and Go are likely important future targets, but they introduce external
tooling and runtime decisions. Python can exercise the same interface with the
standard library.

## Decision

Select Python as the first source adapter vertical.

The first implementation will:

- parse Python source with `ast`;
- resolve functions and classes from manifest-declared modules;
- extract deterministic function-level call graph edges;
- present source snippets for resolved symbols;
- read manifest-declared normalized trace artifacts;
- compute deterministic affected modules from requirement symbols.

The Phase 21 source manifest remains the first manifest format. It binds module
ids to paths, symbols, spec refs, and trace sources. Later language-specific
fields may be added under metadata rather than changing the core shape.

## Consequences

The project proves the source adapter interface with real source parsing while
keeping dependency cost low.

The tradeoff is that Python is not the primary long-term target for every
deployment. Phase 24 is about proving the vertical shape, not choosing the final
language portfolio.
