# Phase 72 - Cross-Language Proof Object

## Status

Implemented.

## Purpose

Aggregate one proof decision across multiple language adapters while preserving
per-language slices and causal trace links.

## Implementation

- `nlreq.cross_language`
- `nlreq cross-language-proof`
- `schemas/cross-language-proof-object.schema.json`

The object records proof status, language slices, trace IDs, causal links,
blockers, and input hashes. It blocks if the proof is not closed or if fewer
than two source languages are present.

## Exit Criteria

- Cross-language closure cannot hide a non-closed proof.
- Missing causal-link events are explicit blockers.
- Per-adapter source and trace identity remains visible.
