# ADR 0027: Temporal Formalism And Bound Policy

## Status

Proposed

## Context

The vision requires temporal and bounded-time requirements. The current evidence
taxonomy already includes `BOUNDED_CHECKED`, but bounded evidence requires a real
backend run. Phase 23 can record temporal semantics during lowering, but it must
not claim the property was checked.

## Decision

The first temporal MVP uses bounded temporal metadata attached to the TLA
lowering artifact.

DSL v2 fragments such as `within 6 hours` lower into:

- target formalism: TLA-oriented skeleton;
- temporal operator metadata;
- numeric bound;
- bound unit;
- source node id.

The lowering artifact records these bounds for future model-checking phases.
It does not satisfy `BOUNDED_CHECKED`.

Unsupported temporal operators refuse explicitly. Timeouts, unsupported bounds,
or missing bounds are non-approving states.

## Consequences

Temporal structure survives the front-door pipeline before full temporal
checking exists. Later phases can consume recorded bounds when implementing real
backend execution and evidence production.

The tradeoff is conservative evidence semantics. Users see bounded temporal
intent in the lowered artifact, but gates must still require a real backend
producer before treating it as checked.
