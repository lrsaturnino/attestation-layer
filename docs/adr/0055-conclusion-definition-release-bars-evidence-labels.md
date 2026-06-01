# ADR 0055: Conclusion Definition, Release Bars, And Evidence-Label Discipline

## Status

Proposed

## Context

The project has a working vertical slice, but the conclusion roadmap needs a
stable finish line. Without a machine-checkable definition, later phases can
drift or overclaim evidence strength.

## Decision

Introduce `ConclusionDefinition`, `ReleaseBar`, and
`ConclusionGapChecklist` artifacts. The checklist enforces conclusion phase
references and ADR numbering. Release bars distinguish alpha, beta, and
conclusion claims.

Evidence labels are constrained by release bar. `PROVEN_INDUCTIVE` remains
forbidden unless a registered proof-producing backend emits it.

Operational rules:

- Phase references must stay inside the conclusion roadmap range.
- Phase-to-ADR numbering is formulaic and machine-checked.
- Group-1 completion requires one implemented checklist item for each phase
  from 46 through 55.
- Release bars can become stricter in future ADRs, but cannot silently weaken
  evidence-label semantics.
- `BOUNDED_CHECKED`, `TRACE_VALIDATED`, and `REVIEWED` must be described as
  bounded, observed, or human-review evidence respectively.

Rejected alternatives:

- A prose-only release definition was rejected because it cannot detect phase
  numbering drift or evidence overclaiming.
- A single "done" flag was rejected because alpha, beta, and conclusion releases
  need different evidence bars.

Validation:

- `nlreq conclusion-gap-checklist` emits the default artifact.
- `nlreq conclusion-gap-check` fails on unknown phases, ADR numbering drift, or
  missing group-1 owner phases.

## Consequences

The roadmap has an auditable machine contract. New phases must update the gap
checklist and cannot silently change evidence semantics.
