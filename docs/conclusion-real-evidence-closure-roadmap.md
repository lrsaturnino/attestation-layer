# Conclusion Real-Evidence Closure Roadmap

**Status:** Draft v1
**Date:** 2026-06-03
**Starts After:** Phase 116 Extended Conclusion Certification
**Current ADR Floor:** ADR 0125 Extended Conclusion Certification
**Source Context:** `docs/claude-convo.md`, `docs/nl-attestation-conclusion-roadmap.md`, implemented phases 0-116

This roadmap closes the gap between the current Attestation Layer development
state and the system described in `docs/claude-convo.md`:

```text
human requirement
-> approved controlled requirement
-> formal claim R
-> R checked against itself
-> affected system areas identified
-> existing formal system spec S proven fresh and covering those areas
-> R checked against S
-> current code behavior and traces grounded against R
-> evidence produced by real registered producers
-> proof object closes
-> downstream action is allowed only after closure
```

The project now has the architectural skeleton, schemas, release reports, ADRs,
and tests for the full path. The remaining work is to replace scaffold-level
evidence with real evidence: robust semantic translation, real formal backend
execution, brownfield spec grounding, production language adapters, replayable
evidence, public benchmark signal, and a release certification that fails unless
those inputs are actually present.

## Executive Summary

The current implementation is close to the Claude discussion in **shape** and
not yet close in **proof strength**.

What exists:

- controlled requirement parsing and canonical IR;
- formal-claim IR and semantic lowering;
- review, approval, provenance, clarification, and refusal artifacts;
- adapter-neutral source and trace interfaces;
- Python, JavaScript, and production-adapter scaffolds;
- system spec registry, source impact, spec coverage, spec freshness, trace
  replay, and trace validation contracts;
- model-checker runner boundaries, Apalache/TLC-facing contracts, TLA
  projection, `S and R` composition reports, counterexample normalization, and
  proof objects;
- evidence artifact store, signatures, producer registries, CI/PR gate reports,
  benchmarks, threat model, documentation index, and conclusion certification;
- extended group 9 release/adoption reports that fail closed on missing release
  evidence.

What is still missing:

- a real product-quality free-form NL intake path;
- a robust Req2LTL-style semantic decomposition translator;
- translator agreement calibrated on semantic accuracy, not only structural
  similarity;
- ALICE-grade contradiction taxonomy and self-consistency checks;
- production Apalache/TLC result parsing on real models and real failures;
- mature `S and R` composition over reviewed formal system specs;
- trustworthy code-to-spec extraction and review promotion workflow;
- continuously enforced spec freshness against changing source code;
- runtime trace producers for real ecosystems;
- production-grade language adapters for Solidity, Go, TypeScript/JavaScript,
  Rust or Java, and a hardened Python path;
- cross-language causal proof closure;
- evidence replay and producer-signature enforcement in normal workflows;
- benchmark coverage strong enough to reveal false closure and false refusal;
- at least one non-toy reference brownfield demo that closes or refuses through
  the real path.

The next roadmap must therefore focus less on adding artifact names and more on
making each named artifact hard to fake.

## Definition Of Real-Evidence Conclusion

This roadmap is done only when the project can credibly claim:

1. **Input closure:** A user can submit free-form or controlled text. Free-form
   text is rewritten into controlled form only through an auditable, reviewed,
   hash-linked path. No silent semantic rewrite is possible.
2. **Translation closure:** The controlled requirement lowers into formal claim
   IR through a measured semantic translation pipeline with provenance,
   ambiguity detection, disagreement handling, and clarification.
3. **Self-consistency closure:** The requirement is checked against itself using
   a documented contradiction taxonomy and deterministic refusal behavior.
4. **Formal closure:** Supported formal claims execute against at least one real
   formal backend with normalized success, counterexample, timeout, unsupported,
   and missing-tool outcomes.
5. **System closure:** New requirement claim `R` is composed with reviewed system
   spec `S`, and the tool can return valid, counterexample, timeout, unsupported,
   stale-spec, missing-coverage, or needs-review outcomes without overclaiming.
6. **Brownfield grounding:** Impact analysis identifies affected code areas,
   spec coverage and freshness are enforced, candidate specs are generated only
   as untrusted drafts, and runtime traces ground current behavior.
7. **Adapter credibility:** At least four materially different programming
   ecosystem adapters can produce certified evidence through the same adapter
   interface. At least one must be transaction/event oriented, one compiled
   service ecosystem, and one dynamic or scripting ecosystem.
8. **Cross-language credibility:** A requirement spanning more than one adapter
   can produce one proof object with per-adapter evidence, causal trace links,
   and explicit blockers.
9. **Evidence integrity:** High-assurance evidence is produced by registered
   real producers, retained in replay bundles, hash-linked, and signed where
   policy requires signatures.
10. **Benchmark credibility:** Public benchmarks track semantic translation,
    system compatibility, trace grounding, adapter evidence, counterexample
    quality, false closure, false refusal, timeout, unknown, runtime, and
    release-gate behavior.
11. **Action gate:** Official APIs and CI integrations allow downstream action
    only when configured evidence premises close.

## Non-Goals

The real-evidence conclusion still does not claim:

- correctness for arbitrary natural language;
- correctness for arbitrary programs;
- proof for unsupported requirement fragments;
- unbounded guarantees where only bounded checking ran;
- semantic equivalence among all formal backends;
- automatic trust in generated specs;
- replacement of human domain review;
- support for every programming language.

The release must keep evidence labels honest. A bounded model check is not an
inductive proof. Trace replay is not theorem evidence. A signed artifact proves
producer identity and integrity, not semantic correctness.

## Consolidated Milestones

| Milestone | Phases | Name | Outcome |
|---:|---:|---|---|
| 10 | 117-123 | Semantic Translation Production Closure | Free-form and controlled requirements translate into formal claims with measured semantic fidelity, repairable ambiguity, and ALICE-style self-consistency. |
| 11 | 124-130 | Real Formal System Closure | Formal claims execute against real backends and compose with reviewed system specs through explicit valid, counterexample, timeout, unsupported, and unknown outcomes. |
| 12 | 131-137 | Brownfield Grounding Closure | Impact, code-to-spec coverage, spec freshness, Specula-style candidate extraction, and trace validation become production evidence paths. |
| 13 | 138-143 | Programming-Language Adapter Closure | The adapter abstraction is proven through production adapters across materially different ecosystems. |
| 14 | 144-150 | Cross-Language Evidence And Release Closure | Multi-adapter proof objects, replayable signed evidence, performance, public benchmarks, CI adoption, beta demos, and final certification converge. |

These milestones are ordered but not perfectly sequential. Benchmark cases,
reference demos, and producer hardening should accumulate continuously.

## Release Bars

| Bar | Required State | What It Can Claim |
|---|---|---|
| Alpha Evidence | Milestone 10 complete, one real formal backend smoke-tested, benchmark seed expanded | The tool can translate and refuse controlled requirements with honest semantic evidence. |
| Formal Beta | Milestones 10-11 complete, real Apalache/TLC outcomes on non-toy specs | The tool can check supported `R` claims against reviewed `S` specs under explicit bounds. |
| Brownfield Beta | Milestones 10-12 complete, one real brownfield module with freshness and traces | The tool can refuse requirements touching stale, uncovered, or trace-contradicting areas. |
| Adapter Beta | Milestones 10-13 complete, at least four adapters certified | The tool is credibly programming-language agnostic for supported evidence classes. |
| Conclusion RC | Milestones 10-14 complete except public external review | The tool can gate downstream action in a reference workflow with retained replayable evidence. |
| Real-Evidence Conclusion | All milestones complete, benchmark thresholds met, release bundle signed | The project can publish the scoped conclusion claim without overclaiming proof strength. |

## Phase Sequence

| Phase | Milestone | Name | Primary Gap Closed | Required ADR |
|---:|---:|---|---|---:|
| 117 | 10 | Production Free-Form Intake Runtime | real NL intake product path | ADR 0126 |
| 118 | 10 | Rewrite Provenance And Replay | reproducible LLM/manual rewrite evidence | ADR 0127 |
| 119 | 10 | Semantic Decomposition Translator | Req2LTL-style intermediate translation | ADR 0128 |
| 120 | 10 | Translator Ensemble Calibration | semantic agreement beyond structural equality | ADR 0129 |
| 121 | 10 | Clarification And Repair UX Hardening | actionable ambiguity and unsupported-fragment loop | ADR 0130 |
| 122 | 10 | ALICE-Grade Self-Consistency | contradiction taxonomy and deterministic refusal | ADR 0131 |
| 123 | 10 | Semantic Translation Benchmark Release Bar | public semantic accuracy and false-acceptance thresholds | ADR 0132 |
| 124 | 11 | Formal Claim Semantics Completion | exact semantics for supported claim classes | ADR 0133 |
| 125 | 11 | Production Apalache Execution | real symbolic bounded checking path | ADR 0134 |
| 126 | 11 | Production TLC Execution | real explicit-state checking path | ADR 0135 |
| 127 | 11 | Real `S and R` TLA Composition | backend-checkable compatibility against reviewed specs | ADR 0136 |
| 128 | 11 | Counterexample Explanation Contract | actionable formal failure surface | ADR 0137 |
| 129 | 11 | Verification Budget And Unknown Policy | honest timeout, bound, and abstraction outcomes | ADR 0138 |
| 130 | 11 | Proof-Producing Backend Boundary | TLAPS/Lean/Coq/Dafny evidence requirements | ADR 0139 |
| 131 | 12 | Production Source Impact | affected code and module discovery under adapter output | ADR 0140 |
| 132 | 12 | Code-To-Spec Coverage Manifest v2 | precise brownfield coverage gates | ADR 0141 |
| 133 | 12 | Spec Freshness And Drift CI | hash-based freshness invariant in workflows | ADR 0142 |
| 134 | 12 | Specula-Style Extraction Integration | candidate specs for uncovered areas | ADR 0143 |
| 135 | 12 | Candidate Spec Review And Promotion | generated specs remain untrusted until reviewed | ADR 0144 |
| 136 | 12 | Runtime Trace Producer SDK Production | real trace producers and metadata | ADR 0145 |
| 137 | 12 | Trace Validation Gate Production | traces ground formal claims against current behavior | ADR 0146 |
| 138 | 13 | Adapter Interface v2 Capability Contract | production adapter contract and capability claims | ADR 0147 |
| 139 | 13 | Solidity Adapter Graduation | transaction/event ecosystem evidence | ADR 0148 |
| 140 | 13 | Go Adapter Graduation | compiled service ecosystem evidence | ADR 0149 |
| 141 | 13 | TypeScript And JavaScript Adapter Graduation | frontend/service runtime evidence | ADR 0150 |
| 142 | 13 | Rust Or Java Adapter Graduation | second compiled ecosystem pressure test | ADR 0151 |
| 143 | 13 | Adapter Certification And Plugin SDK | public adapter conformance surface | ADR 0152 |
| 144 | 14 | Cross-Language Causal Proof Closure | one proof object over multiple adapters | ADR 0153 |
| 145 | 14 | Evidence Replay And Signing Enforcement | retained reproducible high-assurance evidence | ADR 0154 |
| 146 | 14 | Performance, Caching, And Parallel Dispatch | usable runtime at realistic scale | ADR 0155 |
| 147 | 14 | Public Benchmark Suite And Leaderboard | external benchmark accountability | ADR 0156 |
| 148 | 14 | Reference Brownfield Demo And Beta Pilots | real workflow adoption evidence | ADR 0157 |
| 149 | 14 | CI Adoption And Policy Governance Hardening | branch-protection-ready action gates | ADR 0158 |
| 150 | 14 | Final Real-Evidence Conclusion Certification | final release decision and public claim | ADR 0159 |

## ADR Backlog

| ADR | Phase | Title | Decision Required |
|---:|---:|---|---|
| 0126 | 117 | Production Free-Form Intake Runtime | Decide provider boundaries, approval states, and unsafe raw-NL refusal behavior. |
| 0127 | 118 | Rewrite Provenance And Replay | Decide prompt/model metadata, replay hashes, and non-deterministic output retention. |
| 0128 | 119 | Semantic Decomposition Translator | Decide intermediate semantic tree structure and deterministic lowering boundary. |
| 0129 | 120 | Translator Ensemble Calibration | Decide ensemble policy, semantic agreement profiles, and reviewer override requirements. |
| 0130 | 121 | Clarification And Repair UX | Decide source-span repair protocol and version history semantics. |
| 0131 | 122 | Requirement Contradiction Taxonomy | Decide contradiction classes, deterministic checks, and LLM-assisted audit limits. |
| 0132 | 123 | Semantic Translation Benchmark Release Bar | Decide benchmark labels, thresholds, false-acceptance budget, and publication rules. |
| 0133 | 124 | Formal Claim Semantics Completion | Decide exact semantics and unsupported behavior for every supported claim class. |
| 0134 | 125 | Apalache Execution And Result Normalization | Decide command metadata, bounds, parser, counterexample, and evidence-label rules. |
| 0135 | 126 | TLC Execution And Result Normalization | Decide explicit-state outcomes, timeout handling, and invariant mapping. |
| 0136 | 127 | Real `S and R` TLA Composition | Decide module composition, invariant preservation, and spec/requirement namespace policy. |
| 0137 | 128 | Counterexample Explanation Contract | Decide minimum actionable detail for formal failure outputs. |
| 0138 | 129 | Verification Budget And Unknown Policy | Decide timeout, state-space, memory, abstraction, cache, and unknown semantics. |
| 0139 | 130 | Proof-Producing Backend Boundary | Decide what qualifies as `PROVEN_INDUCTIVE` and how proof artifacts are retained. |
| 0140 | 131 | Production Source Impact Semantics | Decide deterministic, trace-touched, dependency, and semantic-suggestion impact roles. |
| 0141 | 132 | Code-To-Spec Coverage Manifest v2 | Decide coverage propagation, review status, and closure effect for coverage gaps. |
| 0142 | 133 | Spec Freshness And Drift CI | Decide hash lock, validation age, drift, and stale-spec refusal policy. |
| 0143 | 134 | Specula-Style Extraction Integration | Decide candidate generator trust model, inputs, and trace-validation requirements. |
| 0144 | 135 | Candidate Spec Review And Promotion | Decide generated spec review, rejection, promotion, and freshness-lock workflow. |
| 0145 | 136 | Runtime Trace Producer SDK | Decide producer identity, runtime metadata, extraction inputs, and loss records. |
| 0146 | 137 | Trace Validation Closure Policy | Decide trace satisfaction, violation, coverage gap, lossy, and unsupported outcomes. |
| 0147 | 138 | Adapter Interface v2 Capability Contract | Decide required methods, capability levels, limitations, and evidence declarations. |
| 0148 | 139 | Solidity Adapter Graduation | Decide Solidity evidence scope, tooling, traces, and unsupported features. |
| 0149 | 140 | Go Adapter Graduation | Decide Go evidence scope, call graph, tracing, and Specula integration. |
| 0150 | 141 | TypeScript And JavaScript Adapter Graduation | Decide TS/JS source, runtime, browser/server split, and trace model. |
| 0151 | 142 | Rust Or Java Adapter Graduation | Decide third/fourth ecosystem selection and graduation bar. |
| 0152 | 143 | Adapter Certification And Plugin SDK | Decide public conformance fixtures, plugin API, and certification failure taxonomy. |
| 0153 | 144 | Cross-Language Causal Proof Closure | Decide causal links, cross-adapter blockers, and proof aggregation semantics. |
| 0154 | 145 | Evidence Replay And Signing Enforcement | Decide replay bundle format, signature requirements, and trust policy. |
| 0155 | 146 | Performance, Caching, And Parallel Dispatch | Decide cache keys, invalidation, parallelism, and performance budgets. |
| 0156 | 147 | Public Benchmark Suite And Leaderboard | Decide benchmark dimensions, data format, scoring, and public reporting. |
| 0157 | 148 | Reference Brownfield Demo And Beta Pilots | Decide demo selection, pilot evidence, and release acceptance criteria. |
| 0158 | 149 | CI Adoption And Policy Governance Hardening | Decide branch protection, waivers, policy drift, and audit retention. |
| 0159 | 150 | Final Real-Evidence Conclusion Certification | Decide final certification inputs, release bundle signing, and public claim language. |

## Detailed Milestone Plans

### Milestone 10 - Semantic Translation Production Closure

Objective: make the front of the pipeline credible. The system must translate
human intent into formal claims without silently changing meaning, and it must
refuse or clarify when meaning cannot be trusted.

Current base:

- `src/nlreq/intake.py`
- `src/nlreq/review_workflow.py`
- `src/nlreq/dsl_v3.py`
- `src/nlreq/semantic_translation.py`
- `src/nlreq/semantic_agreement.py`
- `src/nlreq/translation_repair.py`
- `src/nlreq/translation_benchmark.py`
- `src/nlreq/requirement_self_consistency.py`

Exit criteria:

- raw free-form text never reaches formal parsing without approved controlled
  form;
- translator candidates preserve provenance and source spans;
- semantic decomposition is explicit and deterministic lowering is separated
  from LLM output;
- translator disagreement blocks acceptance unless review resolution is
  hash-bound;
- self-consistency checks implement a documented contradiction taxonomy;
- semantic benchmark includes accepted, refused, ambiguous, needs-review, and
  adversarial cases;
- false semantic acceptance is treated as release-blocking.

#### Phase 117 - Production Free-Form Intake Runtime

Purpose: turn the existing intake schema into a usable product path.

Scope:

- provider-agnostic intake runner for manual and LLM-assisted rewrite;
- raw text artifact retention;
- approved controlled form selection;
- refusal of unapproved controlled form;
- intake state transitions: drafted, proposed, approved, rejected, superseded;
- CLI and API shape for product integration.

Deliverables:

- intake runtime module;
- provider interface for rewrite suggestions;
- replayable intake fixtures;
- product examples for accepted, rejected, and superseded rewrites;
- tests proving parsers refuse raw free-form text.

Exit criteria:

- controlled parser cannot consume free-form text without approval;
- approved text hash is recorded in every downstream translation artifact;
- rejected proposals cannot be selected;
- state transitions are deterministic and auditable.

Required ADR:

- ADR 0126: Production free-form intake runtime and raw-NL refusal policy.

#### Phase 118 - Rewrite Provenance And Replay

Purpose: make rewrite evidence reproducible enough to audit.

Scope:

- prompt registry;
- model/provider metadata;
- input context hashes;
- non-deterministic output retention;
- replay bundle format for rewrite attempts;
- approval binding to exact rewrite output.

Deliverables:

- rewrite provenance schema update;
- prompt registry artifact;
- replay bundle for rewrite proposals;
- tests for hash-bound approval and replay metadata.

Exit criteria:

- a reviewer can inspect original text, controlled rewrite, diff, prompt,
  provider metadata, and hashes;
- replay bundles preserve enough data to explain the rewrite even if the provider
  cannot reproduce identical text;
- approval is invalidated by any rewrite change.

Required ADR:

- ADR 0127: Rewrite provenance, prompt registry, and replay semantics.

#### Phase 119 - Semantic Decomposition Translator

Purpose: replace parser-only translation with a real two-stage semantic
translator inspired by Req2LTL and OnionL.

Scope:

- controlled/NL candidate to semantic decomposition tree;
- semantic scopes, relations, entities, predicates, temporal bounds, and
  obligations;
- deterministic semantic tree to formal claim lowering;
- unsupported-fragment refusal before formal claim emission;
- provenance from tree nodes to controlled text.

Deliverables:

- semantic decomposition schema;
- translator implementation;
- deterministic lowering rules;
- fixtures for all supported requirement classes;
- unsupported and ambiguous fixtures.

Exit criteria:

- formal claim lowering never consumes opaque prose;
- semantic tree is inspectable and hash-linked;
- supported tree fragments lower deterministically;
- unsupported fragments produce stable refusal codes and source spans.

Required ADR:

- ADR 0128: Semantic decomposition translator and deterministic lowering
  boundary.

#### Phase 120 - Translator Ensemble Calibration

Purpose: make translator agreement meaningful.

Scope:

- multiple translator strategies;
- semantic equivalence profiles;
- disagreement classifications;
- confidence calibration against benchmark labels;
- reviewer override with selected candidate hash;
- fail-closed policy for unreviewed disagreement.

Deliverables:

- ensemble run report;
- calibrated agreement report;
- disagreement taxonomy;
- benchmark-backed calibration metrics;
- tests for false agreement and reviewer override.

Exit criteria:

- at least two independent candidates are required for acceptance in configured
  high-assurance mode;
- disagreement blocks unless resolved by hash-bound review;
- agreement method and limits are recorded;
- benchmark tracks semantic false acceptance.

Required ADR:

- ADR 0129: Translator ensemble calibration and semantic agreement policy.

#### Phase 121 - Clarification And Repair UX Hardening

Purpose: make refusal productive for normal users.

Scope:

- source-span highlighting;
- clarification prompt generation;
- repair response application;
- controlled-form version history;
- no automatic rewrite after clarification without approval;
- UI-ready JSON.

Deliverables:

- repair UX schema update;
- clarification history artifact;
- examples for ambiguity, unsupported grammar, conflicting translators, and
  missing domain binding;
- CLI/API repair loop.

Exit criteria:

- every repair prompt names a source span or a no-span reason;
- repair creates a new controlled-form version;
- prior versions remain auditable;
- downstream artifacts bind to the selected version.

Required ADR:

- ADR 0130: Clarification, repair, and controlled-form versioning protocol.

#### Phase 122 - ALICE-Grade Self-Consistency

Purpose: detect contradictions in the requirement before checking it against
the system.

Scope:

- contradiction taxonomy based on ALICE-style categories;
- deterministic checks for mutually exclusive obligations, impossible
  conditions, conflicting temporal bounds, inconsistent numeric constraints, and
  incompatible postconditions;
- optional LLM-assisted contradiction suggestion marked as untrusted;
- SMT-backed overlap checks where supported.

Deliverables:

- contradiction taxonomy reference;
- self-consistency report v2;
- contradiction fixtures;
- benchmark labels for contradiction detection.

Exit criteria:

- self-consistency produces stable contradiction classes;
- LLM suggestions cannot pass or fail a requirement by themselves;
- supported contradictions block before system consistency;
- missed/unknown cases are labeled honestly.

Required ADR:

- ADR 0131: Requirement contradiction taxonomy and self-consistency semantics.

#### Phase 123 - Semantic Translation Benchmark Release Bar

Purpose: make semantic translation quality measurable enough for release.

Scope:

- public corpus expansion;
- adversarial and ambiguous input cases;
- semantic match labels;
- false acceptance and false refusal metrics;
- clarification quality scoring;
- release thresholds.

Deliverables:

- expanded benchmark corpus;
- scoring report;
- release threshold config;
- public results example;
- regression tests.

Exit criteria:

- benchmark fails on any configured false-acceptance budget breach;
- accepted cases require semantic match;
- needs-review and ambiguity cases are first-class outcomes;
- results are corpus-scoped and cannot be inflated by extra cases.

Required ADR:

- ADR 0132: Semantic translation benchmark methodology and release bar.

### Milestone 11 - Real Formal System Closure

Objective: make the formal backend path real enough that `S and R` checks are
mathematical evidence rather than report scaffolding.

Current base:

- `src/nlreq/formal_claim.py`
- `src/nlreq/tla_projection.py`
- `src/nlreq/model_checker_runner.py`
- `src/nlreq/formal_backend.py`
- `src/nlreq/system_checker.py`
- `src/nlreq/system_composition.py`
- `src/nlreq/counterexample_normalization.py`
- `src/nlreq/evidence_boundary.py`

Exit criteria:

- supported claim classes have exact formal semantics;
- Apalache and TLC parse real outcomes;
- `S and R` composition emits backend-checkable artifacts;
- counterexamples map to source spans and refusal reasons;
- timeouts and budget exhaustion become `unknown`, not success;
- proof-producing backend evidence is impossible to fake with bounded results.

#### Phase 124 - Formal Claim Semantics Completion

Purpose: finish the semantics table for supported formal claims.

Scope:

- exact semantics for authorization precondition, state precondition, state
  postcondition, event/state correspondence, numeric invariant, bounded
  temporal property, and cross-module causal obligation;
- unsupported fragments and evidence requirements;
- projection obligations for formal backends and trace validators.

Deliverables:

- formal claim semantics reference;
- golden formal claim fixtures;
- unsupported-fragment tests;
- evidence-requirement matrix.

Exit criteria:

- every supported claim class has named semantics;
- unsupported fragments refuse before backend dispatch;
- evidence labels required by semantics are explicit.

Required ADR:

- ADR 0133: Formal claim semantics completion and unsupported behavior.

#### Phase 125 - Production Apalache Execution

Purpose: make Apalache the first real symbolic bounded checking workhorse.

Scope:

- command execution through model-checker runner;
- version detection;
- bounds and options capture;
- success, violation, timeout, parse error, unsupported, missing-tool outcomes;
- counterexample extraction and normalization.

Deliverables:

- Apalache runner integration;
- output parser fixtures;
- normalized backend response;
- CLI examples;
- replayable model fixtures.

Exit criteria:

- real Apalache command output is parsed;
- bounds are recorded in evidence;
- counterexamples are retained and normalized;
- missing tool and timeout never become success.

Required ADR:

- ADR 0134: Apalache execution, result normalization, and evidence labels.

#### Phase 126 - Production TLC Execution

Purpose: add explicit-state checking as an independent backend path.

Scope:

- TLC command runner;
- model/config handling;
- invariant violation parsing;
- deadlock and temporal-property outcome parsing;
- timeout and state-limit handling.

Deliverables:

- TLC runner integration;
- output fixture corpus;
- normalized response mapping;
- comparison fixtures with Apalache where overlap exists.

Exit criteria:

- TLC success and violation outputs are parsed;
- explicit-state evidence labels are distinct from symbolic evidence labels;
- backend disagreement is reportable.

Required ADR:

- ADR 0135: TLC execution and result normalization.

#### Phase 127 - Real `S and R` TLA Composition

Purpose: compose reviewed system specs with new requirement claims.

Scope:

- load reviewed system spec modules;
- inject requirement claim as invariant/action/temporal property;
- namespace variables and operators safely;
- preserve existing invariants;
- emit backend-checkable TLA/config artifacts;
- map composition failures to refusal codes.

Deliverables:

- composition engine;
- composed TLA artifacts;
- invariant preservation report;
- compatibility fixtures;
- tests for namespace conflicts and unsupported claims.

Exit criteria:

- composed artifacts can be executed by Apalache/TLC;
- existing spec invariants remain visible;
- requirement claim failures produce actionable counterexamples;
- stale or unreviewed specs block composition.

Required ADR:

- ADR 0136: Real `S and R` TLA composition semantics.

#### Phase 128 - Counterexample Explanation Contract

Purpose: turn formal failures into product-grade refusal.

Scope:

- normalize backend traces;
- map states/actions to formal claim fragments;
- map formal claim fragments to controlled text spans;
- explain violated invariant and shortest known trace;
- emit PR-ready Markdown and JSON.

Deliverables:

- counterexample explanation report;
- renderer;
- benchmark scoring for counterexample quality;
- fixtures for Apalache and TLC traces.

Exit criteria:

- every counterexample names backend, bound, violated property, trace steps, and
  source mapping where available;
- refusal report contains next actions;
- benchmark can score counterexample usefulness.

Required ADR:

- ADR 0137: Counterexample explanation and refusal mapping contract.

#### Phase 129 - Verification Budget And Unknown Policy

Purpose: prevent false confidence under state-space explosion.

Scope:

- per-claim and per-backend budgets;
- timeout, memory, max-depth, max-state, and abstraction-limit outcomes;
- cache interaction;
- unknown vs refused policy;
- escalation path for human review.

Deliverables:

- budget policy v2;
- unknown outcome report;
- cache key updates;
- CI policy examples.

Exit criteria:

- budget exhaustion cannot pass closure;
- unknown outcomes are distinct from refused outcomes;
- all backend reports include budget metadata;
- release certification can require no unknowns for selected claims.

Required ADR:

- ADR 0138: Verification budgets, unknown outcomes, and cache semantics.

#### Phase 130 - Proof-Producing Backend Boundary

Purpose: define the path to true proof evidence without requiring it for every
bounded check.

Scope:

- TLAPS/Lean/Coq/Dafny producer contract;
- proof artifact retention;
- proof checker command metadata;
- distinction between proof script, checked proof, and theorem claim;
- evidence label restrictions.

Deliverables:

- proof producer interface;
- proof artifact schema;
- policy tests preventing bounded evidence from claiming `PROVEN_INDUCTIVE`;
- optional TLAPS pilot on a small invariant.

Exit criteria:

- `PROVEN_INDUCTIVE` can be emitted only by a proof-producing backend;
- proof artifacts are replayable;
- missing proof-producing backend does not block bounded release claims when
  claims are labeled correctly.

Required ADR:

- ADR 0139: Proof-producing backend boundary and inductive evidence policy.

### Milestone 12 - Brownfield Grounding Closure

Objective: make the system check current code rather than an idealized fiction.

Current base:

- `src/nlreq/source_impact.py`
- `src/nlreq/spec_drift.py`
- `src/nlreq/spec_freshness.py`
- `src/nlreq/spec_extraction.py`
- `src/nlreq/coverage_alignment.py`
- `src/nlreq/runtime_trace_sdk.py`
- `src/nlreq/trace_normalization.py`
- `src/nlreq/trace_replay.py`
- `src/nlreq/trace_validation.py`

Exit criteria:

- affected modules are identified through adapter output;
- code-to-spec coverage blocks unsupported areas;
- changed code/spec invalidates freshness until revalidated;
- Specula-style extraction produces candidate specs only;
- candidate specs require review before promotion;
- real runtime trace producers emit normalized traces;
- trace validation can satisfy, violate, or mark coverage gaps explicitly.

#### Phase 131 - Production Source Impact

Purpose: identify where a new requirement touches the codebase.

Scope:

- adapter-provided symbol resolution;
- call graph and dependency graph use;
- trace-touched modules;
- semantic suggestions as untrusted hints;
- disagreement reporting.

Deliverables:

- source impact report v2;
- confidence policy;
- fixtures for deterministic, trace, dependency, and semantic impact;
- review path for low-confidence impact.

Exit criteria:

- deterministic adapter impact is separated from LLM suggestions;
- missing or ambiguous symbols block closure;
- impact output feeds coverage and trace requirements.

Required ADR:

- ADR 0140: Production source impact semantics.

#### Phase 132 - Code-To-Spec Coverage Manifest v2

Purpose: make formal spec coverage precise enough to gate requirements.

Scope:

- module-to-spec mappings;
- spec review status;
- dependency propagation;
- trace coverage links;
- partial coverage and unsupported behavior;
- coverage thresholds.

Deliverables:

- coverage manifest v2 schema;
- coverage gate report;
- migration from current manifest;
- fixtures for missing, partial, stale, and reviewed coverage.

Exit criteria:

- requirements touching uncovered modules are refused or unknown according to
  policy;
- reviewed coverage is distinguishable from candidate coverage;
- dependency gaps propagate to affected requirements.

Required ADR:

- ADR 0141: Code-to-spec coverage manifest v2 and closure policy.

#### Phase 133 - Spec Freshness And Drift CI

Purpose: prevent checking against stale formal models.

Scope:

- hash lock of covered code and spec modules;
- validation timestamps;
- drift detection on code and spec changes;
- CI report and branch protection integration;
- stale-spec refusal mapping.

Deliverables:

- freshness lock v2;
- drift CI command;
- stale-spec refusal examples;
- dashboard-ready stale metrics.

Exit criteria:

- changed covered code invalidates freshness;
- changed spec invalidates freshness until trace/formal validation reruns;
- stale specs block release closure.

Required ADR:

- ADR 0142: Spec freshness, drift CI, and stale-spec refusal policy.

#### Phase 134 - Specula-Style Extraction Integration

Purpose: generate candidate formal specs for uncovered brownfield areas.

Scope:

- code presentation to extraction runner;
- LLM-generated candidate TLA/spec artifact;
- structural validation;
- trace-validation requirement;
- no-trust boundary for generated specs.

Deliverables:

- extraction runner interface;
- candidate spec artifact;
- structural validation report;
- trace validation hook;
- examples for accepted and rejected candidates.

Exit criteria:

- generated specs are labeled candidate-only;
- candidate specs cannot satisfy coverage or freshness until reviewed;
- structural and trace validation failures are recorded.

Required ADR:

- ADR 0143: Specula-style extraction trust model and runner contract.

#### Phase 135 - Candidate Spec Review And Promotion

Purpose: move candidate specs into reviewed system spec coverage safely.

Scope:

- review checklist for generated specs;
- promotion artifact;
- reviewer identity and hash binding;
- rejection reasons;
- freshness lock after promotion.

Deliverables:

- candidate review workflow;
- promotion report;
- rejection report;
- tests for stale candidate promotion.

Exit criteria:

- candidate spec promotion requires review;
- rejected candidates remain auditable;
- promoted specs enter coverage manifests and freshness locks.

Required ADR:

- ADR 0144: Candidate spec review, promotion, and rejection workflow.

#### Phase 136 - Runtime Trace Producer SDK Production

Purpose: make trace extraction real across supported ecosystems.

Scope:

- producer registry;
- extraction request/response;
- trace source metadata;
- loss records;
- runtime/tool version capture;
- replay inputs.

Deliverables:

- trace producer SDK v2;
- producer examples;
- signing support for trace producers;
- tests for missing, lossy, and complete traces.

Exit criteria:

- trace producers identify themselves and their runtime;
- lossy traces cannot satisfy high-assurance closure silently;
- trace artifacts can be retained and replayed.

Required ADR:

- ADR 0145: Runtime trace producer SDK and trace evidence metadata.

#### Phase 137 - Trace Validation Gate Production

Purpose: use traces as grounding evidence for current code behavior.

Scope:

- formal claim to trace predicate mapping;
- satisfaction, violation, coverage gap, lossy, stale, unsupported outcomes;
- cross-reference to coverage and freshness;
- product refusal mapping.

Deliverables:

- trace validation report v2;
- validation runner;
- refusal renderer;
- benchmark cases.

Exit criteria:

- trace contradictions block closure;
- missing trace coverage is distinct from contradiction;
- trace satisfaction is labeled grounding evidence, not proof.

Required ADR:

- ADR 0146: Trace validation closure policy and evidence labels.

### Milestone 13 - Programming-Language Adapter Closure

Objective: prove the system is a programming-language-agnostic Attestation
Layer, not a single-language validator.

Current base:

- `src/nlreq/source_adapter.py`
- `src/nlreq/adapter_certification.py`
- `src/nlreq/production_source_adapters.py`
- `src/nlreq/python_source_adapter.py`
- `src/nlreq/javascript_source_adapter.py`
- `docs/adapter-interface.md`
- `docs/adapter-authoring-guide.md`

Exit criteria:

- adapter interface v2 is stable;
- adapter capability claims are machine-readable;
- at least four materially different adapters pass certification;
- adapters produce normalized source, impact, coverage, and trace evidence;
- adapter-specific facts do not leak into requirement IR;
- public plugin SDK allows third-party adapters.

#### Phase 138 - Adapter Interface v2 Capability Contract

Purpose: make adapter requirements production-ready.

Scope:

- required and optional methods;
- capability levels;
- supported evidence labels;
- limitation declarations;
- normalized symbol and trace contracts;
- failure taxonomy.

Deliverables:

- adapter interface v2 spec;
- capability registry schema;
- conformance fixtures;
- migration guide.

Exit criteria:

- adapters cannot claim evidence they do not support;
- unsupported features are explicit;
- gate policy can require adapter capabilities.

Required ADR:

- ADR 0147: Adapter interface v2 and capability contract.

#### Phase 139 - Solidity Adapter Graduation

Purpose: graduate the transaction/event ecosystem adapter.

Scope:

- Solidity symbol resolution;
- ABI/event binding;
- transaction trace extraction;
- inheritance and overload handling;
- source impact and spec coverage mapping;
- Foundry/debug trace integration where available.

Deliverables:

- Solidity adapter;
- certification fixtures;
- trace producer integration;
- end-to-end requirement fixture.

Exit criteria:

- adapter passes v2 certification;
- ambiguous overloaded symbols block;
- transaction/event traces normalize without Solidity leakage into IR.

Required ADR:

- ADR 0148: Solidity adapter production scope and limitations.

#### Phase 140 - Go Adapter Graduation

Purpose: graduate a compiled service ecosystem adapter.

Scope:

- Go symbol resolution and package graph;
- call graph extraction;
- trace extraction through runtime traces/OpenTelemetry where applicable;
- Specula integration path;
- code-to-spec coverage mapping.

Deliverables:

- Go adapter;
- certification fixtures;
- brownfield demo module;
- trace producer integration.

Exit criteria:

- adapter passes v2 certification;
- call graph and package impact are deterministic for fixtures;
- traces normalize through the shared schema.

Required ADR:

- ADR 0149: Go adapter production scope and Specula integration.

#### Phase 141 - TypeScript And JavaScript Adapter Graduation

Purpose: cover frontend/service runtime requirements.

Scope:

- TypeScript compiler API or language-service resolution;
- JavaScript fallback behavior;
- browser and Node runtime trace sources;
- API route and event binding;
- source maps where needed.

Deliverables:

- TypeScript/JavaScript adapter;
- certification fixtures;
- browser/server trace examples;
- limitations for dynamic patterns.

Exit criteria:

- adapter handles static TypeScript fixtures;
- unsupported dynamic JavaScript is explicit;
- frontend/service traces can ground supported claims.

Required ADR:

- ADR 0150: TypeScript and JavaScript adapter production scope.

#### Phase 142 - Rust Or Java Adapter Graduation

Purpose: add a second compiled ecosystem pressure test.

Scope:

- select Rust or Java based on available tooling and reference demo needs;
- symbol and module resolution;
- call graph/dependency extraction;
- trace source integration;
- coverage mapping.

Deliverables:

- selected adapter;
- selection rationale;
- certification fixtures;
- end-to-end evidence fixture.

Exit criteria:

- selected adapter passes v2 certification;
- selection proves the interface is not Go-specific;
- unsupported ecosystem features are documented.

Required ADR:

- ADR 0151: Rust or Java adapter selection and graduation criteria.

#### Phase 143 - Adapter Certification And Plugin SDK

Purpose: make third-party adapter authoring possible.

Scope:

- public conformance harness;
- fixture format;
- plugin loading contract;
- adapter metadata;
- certification result taxonomy;
- authoring docs and examples.

Deliverables:

- adapter plugin SDK;
- certification CLI;
- public fixtures;
- adapter template;
- docs.

Exit criteria:

- third-party adapter can run conformance without modifying core;
- certification failures are actionable;
- public docs explain capability declarations and evidence limits.

Required ADR:

- ADR 0152: Adapter certification suite and plugin SDK contract.

### Milestone 14 - Cross-Language Evidence And Release Closure

Objective: finish the real conclusion claim by proving closure across
multi-adapter evidence, replayable artifacts, performance constraints, public
benchmarks, CI governance, and final certification.

Current base:

- `src/nlreq/cross_language.py`
- `src/nlreq/artifact_store.py`
- `src/nlreq/signed_evidence.py`
- `src/nlreq/evidence_producers.py`
- `src/nlreq/benchmark_reporting.py`
- `src/nlreq/ci_pr_gate.py`
- `src/nlreq/conclusion_certification.py`
- `tests/test_milestone_group9.py`

Exit criteria:

- one proof object can aggregate evidence across adapters;
- evidence is retained, replayable, and signed where required;
- performance is usable in CI;
- public benchmark results are reproducible;
- CI hard gate is branch-protection ready;
- reference brownfield demo and beta pilots exercise the real path;
- final certification cannot pass on scaffold evidence.

#### Phase 144 - Cross-Language Causal Proof Closure

Purpose: close requirements spanning multiple languages or runtimes.

Scope:

- causal trace links;
- per-adapter evidence hashes;
- cross-adapter blockers;
- proof object aggregation;
- mixed evidence labels.

Deliverables:

- cross-language proof object v2;
- causal link schema;
- multi-adapter fixture;
- closure gate integration.

Exit criteria:

- a multi-adapter requirement can close or refuse as one proof object;
- per-adapter blockers remain visible;
- causal trace gaps block relevant claims.

Required ADR:

- ADR 0153: Cross-language causal proof closure semantics.

#### Phase 145 - Evidence Replay And Signing Enforcement

Purpose: make high-assurance evidence reproducible and anti-forgery hardened.

Scope:

- replay bundle format;
- producer key registry;
- signature requirements by evidence level;
- artifact lookup validation;
- replay command metadata.

Deliverables:

- replay bundle v2;
- signing enforcement policy;
- replay verifier;
- tests for tampering, missing producer, untrusted key, and missing artifact.

Exit criteria:

- high-assurance evidence requires registered producer identity;
- signed evidence verifies against retained payload hashes;
- release certification blocks missing replay bundles.

Required ADR:

- ADR 0154: Evidence replay bundle and signing enforcement policy.

#### Phase 146 - Performance, Caching, And Parallel Dispatch

Purpose: make the gate usable in real CI workflows.

Scope:

- cache keys for translation, formal backend, trace validation, and adapter
  evidence;
- parallel dispatch;
- timeout coordination;
- incremental invalidation;
- runtime reporting.

Deliverables:

- cache policy v2;
- parallel dispatcher;
- performance benchmark;
- CI runtime budgets.

Exit criteria:

- unchanged evidence reuses cache safely;
- changed inputs invalidate cache;
- CI runtime stays within configured release budget for reference demo.

Required ADR:

- ADR 0155: Performance, caching, and parallel dispatch policy.

#### Phase 147 - Public Benchmark Suite And Leaderboard

Purpose: make public evaluation credible.

Scope:

- benchmark case taxonomy;
- release thresholds;
- public results format;
- false closure/refusal accounting;
- counterexample quality scoring;
- adapter and trace coverage dimensions.

Deliverables:

- public benchmark suite;
- leaderboard/report format;
- benchmark runner;
- expected results and observed results examples.

Exit criteria:

- public report names all benchmark dimensions;
- false closure is release-blocking under configured budget;
- benchmark cases cover translation, formal, trace, adapter, and release gates.

Required ADR:

- ADR 0156: Public benchmark suite, scoring, and reporting policy.

#### Phase 148 - Reference Brownfield Demo And Beta Pilots

Purpose: prove the system in a credible workflow.

Scope:

- select real or realistic brownfield system;
- run accepted and refused requirements;
- retain replay bundles;
- capture CI and PR outputs;
- collect beta pilot feedback.

Deliverables:

- reference demo repository or fixture set;
- demo runbook;
- replay bundles;
- beta pilot reports;
- known limitations.

Exit criteria:

- at least one accepted and one refused requirement run through the real path;
- demo artifacts are replayable;
- beta pilot feedback is captured as release findings.

Required ADR:

- ADR 0157: Reference brownfield demo and beta pilot acceptance criteria.

#### Phase 149 - CI Adoption And Policy Governance Hardening

Purpose: make action gating enforceable in normal repositories.

Scope:

- GitHub/GitLab CI examples;
- required-check semantics;
- waiver policy;
- branch protection integration;
- policy drift detection;
- audit retention.

Deliverables:

- CI integration templates;
- policy governance report v2;
- waiver audit integration;
- branch-protection runbook.

Exit criteria:

- hard-gate mode can be used as a required check;
- waivers are hash-bound, time-limited, and auditable;
- policy changes are retained and reviewed.

Required ADR:

- ADR 0158: CI adoption, waiver governance, and branch-protection policy.

#### Phase 150 - Final Real-Evidence Conclusion Certification

Purpose: certify the scoped real-evidence conclusion release.

Scope:

- collect all required milestone evidence;
- verify schema freeze;
- verify replay bundles and signatures;
- verify benchmark thresholds;
- verify docs and TCB review;
- sign release bundle;
- publish public claim boundaries.

Deliverables:

- final certification report;
- signed release bundle;
- public limitations document;
- release checklist;
- reproducibility instructions.

Exit criteria:

- certification blocks on missing or scaffold-only evidence;
- public claim language is scoped to supported adapters, claims, bounds, and
  evidence labels;
- release bundle can be replayed by an external reviewer.

Required ADR:

- ADR 0159: Final real-evidence conclusion certification and public claim
  boundary.

## Cross-Milestone Dependencies

- Phase 119 depends on Phase 117 and Phase 118.
- Phase 120 depends on Phase 119 and benchmark labels from Phase 123.
- Phase 122 depends on Phase 124 semantics for deeper formal checks.
- Phase 127 depends on Phases 124-126 and reviewed system specs from Phase 132.
- Phase 134 depends on Phase 131 impact and Phase 132 coverage manifest.
- Phase 135 depends on Phase 134 candidate extraction.
- Phase 137 depends on Phases 136, 132, and 133.
- Phases 139-142 depend on Phase 138.
- Phase 144 depends on at least two graduated adapters from Phases 139-142.
- Phase 145 depends on producer identities from adapters and trace producers.
- Phase 147 should begin early but cannot finalize thresholds until Phases
  119-145 produce real benchmarkable evidence.
- Phase 150 depends on every previous phase in this roadmap.

## Evidence Label Policy

The following evidence-label discipline remains mandatory:

- `TYPE_CHECKED` requires schema/type validation over exact input hashes.
- `STATICALLY_RESOLVED` requires adapter-certified symbol resolution.
- `SMT_CHECKED` requires solver command, version, options, and replayable query.
- `BOUNDED_CHECKED` requires model checker command, version, bounds, options,
  and normalized output.
- `CONSISTENCY_CHECKED` requires named self-consistency or `S and R` semantics.
- `TRACE_VALIDATED` requires normalized traces from registered producers and loss
  policy outcome.
- `REVIEWED` requires hash-bound reviewer identity and stale-review detection.
- `SIGNED` requires verified producer key and payload hash.
- `PROVEN_INDUCTIVE` is reserved for proof-producing backends with checked proof
  artifacts.

No phase in this roadmap may weaken these labels.

## Highest-Risk Gaps

1. **Semantic false acceptance:** The translator accepts a requirement with the
   wrong meaning. Mitigation: controlled input, ensemble disagreement,
   provenance, clarification, and benchmark false-acceptance budgets.
2. **Spec fiction:** The system spec describes an idealized system instead of
   current code. Mitigation: spec freshness, trace validation, candidate spec
   review, and drift CI.
3. **State-space explosion:** Formal backends time out or under-approximate.
   Mitigation: explicit budgets, unknown outcomes, bounds in evidence, and
   compositional verification.
4. **Adapter leakage:** Language-specific facts enter the requirement IR.
   Mitigation: adapter interface v2, capability registry, and certification.
5. **Evidence forgery or replay:** Reports reference artifacts that cannot be
   reproduced. Mitigation: artifact store, replay bundles, producer registry,
   signatures, and release bundle verification.
6. **Benchmark gaming:** Public numbers improve without testing real risks.
   Mitigation: corpus-scoped scoring, false closure budgets, dimension coverage,
   and public fixtures.

## Immediate Next Work

The highest-leverage next implementation target is one real vertical closure,
not another release-report layer:

```text
one non-toy controlled requirement
-> semantic decomposition translator
-> formal claim R
-> real reviewed system spec S
-> real Apalache or TLC execution over S and R
-> real trace validation from current code
-> proof object closes or refuses
```

Recommended first sprint:

1. Implement Phase 117 and Phase 118 enough to run approved controlled input
   through replayable rewrite provenance.
2. Implement Phase 119 for one or two claim classes using the existing formal
   claim IR.
3. Implement Phase 125 on a small real TLA model with Apalache output fixtures.
4. Build one benchmark case that must refuse due to semantic ambiguity and one
   that must refuse due to formal counterexample.
5. Use those cases to drive Phase 123 benchmark thresholds before expanding
   adapters.

This keeps momentum anchored on the original Claude-conversation thesis:
requirements should not proceed because an agent sounded confident; they should
proceed only when the required premises close with recorded evidence.
