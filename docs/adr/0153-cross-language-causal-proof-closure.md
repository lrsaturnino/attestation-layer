# ADR 0153: Cross-Language Causal Proof Closure

## Status

Accepted

## Context

Earlier cross-language evidence recorded adapter diversity, but it did not make
per-adapter evidence, replay bundles, or causal trace links strong enough to
support a final conclusion claim.

## Decision

Introduce `CrossLanguageProofObjectV2` with adapter evidence slices, retained
evidence references, replay bundle hashes, and required causal trace links.
Closure requires a closed base proof, at least two languages, required adapter
slices, retained evidence, replay bundle hashes, and satisfied causal links.

## Consequences

Cross-language closure can now fail for precise reasons instead of collapsing
multi-adapter gaps into a generic open proof. The tradeoff is that callers must
provide normalized traces and retained evidence references, not only manifests.

## Validation

Group 14 tests verify accepted multi-adapter closure and missing trace-link
blocking.
