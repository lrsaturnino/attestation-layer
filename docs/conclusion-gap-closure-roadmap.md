# Conclusion Gap Closure Roadmap

**Status:** Draft planning document  
**Extends:** `docs/nl-attestation-conclusion-roadmap.md` phases 46-82  
**Starts at:** Phase 83, ADR 0092  
**Source context:** `docs/claude-convo.md`, current implementation through `d03252e`  
**Purpose:** Close the gap between the current Attestation Layer and the end-state discussed in `claude-convo.md`: a general-purpose requirement gate that turns human requirements into auditable formal claims, checks those claims against themselves and the current system model, grounds them in real code and traces, and allows downstream action only when the evidence closes.

## Executive Summary

The current repository has the right architecture shape. It already contains:

- controlled requirement parsing and compositional IR;
- review, provenance, clarification, and refusal surfaces;
- source adapter interfaces and conformance concepts;
- system spec registry, spec coverage, trace alignment, trace replay, and spec freshness artifacts;
- TLA projection, model-checker runner contracts, Apalache/TLC backend wrappers, system consistency checks, proof objects, and closure gates;
- evidence retention, signatures, CI/PR reporting, benchmark evaluation, threat model, public docs, and conclusion certification artifacts.

The remaining gap is not mostly "more files." The remaining gap is evidence strength and semantic depth.

The current state is best described as a broad deterministic scaffold. It proves that the pieces can be named, serialized, routed, and tested together. It does not yet prove that the system can reliably vet real natural-language requirements against real brownfield systems with production-grade formal semantics and trace-grounded evidence.

This roadmap extends the conclusion work after Phase 82. It groups the missing work into consolidated milestones rather than another long flat checklist. Each milestone has phases, ADRs, exit criteria, and evidence bars.

## Current-State Assessment

### What Is Already Credible

| Area | Current State | Credibility |
|---|---|---|
| Adapter-agnostic architecture | `SourceLanguageAdapter`, source manifests, routing, conformance docs, multiple adapter families | Strong architectural foundation |
| Controlled input | DSL parsing, free-form intake, controlled rewrite approval, review workflow | Good first-version controlled path |
| Provenance and refusal | Source spans, provenance graph, clarification loop, product refusal report | Good user-facing refusal skeleton |
| IR and schemas | Compositional IR, schema generation, artifact catalog | Good serialization and audit base |
| Formal backend boundary | Model-checker runner, backend request/response, TLA adapter, Apalache/TLC backend classes | Good boundary; production execution depth still limited |
| System consistency | Deterministic and solver-backed `S and R` checks | Useful scaffold; not yet mature formal composition |
| Brownfield grounding | source impact, spec coverage, trace alignment/replay, spec drift/freshness | Good contracts; needs real-world pressure |
| Evidence closure | proof object, closure gate, evidence boundary | Good closure semantics; evidence quality still uneven |
| Release controls | benchmark evaluation, signed evidence, artifact store, CI/PR gate, threat model, conclusion certification | Good release shape; not yet enough production signal |

### What Is Still Missing

| Gap | Why It Matters | Current Weakness | Required End State |
|---|---|---|---|
| Semantic translation robustness | The product lives or dies on NL/controlled requirement meaning | Multi-pass and logical agreement exist, but not a production Req2LTL-style semantic translator | Controlled text maps to formal claims with measurable semantic accuracy, disagreement handling, and bidirectional repair |
| Formal claim semantics | A formal projection must mean the same thing as the requirement | TLA projection is narrow and mostly artifact-level | Every supported claim kind has explicit semantics, executable checks, and refusal behavior |
| Real `S and R` closure | The core promise is checking requirement R against system S | Current composition is useful but not a complete formal compatibility engine | Supported R claims compose with reviewed S specs through Apalache/TLC or SMT with reproducible counterexamples |
| Trace grounding | Prevents checking fiction instead of current code | Normalized traces and replay exist, but real producer coverage is shallow | Adapters emit normalized traces that can validate formal claims against current behavior |
| Specula-style extraction | Brownfield systems rarely start with formal specs | Extraction workbench exists as a candidate path, not production trust workflow | Missing spec coverage produces reviewed candidate specs, freshness locks, and explicit promotion workflow |
| Adapter agnosticism under pressure | The architecture claim must survive real ecosystems | Interfaces exist; only shallow/limited production pressure | At least two real adapters satisfy one shared evidence/trace/conformance contract without IR leakage |
| Evidence producer integrity | High-assurance claims require real producer identity and replay | Signing/artifact store exist; producer trust is early | Evidence is retained, reproducible, signed when required, and tied to producer capability records |
| Public benchmark signal | Prevents "demo passed" from becoming false confidence | Corpus/reporting exist; coverage and difficulty are limited | Public benchmark tracks false closure, false refusal, semantic mismatch, counterexample quality, runtime, and adapter coverage |
| Conclusion certification bar | Current certification checks artifact presence, not enough real closure | Certification can pass on scaffold-level evidence | Certification requires real vertical closures, benchmark thresholds, producer trust, and documented limitations |

## Target Product Shape

The end-state from `claude-convo.md` is:

```text
Human requirement
  -> controlled requirement or approved rewrite
  -> structured semantic IR
  -> formal claim R
  -> self-consistency check over R
  -> impact and spec coverage check
  -> freshness check for existing system spec S
  -> formal compatibility check over S and R
  -> trace validation against current behavior
  -> proof object and closure decision
  -> accepted package or structured refusal
```

The critical product rule:

```text
No downstream action is allowed merely because a model, prompt, reviewer, or
doc says the requirement is acceptable. Action is allowed only when the required
premises close with recorded evidence at the configured evidence level.
```

This roadmap treats that as the conclusion target.

## Evidence Levels Required For The Extended Conclusion

The extended conclusion must keep the existing evidence-label discipline and make the following stricter:

| Evidence Label | Extended Conclusion Requirement |
|---|---|
| `TYPE_CHECKED` | Only emitted by schema/type validators with exact input hashes. |
| `STATICALLY_RESOLVED` | Only emitted by an adapter passing conformance for the relevant symbol class. |
| `SMT_CHECKED` | Requires solver command/version/options and a replayable SMT query artifact. |
| `BOUNDED_CHECKED` | Requires model checker command/version/options, explicit bounds, and normalized result parsing. |
| `CONSISTENCY_CHECKED` | Requires self-consistency or `S and R` compatibility check with named semantics. |
| `TRACE_VALIDATED` | Requires normalized traces from a registered producer and loss policy result. |
| `REVIEWED` | Requires hash-bound review artifact, reviewer identity, checklist, and stale detection. |
| `PROVEN_INDUCTIVE` | Reserved for a proof-producing backend such as TLAPS/Lean/Coq/Dafny with proof artifact. |

No extended conclusion phase may weaken these labels.

## Consolidated Milestones

| Milestone | Phases | Name | Outcome |
|---:|---:|---|---|
| 5 | 83-88 | Semantic Translation Closure | Requirements translate into formal claims with measurable semantic fidelity and repairable refusals. |
| 6 | 89-95 | Formal System Closure | Supported claims close against reviewed system specs through real model-checking or solver-backed semantics. |
| 7 | 96-102 | Brownfield Grounding Closure | Impact, spec coverage, Specula-style extraction, freshness, and trace validation become production-grade. |
| 8 | 103-109 | Adapter And Evidence Closure | Adapter agnosticism is proven through real conformance, normalized evidence, and multi-adapter proof closure. |
| 9 | 110-116 | Release And Adoption Closure | Benchmarks, CI gates, public docs, threat model, and certification enforce the real conclusion bar. |

Each milestone is intentionally larger than a phase group. The project should not declare extended conclusion by finishing one group in isolation; the final release requires all five.

## Milestone 5: Semantic Translation Closure

### Objective

Turn the current controlled-input and translator-workbench scaffold into a robust semantic translation pipeline. The system must distinguish:

- syntactic validity;
- structural agreement;
- semantic agreement;
- unsupported semantics;
- ambiguous controlled text;
- free-form rewrite risk;
- reviewer-approved controlled intent.

### Current Base

Relevant current artifacts:

- current controlled-language parser modules
- `src/nlreq/intake.py`
- `src/nlreq/review_workflow.py`
- `src/nlreq/translator_workbench.py`
- `src/nlreq/translator_agreement.py`
- `src/nlreq/logical_agreement.py`
- `src/nlreq/provenance.py`
- `src/nlreq/refusal.py`
- `docs/phase-47-free-form-intake-controlled-rewrite.md`
- `docs/phase-51-multi-pass-nl-translator-workbench.md`
- `docs/phase-53-logical-translator-agreement.md`

### Exit Criteria

Milestone 5 exits only when:

- supported controlled requirements lower into a formal-claim IR with canonical semantics;
- unsupported language produces stable structured refusal, not partial translation;
- free-form rewrites preserve original text, diff, approval, and model metadata;
- translator disagreement blocks acceptance unless a reviewer resolves it;
- formal claim fragments retain source-span provenance back to canonical controlled text;
- a semantic translation benchmark reports syntactic validity, semantic match, ambiguity rate, clarification quality, and false acceptance;
- at least three supported claim classes have golden fixtures across accepted, refused, and needs-review outcomes.

### Phases

| Phase | Name | Purpose | Primary Deliverables | Required ADR |
|---:|---|---|---|---|
| 83 | Formal Claim IR | Define the requirement-to-formal-claim layer between controlled text and backend-specific targets. | `FormalClaim`, claim grammar, source-span model, schema, golden fixtures | ADR 0092 |
| 84 | Controlled Requirement Semantics | Specify semantics for each supported controlled-language construct. | semantics reference, parser diagnostics, canonicalization tests | ADR 0093 |
| 85 | Req2LTL-Style Intermediate Translator | Add a two-stage translator: controlled/NL candidate -> semantic tree -> formal claim. | semantic tree schema, deterministic lowering rules, translator fixtures | ADR 0094 |
| 86 | Semantic Agreement Gate | Move beyond structural comparison for supported formulas. | equivalence profiles, disagreement report, refusal mapping | ADR 0095 |
| 87 | Translation Repair And Clarification UX | Make refusals actionable through provenance and next actions. | source-span highlighting, clarification prompt schema, repair loop | ADR 0096 |
| 88 | Semantic Translation Benchmark Expansion | Measure whether translation is good enough for conclusion claims. | benchmark corpus, semantic labels, scoring report, thresholds | ADR 0097 |

### ADR Backlog

| ADR | Title | Decision Required |
|---:|---|---|
| 0092 | Formal Claim IR Boundary | Decide what lives in formal claim IR versus backend projections. |
| 0093 | Controlled Requirement Semantics | Define exact semantics of supported controlled text and refusal behavior. |
| 0094 | Two-Stage Semantic Translation Pipeline | Commit to intermediate-tree translation rather than direct NL-to-backend output. |
| 0095 | Semantic Agreement And Equivalence Profiles | Define supported equivalence checks, limits, and disagreement policy. |
| 0096 | Clarification And Repair Protocol | Define how users repair ambiguous or unsupported requirements. |
| 0097 | Semantic Translation Benchmark Methodology | Define benchmark labels, scoring, thresholds, and false-acceptance budget. |

### Non-Goals

- General free-form NL acceptance without controlled approval.
- Full semantic equivalence across arbitrary formulas.
- Translation into every formal backend.
- Treating LLM output as evidence without deterministic or reviewed gates.

## Milestone 6: Formal System Closure

### Objective

Make the formal core strong enough to support the central claim:

```text
Given existing reviewed system spec S and new requirement claim R, the tool can
deterministically decide whether supported fragments of S and R are compatible,
or return a bounded/unknown/counterexample result with honest evidence labels.
```

### Current Base

Relevant current artifacts:

- `src/nlreq/tla_projection.py`
- `src/nlreq/formal_backend.py`
- `src/nlreq/model_checker_runner.py`
- `src/nlreq/system_checker.py`
- `src/nlreq/system_spec.py`
- `src/nlreq/system_composition.py`
- `src/nlreq/counterexample_normalization.py`
- `src/nlreq/proof_closure.py`
- `src/nlreq/evidence_boundary.py`
- `docs/phase-56-apalache-backend-production-integration.md`
- `docs/phase-57-tlc-backend-production-integration.md`
- `docs/phase-60-real-s-and-r-composition.md`

### Exit Criteria

Milestone 6 exits only when:

- every supported formal claim has a documented projection into at least one checking backend;
- Apalache and TLC integrations parse real success, violation, timeout, unsupported, and missing-tool outcomes;
- `S and R` composition is reproducible and produces named invariant/counterexample results;
- counterexamples are normalized with enough information for refusal, PR comment, benchmark, and reproduction;
- verification budgets produce honest `unknown` instead of false success;
- no bounded result is labeled as inductive proof;
- at least one non-toy system spec can accept and reject real requirement claims.

### Phases

| Phase | Name | Purpose | Primary Deliverables | Required ADR |
|---:|---|---|---|---|
| 89 | Formal Claim To TLA Semantics | Specify lowering from formal claim IR into TLA modules/configs. | projection rules, golden `.tla` outputs, unsupported diagnostics | ADR 0098 |
| 90 | Production Apalache Result Parser | Replace shallow command status handling with normalized Apalache semantics. | parser, counterexample extraction, fixture corpus | ADR 0099 |
| 91 | Production TLC Result Parser | Add explicit TLC outcome parsing and normalization. | TLC parser, invariant violation fixtures, timeout fixtures | ADR 0100 |
| 92 | Real `S and R` Composition Engine | Compose reviewed system spec S with requirement R using backend-checkable artifacts. | composition module, invariant preservation report, compatibility fixtures | ADR 0101 |
| 93 | Counterexample Explanation Quality | Turn backend traces into actionable product refusals and deltas. | explanation renderer, provenance map, benchmark scoring | ADR 0102 |
| 94 | Verification Budget Enforcement | Make timeout, state-space limit, and abstraction explicit closure outcomes. | budget schema, cache interaction, unknown policy | ADR 0103 |
| 95 | Inductive Proof Producer Boundary | Define what would be required for TLAPS/Lean/Coq/Dafny proof evidence. | proof producer contract, proof artifact schema, policy tests | ADR 0104 |

### ADR Backlog

| ADR | Title | Decision Required |
|---:|---|---|
| 0098 | Formal Claim To TLA Projection Semantics | Define exact backend projection rules and unsupported fragments. |
| 0099 | Apalache Result Normalization | Define Apalache output parsing, evidence labels, and counterexample mapping. |
| 0100 | TLC Result Normalization | Define TLC output parsing and explicit-state evidence labels. |
| 0101 | `S and R` Formal Composition | Define how system specs and requirement claims compose without violating invariants. |
| 0102 | Counterexample Explanation Contract | Define minimum actionable detail for formal failure output. |
| 0103 | Verification Budgets And Unknown Results | Define closure behavior under bounded search, timeout, memory, and abstraction limits. |
| 0104 | Inductive Proof Producer Contract | Define the boundary for true proof-level evidence. |

### Non-Goals

- Claiming full verification for unsupported fragments.
- Hiding state-space explosion behind success wording.
- Accepting generated TLA as evidence before a backend executes it.
- Requiring TLAPS/Lean/Coq/Dafny for the first extended conclusion release.

## Milestone 7: Brownfield Grounding Closure

### Objective

Make the brownfield story real. A requirement should not be accepted against an imaginary or stale system model. The tool must know:

- what code areas the requirement touches;
- which formal specs cover those areas;
- whether the specs are fresh;
- whether trace evidence exists;
- whether missing specs can be bootstrapped through a reviewed Specula-style workflow.

### Current Base

Relevant current artifacts:

- `src/nlreq/source_impact.py`
- `src/nlreq/spec_drift.py`
- `src/nlreq/spec_freshness.py`
- `src/nlreq/spec_extraction.py`
- `src/nlreq/coverage_alignment.py`
- `src/nlreq/trace_replay.py`
- `src/nlreq/trace_validation.py`
- `src/nlreq/runtime_trace_sdk.py`
- `src/nlreq/trace_normalization.py`
- `docs/phase-62-specula-style-extraction-runner.md`
- `docs/phase-64-spec-freshness-lockfile.md`
- `docs/phase-66-trace-normalization.md`

### Exit Criteria

Milestone 7 exits only when:

- source impact can identify affected modules through deterministic adapter output and optional semantic context;
- code-to-spec manifests map code, specs, traces, and dependencies with review status;
- changed source or changed spec invalidates freshness until revalidated;
- missing spec coverage blocks closure and optionally queues candidate extraction;
- Specula-style candidate specs are never trusted until reviewed and freshness-locked;
- normalized traces include loss records and trace producer metadata;
- trace validation can classify satisfied, violated, coverage gap, lossy, and unsupported cases.

### Phases

| Phase | Name | Purpose | Primary Deliverables | Required ADR |
|---:|---|---|---|---|
| 96 | Production Source Impact | Harden source impact with adapter-provided symbols, call graphs, dependency graphs, and semantic disagreement. | impact report, confidence policy, review fixtures | ADR 0105 |
| 97 | Code-To-Spec Coverage Contract | Make coverage precise enough to block requirements touching unreviewed areas. | manifest contract, dependency semantics, coverage gates | ADR 0106 |
| 98 | Spec Freshness CI Gate | Enforce hash-based freshness in local and CI workflows. | lockfile policy, CI report, stale refusal | ADR 0107 |
| 99 | Specula-Style Candidate Extraction Integration | Define how candidate specs are generated, reviewed, promoted, or rejected. | extraction runner boundary, candidate review workflow, promotion artifacts | ADR 0108 |
| 100 | Trace Producer Contract | Make runtime trace producers replayable and auditable. | producer registry, trace source contract, extraction metadata | ADR 0109 |
| 101 | Normalized Trace Semantics | Strengthen normalized traces across runtimes without leaking adapter details into IR. | trace schema, lossy policy, causal fields, fixture suite | ADR 0110 |
| 102 | Trace Validation Gate | Use normalized traces as grounding evidence for formal claims. | validation report, refusal mapping, benchmark cases | ADR 0111 |

### ADR Backlog

| ADR | Title | Decision Required |
|---:|---|---|
| 0105 | Production Source Impact Semantics | Define deterministic, trace-touched, and semantic-suggestion impact roles. |
| 0106 | Code-To-Spec Coverage Contract | Define review status, dependency propagation, and closure effect for gaps. |
| 0107 | Spec Freshness CI Policy | Define hash lock, drift handling, and stale-spec refusal. |
| 0108 | Specula-Style Extraction Trust Workflow | Define candidate generation, review, promotion, and non-evidence boundaries. |
| 0109 | Runtime Trace Producer Contract | Define producer identity, replay inputs, and trace extraction metadata. |
| 0110 | Normalized Trace Semantics | Define portable trace shape, loss records, causality, and adapter metadata. |
| 0111 | Trace Validation Closure Policy | Define how trace validation affects acceptance, refusal, and evidence levels. |

### Non-Goals

- Automatically trusting generated specs.
- Treating trace validation as proof of all possible behavior.
- Requiring full source coverage for all modules before any requirement can be reviewed.
- Accepting adapter-specific trace fields in semantic IR.

## Milestone 8: Adapter And Evidence Closure

### Objective

Prove the project is an agnostic Attestation Layer, not a single-ecosystem validator. This milestone makes adapters, evidence producers, and cross-adapter proof closure production-worthy.

### Current Base

Relevant current artifacts:

- `src/nlreq/source_adapter.py`
- `src/nlreq/adapter_certification.py`
- `src/nlreq/production_source_adapters.py`
- `src/nlreq/cross_language.py`
- `src/nlreq/signed_evidence.py`
- `src/nlreq/artifact_store.py`
- `src/nlreq/evidence_producers.py`
- `docs/adapter-interface.md`
- `docs/adapter-authoring-guide.md`
- `docs/phase-67-solidity-adapter.md`
- `docs/phase-68-go-adapter.md`
- `docs/phase-72-cross-language-proof-object.md`

### Exit Criteria

Milestone 8 exits only when:

- adapter conformance is executable and required for gate-satisfying evidence;
- at least two real adapters pass the same conformance suite;
- every adapter reports supported evidence levels and limitations;
- real adapter evidence can be retained, replayed, and signed when policy requires it;
- cross-language proof objects retain per-adapter hashes and blockers;
- normalized trace and source facts remain adapter-neutral at the IR/proof layer;
- adapter certification blocks ambiguous symbols, missing traces, and unsupported evidence claims.

### Phases

| Phase | Name | Purpose | Primary Deliverables | Required ADR |
|---:|---|---|---|---|
| 103 | Adapter Conformance Suite Hardening | Make conformance the entry gate for adapters. | shared test harness, fixture contract, failure taxonomy | ADR 0112 |
| 104 | First Real Adapter Graduation | Promote one real adapter from static support to gate-satisfying evidence producer. | adapter selection, certification, end-to-end fixture | ADR 0113 |
| 105 | Second Real Adapter Graduation | Validate the adapter abstraction under a different ecosystem. | second adapter, comparative conformance, trace/source differences | ADR 0114 |
| 106 | Adapter Evidence Capability Registry | Let policies require adapter capabilities by evidence level. | capability schema, producer mapping, routing integration | ADR 0115 |
| 107 | Evidence Artifact Replay Bundles | Make evidence replayable from retained artifacts. | replay bundle manifest, resolver, reproducibility tests | ADR 0116 |
| 108 | Signed Evidence Enforcement | Require signatures for high-assurance producer claims. | key registry policy, signature verification, CI failure modes | ADR 0117 |
| 109 | Cross-Adapter Proof Closure | Close proof objects over evidence from more than one adapter without hiding blockers. | cross-language proof policy, causal links, closure integration | ADR 0118 |

### ADR Backlog

| ADR | Title | Decision Required |
|---:|---|---|
| 0112 | Adapter Conformance Suite Contract | Define what every adapter must pass and how failures are reported. |
| 0113 | First Real Adapter Graduation | Select and justify the first production-grade adapter evidence path. |
| 0114 | Second Real Adapter Graduation | Select and justify the adapter that proves the abstraction generalizes. |
| 0115 | Adapter Evidence Capability Registry | Define supported evidence levels, limitations, and policy matching. |
| 0116 | Evidence Replay Bundle Format | Define retained artifact layout and replay requirements. |
| 0117 | Signed Evidence Enforcement Policy | Define when signatures are required and how trust is configured. |
| 0118 | Cross-Adapter Proof Closure Policy | Define how multi-adapter evidence closes, blocks, or remains unknown. |

### Non-Goals

- Supporting every programming language.
- Making adapter certification imply semantic completeness.
- Letting adapter-specific facts leak into requirement IR.
- Treating signed evidence as proof of correctness.

## Milestone 9: Release And Adoption Closure

### Objective

Make the system adoptable and defensible. The extended conclusion release must be able to say:

- what it can prove;
- what it can only check within bounds;
- what it observed from traces;
- what it refused;
- what remains unknown;
- how often it is wrong on public benchmarks;
- how users integrate it in real PR workflows.

### Current Base

Relevant current artifacts:

- `src/nlreq/benchmark_reporting.py`
- `src/nlreq/ci_pr_gate.py`
- `src/nlreq/conclusion_certification.py`
- `src/nlreq/public_sdk.py`
- `src/nlreq/reference_demo.py`
- `src/nlreq/threat_model.py`
- `src/nlreq/verification_cache.py`
- `docs/release-bar-matrix.md`
- `docs/conclusion-definition.md`
- `docs/phase-75-ci-pr-action-gate.md`
- `docs/phase-76-benchmark-corpus.md`
- `docs/phase-82-conclusion-release-certification.md`

### Exit Criteria

Milestone 9 exits only when:

- CI can run report-only, soft-gate, and hard-gate modes with stable JSON and Markdown outputs;
- benchmark evaluation includes semantic translation, system compatibility, trace grounding, adapter evidence, false closure, false refusal, runtime, and counterexample quality;
- the reference demo exercises the real extended path, not only artifact presence;
- public docs explain evidence labels, limitations, and failure modes;
- threat model names the TCB and adversarial assumptions;
- release certification fails unless required benchmark, demo, schema, producer, and docs evidence is present;
- the project can publish a conclusion claim without overclaiming proof strength.

### Phases

| Phase | Name | Purpose | Primary Deliverables | Required ADR |
|---:|---|---|---|---|
| 110 | End-To-End Requirement Gate Hardening | Make one command run the real extended pipeline with stable outputs. | gate report, artifact layout, refusal UX, golden E2E fixtures | ADR 0119 |
| 111 | CI Adoption Modes | Harden report-only, soft-gate, and hard-gate workflows. | CI report schema, PR Markdown, policy config | ADR 0120 |
| 112 | Extended Benchmark Corpus | Measure semantic, formal, trace, adapter, and release behavior. | corpus, scoring, public report, failure taxonomy | ADR 0121 |
| 113 | Reference Brownfield Demo | Prove the system against one credible real or realistic system. | demo repo, scripts, replay bundle, expected outputs | ADR 0122 |
| 114 | Public SDK And Docs Freeze | Make external adoption possible without reading internals. | SDK docs, CLI guide, schema guide, adapter guide | ADR 0123 |
| 115 | Threat Model And TCB Review | Name what must be trusted and how evidence can be attacked. | TCB inventory, adversarial scenarios, mitigations | ADR 0124 |
| 116 | Extended Conclusion Certification | Certify the release against the stricter closure bar. | certification report, release checklist, signed release bundle | ADR 0125 |

### ADR Backlog

| ADR | Title | Decision Required |
|---:|---|---|
| 0119 | End-To-End Requirement Gate Contract | Define the real pipeline, artifact layout, and final status semantics. |
| 0120 | CI Adoption And Gate Modes | Define report-only, soft-gate, hard-gate, waivers, and PR rendering. |
| 0121 | Extended Benchmark Methodology | Define benchmark dimensions and release thresholds. |
| 0122 | Reference Brownfield Demo Contract | Define demo selection, reproducibility, and acceptance criteria. |
| 0123 | Public SDK And Documentation Freeze | Define public API, schema, examples, and compatibility commitments. |
| 0124 | Threat Model And TCB Review | Define trusted components, attacker model, and residual risks. |
| 0125 | Extended Conclusion Certification | Define the final release certification process and failure conditions. |

### Non-Goals

- Claiming universal natural-language understanding.
- Certifying unsupported domains.
- Making hard-gate mode mandatory for first adopters.
- Hiding unknown or inconclusive results to improve benchmark optics.

## Phase And ADR Index

### Phase Index

| Phase | Milestone | Name | Required ADR |
|---:|---:|---|---:|
| 83 | 5 | Formal Claim IR | 0092 |
| 84 | 5 | Controlled Requirement Semantics | 0093 |
| 85 | 5 | Req2LTL-Style Intermediate Translator | 0094 |
| 86 | 5 | Semantic Agreement Gate | 0095 |
| 87 | 5 | Translation Repair And Clarification UX | 0096 |
| 88 | 5 | Semantic Translation Benchmark Expansion | 0097 |
| 89 | 6 | Formal Claim To TLA Semantics | 0098 |
| 90 | 6 | Production Apalache Result Parser | 0099 |
| 91 | 6 | Production TLC Result Parser | 0100 |
| 92 | 6 | Real `S and R` Composition Engine | 0101 |
| 93 | 6 | Counterexample Explanation Quality | 0102 |
| 94 | 6 | Verification Budget Enforcement | 0103 |
| 95 | 6 | Inductive Proof Producer Boundary | 0104 |
| 96 | 7 | Production Source Impact | 0105 |
| 97 | 7 | Code-To-Spec Coverage Contract | 0106 |
| 98 | 7 | Spec Freshness CI Gate | 0107 |
| 99 | 7 | Specula-Style Candidate Extraction Integration | 0108 |
| 100 | 7 | Trace Producer Contract | 0109 |
| 101 | 7 | Normalized Trace Semantics | 0110 |
| 102 | 7 | Trace Validation Gate | 0111 |
| 103 | 8 | Adapter Conformance Suite Hardening | 0112 |
| 104 | 8 | First Real Adapter Graduation | 0113 |
| 105 | 8 | Second Real Adapter Graduation | 0114 |
| 106 | 8 | Adapter Evidence Capability Registry | 0115 |
| 107 | 8 | Evidence Artifact Replay Bundles | 0116 |
| 108 | 8 | Signed Evidence Enforcement | 0117 |
| 109 | 8 | Cross-Adapter Proof Closure | 0118 |
| 110 | 9 | End-To-End Requirement Gate Hardening | 0119 |
| 111 | 9 | CI Adoption Modes | 0120 |
| 112 | 9 | Extended Benchmark Corpus | 0121 |
| 113 | 9 | Reference Brownfield Demo | 0122 |
| 114 | 9 | Public SDK And Docs Freeze | 0123 |
| 115 | 9 | Threat Model And TCB Review | 0124 |
| 116 | 9 | Extended Conclusion Certification | 0125 |

### ADR Index

| ADR | Phase | Title |
|---:|---:|---|
| 0092 | 83 | Formal Claim IR Boundary |
| 0093 | 84 | Controlled Requirement Semantics |
| 0094 | 85 | Two-Stage Semantic Translation Pipeline |
| 0095 | 86 | Semantic Agreement And Equivalence Profiles |
| 0096 | 87 | Clarification And Repair Protocol |
| 0097 | 88 | Semantic Translation Benchmark Methodology |
| 0098 | 89 | Formal Claim To TLA Projection Semantics |
| 0099 | 90 | Apalache Result Normalization |
| 0100 | 91 | TLC Result Normalization |
| 0101 | 92 | `S and R` Formal Composition |
| 0102 | 93 | Counterexample Explanation Contract |
| 0103 | 94 | Verification Budgets And Unknown Results |
| 0104 | 95 | Inductive Proof Producer Contract |
| 0105 | 96 | Production Source Impact Semantics |
| 0106 | 97 | Code-To-Spec Coverage Contract |
| 0107 | 98 | Spec Freshness CI Policy |
| 0108 | 99 | Specula-Style Extraction Trust Workflow |
| 0109 | 100 | Runtime Trace Producer Contract |
| 0110 | 101 | Normalized Trace Semantics |
| 0111 | 102 | Trace Validation Closure Policy |
| 0112 | 103 | Adapter Conformance Suite Contract |
| 0113 | 104 | First Real Adapter Graduation |
| 0114 | 105 | Second Real Adapter Graduation |
| 0115 | 106 | Adapter Evidence Capability Registry |
| 0116 | 107 | Evidence Replay Bundle Format |
| 0117 | 108 | Signed Evidence Enforcement Policy |
| 0118 | 109 | Cross-Adapter Proof Closure Policy |
| 0119 | 110 | End-To-End Requirement Gate Contract |
| 0120 | 111 | CI Adoption And Gate Modes |
| 0121 | 112 | Extended Benchmark Methodology |
| 0122 | 113 | Reference Brownfield Demo Contract |
| 0123 | 114 | Public SDK And Documentation Freeze |
| 0124 | 115 | Threat Model And TCB Review |
| 0125 | 116 | Extended Conclusion Certification |

## Dependency Graph

```text
Milestone 5 Semantic Translation Closure
  -> Milestone 6 Formal System Closure
  -> Milestone 7 Brownfield Grounding Closure
  -> Milestone 8 Adapter And Evidence Closure
  -> Milestone 9 Release And Adoption Closure
```

Some work can run in parallel:

- Phase 103 adapter conformance hardening can start while Milestone 6 formal checks mature.
- Phase 112 benchmark expansion should start early and collect fixtures from every milestone.
- Phase 114 public docs can draft early but must freeze late.
- Phase 115 threat model should start before signed evidence enforcement, not after.

Hard dependencies:

- Phase 89 depends on Phase 83.
- Phase 92 depends on Phases 89-91.
- Phase 99 depends on Phases 96-98.
- Phase 102 depends on Phases 100-101.
- Phase 109 depends on Phases 103-108.
- Phase 116 depends on all prior phases.

## Consolidated Milestone Release Bars

| Milestone | Minimum Release Bar |
|---:|---|
| 5 | Can refuse ambiguous, unsupported, or semantically divergent requirements with source-span next actions. |
| 6 | Can produce real bounded formal compatibility evidence or honest unknown/counterexample for supported claims. |
| 7 | Can block closure on stale/missing specs and validate claims against normalized real traces. |
| 8 | Can close one proof object using evidence from at least two conforming real adapters. |
| 9 | Can certify a release with benchmark thresholds, replayable evidence, signed producer claims where required, and public limitations. |

## Extended Conclusion Definition

The extended conclusion is reached when:

1. A human requirement can enter through controlled text or approved free-form rewrite.
2. The requirement is translated into formal claim IR with source-span provenance.
3. Ambiguity, unsupported semantics, and translation disagreement are refused with actionable repair steps.
4. The formal claim is self-consistency checked.
5. The affected system surface is identified through adapter-backed impact analysis.
6. Covered modules have reviewed, fresh system specs.
7. Missing specs can be bootstrapped only as reviewed candidates, never as trusted evidence.
8. The claim is checked against the reviewed system spec with real solver/model-checker evidence for supported fragments.
9. Counterexamples are normalized and explainable.
10. Runtime traces from registered producers validate current behavior where trace evidence is required.
11. Adapter evidence is accepted only from adapters that pass conformance and declare capability.
12. Evidence artifacts are retained and replayable.
13. High-assurance producer evidence is signed when policy requires it.
14. CI/PR gates can run in report-only, soft-gate, and hard-gate modes.
15. Public benchmark thresholds include false closure and false refusal budgets.
16. Public docs explain evidence labels, limits, and integration steps.
17. Threat model and TCB are documented.
18. Conclusion certification fails closed when required evidence is missing, stale, unsigned, unsupported, or inconclusive.

## Open Decisions

These decisions should be resolved before implementing Phase 83:

1. **Formal claim IR shape:** extend the current requirement IR, add a sibling artifact, or introduce a new package-level claim artifact?
2. **Primary formal backend:** keep TLA/Apalache as the first production path, or put SMT first for the supported claim subset?
3. **First real extended demo:** use a repository fixture, a real open-source brownfield target, or a controlled internal domain?
4. **Second real adapter:** choose by difference from first adapter, not convenience. The second adapter should pressure-test traces, source impact, and symbol resolution.
5. **Benchmark false closure budget:** should extended conclusion require zero false closures for hard-gated benchmark cases?
6. **Trace requirement policy:** which claim kinds require trace evidence versus formal evidence only?
7. **Specula integration depth:** interoperate with selected artifacts, shell out to Specula, or implement an independent extraction workbench?
8. **Proof-level future:** reserve `PROVEN_INDUCTIVE` only, or plan a specific TLAPS/Lean/Coq/Dafny prototype?

## Risks And Mitigations

| Risk | Impact | Mitigation |
|---|---|---|
| Semantic translator accepts wrong meaning | False closure on wrong requirement | controlled input, multi-pass agreement, source-span review, benchmark false-acceptance budget |
| Model checker times out often | Tool becomes mostly unknown | budget policy, abstraction, SMT-first subsets, compositional specs |
| Spec coverage is too low | Brownfield adoption stalls | Specula-style candidate extraction, coverage dashboard, graceful needs-review |
| Trace normalization loses critical semantics | False trace validation | loss records, high-assurance loss policy, adapter-specific retained metadata |
| Adapter interface leaks language details | Agnostic claim fails | conformance suite, IR leak tests, second real adapter requirement |
| Signed evidence is mistaken for correctness | Overclaiming | docs and policy distinguish identity/integrity from semantic validity |
| Benchmark is too easy | Release claims become untrustworthy | public false closure budget, hard negative cases, cross-adapter cases |
| Hard gate blocks too early | Adoption fails | report-only and soft-gate phases before hard-gate enforcement |

## Recommended Implementation Order

1. Phase 83: Formal Claim IR.
2. Phase 84: Controlled Requirement Semantics.
3. Phase 86: Semantic Agreement Gate.
4. Phase 89: Formal Claim To TLA Semantics.
5. Phase 92: Real `S and R` Composition Engine.
6. Phase 97: Code-To-Spec Coverage Contract.
7. Phase 98: Spec Freshness CI Gate.
8. Phase 101: Normalized Trace Semantics.
9. Phase 103: Adapter Conformance Suite Hardening.
10. Phase 104: First Real Adapter Graduation.
11. Phase 112: Extended Benchmark Corpus.
12. Phase 116: Extended Conclusion Certification.

This order prioritizes the critical path. Other phases can run in parallel once their input contracts are stable.

## First Concrete Slice

The first slice should prove that the roadmap is executable without waiting for all phases.

### Slice Requirement

Use one controlled requirement with:

- one authorization or state-precondition claim;
- one unambiguous symbol binding through a conforming adapter;
- one reviewed system spec fixture;
- one formal compatibility check;
- one negative fixture that produces a counterexample or refusal;
- one benchmark case.

### Slice Outputs

The slice must emit:

- formal claim IR;
- source-span provenance;
- review artifact;
- source impact report;
- spec coverage report;
- spec freshness report;
- TLA projection or SMT query;
- backend response;
- normalized counterexample when failing;
- proof object;
- closure gate report;
- refusal or accepted package;
- benchmark result.

### Slice Acceptance

The slice passes only if:

- all artifacts are deterministic across two runs;
- changing the source fixture makes spec freshness fail;
- removing the binding makes symbol resolution fail;
- changing the requirement to an incompatible one produces a structured refusal;
- the benchmark detects a false acceptance if the negative case is forced to pass.

## Document Maintenance

This roadmap is an extension plan, not a replacement for `docs/nl-attestation-conclusion-roadmap.md`.

When a phase in this document is implemented:

1. Add a phase spec at `docs/phase-XX-*.md`.
2. Add its ADR at `docs/adr/00YY-*.md`.
3. Add or update schemas through `scripts/generate_schema.py`.
4. Add tests for the artifact, CLI, and refusal behavior.
5. Update a future extended gap checklist artifact.
6. Update benchmark fixtures if the phase affects closure semantics.
7. Preserve evidence-label discipline.

No phase should be marked done merely because a schema exists. The extended roadmap requires real semantic behavior, executable checks, and failure-mode tests.
