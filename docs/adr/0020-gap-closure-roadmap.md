# ADR 0020: Gap Closure Roadmap

## Status

Proposed

## Context

The current implementation has the architecture shape of the NL Requirement
Attestation Layer: controlled-NL parsing, flat typed IR, evidence objects,
package hashing, status decisions, gates, continuous reports, handoff artifacts,
and declaration-level adapters.

`docs/vision-gap-spec.md` identifies the missing verification spine:
compositional IR, formal lowering, source-code adapters, first-class system
specs `S`, `S ∧ R` checking, spec coverage, code/spec trace alignment,
multi-backend proof objects, and closure-as-action-gate.

The remaining work is too large and too dependent on foundational design choices
to fully specify upfront. A complete upfront design would likely hard-code false
assumptions before the IR, backend boundary, and source-adapter boundary are
tested.

## Decision

Create a gap-closure roadmap and use phase-by-phase detailed scoping.

Phase 18 is documentation-only and establishes:

- `docs/vision-gap-roadmap.md`;
- `docs/phase-18-gap-closure-roadmap.md`;
- a follow-on phase sequence from Phase 19 through Phase 29;
- an ADR queue from ADR 0021 through ADR 0038.

The phase sequence is:

1. Phase 19 — Compositional IR Spine.
2. Phase 20 — Formal Backend Boundary.
3. Phase 21 — Source LanguageAdapter Boundary.
4. Phase 22 — DSL v2.
5. Phase 23 — Translator And Drafting MVP.
6. Phase 24 — First Real Source Vertical.
7. Phase 25 — System Spec Registry.
8. Phase 26 — `S ∧ R` Checker.
9. Phase 27 — Spec Coverage And Trace Alignment.
10. Phase 28 — Proof Closure Gate.
11. Phase 29 — Agnostic Wedge.

Each future phase must produce or update its own phase spec and ADRs before
implementation starts.

## Consequences

The project gets a concrete path from the current adapter-heavy implementation
to the full proof-carrying requirement gate without pretending that all details
are knowable upfront.

The tradeoff is that later ADR numbers and phase scopes are advisory until the
preceding phases land. If implementation reveals better splits, the roadmap
should be updated rather than forcing work into stale buckets.

Phase 18 does not add product capability. It only creates the control structure
for the capability-building phases that follow.
