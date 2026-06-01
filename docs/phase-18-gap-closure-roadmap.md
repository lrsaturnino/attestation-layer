# Phase 18 Gap Closure Roadmap

Phase 18 turns the vision/implementation gap inventory into a concrete build
program.

This phase is documentation-only. It does not change runtime behavior, schemas,
CLI commands, evidence semantics, or package validation.

## Purpose

The phase lets the Attestation Layer say:

```text
The gap between the current Phase-0-plus implementation and the full vision has
been decomposed into ordered build phases, and each phase has an ADR queue,
scope boundary, and exit criterion.
```

It does not say:

```text
The compositional IR exists.
Formal backends lower from the IR.
Source-language adapters analyze real code.
System specs S are registered.
S ∧ R is checked.
Trace alignment or closure gates are implemented.
```

Phase 18 is planning control, not capability delivery.

## Why This Comes After Phase 17

Phases 7-17 expanded the system horizontally with declaration-level adapters and
supporting workflow machinery. `docs/vision-gap-spec.md` shows that the remaining
work is no longer another shallow adapter. The next work must build the vertical
verification spine: compositional IR, formal lowering, source-code adapters,
system specs, `S ∧ R`, trace alignment, and proof closure.

Starting that spine without an explicit roadmap would blur foundational design
decisions with implementation details.

## Deliverables

Phase 18 adds:

- `docs/vision-gap-roadmap.md` — concrete phase sequence and ADR queue;
- `docs/phase-18-gap-closure-roadmap.md` — this phase spec;
- `docs/adr/0020-gap-closure-roadmap.md` — ADR for the roadmap and phase
  discipline.

## Roadmap Shape

The roadmap defines these follow-on phases:

| Phase | Name | Primary outcome |
|---|---|---|
| 19 | Compositional IR Spine | Replace the flat claim spine with a compositional IR. |
| 20 | Formal Backend Boundary | Define IR-to-formal backend contracts. |
| 21 | Source LanguageAdapter Boundary | Define real source-code adapter and trace boundaries. |
| 22 | DSL v2 | Expand controlled input only after the IR exists. |
| 23 | Translator And Drafting MVP | Draft approved controlled text and lower controlled requirements into formal backend input. |
| 24 | First Real Source Vertical | Prove one source-language vertical and impact analysis. |
| 25 | System Spec Registry | Make system spec `S` first-class. |
| 26 | `S ∧ R` Checker | Check new requirements against verified system specs. |
| 27 | Spec Coverage And Trace Alignment | Gate coverage, freshness, and code/spec trace alignment. |
| 28 | Proof Closure Gate | Aggregate proofs and require closure for downstream action. |
| 29 | Agnostic Wedge | Prove the abstraction across a second language or formalism. |

## Scope Rule

Phase 18 establishes the program shape. Later phases should be scoped in detail
one at a time.

This avoids locking speculative details for phases whose constraints depend on
the IR, backend boundary, and source-adapter boundary.

## ADR Queue

Phase 18 reserves ADRs 0021-0038 for the follow-on decisions listed in
`docs/vision-gap-roadmap.md`.

The reservation is advisory, not an implementation requirement. If later work
reveals that an ADR should split or merge, the queue may change as long as the
roadmap is updated with the new decision record.

## Success Criterion

Phase 18 succeeds when:

- the roadmap identifies every gap from `docs/vision-gap-spec.md`;
- every follow-on phase has primary gap coverage;
- the phase sequence is acyclic and follows the dependency ordering;
- the ADR queue starts after the current ADR set;
- the roadmap states that detailed design happens phase by phase;
- and no runtime capability is claimed by this planning phase.

## Boundary

This phase does not implement the compositional IR, DSL v2, translation,
formal-backend lowering, source-code adapters, system-spec registry, `S ∧ R`
checking, Specula integration, trace alignment, proof objects, or closure gates.

Those belong to Phases 19-29.
