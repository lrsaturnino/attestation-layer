# Vision Gap Closure Roadmap

**Status:** Draft v1  
**Date (UTC):** 2026-05-30  
**Source:** `docs/vision-gap-spec.md`

This roadmap turns the vision/implementation gap inventory into concrete build
phases and ADR work.

It intentionally does **not** fully design every phase upfront. The stable
program shape is locked here; detailed phase specs and ADRs should be written
just before each phase starts, when the previous phase has exposed real
constraints.

## Operating Rule

Scope the whole journey lightly, then implement phase by phase.

Upfront scope should define:

- phase boundaries;
- dependency order;
- ADR queue;
- phase exit criteria;
- invariants that future phases must not violate.

Per-phase scope should define:

- exact schema/API/CLI changes;
- migration plan;
- tests and fixtures;
- evidence semantics;
- compatibility rules;
- implementation steps.

## Non-Negotiable Invariants

- LLMs may draft or decompose, but they never decide acceptance.
- Deterministic schemas, parsers, validators, checkers, review records, and
  proof objects decide what enters the package.
- Evidence levels must never be inflated. `PROVEN_INDUCTIVE` requires a real
  proof backend; bounded model checking is not proof.
- Timeout, ambiguity, parser disagreement, backend disagreement, stale specs, and
  missing trace coverage are non-approving states.
- The IR remains the spine. Programming languages, formal backends, and natural
  language surfaces are adapters around it.
- Existing package hashing, source-span provenance, status-decision purity,
  conformance discipline, and shadow/soft/hard adoption mechanics should be
  extended rather than replaced.

## Phase Sequence

| Phase | Name | Primary gaps | Outcome |
|---|---|---|---|
| 18 | Gap Closure Roadmap | all | Concrete program roadmap and ADR queue. |
| 19 | Compositional IR Spine | GAP-A3 | New IR shape that can express multi-premise, temporal, quantified, and cross-cutting requirements. |
| 20 | Formal Backend Boundary | GAP-C4 | Backend interface and first lowering target boundary, before full backend implementation. |
| 21 | Source LanguageAdapter Boundary | GAP-C1, GAP-C3 | Source-code adapter interface plus verification-grade trace schema. |
| 22 | DSL v2 | GAP-A1 | Controlled input surface that targets the compositional IR. |
| 23 | Translator And Drafting MVP | GAP-A2, GAP-A4, GAP-A5 | Prose drafting/provenance plus controlled requirement to IR to one formal backend, with temporal MVP if feasible. |
| 24 | First Real Source Vertical | GAP-C2, GAP-B4 | One real source adapter and deterministic impact analysis. |
| 25 | System Spec Registry | GAP-B1 | Versioned registry of system specs `S` addressable by module. |
| 26 | `S ∧ R` Checker | GAP-B2, GAP-B3 | Symbolic system-consistency check with counterexamples and timeout semantics. |
| 27 | Spec Coverage And Trace Alignment | GAP-B5, GAP-B6, GAP-X3 | Coverage gating, Specula boundary, code/spec trace alignment, freshness. |
| 28 | Proof Closure Gate | GAP-X1, GAP-X2, GAP-X4 | Multi-premise proof object and downstream closure gate. |
| 29 | Agnostic Wedge | GAP-X5 | A second-language or second-formalism wedge proving the abstraction. |

## Phase Details

### Phase 18 — Gap Closure Roadmap

Purpose: convert the gap spec into an executable program plan.

Deliverables:

- this roadmap;
- `docs/phase-18-gap-closure-roadmap.md`;
- ADR 0020 documenting the phase discipline and ADR queue.

Exit criteria:

- new build phases are named and ordered;
- each phase has explicit gap coverage;
- the ADR queue is numbered and sequenced;
- future phases know whether to scope everything upfront or phase by phase.

### Phase 19 — Compositional IR Spine

Primary gap: GAP-A3.

This phase is the main design hinge. It should not attempt DSL expansion,
translation, source adapters, or `S ∧ R` checking beyond what is needed to prove
the IR shape.

Required ADR:

- ADR 0021: Compositional IR notation, schema, and migration from flat IR.

Exit criteria:

- IR schema represents semantic scopes, relations, atomic propositions,
  quantifiers, actions with pre/post state, temporal clauses, numeric/logical
  constraints, external-context references, provenance, and confidence markers;
- current flat IR migrates or is wrapped without breaking existing packages;
- at least one multi-premise requirement fixture is representable;
- backend-specific details are annotations, not the spine.

### Phase 20 — Formal Backend Boundary

Primary gap: GAP-C4.

This phase defines the backend contract before attempting broad formal lowering.
The goal is to prevent the new IR from accidentally becoming "TLA-shaped" or
"SMT-shaped."

Required ADR:

- ADR 0022: Formal backend interface, first target, lowering contract, and
  cross-backend agreement semantics.

Exit criteria:

- backend interface accepts the compositional IR and returns normalized backend
  results;
- first target backend is selected;
- unsupported constructs are explicit;
- backend annotations are scoped and versioned;
- existing `core_smt` and TLA command adapter boundaries are accounted for.

### Phase 21 — Source LanguageAdapter Boundary

Primary gaps: GAP-C1, GAP-C3.

This phase defines how real source code enters the system without tying the core
to Solidity, Go, Python, or any one runtime.

Required ADRs:

- ADR 0023: Source LanguageAdapter interface and coexistence with declaration
  adapters.
- ADR 0024: Verification-grade `NormalizedTrace` schema and lossy-normalization
  rules.

Exit criteria:

- source adapter interface covers symbol resolution, call graph, binding
  validation, code presentation for drafting, trace extraction, and manifest
  parsing;
- null/stub adapter exercises the interface end to end;
- trace schema records timestamp, actor, action, pre/post state, causal
  predecessor, language/runtime, source hash, and metadata;
- existing runtime-trace adapter compatibility is documented.

### Phase 22 — DSL v2

Primary gap: GAP-A1.

This phase expands the controlled input surface only after the IR can receive the
resulting structure.

Required ADR:

- ADR 0025: DSL v2 grammar, refusal taxonomy, and relationship to the IR.

Exit criteria:

- grammar expresses a small corpus of real target-domain requirements;
- parser refusals name the missing or ambiguous fragment;
- all parsed output maps into the compositional IR;
- unsupported language remains explicit.

### Phase 23 — Translator And Drafting MVP

Primary gaps: GAP-A2, GAP-A4, GAP-A5.

This phase proves the front door: controlled requirement to compositional IR to
formal backend. It also adds the guarded prose-to-controlled-form drafting path
so free-form prose can enter the pipeline without making LLM output authoritative.

Required ADRs:

- ADR 0026: Translator trust model, deterministic lowering, equivalence checks,
  LLM drafting provenance, and clarification loop.
- ADR 0027: Temporal formalism and bound policy.

Exit criteria:

- a controlled requirement lowers into one formal backend deterministically;
- free-form prose can produce a controlled-language draft with original text,
  suggested text, diff, prompt/model metadata, timestamp, and explicit approval;
- no parser or verifier runs on an unapproved draft;
- translation disagreements or unsupported constructs refuse with fragment-level
  explanations;
- temporal/bounded claims either produce bounded evidence with recorded bounds or
  refuse as unsupported;
- LLM-originated decomposition, if introduced, is provenance-marked and never
  auto-accepted.

### Phase 24 — First Real Source Vertical

Primary gaps: GAP-C2, GAP-B4.

Pick one source language and complete a vertical slice. Do not pick two at once.

Required ADR:

- ADR 0028: First source adapter selection, tool dependencies, and code-to-spec
  manifest format.

Exit criteria:

- one real source adapter resolves symbols from a real codebase;
- call graph and manifest parsing work;
- deterministic impact analysis returns affected modules;
- semantic/LLM impact estimation, if used, is disagreement-checking only;
- normalized traces are emitted for at least one useful path.

### Phase 25 — System Spec Registry

Primary gap: GAP-B1.

This phase introduces `S` as a first-class system artifact. Start with manual,
reviewed, versioned specs; Specula-style extraction belongs in Phase 27.

Required ADR:

- ADR 0029: System spec `S` representation, sourcing, versioning, and freshness
  metadata.

Exit criteria:

- modules bind to formal specs through a registry;
- spec hashes and versions are recorded;
- requirements can identify relevant `S` entries through impact output;
- stale or missing `S` is a non-approving state.

### Phase 26 — `S ∧ R` Checker

Primary gaps: GAP-B2, GAP-B3.

This is the core thesis phase: a requirement is checked against the verified
system model, not only against itself.

Required ADRs:

- ADR 0030: `S ∧ R` checker choice, verification budget, timeout semantics, and
  counterexample artifact schema.
- ADR 0031: Requirement-set contradiction taxonomy and scope.

Exit criteria:

- formal `R` can be composed with relevant `S`;
- checker returns satisfiable, counterexample, timeout, or unsupported;
- counterexamples name the violated invariant/state/action where available;
- timeout and unsupported results never approve;
- requirement-set contradictions are detected at the chosen scope.

### Phase 27 — Spec Coverage And Trace Alignment

Primary gaps: GAP-B5, GAP-B6, GAP-X3.

This phase closes the brownfield drift problem: specs must cover affected code
and must match real traces.

Required ADRs:

- ADR 0032: Spec coverage metric, thresholds, and Specula integration boundary.
- ADR 0033: Code/spec trace-validation semantics.
- ADR 0034: Spec freshness invariant and CI thresholds.

Exit criteria:

- affected modules have coverage status;
- requirements touching under-specified modules are blocked;
- extraction proposals are draft artifacts requiring review;
- traces are replayed against `R` and `S`;
- code changes can mark specs stale and trigger re-validation.

### Phase 28 — Proof Closure Gate

Primary gaps: GAP-X1, GAP-X2, GAP-X4.

This phase turns evidence into closure.

Required ADRs:

- ADR 0035: Multi-backend dispatch policy and proof-object schema.
- ADR 0036: Closure-gate semantics and PR/backlog integration.
- ADR 0037: Evidence producer to evidence-level mapping and reproducibility
  metadata.

Exit criteria:

- each requirement premise can be routed to a backend;
- one aggregated proof object records all discharged premises;
- downstream action requires a closed proof object;
- high-assurance evidence levels are emitted only by real producers.

### Phase 29 — Agnostic Wedge

Primary gap: GAP-X5.

This phase proves the project is infrastructure rather than a single-language
tool.

Required ADR:

- ADR 0038: Agnosticism scope per version and cross-language proof model.

Exit criteria:

- one requirement spanning two source languages or two formal backends closes as
  one proof object;
- adapter-specific facts remain outside the IR spine;
- unresolved cross-language trace or proof limitations are explicit.

## ADR Queue

| ADR | Title | Phase | Gap coverage |
|---|---|---|---|
| 0020 | Gap closure roadmap and phase discipline | 18 | all |
| 0021 | Compositional IR notation, schema, and migration | 19 | GAP-A3 |
| 0022 | Formal backend interface and lowering contract | 20 | GAP-C4 |
| 0023 | Source LanguageAdapter interface | 21 | GAP-C1 |
| 0024 | Verification-grade NormalizedTrace schema | 21 | GAP-C3 |
| 0025 | DSL v2 grammar and refusal taxonomy | 22 | GAP-A1 |
| 0026 | Translator trust model, drafting provenance, and deterministic lowering | 23 | GAP-A2, GAP-A4 |
| 0027 | Temporal formalism and bound policy | 23 | GAP-A5 |
| 0028 | First source adapter selection and manifest format | 24 | GAP-C2, GAP-B4 |
| 0029 | System spec `S` registry | 25 | GAP-B1 |
| 0030 | `S ∧ R` checker semantics | 26 | GAP-B2 |
| 0031 | Requirement-set contradiction taxonomy | 26 | GAP-B3 |
| 0032 | Spec coverage and Specula boundary | 27 | GAP-B5 |
| 0033 | Code/spec trace validation | 27 | GAP-B6 |
| 0034 | Spec freshness invariant and CI thresholds | 27 | GAP-X3 |
| 0035 | Multi-backend proof object | 28 | GAP-X1 |
| 0036 | Closure gate semantics | 28 | GAP-X2 |
| 0037 | Evidence producer mapping | 28 | GAP-X4 |
| 0038 | Agnosticism and cross-language proof model | 29 | GAP-X5 |

## What Not To Do

- Do not write all ADRs in full before Phase 19 starts.
- Do not implement `S ∧ R` before the IR and backend boundary exist.
- Do not expand the DSL before the compositional IR can preserve its semantics.
- Do not build a second language adapter before the first vertical proves the
  source-adapter interface.
- Do not treat Specula output, LLM decomposition, or trace observations as
  accepted evidence without review and normalized backend results.
