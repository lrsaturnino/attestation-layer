# Final Real-Evidence Gap Closure Roadmap

**Status:** Draft v1
**Date:** 2026-06-03
**Starts After:** Phase 150 Final Real-Evidence Conclusion Certification
**Current ADR Floor:** ADR 0159 Final Real-Evidence Conclusion Certification
**Source Context:** `docs/claude-convo.md`,
`docs/conclusion-real-evidence-closure-roadmap.md`, implemented phases 0-150

This roadmap closes the remaining gap between the current Attestation Layer
implementation and the system described in `docs/claude-convo.md`.

The current repo now has the shape of the target system:

```text
human requirement
-> approved controlled requirement
-> formal claim R
-> R checked against itself
-> affected system areas identified
-> formal system spec S coverage/freshness checked
-> R checked against S
-> current code behavior and traces grounded against R
-> evidence retained, replayed, and signed
-> proof object closes
-> downstream action allowed only after closure
```

The remaining problem is not that the pipeline lacks artifact names. It is that
too many artifacts are still easy to satisfy with fixtures, scaffolds, or
shallow examples. This roadmap therefore shifts the project from
**contract-complete** to **real-evidence-complete**.

## Executive Summary

The current state is close to the Claude discussion in architecture and not yet
close enough in proof strength.

What is strong today:

- adapter-neutral architecture and source/trace interfaces;
- controlled requirement parsing, canonical IR, formal claim IR, semantic
  lowering, provenance, review, repair, and refusal contracts;
- model-checker runner boundaries and normalized formal backend outcomes;
- system spec registry, source impact, coverage, freshness, trace validation,
  trace replay, and S-and-R composition contracts;
- proof object, closure gate, CI gate, producer registry, artifact store,
  signatures, replay bundle, benchmark, demo, governance, and final
  certification reports;
- phase specs, ADRs, generated schemas, and focused tests through phase 150.

What is still not strong enough:

- semantic translation has not been proven on a large labeled requirement
  corpus with measured semantic accuracy;
- free-form intake is not yet product-quality enough for real users;
- contradiction checking is not yet ALICE-grade in taxonomy depth or measured
  recall;
- formal backend execution is not yet routinely run against non-toy TLA+
  models with real success, counterexample, timeout, unsupported, and
  missing-tool paths;
- S-and-R composition is not yet mature on reviewed system specs under realistic
  namespace, bound, and invariant interactions;
- brownfield spec extraction and promotion are not yet trustworthy enough to
  ground a production codebase;
- spec freshness is represented, but not yet continuously enforced as normal CI
  behavior against changing source code;
- production language adapters exist as credible scaffolds, but not as hardened
  wrappers over mature ecosystem tools across at least four languages;
- runtime trace producers are not yet deep enough for real causality and
  replay across ecosystems;
- public benchmarks and beta demos exist as schema-backed reports, but do not
  yet exert enough pressure to reveal false closure, false refusal, and shallow
  evidence;
- final certification can block missing inputs, but still needs real input
  sources that are difficult to fake.

The next work must therefore use fewer new nouns and more hostile evidence.

## Target Claim

This roadmap is done only when the project can credibly publish the following
claim:

> For supported requirement classes and supported adapters, the Attestation
> Layer can convert reviewed human requirements into formal claim obligations,
> check the requirement against itself and against fresh reviewed system specs,
> ground affected code behavior with retained traces and real producer evidence,
> refuse on ambiguity, unsupported semantics, stale specs, missing coverage,
> counterexamples, timeout, trace contradiction, or policy failure, and allow
> downstream action only when the configured evidence premises close.

This claim is intentionally scoped. It does not claim:

- correctness for arbitrary natural language;
- correctness for arbitrary programs;
- automatic trust in generated specs;
- proof for unsupported semantic fragments;
- unbounded guarantees from bounded model checking;
- semantic equivalence among all formal backends;
- replacement of expert review;
- support for every programming language.

## Gap-To-Roadmap Mapping

| Gap | Required Closure |
|---|---|
| Product free-form intake remains fragile | Controlled rewrite runtime with replay, review, ambiguity, and refusal telemetry from real users |
| Semantic translation is not yet measured enough | Large labeled corpus, two-stage semantic tree, semantic equivalence profiles, false-acceptance thresholds |
| Contradiction checking is shallow | ALICE-style taxonomy, deterministic checks, LLM-assisted audit only as marked evidence |
| Formal backend outcomes are not yet production-grade | Real Apalache/TLC runners, parsers, counterexample normalization, timeout and missing-tool policy |
| S-and-R composition is not mature | Reviewed system spec packaging, namespace policy, invariant preservation, compatibility counterexamples |
| Brownfield spec grounding is not trustworthy | Deterministic impact, code-to-spec coverage, Specula-style extraction, review promotion, trace validation |
| Spec drift remains easy | Hash-locked freshness, trace validation on changed modules, stale-spec branch blocking |
| Adapter credibility remains incomplete | Hardened Solidity, Go, TypeScript/JavaScript, Python, Rust or Java adapters through the same contract |
| Cross-language evidence is contract-level | Real multi-adapter demo with causal traces, replay bundles, and per-adapter blockers |
| Benchmarks are not yet hostile | Public corpus with false closure/refusal, counterexample quality, runtime, adapter, trace, and release-gate dimensions |
| Final certification can certify fixture completeness | Certification must require real producer identities, real replay bundles, real benchmark results, and non-toy demo artifacts |

## Consolidated Milestones

| Milestone | Phases | Name | Outcome |
|---:|---:|---|---|
| 15 | 151-156 | Semantic Intake And Translation Evidence | Free-form and controlled requirements translate into formal claims with measured semantic accuracy, ambiguity handling, and contradiction refusal. |
| 16 | 157-163 | Real Formal Backend And S-and-R Closure | Formal claims execute against real Apalache/TLC targets and compose with reviewed system specs under explicit budget and counterexample policy. |
| 17 | 164-171 | Brownfield Spec Grounding And Drift Closure | Impact, spec coverage, Specula-style extraction, review promotion, freshness, and trace validation become continuous production workflows. |
| 18 | 172-179 | Production Adapter And Trace Closure | Multiple materially different language adapters produce real source, trace, and evidence artifacts through one adapter contract. |
| 19 | 180-186 | Replay, Benchmark, And Release Evidence Closure | Replay/signing, benchmarks, demos, beta pilots, and CI governance are backed by real retained evidence. |
| 20 | 187-192 | External Review And Conclusion Publication | The release bundle survives hostile review, public benchmark reproduction, and final claim signing. |

## Release Bars

| Bar | Required State | What It Can Claim |
|---|---|---|
| Translation Evidence Alpha | Milestone 15 complete on a labeled corpus | The tool can translate supported requirement text with measured semantic accuracy and honest refusal. |
| Formal Evidence Beta | Milestones 15-16 complete on non-toy TLA+ specs | The tool can check supported R claims against reviewed S specs under explicit bounds. |
| Brownfield Evidence Beta | Milestones 15-17 complete on one real codebase module | The tool can refuse stale, uncovered, or trace-contradicting brownfield requirements. |
| Adapter Evidence Beta | Milestones 15-18 complete with four certified adapters | The adapter abstraction is credibly programming-language agnostic for supported evidence classes. |
| Real-Evidence RC | Milestones 15-19 complete with retained replay bundles and public benchmark reports | A reference workflow can hard-gate downstream action with reproducible evidence. |
| Published Real-Evidence Conclusion | Milestones 15-20 complete with external review and signed bundle | The scoped public conclusion claim can be published without overclaiming. |

## Phase Sequence

| Phase | Milestone | Name | Primary Gap Closed | Required ADR |
|---:|---:|---|---|---:|
| 151 | 15 | Product Free-Form Intake Evidence Runtime | real user-facing intake path | ADR 0160 |
| 152 | 15 | Controlled Rewrite Replay Corpus | auditable NL-to-controlled rewrite evidence | ADR 0161 |
| 153 | 15 | Semantic Decomposition IR v2 | robust Req2LTL-style intermediate tree | ADR 0162 |
| 154 | 15 | Semantic Equivalence And Translator Calibration | semantic agreement beyond structural equality | ADR 0163 |
| 155 | 15 | ALICE-Grade Contradiction Engine | contradiction taxonomy and recall measurement | ADR 0164 |
| 156 | 15 | Translation Release Corpus And Thresholds | public semantic accuracy and false-acceptance bar | ADR 0165 |
| 157 | 16 | Formal Claim Semantics Exhaustion | exact supported/unsupported semantics table | ADR 0166 |
| 158 | 16 | Production Apalache Runner Hardening | real symbolic bounded checking path | ADR 0167 |
| 159 | 16 | Production TLC Runner Hardening | real explicit-state checking path | ADR 0168 |
| 160 | 16 | Reviewed System Spec Package Format | stable S artifact contract | ADR 0169 |
| 161 | 16 | Production S-and-R Compatibility Checker | mature R against S composition | ADR 0170 |
| 162 | 16 | Counterexample Explanation And Replay | actionable formal failure evidence | ADR 0171 |
| 163 | 16 | Verification Budget And Abstraction Profiles | honest timeout, unknown, and bounded labels | ADR 0172 |
| 164 | 17 | Multi-Language Impact Analysis v2 | affected system area discovery | ADR 0173 |
| 165 | 17 | Code-To-Spec Coverage Manifest v3 | precise coverage propagation and blockers | ADR 0174 |
| 166 | 17 | Specula-Style Extraction Runner Production | candidate specs from real code | ADR 0175 |
| 167 | 17 | Candidate Spec Review Workbench | human promotion and rejection workflow | ADR 0176 |
| 168 | 17 | Continuous Spec Freshness CI | stale-spec branch blocking | ADR 0177 |
| 169 | 17 | Trace Producer SDK v2 | real producer metadata and loss accounting | ADR 0178 |
| 170 | 17 | Trace Validation Against Formal Claims v2 | current behavior grounded against R | ADR 0179 |
| 171 | 17 | Brownfield Delta And Remediation Reports | actionable spec/code/test deltas | ADR 0180 |
| 172 | 18 | Adapter Conformance Suite v3 | shared certification behavior | ADR 0181 |
| 173 | 18 | Solidity Adapter Production Hardening | transaction/event ecosystem evidence | ADR 0182 |
| 174 | 18 | Go Adapter Production Hardening | compiled service ecosystem evidence | ADR 0183 |
| 175 | 18 | TypeScript/JavaScript Adapter Production Hardening | dynamic/frontend/service evidence | ADR 0184 |
| 176 | 18 | Python Adapter Production Hardening | dynamic scripting ecosystem evidence | ADR 0185 |
| 177 | 18 | Rust Or Java Adapter Production Hardening | second compiled ecosystem evidence | ADR 0186 |
| 178 | 18 | Cross-Adapter Causal Trace Closure | real multi-adapter causality | ADR 0187 |
| 179 | 18 | Adapter Plugin Marketplace And Version Policy | external adapter lifecycle | ADR 0188 |
| 180 | 19 | Replay Bundle v3 And Artifact Retention | reproducible high-assurance evidence | ADR 0189 |
| 181 | 19 | Producer Key Management And Trust Policy | real producer identity enforcement | ADR 0190 |
| 182 | 19 | Public Benchmark Corpus v2 | hostile benchmark accountability | ADR 0191 |
| 183 | 19 | Benchmark Runner And Leaderboard Automation | reproducible public reports | ADR 0192 |
| 184 | 19 | Non-Toy Reference Brownfield Demo | accepted/refused real workflow | ADR 0193 |
| 185 | 19 | Beta Pilot Evidence Program | external workflow findings | ADR 0194 |
| 186 | 19 | CI Hard Gate Governance Deployment | branch-protection-ready adoption | ADR 0195 |
| 187 | 20 | Threat Model And TCB Re-Review | release trust boundary | ADR 0196 |
| 188 | 20 | External Reproduction And Red-Team Review | hostile validation of claims | ADR 0197 |
| 189 | 20 | Public Documentation And Schema Freeze v2 | adoption without internals | ADR 0198 |
| 190 | 20 | Release Bundle Signing And Publication | signed release evidence | ADR 0199 |
| 191 | 20 | Conclusion Claim Language And Limitations | public non-overclaiming statement | ADR 0200 |
| 192 | 20 | Final Real-Evidence Conclusion Decision | final ship/no-ship gate | ADR 0201 |

## ADR Backlog

| ADR | Phase | Title | Decision Required |
|---:|---:|---|---|
| 0160 | 151 | Product Free-Form Intake Evidence Runtime | Decide provider boundaries, raw-NL refusal, reviewer states, and telemetry retention. |
| 0161 | 152 | Controlled Rewrite Replay Corpus | Decide prompt metadata, model metadata, manual rewrite metadata, hash links, and replay retention. |
| 0162 | 153 | Semantic Decomposition IR v2 | Decide semantic tree nodes, source span rules, unsupported fragments, and deterministic lowering boundary. |
| 0163 | 154 | Semantic Equivalence And Translator Calibration | Decide equivalence profiles, disagreement thresholds, reviewer override, and calibration metrics. |
| 0164 | 155 | ALICE-Grade Contradiction Engine | Decide contradiction classes, deterministic checks, LLM audit role, and recall targets. |
| 0165 | 156 | Translation Release Corpus And Thresholds | Decide corpus format, labels, minimum semantic accuracy, false acceptance budget, and publication. |
| 0166 | 157 | Formal Claim Semantics Exhaustion | Decide exact semantics and unsupported outcomes for every claim class. |
| 0167 | 158 | Production Apalache Runner Hardening | Decide command contract, parser, bounds, counterexample retention, and missing-tool policy. |
| 0168 | 159 | Production TLC Runner Hardening | Decide TLC output normalization, state-space limits, invariant mapping, and timeout semantics. |
| 0169 | 160 | Reviewed System Spec Package Format | Decide S package contents, review status, namespace policy, freshness locks, and invariant manifest. |
| 0170 | 161 | Production S-and-R Compatibility Checker | Decide composition semantics, valid/counterexample/timeout/unsupported/stale outcomes, and evidence labels. |
| 0171 | 162 | Counterexample Explanation And Replay | Decide minimum counterexample fields, source-span mapping, trace replay, and user-facing explanations. |
| 0172 | 163 | Verification Budget And Abstraction Profiles | Decide release budgets, abstraction labels, unknown handling, cache interaction, and escalation. |
| 0173 | 164 | Multi-Language Impact Analysis v2 | Decide deterministic impact roles, semantic hints, dependency propagation, and disagreement policy. |
| 0174 | 165 | Code-To-Spec Coverage Manifest v3 | Decide coverage roles, thresholds, stale propagation, generated candidates, and closure effect. |
| 0175 | 166 | Specula-Style Extraction Runner Production | Decide extractor trust model, inputs, outputs, trace-validation requirement, and failure taxonomy. |
| 0176 | 167 | Candidate Spec Review Workbench | Decide promotion, rejection, reviewer identity, review diffs, freshness locks, and audit trails. |
| 0177 | 168 | Continuous Spec Freshness CI | Decide changed-code detection, freshness hash policy, validation age, branch blocking, and waivers. |
| 0178 | 169 | Trace Producer SDK v2 | Decide producer identity, runtime metadata, clock model, causality, loss records, and signatures. |
| 0179 | 170 | Trace Validation Against Formal Claims v2 | Decide satisfaction, violation, gap, lossy, stale, unsupported, and replay semantics. |
| 0180 | 171 | Brownfield Delta And Remediation Reports | Decide generated remediation artifacts, ownership, priority, and release-blocking conditions. |
| 0181 | 172 | Adapter Conformance Suite v3 | Decide required fixtures, capability levels, limitation taxonomy, and pass/fail semantics. |
| 0182 | 173 | Solidity Adapter Production Hardening | Decide EVM tooling, transaction traces, event semantics, library/inheritance handling, and unsupported features. |
| 0183 | 174 | Go Adapter Production Hardening | Decide gopls/call graph use, package coverage, OpenTelemetry/runtime trace shape, and build metadata. |
| 0184 | 175 | TypeScript/JavaScript Adapter Production Hardening | Decide tsserver usage, browser/server split, async traces, dynamic limitations, and bundler metadata. |
| 0185 | 176 | Python Adapter Production Hardening | Decide AST/import resolution, dynamic features, runtime traces, package metadata, and unsupported cases. |
| 0186 | 177 | Rust Or Java Adapter Production Hardening | Decide selected ecosystem, compiler metadata, call graph, trace source, and limitations. |
| 0187 | 178 | Cross-Adapter Causal Trace Closure | Decide causal link schema, clocks, correlation ids, missing-link blockers, and replay requirements. |
| 0188 | 179 | Adapter Plugin Marketplace And Version Policy | Decide plugin manifest versioning, compatibility, deprecation, trust, and certification renewal. |
| 0189 | 180 | Replay Bundle v3 And Artifact Retention | Decide bundle layout, artifact retention, reproducibility commands, compression, and retention duration. |
| 0190 | 181 | Producer Key Management And Trust Policy | Decide key registry lifecycle, trust levels, rotation, revocation, and high-assurance enforcement. |
| 0191 | 182 | Public Benchmark Corpus v2 | Decide case taxonomy, labels, hostile cases, false closure/refusal budgets, and corpus governance. |
| 0192 | 183 | Benchmark Runner And Leaderboard Automation | Decide runner API, environment capture, scoring, reproducibility, and public report format. |
| 0193 | 184 | Non-Toy Reference Brownfield Demo | Decide demo target, acceptance/refusal cases, required artifacts, and publication rules. |
| 0194 | 185 | Beta Pilot Evidence Program | Decide pilot selection, feedback schema, severity policy, and release-blocking findings. |
| 0195 | 186 | CI Hard Gate Governance Deployment | Decide required checks, branch protection, waiver review, audit retention, and policy drift. |
| 0196 | 187 | Threat Model And TCB Re-Review | Decide final TCB boundary, attack scenarios, accepted residual risks, and release mitigations. |
| 0197 | 188 | External Reproduction And Red-Team Review | Decide reviewer criteria, reproduction package, red-team scope, and response process. |
| 0198 | 189 | Public Documentation And Schema Freeze v2 | Decide public docs, compatibility promises, schema freeze, migration policy, and SDK guide. |
| 0199 | 190 | Release Bundle Signing And Publication | Decide signing keys, bundle contents, publication channel, and verification instructions. |
| 0200 | 191 | Conclusion Claim Language And Limitations | Decide exact public claim, scoped limitations, unsupported domains, and evidence labels. |
| 0201 | 192 | Final Real-Evidence Conclusion Decision | Decide final ship/no-ship criteria and certification authority. |

## Detailed Milestone Plans

### Milestone 15 - Semantic Intake And Translation Evidence

Objective: make the front of the pipeline credible. The project must prove that
requirements are not silently rewritten, over-interpreted, or accepted when the
semantic translation is ambiguous.

Current base:

- `src/nlreq/intake.py`
- `src/nlreq/review_workflow.py`
- `src/nlreq/dsl_v3.py`
- `src/nlreq/semantic_translation.py`
- `src/nlreq/semantic_agreement.py`
- `src/nlreq/translation_repair.py`
- `src/nlreq/translation_benchmark.py`
- `src/nlreq/requirement_self_consistency.py`
- phases 117-123 specs and ADRs

Exit criteria:

- raw free-form text never reaches formal parsing without approved controlled
  form;
- every rewrite has prompt/model/manual metadata and replay hash links;
- semantic decomposition is explicit and source-span-preserving;
- unsupported fragments refuse before formal claim emission;
- translator agreement is calibrated against semantic accuracy labels;
- contradiction detection has taxonomy-level coverage and measured recall;
- release thresholds block false semantic acceptance.

#### Phase 151 - Product Free-Form Intake Evidence Runtime

Purpose: turn free-form intake from a contract into a product path.

Scope:

- raw NL intake records;
- provider and model metadata;
- manual rewrite states;
- reviewer approval states;
- unsafe raw-NL refusal;
- telemetry for clarification, refusal, and accepted rewrite rates.

Deliverables:

- intake runtime report v2;
- CLI/API path for free-form submission;
- review queue artifact;
- refusal telemetry report;
- fixtures for accepted, clarified, refused, and unsafe requests.

Exit criteria:

- raw free-form text cannot be lowered directly;
- approved controlled text is hash-linked to raw input;
- every provider/model/manual rewrite path is replayable or explicitly marked
  non-replayable;
- refusal codes distinguish unsafe input, ambiguous input, unsupported input,
  and missing approval.

Required ADR:

- ADR 0160: Product free-form intake evidence runtime.

#### Phase 152 - Controlled Rewrite Replay Corpus

Purpose: make rewrite behavior measurable and reproducible.

Scope:

- rewrite corpus format;
- prompt and model metadata;
- manual rewrite metadata;
- deterministic replay checks;
- non-deterministic output retention;
- source-span diffing.

Deliverables:

- controlled rewrite corpus schema;
- replay runner;
- rewrite diff report;
- corpus seed with realistic requirements;
- test cases for semantic drift between raw and controlled text.

Exit criteria:

- every corpus item has raw text, controlled text, approval, and expected
  semantic preservation labels;
- replay reports name prompt/model drift;
- semantic rewrite drift blocks release metrics;
- manual rewrites are retained with reviewer identity.

Required ADR:

- ADR 0161: Controlled rewrite replay corpus.

#### Phase 153 - Semantic Decomposition IR v2

Purpose: move from structurally valid lowering to robust semantic
decomposition.

Scope:

- Req2LTL/OnionL-inspired intermediate tree;
- semantic scopes;
- logical relations;
- atomic propositions;
- temporal fragments;
- source spans;
- unsupported fragment markers.

Deliverables:

- semantic decomposition IR v2 schema;
- deterministic lowering from semantic tree to formal claim IR;
- bidirectional source-span map;
- unsupported-fragment refusal report;
- golden fixtures for supported and unsupported claims.

Exit criteria:

- formal claim lowering consumes semantic tree nodes, not opaque prose;
- every formal claim fragment maps back to controlled text;
- unsupported nodes produce structured refusal;
- semantic tree shape is stable under canonical JSON.

Required ADR:

- ADR 0162: Semantic decomposition IR v2.

#### Phase 154 - Semantic Equivalence And Translator Calibration

Purpose: decide when multiple translations mean the same thing.

Scope:

- translator ensemble candidates;
- semantic equivalence profiles;
- source-span comparison;
- contradiction-sensitive disagreement;
- reviewer override;
- calibration metrics.

Deliverables:

- semantic equivalence report v2;
- translator calibration corpus;
- disagreement taxonomy;
- reviewer override artifact;
- release dashboard for precision, recall, false accept, and false refusal.

Exit criteria:

- agreement is not based only on structural equality;
- semantic disagreements block automatic acceptance;
- reviewer overrides are hash-linked and auditable;
- false semantic acceptance has a configured release budget.

Required ADR:

- ADR 0163: Semantic equivalence and translator calibration.

#### Phase 155 - ALICE-Grade Contradiction Engine

Purpose: detect contradictions inside a requirement or requirement set.

Scope:

- contradiction taxonomy;
- deterministic checks;
- LLM-assisted contradiction audit;
- conflict explanations;
- recall measurement;
- unsupported contradiction classes.

Deliverables:

- contradiction taxonomy v2;
- contradiction engine report;
- requirement-pair corpus;
- ALICE-style decision tree implementation;
- false-negative measurement report.

Exit criteria:

- contradiction classes are explicit;
- deterministic checks run before LLM audit;
- LLM audit evidence is marked as such;
- contradictions produce refusal with source spans;
- measured recall is reported and release-gated.

Required ADR:

- ADR 0164: ALICE-grade contradiction engine.

#### Phase 156 - Translation Release Corpus And Thresholds

Purpose: make semantic translation quality a release blocker.

Scope:

- public and private corpus split;
- semantic labels;
- false acceptance budget;
- false refusal budget;
- unsupported-fragment accounting;
- benchmark publication.

Deliverables:

- translation release corpus v2;
- expected semantic decomposition labels;
- benchmark runner;
- public report;
- threshold policy.

Exit criteria:

- corpus covers positive, ambiguous, contradictory, unsupported, temporal,
  numeric, authorization, and state-transition requirements;
- semantic accuracy is measured against labels;
- false acceptance over budget blocks release;
- public results can be reproduced.

Required ADR:

- ADR 0165: Translation release corpus and thresholds.

### Milestone 16 - Real Formal Backend And S-and-R Closure

Objective: make formal checking real. Supported formal claims must execute
against actual backend tools and compose with reviewed system specs without
overclaiming bounded evidence.

Current base:

- `src/nlreq/formal_claim.py`
- `src/nlreq/formal_backend.py`
- `src/nlreq/model_checker_runner.py`
- `src/nlreq/tla_projection.py`
- `src/nlreq/system_composition.py`
- `src/nlreq/counterexample_normalization.py`
- `src/nlreq/verification_budget.py`
- phases 124-130 specs and ADRs

Exit criteria:

- Apalache and TLC runners parse real command outputs;
- missing tools, timeouts, counterexamples, unsupported fragments, and valid
  outcomes are normalized;
- S packages are reviewed, fresh, and namespace-safe;
- R against S returns valid, counterexample, timeout, unsupported, stale-spec,
  missing-coverage, or needs-review;
- counterexamples are mapped to requirement spans, spec states, and traces.

#### Phase 157 - Formal Claim Semantics Exhaustion

Purpose: remove ambiguity from supported formal claim semantics.

Scope:

- claim kind semantics;
- temporal bounds;
- numeric constraints;
- authorization predicates;
- state pre/postconditions;
- event-state correspondence;
- unsupported claim behavior.

Deliverables:

- formal claim semantics table v2;
- golden fixtures for every supported claim class;
- unsupported claim fixtures;
- lowering conformance tests.

Exit criteria:

- every supported claim kind has exact semantics;
- every unsupported fragment refuses deterministically;
- semantics table maps to backend projections;
- tests cover each claim class.

Required ADR:

- ADR 0166: Formal claim semantics exhaustion.

#### Phase 158 - Production Apalache Runner Hardening

Purpose: make Apalache a real evidence producer.

Scope:

- command execution contract;
- tool discovery;
- version capture;
- bounds;
- output parser;
- counterexample parser;
- missing-tool and timeout behavior.

Deliverables:

- Apalache runner v2;
- command metadata schema;
- output parser tests using real sample outputs;
- counterexample normalization fixtures;
- missing-tool and timeout fixtures.

Exit criteria:

- runner can execute or clearly report missing tool;
- valid, counterexample, timeout, unsupported, and tool-error outcomes are
  normalized;
- bounded evidence labels include bounds;
- output artifacts are retained for replay.

Required ADR:

- ADR 0167: Production Apalache runner hardening.

#### Phase 159 - Production TLC Runner Hardening

Purpose: make TLC a second real formal backend path.

Scope:

- TLC command execution;
- config handling;
- invariant mapping;
- state trace parsing;
- state-space exhaustion;
- timeout and memory behavior.

Deliverables:

- TLC runner v2;
- TLC output parser;
- state trace normalizer;
- invariant mapping report;
- cross-check fixtures against Apalache where feasible.

Exit criteria:

- TLC results are normalized without manual parsing;
- counterexample traces retain state/action details;
- TLC-specific limits are represented honestly;
- disagreement with Apalache is visible, not hidden.

Required ADR:

- ADR 0168: Production TLC runner hardening.

#### Phase 160 - Reviewed System Spec Package Format

Purpose: make existing formal system spec `S` a first-class reviewed artifact.

Scope:

- spec module package;
- invariant manifest;
- namespace manifest;
- review status;
- freshness locks;
- coverage references;
- backend compatibility.

Deliverables:

- system spec package schema;
- reviewed spec manifest;
- invariant manifest;
- namespace policy;
- freshness lock integration.

Exit criteria:

- S cannot be used for release closure unless reviewed;
- invariants and assumptions are explicit;
- spec package records backend compatibility;
- namespace collisions with R are detected.

Required ADR:

- ADR 0169: Reviewed system spec package format.

#### Phase 161 - Production S-and-R Compatibility Checker

Purpose: mature `S and R` composition over real specs.

Scope:

- module composition;
- invariant preservation;
- assumption compatibility;
- namespace policy;
- backend dispatch;
- stale spec and missing coverage behavior.

Deliverables:

- S-and-R checker v2;
- compatibility report v2;
- real TLA fixture;
- counterexample fixture;
- timeout/unsupported/stale fixtures.

Exit criteria:

- checker returns explicit valid, counterexample, timeout, unsupported,
  stale-spec, missing-coverage, or needs-review;
- counterexamples identify violated invariant and requirement fragment;
- stale or unreviewed S blocks closure;
- unsupported R fragments do not overclaim compatibility.

Required ADR:

- ADR 0170: Production S-and-R compatibility checker.

#### Phase 162 - Counterexample Explanation And Replay

Purpose: make formal failures actionable.

Scope:

- counterexample state/action sequence;
- mapping to R source spans;
- mapping to S invariants;
- trace replay links;
- minimized explanations;
- user-facing refusal text.

Deliverables:

- counterexample explanation v2;
- replay bundle links;
- source-span mapping;
- invariant mapping;
- explanation quality tests.

Exit criteria:

- every counterexample names violated property, state/action path, and relevant
  requirement spans;
- replay instructions are retained where available;
- explanations distinguish formal counterexamples from trace violations;
- user-facing text does not overclaim proof strength.

Required ADR:

- ADR 0171: Counterexample explanation and replay.

#### Phase 163 - Verification Budget And Abstraction Profiles

Purpose: keep bounded/unknown outcomes honest.

Scope:

- per-backend budgets;
- time, memory, depth, state-space, and solver budgets;
- abstraction profiles;
- unknown semantics;
- cache interaction;
- escalation rules.

Deliverables:

- budget policy v2;
- abstraction profile schema;
- budgeted outcome report;
- release threshold policy;
- tests for timeout and unknown behavior.

Exit criteria:

- budget exhaustion cannot become acceptance;
- abstraction labels are visible in evidence;
- cache keys include budget and abstraction inputs;
- release certification can require stronger budgets for selected claims.

Required ADR:

- ADR 0172: Verification budget and abstraction profiles.

### Milestone 17 - Brownfield Spec Grounding And Drift Closure

Objective: make legacy-code grounding credible. The tool must identify affected
areas, prove formal spec coverage, generate candidate specs only as untrusted
drafts, promote specs only through review, and continuously reject stale specs.

Current base:

- `src/nlreq/source_impact.py`
- `src/nlreq/coverage_alignment.py`
- `src/nlreq/spec_extraction.py`
- `src/nlreq/spec_freshness.py`
- `src/nlreq/spec_drift.py`
- `src/nlreq/runtime_trace_sdk.py`
- `src/nlreq/trace_validation.py`
- phases 131-137 specs and ADRs

Exit criteria:

- affected areas are derived from deterministic adapter outputs plus marked
  semantic hints;
- uncovered affected areas block closure;
- generated specs are untrusted until reviewed;
- freshness is enforced continuously in CI;
- traces ground claims against current code behavior;
- brownfield deltas are actionable.

#### Phase 164 - Multi-Language Impact Analysis v2

Purpose: identify affected system areas across adapters.

Scope:

- symbol resolution;
- call graph;
- dependency graph;
- trace touchpoints;
- semantic hints;
- impact confidence;
- disagreement between deterministic and semantic impact.

Deliverables:

- impact report v2;
- impact role taxonomy;
- adapter impact fixtures;
- disagreement report;
- impacted spec lookup.

Exit criteria:

- deterministic impact and semantic suggestions are separated;
- trace-touched areas are recorded;
- dependency propagation is bounded and explainable;
- disagreement can block or request review under policy.

Required ADR:

- ADR 0173: Multi-language impact analysis v2.

#### Phase 165 - Code-To-Spec Coverage Manifest v3

Purpose: decide whether affected code has reviewed formal coverage.

Scope:

- code module to spec module mapping;
- symbol-level coverage;
- reviewed/candidate/stale states;
- transitive coverage;
- coverage thresholds;
- closure effect.

Deliverables:

- coverage manifest v3 schema;
- coverage gate report v3;
- coverage propagation algorithm;
- candidate coverage blocker;
- fixtures for full, partial, missing, candidate, and stale coverage.

Exit criteria:

- affected uncovered modules block closure;
- candidate specs do not count as reviewed coverage;
- stale specs do not count as fresh coverage;
- coverage gaps name exact impacted modules and symbols.

Required ADR:

- ADR 0174: Code-to-spec coverage manifest v3.

#### Phase 166 - Specula-Style Extraction Runner Production

Purpose: generate candidate formal specs from real code areas.

Scope:

- adapter canonical code presentation;
- extraction prompts;
- candidate TLA+ module generation;
- structural validation;
- trace validation requirement;
- candidate trust labels.

Deliverables:

- extraction runner;
- candidate spec package;
- structural validation report;
- trace-validation prerequisite report;
- extraction failure taxonomy.

Exit criteria:

- generated specs are always marked candidate/untrusted;
- candidates retain source code hashes and prompt metadata;
- structurally invalid candidates are rejected;
- candidates cannot satisfy release coverage until promoted.

Required ADR:

- ADR 0175: Specula-style extraction runner production.

#### Phase 167 - Candidate Spec Review Workbench

Purpose: make generated specs reviewable and promotable.

Scope:

- reviewer identity;
- spec diff;
- source-to-spec mapping;
- trace validation evidence;
- promotion;
- rejection;
- review history.

Deliverables:

- candidate review report;
- promotion report;
- rejection report;
- reviewed spec package output;
- CLI/API for review workflow.

Exit criteria:

- promoted specs have reviewer identity and reviewed source hashes;
- rejected specs retain reasons;
- promotion creates freshness locks;
- review history is immutable and hash-linked.

Required ADR:

- ADR 0176: Candidate spec review workbench.

#### Phase 168 - Continuous Spec Freshness CI

Purpose: prevent specs from drifting from code.

Scope:

- changed code detection;
- coverage lookup;
- freshness hash validation;
- trace validation recency;
- spec lag metrics;
- branch blocking and waivers.

Deliverables:

- freshness CI report v2;
- GitHub/GitLab workflow examples;
- spec lag dashboard artifact;
- stale-spec waiver policy;
- fixtures for stale, fresh, waived, and missing validation.

Exit criteria:

- changed covered code invalidates freshness until validation reruns;
- stale specs block requirement closure and hard-gate CI;
- waivers are reviewed, time-limited, and hash-bound;
- spec lag is visible per module.

Required ADR:

- ADR 0177: Continuous spec freshness CI.

#### Phase 169 - Trace Producer SDK v2

Purpose: make real traces producer-backed and replayable.

Scope:

- producer registration;
- runtime metadata;
- monotonic time and wall clock;
- correlation ids;
- causal predecessor links;
- loss records;
- signing policy.

Deliverables:

- trace producer SDK v2;
- producer registry v2;
- trace loss report;
- signed trace evidence report;
- sample producers for at least two ecosystems.

Exit criteria:

- traces identify producer, runtime, tool version, and source hashes;
- lossy traces are visible and can block;
- causal links are normalized;
- high-assurance traces are signed where policy requires.

Required ADR:

- ADR 0178: Trace producer SDK v2.

#### Phase 170 - Trace Validation Against Formal Claims v2

Purpose: ground requirement R against current behavior.

Scope:

- formal claim to trace predicate mapping;
- satisfied, violation, gap, lossy, stale, unsupported outcomes;
- replay bundle integration;
- counterexample comparison;
- coverage threshold.

Deliverables:

- trace validation gate v2;
- claim-to-trace predicate library;
- violation explanations;
- trace replay integration;
- fixtures for satisfaction and violation across adapters.

Exit criteria:

- current traces can satisfy or contradict supported claims;
- trace gaps and lossy traces do not pass silently;
- unsupported trace predicates refuse or require review;
- trace validation outputs feed proof closure.

Required ADR:

- ADR 0179: Trace validation against formal claims v2.

#### Phase 171 - Brownfield Delta And Remediation Reports

Purpose: tell engineers what must change when closure fails.

Scope:

- spec gaps;
- stale specs;
- trace violations;
- formal counterexamples;
- affected code modules;
- required tests and traces;
- remediation ownership.

Deliverables:

- brownfield delta report;
- remediation plan artifact;
- PR annotation format;
- backlog export format;
- tests for accepted, refused, and unknown deltas.

Exit criteria:

- every brownfield refusal has actionable next steps;
- deltas separate code change, spec update, trace update, and review work;
- remediation reports can be attached to PRs or issues;
- final certification requires no unresolved release-blocking deltas.

Required ADR:

- ADR 0180: Brownfield delta and remediation reports.

### Milestone 18 - Production Adapter And Trace Closure

Objective: prove programming-language agnosticism through real adapters. The
core must stay language-neutral while adapters wrap ecosystem tooling and
produce normalized source, impact, trace, coverage, and evidence artifacts.

Current base:

- `src/nlreq/source_adapter.py`
- `src/nlreq/production_source_adapters.py`
- `src/nlreq/adapter_certification.py`
- `src/nlreq/cross_language.py`
- phases 138-143 and 144 specs and ADRs

Exit criteria:

- at least four materially different adapters pass conformance;
- adapters expose limitations rather than pretending support;
- adapters produce real impact and trace artifacts;
- cross-adapter causal proof closes on a reference workflow;
- plugin versioning and certification renewal are defined.

#### Phase 172 - Adapter Conformance Suite v3

Purpose: make adapter certification strict enough for production.

Scope:

- required capabilities;
- limitation taxonomy;
- source presentation;
- symbol resolution ambiguity;
- call graph;
- trace extraction;
- coverage parsing;
- plugin manifest compatibility.

Deliverables:

- conformance suite v3;
- certification fixtures per capability;
- negative fixtures;
- conformance report v3;
- adapter author guide update.

Exit criteria:

- adapters cannot claim unsupported evidence;
- ambiguous symbols block;
- missing limitations block;
- trace and impact fixtures are required for production_candidate status.

Required ADR:

- ADR 0181: Adapter conformance suite v3.

#### Phase 173 - Solidity Adapter Production Hardening

Purpose: graduate the transaction/event ecosystem adapter.

Scope:

- solc AST;
- ABI metadata;
- inheritance and library resolution;
- event semantics;
- transaction trace normalization;
- on-chain/deployed metadata;
- unsupported EVM features.

Deliverables:

- Solidity adapter v3;
- EVM trace producer;
- source impact fixtures;
- trace fixtures;
- limitation report;
- conformance certification.

Exit criteria:

- overloaded functions and inherited symbols resolve or block;
- events and transaction calls normalize to trace schema;
- unsupported features are explicit;
- adapter produces retained evidence on a real contract fixture.

Required ADR:

- ADR 0182: Solidity adapter production hardening.

#### Phase 174 - Go Adapter Production Hardening

Purpose: graduate the compiled service ecosystem adapter.

Scope:

- packages and modules;
- gopls or Go tooling integration;
- static call graph;
- interface dispatch limitations;
- OpenTelemetry/runtime traces;
- build metadata.

Deliverables:

- Go adapter v3;
- Go source impact fixtures;
- Go trace producer;
- coverage manifest examples;
- conformance certification.

Exit criteria:

- package-level and symbol-level impact works on a real Go fixture;
- call graph limitations are explicit;
- runtime traces normalize to shared schema;
- adapter can participate in brownfield demo evidence.

Required ADR:

- ADR 0183: Go adapter production hardening.

#### Phase 175 - TypeScript/JavaScript Adapter Production Hardening

Purpose: graduate the frontend/service and dynamic JavaScript ecosystem.

Scope:

- tsserver integration;
- bundler metadata;
- browser/server split;
- async traces;
- dynamic property limitations;
- source maps.

Deliverables:

- TypeScript adapter v3;
- JavaScript adapter v3;
- async trace producer;
- source map handling;
- conformance certification.

Exit criteria:

- TS static symbols resolve through project metadata;
- JS dynamic limitations block when unsafe;
- async causal traces retain correlation ids;
- browser and server runtimes are distinguished.

Required ADR:

- ADR 0184: TypeScript/JavaScript adapter production hardening.

#### Phase 176 - Python Adapter Production Hardening

Purpose: harden the dynamic scripting adapter.

Scope:

- AST symbol resolution;
- import graph;
- decorators and dynamic dispatch limitations;
- pytest or runtime trace extraction;
- package metadata;
- monkeypatch/reflection limitations.

Deliverables:

- Python adapter v3;
- Python impact fixtures;
- Python trace producer;
- dynamic limitation taxonomy;
- conformance certification.

Exit criteria:

- imports and decorated symbols resolve or block;
- dynamic behavior limitations are explicit;
- runtime traces normalize to shared schema;
- adapter can produce retained evidence for a real package fixture.

Required ADR:

- ADR 0185: Python adapter production hardening.

#### Phase 177 - Rust Or Java Adapter Production Hardening

Purpose: add a second compiled ecosystem pressure test beyond Go.

Scope:

- ecosystem selection;
- compiler metadata;
- package/module graph;
- call graph;
- runtime traces;
- generics/traits or overloads/interfaces;
- limitations.

Deliverables:

- selected adapter v3;
- selection ADR evidence;
- impact fixtures;
- trace producer;
- conformance certification.

Exit criteria:

- selected adapter stresses the interface differently from Go;
- language-specific ambiguity blocks cleanly;
- runtime traces participate in cross-adapter closure;
- limitations are documented and schema-backed.

Required ADR:

- ADR 0186: Rust or Java adapter production hardening.

#### Phase 178 - Cross-Adapter Causal Trace Closure

Purpose: prove real multi-adapter causal evidence.

Scope:

- correlation ids;
- clock model;
- causal predecessor links;
- cross-runtime traces;
- missing link blockers;
- replay bundle integration.

Deliverables:

- cross-adapter causal trace fixture;
- causal closure report v3;
- replay bundle links;
- per-adapter blocker propagation;
- demo requirement spanning at least two adapters.

Exit criteria:

- one requirement spanning at least two adapters closes or refuses as one proof
  object;
- missing causal links block relevant claims;
- per-adapter blockers remain visible;
- replay bundles can reproduce causal evidence.

Required ADR:

- ADR 0187: Cross-adapter causal trace closure.

#### Phase 179 - Adapter Plugin Marketplace And Version Policy

Purpose: make external adapters maintainable.

Scope:

- plugin manifest versioning;
- adapter capability versioning;
- compatibility matrix;
- deprecation;
- certification renewal;
- trust policy.

Deliverables:

- plugin marketplace manifest;
- adapter compatibility report;
- certification renewal report;
- deprecation policy;
- public SDK update.

Exit criteria:

- adapter plugins declare compatible core versions;
- stale certifications expire;
- breaking adapter changes require renewal;
- external users can install and validate adapters without reading internals.

Required ADR:

- ADR 0188: Adapter plugin marketplace and version policy.

### Milestone 19 - Replay, Benchmark, And Release Evidence Closure

Objective: make release evidence hard to fake. Benchmarks, demos, replay
bundles, producer keys, beta pilots, and CI governance must be backed by real
retained artifacts.

Current base:

- `src/nlreq/artifact_store.py`
- `src/nlreq/signed_evidence.py`
- `src/nlreq/evidence_producers.py`
- `src/nlreq/benchmark_reporting.py`
- `src/nlreq/reference_demo.py`
- `src/nlreq/policy_governance.py`
- `src/nlreq/conclusion_certification.py`
- phases 145-150 specs and ADRs

Exit criteria:

- high-assurance evidence is signed by trusted registered producers;
- replay bundles can reproduce retained artifacts;
- public benchmarks are hostile enough to reveal false closure/refusal;
- one non-toy brownfield demo closes and refuses through the real path;
- beta pilot findings are retained and resolved;
- CI hard gate is branch-protection ready.

#### Phase 180 - Replay Bundle v3 And Artifact Retention

Purpose: make replay bundles durable release artifacts.

Scope:

- bundle layout;
- artifact retention;
- command metadata;
- environment metadata;
- compression;
- retention duration;
- reproducibility verification.

Deliverables:

- replay bundle v3 schema;
- retention policy;
- replay verifier v3;
- release bundle exporter;
- tests for tampering, missing files, and environment drift.

Exit criteria:

- every release-critical artifact is in a replay bundle;
- bundle verification detects tampering and missing files;
- commands and environment metadata are retained;
- retention policy is documented and enforceable.

Required ADR:

- ADR 0189: Replay bundle v3 and artifact retention.

#### Phase 181 - Producer Key Management And Trust Policy

Purpose: make producer identity meaningful.

Scope:

- producer key registry lifecycle;
- trust levels;
- key rotation;
- key revocation;
- high-assurance enforcement;
- audit log.

Deliverables:

- producer key registry v2;
- trust policy report;
- rotation/revocation fixtures;
- signing audit report;
- release enforcement integration.

Exit criteria:

- revoked keys cannot satisfy release evidence;
- rotated keys preserve audit history;
- high-assurance evidence requires trusted keys;
- missing producer identity blocks certification.

Required ADR:

- ADR 0190: Producer key management and trust policy.

#### Phase 182 - Public Benchmark Corpus v2

Purpose: make benchmarks hostile and representative.

Scope:

- semantic translation;
- self-consistency;
- S-and-R compatibility;
- trace grounding;
- adapter evidence;
- counterexample quality;
- false closure;
- false refusal;
- timeout and unknown;
- runtime.

Deliverables:

- public benchmark corpus v2;
- private holdout corpus;
- expected outcomes;
- corpus governance policy;
- scoring thresholds.

Exit criteria:

- corpus includes adversarial false-closure cases;
- false refusal is tracked separately from false closure;
- timeout and unknown are not counted as success;
- benchmark cases cover all release-critical dimensions.

Required ADR:

- ADR 0191: Public benchmark corpus v2.

#### Phase 183 - Benchmark Runner And Leaderboard Automation

Purpose: make public reports reproducible.

Scope:

- benchmark runner API;
- environment capture;
- scoring;
- leaderboard entries;
- result signing;
- reproducibility instructions.

Deliverables:

- benchmark runner v2;
- leaderboard generator;
- signed benchmark report;
- reproduction guide;
- CI workflow.

Exit criteria:

- public benchmark report can be regenerated from retained inputs;
- leaderboard entries include environment and report hashes;
- failed dimensions block release;
- benchmark runner itself is versioned.

Required ADR:

- ADR 0192: Benchmark runner and leaderboard automation.

#### Phase 184 - Non-Toy Reference Brownfield Demo

Purpose: prove the real path on a credible codebase.

Scope:

- demo target selection;
- accepted requirement;
- refused requirement;
- reviewed system spec;
- impact analysis;
- spec coverage/freshness;
- traces;
- replay bundles;
- CI outputs.

Deliverables:

- reference demo repo or fixture set;
- demo runbook;
- accepted requirement package;
- refused requirement package;
- replay bundles;
- CI gate reports.

Exit criteria:

- at least one accepted and one refused requirement run through the real path;
- demo uses reviewed spec coverage;
- traces are generated by real producers;
- replay bundles verify;
- demo can be rerun by an external reviewer.

Required ADR:

- ADR 0193: Non-toy reference brownfield demo.

#### Phase 185 - Beta Pilot Evidence Program

Purpose: collect external workflow evidence.

Scope:

- pilot participant selection;
- workflow definition;
- evidence retention;
- feedback schema;
- severity taxonomy;
- mitigation tracking.

Deliverables:

- pilot report schema v2;
- pilot run reports;
- release findings;
- mitigation reports;
- acceptance summary.

Exit criteria:

- at least two pilots exercise the real path;
- blocker findings are mitigated or release-blocking;
- pilot evidence is retained and hash-linked;
- false closure/refusal reports feed benchmark updates.

Required ADR:

- ADR 0194: Beta pilot evidence program.

#### Phase 186 - CI Hard Gate Governance Deployment

Purpose: make downstream action gating enforceable.

Scope:

- required checks;
- branch protection;
- waiver governance;
- policy drift;
- audit retention;
- host platform differences.

Deliverables:

- GitHub hard-gate template;
- GitLab hard-gate template;
- branch-protection runbook;
- waiver audit integration;
- policy drift report.

Exit criteria:

- hard gate can be configured as a required check;
- waivers are reviewed, hash-bound, time-limited, and auditable;
- policy changes require review;
- branch protection evidence feeds final certification.

Required ADR:

- ADR 0195: CI hard gate governance deployment.

### Milestone 20 - External Review And Conclusion Publication

Objective: publish only after hostile review. The release must be reproducible,
documented, signed, and honest about limitations.

Current base:

- `src/nlreq/threat_model.py`
- `src/nlreq/public_sdk.py`
- `src/nlreq/conclusion_certification.py`
- docs and schemas through phase 150

Exit criteria:

- threat model and TCB are reviewed;
- external reviewers can reproduce the benchmark and reference demo;
- public docs explain supported and unsupported claims;
- schemas are frozen and signed;
- final claim language is scoped and approved;
- final certification decision is retained.

#### Phase 187 - Threat Model And TCB Re-Review

Purpose: update the trust boundary after real evidence integration.

Scope:

- TCB inventory;
- attack scenarios;
- LLM translation attacks;
- producer forgery;
- stale spec attacks;
- adapter spoofing;
- benchmark gaming;
- accepted residual risks.

Deliverables:

- threat model v2;
- TCB review report v2;
- mitigation checklist;
- residual risk acceptance report;
- release-blocking attack scenarios.

Exit criteria:

- every release-critical component is in or out of TCB explicitly;
- unmitigated high-severity attack scenarios block release;
- accepted residual risks are reviewed;
- public docs name trust boundaries.

Required ADR:

- ADR 0196: Threat model and TCB re-review.

#### Phase 188 - External Reproduction And Red-Team Review

Purpose: test whether outsiders can reproduce and break the claim.

Scope:

- reviewer package;
- reproduction instructions;
- benchmark reproduction;
- reference demo reproduction;
- red-team scenarios;
- issue response.

Deliverables:

- external review package;
- reproduction reports;
- red-team findings;
- response and mitigation reports;
- release review summary.

Exit criteria:

- at least one external reviewer reproduces benchmark and demo;
- blocker findings are resolved or release-blocking;
- red-team false-closure findings update benchmark corpus;
- review artifacts are retained.

Required ADR:

- ADR 0197: External reproduction and red-team review.

#### Phase 189 - Public Documentation And Schema Freeze v2

Purpose: make adoption possible without reading internals.

Scope:

- public docs;
- CLI/API guide;
- schema guide;
- adapter guide;
- evidence labels;
- limitations;
- migration policy.

Deliverables:

- public documentation index v2;
- frozen schema hash manifest;
- compatibility commitments;
- migration guide;
- release notes.

Exit criteria:

- docs cover operators, adapter authors, reviewers, and API users;
- every public artifact has a schema reference;
- schema hashes are frozen;
- compatibility commitments are explicit.

Required ADR:

- ADR 0198: Public documentation and schema freeze v2.

#### Phase 190 - Release Bundle Signing And Publication

Purpose: publish a verifiable release bundle.

Scope:

- bundle contents;
- schema hashes;
- benchmark reports;
- replay bundles;
- reference demo artifacts;
- docs;
- signatures;
- verification instructions.

Deliverables:

- release bundle;
- signed release manifest;
- verification command;
- publication checklist;
- archived artifact links.

Exit criteria:

- release bundle includes all required evidence;
- release signature verifies;
- verification instructions work from a clean checkout;
- missing artifacts block publication.

Required ADR:

- ADR 0199: Release bundle signing and publication.

#### Phase 191 - Conclusion Claim Language And Limitations

Purpose: write the public claim without overclaiming.

Scope:

- supported requirement classes;
- supported adapters;
- evidence labels;
- bounded vs inductive guarantees;
- unsupported domains;
- known limitations;
- user obligations.

Deliverables:

- conclusion claim document;
- limitation matrix;
- evidence label glossary;
- public FAQ;
- reviewer signoff.

Exit criteria:

- claim names scope and non-goals;
- bounded checking is not described as proof;
- generated specs are not described as trusted unless promoted;
- unsupported domains are explicit.

Required ADR:

- ADR 0200: Conclusion claim language and limitations.

#### Phase 192 - Final Real-Evidence Conclusion Decision

Purpose: make the final ship/no-ship decision.

Scope:

- all milestone evidence;
- certification report;
- external review;
- threat model;
- benchmark thresholds;
- demo replay;
- CI governance;
- signed bundle;
- public claim.

Deliverables:

- final certification report v2;
- ship/no-ship decision record;
- signed conclusion bundle;
- release announcement draft;
- post-release monitoring plan.

Exit criteria:

- every required criterion passes;
- no scaffold evidence is included;
- external blockers are closed or accepted as release blockers;
- final report is signed and retained;
- public claim is published only after certification.

Required ADR:

- ADR 0201: Final real-evidence conclusion decision.

## Dependency Graph

- Phases 151-156 must complete before semantic translation can be used as
  release evidence.
- Phases 157-163 depend on phase 153 semantic decomposition IR v2.
- Phase 161 depends on phase 160 reviewed system spec packages.
- Phases 164-171 depend on adapter impact outputs from milestone 18, but can
  start with current scaffolds.
- Phase 166 depends on phase 164 impact and adapter code presentation.
- Phase 168 depends on phase 165 coverage manifest v3 and phase 167 promotion.
- Phase 170 depends on phase 169 trace producer SDK v2.
- Phases 173-177 depend on phase 172 conformance suite v3.
- Phase 178 depends on at least two production-hardened adapters.
- Phase 184 depends on milestones 15-18.
- Phase 186 depends on phase 184 demo evidence and phase 181 producer trust.
- Milestone 20 depends on milestones 15-19.

## Acceptance Strategy

Each phase must ship:

- a phase spec;
- an ADR;
- schema updates where public artifacts change;
- implementation;
- focused tests;
- at least one negative test proving refusal/blocking behavior;
- documentation of evidence labels and limitations.

Each milestone must ship:

- a milestone digest;
- a test file or test marker for the milestone;
- schema drift verification;
- one end-to-end fixture that combines the milestone outputs;
- a gap statement naming what still remains outside the milestone.

The final release must pass:

```bash
uv run pytest
uv run python scripts/check_schema_drift.py
```

and a release-specific reproduction command that verifies:

- replay bundles;
- producer signatures;
- benchmark reports;
- reference demo artifacts;
- CI governance reports;
- final certification report.

## Immediate Next Actions

1. Implement phase 151 and phase 152 together so free-form intake and rewrite
   replay produce real corpus evidence.
2. Implement phase 153 before expanding translators further; the semantic IR is
   the backbone for the rest of the work.
3. Choose one non-toy reference target for phase 184 now, even if execution
   happens later. The target should force real impact analysis, spec coverage,
   traces, S-and-R checking, replay, and CI governance.
4. Start public benchmark corpus design in parallel with phase 156, because
   false-closure cases discovered during implementation should become benchmark
   cases immediately.
5. Treat every generated spec as untrusted until the phase 167 review workbench
   promotes it.

## Conclusion

Phases 0-150 built the system's contract surface. Phases 151-192 must prove the
contract against real evidence.

The project reaches the Claude discussion only when the action gate is backed
by measured semantic translation, reviewed fresh system specs, real formal
backend execution, real adapter traces, retained replay bundles, signed
producer evidence, hostile benchmarks, non-toy demos, and external
reproduction.

Until then, the correct claim is:

> The Attestation Layer has the architecture of a real-evidence requirement
> closure system and is ready for real-evidence hardening.

After this roadmap, the intended claim is:

> The Attestation Layer can enforce scoped real-evidence requirement closure for
> supported requirement classes and supported language adapters.
