# ADR 0037: Evidence Producer Mapping

## Status

Proposed

## Context

Evidence levels are meaningful only if the system records which producer emitted
them. A boundary checker, trace classifier, drafting tool, or LLM output must
not be able to claim the same assurance as a real backend.

## Decision

Introduce an evidence producer mapping artifact.

Each producer records:

- producer id;
- producer kind;
- whether it is a real evidence producer;
- allowed evidence levels;
- tool and version metadata;
- optional command and reproducibility fields.

Proof closure checks every backend result against this mapping. High-assurance
levels such as `BOUNDED_CHECKED` and `PROVEN_INDUCTIVE` require a real producer.
The default mapping does not grant `PROVEN_INDUCTIVE` to any current backend.

## Consequences

Evidence cannot be upgraded by changing a result field alone. A future proof
assistant or model checker must be added as an explicit producer with
reproducibility metadata before its results can close high-assurance premises.
