# Verification Power Roadmap

**Status:** Draft v1  
**Date (UTC):** 2026-06-01  
**Starts After:** Phase 29 Agnostic Wedge  
**Source:** `docs/claude-convo.md`

Phases 19-29 built the architecture: compositional IR, source adapter boundary,
formal backend boundary, system spec registry, coverage and trace alignment,
proof closure, and the agnostic wedge.

This roadmap is the next program: turn that architecture into verification
power. The goal is to move from schema-backed deterministic closure to real
solver-backed, trace-grounded, reproducible verification.

## Current Baseline

The system can now express and gate the desired flow:

```text
controlled requirement -> compositional IR -> formal artifact boundary
-> system/spec consistency result -> coverage and trace alignment
-> proof object -> closure gate -> agnostic wedge
```

The current implementation is intentionally conservative. Several components
are boundary or MVP implementations:

- formal backends define contracts but do not yet execute Apalache, TLC, TLAPS,
  Alloy, Lean, or another real checker;
- `S and R` checking is deterministic and marker-based, not solver-backed;
- trace alignment classifies normalized traces but does not replay real runtime
  traces against a formalized requirement;
- spec coverage is registry-based, not code-to-spec extraction;
- translation lowers to a TLA skeleton but does not prove semantic equivalence;
- proof closure aggregates evidence, but high-assurance producers are not yet
  real integrations.

## Target Capability

The target from `docs/claude-convo.md` is:

```text
NL or controlled requirement -> formal claim R
R checked against itself
R checked against the existing system spec S
R grounded against current code behavior through traces
all affected code areas covered by fresh reviewed specs
all evidence emitted by real registered producers
proof object closes
downstream action is allowed only after closure
```

The decisive difference is that failures should be mathematical or empirical
artifacts:

- parser disagreement;
- unsupported formal fragment;
- self-contradiction;
- model-checker counterexample;
- timeout with explicit verification budget;
- stale or missing spec coverage;
- trace mismatch against current behavior;
- backend disagreement;
- untrusted producer attempting to claim high assurance.

## Operating Rule

Do not add assurance labels before the producer exists.

`BOUNDED_CHECKED` requires a real bounded checker run with recorded bounds.
`PROVEN_INDUCTIVE` requires a real proof backend or proof assistant result.
Trace observations and LLM translations remain non-proof context unless a
separate deterministic checker consumes them.

## Phase Sequence

| Phase | Name | Verification gain | Outcome |
|---|---|---|---|
| 30 | Real Model-Checker Runner | real bounded verification | Execute a model checker with budgets, normalized results, and counterexamples. |
| 31 | TLA+ Backend MVP | first real formal target | Lower supported IR to runnable TLA+ and execute Apalache or TLC. |
| 32 | Requirement Self-Consistency | reject contradictory R | Check formalized requirements before composing with system specs. |
| 33 | Solver-Backed `S and R` | real system compatibility | Compose reviewed system specs with R and return solver-backed compatibility. |
| 34 | Translator Agreement Gate | untrusted NL/formal bridge | Multi-translation, structural comparison, disagreement refusal, clarification output. |
| 35 | Trace Replay Grounding | Specula-style grounding | Replay real traces against R and selected S context, not only classify actions. |
| 36 | Spec Extraction Workbench | code to candidate spec | Generate candidate specs for under-specified modules with review-only status. |
| 37 | Spec Drift CI | freshness from code changes | Detect code/spec drift and block stale specs before proof closure. |
| 38 | Impact Analysis v2 | better brownfield targeting | Combine static call graph, manifests, and semantic disagreement checks. |
| 39 | Delta Extractor | actionable requirement review | Emit required spec, code, test, and trace deltas from failed checks. |
| 40 | Verification Budget And Abstraction | state-space control | Record bounds, timeouts, abstraction levels, and compositional assumptions. |
| 41 | Real Evidence Producers | trustworthy proof levels | Map actual tools to evidence levels and reproducibility metadata. |
| 42 | Backend Agreement | multi-backend confidence | Compare results from at least two formal targets where semantics overlap. |
| 43 | Second Real Source Adapter | real agnosticism | Close a proof object over a second production language adapter. |
| 44 | End-To-End Requirement Gate | product-grade closure | One command gates a requirement from input through proof closure. |
| 45 | Public Benchmark Corpus | measurable progress | Track examples, counterexamples, timeouts, drift, and closure rates. |

## Phase Details

### Phase 30 - Real Model-Checker Runner

Purpose: replace boundary-only backend status with actual checker execution.

Scope:

- define a runner interface for local executable tools;
- support timeout, max depth, max states, memory budget, and solver options;
- normalize stdout/stderr, exit code, tool version, and command line;
- parse valid, counterexample, timeout, unsupported, and tool-error outcomes;
- store reproducibility metadata.

Exit criteria:

- at least one real checker command can run from the CLI;
- results include exact bounds and command metadata;
- counterexample artifacts are normalized;
- timeout and tool-error never approve.

Required ADR:

- ADR 0039: Model-checker runner contract and reproducibility metadata.

### Phase 31 - TLA+ Backend MVP

Purpose: make TLA+ a real formal target, not only a lowering skeleton.

Scope:

- choose first execution target: Apalache for bounded symbolic checks or TLC for
  explicit-state checks;
- define supported IR fragment for runnable TLA+;
- emit `.tla` and config artifacts;
- execute the runner from Phase 30;
- map real checker outcomes to `BackendResult`;
- record bounds as evidence metadata.

Exit criteria:

- a supported DSL v2 fixture lowers to runnable TLA+;
- the checker runs in tests or an integration test path;
- valid and counterexample outcomes are both represented;
- successful bounded runs may emit `BOUNDED_CHECKED`, not
  `PROVEN_INDUCTIVE`.

Required ADR:

- ADR 0040: First real TLA+ execution target and bounded-evidence semantics.

### Phase 32 - Requirement Self-Consistency

Purpose: reject formalized requirement `R` before composing it with system spec
`S` when `R` is internally contradictory.

Scope:

- build a self-consistency request from `RequirementIRV2`;
- run the formal backend over `R` alone;
- detect contradictory obligations, impossible preconditions, and unsupported
  temporal forms;
- return structured refusal and source spans.

Exit criteria:

- contradictory fixtures fail before system composition;
- unsupported fragments name the exact IR node;
- timeouts record budget and never approve.

Required ADR:

- ADR 0041: Requirement self-consistency semantics and contradiction evidence.

### Phase 33 - Solver-Backed `S and R`

Purpose: replace the current marker-based `S and R` checker with real
composition against reviewed system specs.

Scope:

- compose selected system specs `S` with requirement fragment `R`;
- define composition points: invariants, actions, assumptions, and temporal
  bounds;
- execute the selected checker;
- return counterexamples naming invariant, action, state, and requirement node
  where available.

Exit criteria:

- system compatibility is backed by a real checker run;
- counterexamples include actionable trace/state data;
- stale, missing, or unreviewed specs still block before execution;
- successful bounded checks emit only bounded evidence.

Required ADR:

- ADR 0042: Solver-backed system consistency and counterexample contract.

### Phase 34 - Translator Agreement Gate

Purpose: treat NL to formal translation as untrusted and require agreement
before downstream verification.

Scope:

- run multiple translator strategies over the same controlled requirement;
- compare generated IR/formal fragments structurally;
- detect semantic disagreements in actions, predicates, bounds, and obligations;
- emit clarification questions when disagreement is material;
- prohibit unapproved or disagreed translations from proof closure.

Exit criteria:

- agreement and disagreement fixtures are deterministic;
- disagreements identify the conflicting fragment;
- translation provenance is preserved;
- LLM-originated output cannot auto-approve.

Required ADR:

- ADR 0043: Translator agreement, equivalence limits, and clarification loop.

### Phase 35 - Trace Replay Grounding

Purpose: make trace validation semantic, not only action-name alignment.

Scope:

- bind normalized trace events to IR nodes and formal actions;
- replay trace sequences against the requirement model where supported;
- classify already-satisfied, violating, uncovered, and unsupported behavior;
- preserve lossy-normalization warnings from adapters;
- make trace coverage a proof-context gate, not proof itself.

Exit criteria:

- real traces from at least one adapter replay against a requirement;
- violations include event ids and expected/actual state fragments;
- uncovered behavior blocks closure unless explicitly waived by policy;
- trace replay never emits `PROVEN_INDUCTIVE`.

Required ADR:

- ADR 0044: Trace replay semantics and lossy-normalization limits.

### Phase 36 - Spec Extraction Workbench

Purpose: support brownfield apps where affected modules have no reviewed formal
spec.

Scope:

- add a Specula-like workbench for code to candidate spec;
- combine static structure, code presentation, LLM draft, and trace grounding;
- mark all extracted specs as draft until reviewed;
- record extraction provenance and known gaps;
- never let extracted draft specs satisfy freshness or proof closure.

Exit criteria:

- under-specified modules can produce candidate specs;
- candidate specs have trace-grounding reports;
- review promotion is explicit and hash-based;
- draft extraction output cannot close proofs.

Required ADR:

- ADR 0045: Spec extraction workbench, review promotion, and draft trust model.

### Phase 37 - Spec Drift CI

Purpose: keep formal specs from becoming fiction as code changes.

Scope:

- extend code-to-spec manifest with source hashes and dependency edges;
- detect changed code that affects covered modules;
- mark specs stale automatically;
- run trace replay or extraction workbench suggestions in CI;
- block closure on stale specs.

Exit criteria:

- code changes can stale affected spec entries deterministically;
- stale specs block proof closure;
- CI reports name affected modules, specs, and required refresh actions.

Required ADR:

- ADR 0046: Spec drift invariant, code-to-spec hash model, and CI enforcement.

### Phase 38 - Impact Analysis v2

Purpose: improve brownfield targeting before spec coverage and verification.

Scope:

- add deterministic call graph expansion for the first real source adapter;
- combine symbol bindings, manifests, imports, and runtime trace touchpoints;
- add optional semantic impact suggestions as disagreement context only;
- report deterministic/semantic conflicts.

Exit criteria:

- affected modules are derived from source structure, not only manifest entries;
- impact disagreements are visible and non-approving;
- spec coverage consumes the richer impact report.

Required ADR:

- ADR 0047: Impact analysis v2 and semantic-disagreement policy.

### Phase 39 - Delta Extractor

Purpose: convert failed verification into senior-review-grade action items.

Scope:

- consume self-consistency, `S and R`, trace replay, coverage, and drift reports;
- emit required changes to specs, code modules, tests, traces, and requirements;
- include counterexample summaries and source spans;
- distinguish code-change-needed from requirement-change-needed.

Exit criteria:

- failed closure produces a deterministic delta report;
- reports are stable JSON plus human-readable markdown;
- PR/backlog integration can consume the delta report.

Required ADR:

- ADR 0048: Delta extraction taxonomy and ownership boundaries.

### Phase 40 - Verification Budget And Abstraction

Purpose: handle state-space explosion honestly.

Scope:

- define verification budgets by requirement class;
- record bounded depth, finite domains, abstraction level, and assumptions;
- support timeout, unknown, and inconclusive outcomes;
- introduce compositional assumptions for subsystem checks.

Exit criteria:

- every bounded proof object records its bounds;
- timeout and unknown are distinct from counterexample;
- abstraction assumptions are reviewable and hash-addressed;
- budget exhaustion cannot approve.

Required ADR:

- ADR 0049: Verification budgets, abstraction levels, and unknown semantics.

### Phase 41 - Real Evidence Producers

Purpose: make proof closure depend on actual tools, not trusted labels.

Scope:

- register real producer identities for Apalache/TLC/TLAPS or selected tools;
- record binary path, version, command, input hashes, and output hashes;
- enforce producer-to-evidence-level policy;
- reject forged or manually edited high-assurance evidence.

Exit criteria:

- proof closure validates producer metadata;
- high-assurance levels require a real producer;
- reproducibility metadata is sufficient to rerun the check.

Required ADR:

- ADR 0050: Real evidence producer registry and anti-forgery checks.

### Phase 42 - Backend Agreement

Purpose: raise confidence by comparing overlapping formal targets.

Scope:

- run two backends over an overlapping supported fragment;
- compare result status, bounds, unsupported constructs, and counterexamples;
- block closure on backend disagreement unless policy scopes it to report-only;
- record non-overlapping semantics explicitly.

Exit criteria:

- at least one fixture runs through two formal targets;
- agreement and disagreement are deterministic artifacts;
- backend disagreement cannot be hidden inside a closed proof.

Required ADR:

- ADR 0051: Multi-backend agreement semantics and non-overlap policy.

### Phase 43 - Second Real Source Adapter

Purpose: make the agnostic claim operational with a second production adapter.

Scope:

- select a second real source ecosystem;
- implement manifest parsing, symbol resolution, call graph, code presentation,
  trace extraction, and conformance tests;
- run impact, coverage, trace replay, and proof closure through it;
- compare normalized trace limits against the first adapter.

Exit criteria:

- two production adapters pass the same conformance suite;
- an agnostic wedge closes over cross-language evidence;
- adapter-specific facts remain outside the IR spine.

Required ADR:

- ADR 0052: Second source adapter selection and cross-language evidence model.

### Phase 44 - End-To-End Requirement Gate

Purpose: package the envisioned workflow as one product-grade command.

Scope:

- one CLI/API entry point for requirement intake;
- execute parse, translation agreement, self-consistency, impact, coverage,
  system consistency, trace replay, delta extraction, proof object, and closure
  gate;
- return one structured acceptance or refusal artifact.

Exit criteria:

- a requirement can be accepted, refused, or marked unknown by one command;
- all intermediate artifacts are stored and hash-linked;
- no downstream action can proceed without closed proof.

Required ADR:

- ADR 0053: End-to-end requirement gate artifact and action API contract.

### Phase 45 - Public Benchmark Corpus

Purpose: measure whether verification power is improving.

Scope:

- create a corpus of requirements, specs, code samples, traces, and expected
  outcomes;
- include positive closures, counterexamples, parser disagreements, stale specs,
  trace mismatches, timeouts, and backend disagreements;
- track closure rate, false closure rate, counterexample quality, and runtime.

Exit criteria:

- every future phase can be evaluated against stable examples;
- regressions in refusal or closure behavior are visible;
- benchmark results are publishable as evidence of progress.

Required ADR:

- ADR 0054: Verification benchmark corpus and quality metrics.

## ADR Queue

| ADR | Title | Phase |
|---|---|---|
| 0039 | Model-checker runner contract | 30 |
| 0040 | First real TLA+ execution target | 31 |
| 0041 | Requirement self-consistency semantics | 32 |
| 0042 | Solver-backed system consistency | 33 |
| 0043 | Translator agreement and clarification loop | 34 |
| 0044 | Trace replay semantics | 35 |
| 0045 | Spec extraction workbench trust model | 36 |
| 0046 | Spec drift invariant and CI enforcement | 37 |
| 0047 | Impact analysis v2 | 38 |
| 0048 | Delta extraction taxonomy | 39 |
| 0049 | Verification budgets and unknown semantics | 40 |
| 0050 | Real evidence producer registry | 41 |
| 0051 | Multi-backend agreement semantics | 42 |
| 0052 | Second source adapter selection | 43 |
| 0053 | End-to-end requirement gate | 44 |
| 0054 | Verification benchmark corpus | 45 |

## Recommended Build Order

Build in this order if the goal is maximum verification gain per phase:

1. Phase 30 and Phase 31 first, because real checker execution changes evidence
   semantics everywhere.
2. Phase 32 and Phase 33 next, because self-consistency and solver-backed
   `S and R` are the core of requirement validation.
3. Phase 35 and Phase 37 before broad extraction, because traces and drift are
   what prevent formal specs from becoming fiction.
4. Phase 36 after trace grounding exists, so extracted specs can be validated
   against real behavior.
5. Phase 39 and Phase 44 when the refusal surface needs to become a usable
   product workflow.
6. Phase 42 and Phase 43 once one real backend and one real adapter are stable.

## What Not To Do

- Do not label any result `PROVEN_INDUCTIVE` until a real proof backend exists.
- Do not treat LLM-generated TLA+ as accepted without agreement checks and
  deterministic validation.
- Do not let draft extracted specs satisfy coverage.
- Do not allow trace observations to replace formal proof.
- Do not hide timeouts or state-space limits behind green statuses.
- Do not build broad adapter support before the first real verifier path is
  genuinely useful.
