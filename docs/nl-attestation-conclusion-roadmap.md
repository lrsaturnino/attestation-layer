# NL Attestation Layer Conclusion Roadmap

**Status:** Draft v1
**Date:** 2026-06-01
**Starts After:** Phase 45 Public Benchmark Corpus
**Current ADR Floor:** ADR 0091 Conclusion Release Certification
**Source Context:** `docs/claude-convo.md`, `docs/verification-power-roadmap.md`, implemented phases 0-45

This roadmap closes the remaining gap between the current Attestation Layer and
the target described in `docs/claude-convo.md`:

```text
Human requirement
-> controlled or clarified requirement
-> formal claim R
-> R checked against itself
-> R checked against current system spec S
-> R grounded against current code behavior and traces
-> all affected code/spec areas fresh and covered
-> all high-assurance evidence emitted by real producers
-> proof object closes
-> downstream action is allowed only after closure
```

The repository now has the architectural skeleton and the first working vertical
slice. The remaining work is to turn the skeleton into a production-grade,
programming-language-agnostic natural-language requirement gate.

## Current Baseline After Phase 45

Implemented capabilities:

- controlled DSL to compositional IR;
- adapter-neutral core and package format;
- source adapter boundary and conformance tests;
- normalized trace schema;
- Python source adapter;
- JavaScript source adapter;
- formal backend boundary;
- real model-checker runner contract;
- TLA backend MVP;
- translator agreement gate;
- requirement self-consistency;
- system spec registry;
- deterministic system consistency check;
- solver-backed system consistency path;
- spec coverage and trace alignment;
- trace replay grounding;
- spec extraction workbench;
- spec drift CI semantics;
- source impact analysis;
- delta extraction;
- verification budgets;
- evidence producer validation;
- backend agreement reports;
- end-to-end `requirement-gate`;
- public seed benchmark corpus.

Known remaining gaps:

- free-form NL intake is not yet a real product path;
- NL-to-IR translation is deterministic parser based, not robust LLM-assisted
  multi-pass translation with clarification;
- translator agreement is structural, not deep logical equivalence;
- self-consistency is limited and not yet an ALICE-grade contradiction taxonomy;
- TLA execution is MVP-level and not yet a production Apalache/TLC/TLAPS stack;
- system consistency is not yet full `S and R` composition over mature formal
  system specs;
- Specula-style code-to-spec extraction is not yet production-grade;
- real runtime trace extraction is not yet integrated for major ecosystems;
- source adapters are Python and JavaScript only;
- Solidity, Go, Rust, Java, and TypeScript production adapters are missing;
- cross-language causal trace stitching is missing;
- evidence signing, artifact retention, and TCB audit are missing;
- benchmark corpus is a seed corpus, not a serious public evaluation suite;
- CI/PR/product adoption surfaces are not hardened.

## Definition Of Conclusion

This roadmap is done when the project can credibly claim:

1. **Input closure:** A human can submit either controlled text or free-form text.
   Free-form text must be rewritten into controlled form with explicit approval,
   provenance, and a diff. No silent semantic rewrite is allowed.
2. **Translation closure:** The requirement becomes compositional IR with
   source-span provenance, translator agreement, and clarification output for
   ambiguity.
3. **Self-consistency closure:** The requirement is checked against itself with
   a documented contradiction taxonomy and deterministic refusal surface.
4. **Formal closure:** Supported fragments are checked by at least one real
   formal backend with recorded bounds, command metadata, versions, and
   counterexamples.
5. **System closure:** The new requirement R is checked against the existing
   reviewed system spec set S, with satisfiable, counterexample, timeout, and
   unsupported outcomes represented explicitly.
6. **Brownfield grounding:** Impact analysis identifies affected modules;
   missing or stale formal specs block closure; Specula-style candidate specs can
   be generated for gaps; current runtime traces are replayed against R.
7. **Adapter credibility:** At least three materially different production
   programming-language adapters pass conformance. At least one must be a
   statically typed compiled/runtime ecosystem and one must be event/transaction
   oriented.
8. **Cross-language credibility:** A requirement spanning multiple language
   adapters can produce one proof object and one closure decision.
9. **Evidence integrity:** High-assurance evidence is produced only by real,
   registered, reproducible producers. Artifacts are hash-linked, retained, and
   auditable.
10. **Benchmark credibility:** A public benchmark suite tracks accepted,
    refused, unknown, timeout, drift, trace mismatch, backend disagreement, false
    closure, false refusal, counterexample quality, and runtime.
11. **Action gate:** Downstream actions cannot proceed through the official API
    unless the closure gate passes.

## Non-Goals

The conclusion release still does not claim:

- full correctness for arbitrary natural language;
- full correctness for arbitrary programs;
- unbounded proofs where only bounded checking ran;
- semantic equivalence between all formal backends;
- automatic spec updates without human review;
- replacement of domain experts;
- support for every programming language.

The project should remain strict about evidence labels. A bounded model check is
not a proof. A trace replay is not a theorem. An LLM translation is not a trusted
formal artifact until deterministic checks consume it.

## Milestone Groups

| Group | Phases | Theme |
|---|---:|---|
| A | 46-50 | product definition, intake, and controlled-form approval |
| B | 51-55 | translation, provenance, clarification, and contradiction taxonomy |
| C | 56-61 | real formal backend maturity and `S and R` composition |
| D | 62-66 | brownfield grounding, spec extraction, freshness, and traces |
| E | 67-72 | production adapters and cross-language evidence |
| F | 73-78 | evidence integrity, scale, CI adoption, and benchmarks |
| G | 79-82 | release hardening, public docs, and conclusion certification |

## Four-Step Program View

The detailed phase sequence is the implementation backlog. For sprint and
program planning, the conclusion roadmap can be managed as four larger delivery
steps:

| Step | Phases | Theme | Outcome |
|---:|---:|---|---|
| 1 | 46-55 | Safe Requirement Intake | A human requirement can safely become an approved controlled requirement and IR candidate, or be refused with precise next actions. |
| 2 | 56-61 | Formal Closure Core | The system can check requirement `R` against itself and against reviewed system spec `S`, with explicit valid, counterexample, timeout, unsupported, and needs-review outcomes. |
| 3 | 62-72 | Brownfield Grounding And Adapters | The gate can identify affected code, require fresh specs, replay real traces, and aggregate evidence across multiple programming ecosystems. |
| 4 | 73-82 | Productionization And Release | Downstream actions can be gated in real engineering workflows with retained evidence, benchmark accountability, documented limits, and a reproducible conclusion release. |

Step 1 builds the front door of the system: conclusion definition, free-form
intake, controlled rewrite approval, DSL v3, review workflow, refusal surface,
multi-pass translation, provenance, clarification, logical agreement,
contradiction taxonomy, and the translation corpus.

Step 2 makes the formal verification spine real: Apalache, TLC when included,
TLA projection, counterexample normalization, real `S and R` composition, and
the proof-level evidence boundary.

Step 3 connects the formal core to real code and runtime behavior:
Specula-style extraction, code-to-spec manifest, freshness lockfile, runtime
trace extraction, trace normalization, production adapters, adapter
certification, and cross-language proof objects.

Step 4 makes the project adoptable, auditable, and defensible: artifact storage,
signed evidence, CI/PR gating, benchmark evaluation, performance and caching, waiver
governance, threat model, reference brownfield demo, public docs and SDK, and
final release certification.

Benchmark expansion should run continuously across all four steps. Phase 76
stabilizes the public benchmark methodology and release criteria, but every
step should contribute fixtures for the capabilities it introduces.

## Phase Sequence

| Phase | Name | Primary Gap Closed | Required ADR |
|---:|---|---|---|
| 46 | Conclusion Definition And Gap Audit | shared finish line | ADR 0055 |
| 47 | Free-Form Intake And Controlled Rewrite | safe human input path | ADR 0056 |
| 48 | Controlled Requirement DSL v3 | richer but bounded input grammar | ADR 0057 |
| 49 | Requirement Review And Approval Workflow | no silent semantic shifts | ADR 0058 |
| 50 | Product Refusal Surface | actionable iteration loop | ADR 0059 |
| 51 | Multi-Pass NL Translator Workbench | untrusted NL-to-IR bridge | ADR 0060 |
| 52 | Bidirectional Provenance And Clarification | explain ambiguity precisely | ADR 0061 |
| 53 | Logical Translator Agreement | beyond structural diffs | ADR 0062 |
| 54 | Contradiction Taxonomy | ALICE-style self-checking | ADR 0063 |
| 55 | Requirement Corpus For Translation | measure semantic translation quality | ADR 0064 |
| 56 | Apalache Backend Production Integration | real symbolic bounded checking | ADR 0065 |
| 57 | TLC Backend Production Integration | explicit-state checking path | ADR 0066 |
| 58 | TLA Projection Semantics | larger formal fragment | ADR 0067 |
| 59 | Counterexample Normalization | actionable formal failures | ADR 0068 |
| 60 | Real `S and R` Composition | system compatibility against specs | ADR 0069 |
| 61 | Proof-Level Evidence Boundary | separate bounded from inductive proof | ADR 0070 |
| 62 | Specula-Style Extraction Runner | code to candidate spec | ADR 0071 |
| 63 | Code-To-Spec Manifest | brownfield coverage map | ADR 0072 |
| 64 | Spec Freshness Lockfile | reproducible freshness invariant | ADR 0073 |
| 65 | Runtime Trace Extraction SDK | real trace producers | ADR 0074 |
| 66 | Trace Normalization | cross-runtime trace semantics | ADR 0075 |
| 67 | Solidity Adapter | event/transaction adapter | ADR 0076 |
| 68 | Go Adapter | compiled service adapter | ADR 0077 |
| 69 | TypeScript Adapter | frontend/service adapter | ADR 0078 |
| 70 | Rust Or Java Adapter | third ecosystem pressure test | ADR 0079 |
| 71 | Adapter Certification Suite | stable plugin contract | ADR 0080 |
| 72 | Cross-Language Proof Object | one closure over multiple adapters | ADR 0081 |
| 73 | Evidence Artifact Store | retention and replayability | ADR 0082 |
| 74 | Signed Evidence And Producer Attestation | anti-forgery hardening | ADR 0083 |
| 75 | CI And PR Action Gate | adoption surface | ADR 0084 |
| 76 | Benchmark Evaluation | serious public evaluation | ADR 0085 |
| 77 | Performance And Caching | usable runtime | ADR 0086 |
| 78 | Policy And Waiver Governance | controlled exceptions | ADR 0087 |
| 79 | Threat Model And TCB Audit | security review | ADR 0088 |
| 80 | Reference Brownfield Demo | credible real-system demo | ADR 0089 |
| 81 | Public Documentation And SDK | external adopter path | ADR 0090 |
| 82 | Conclusion Release Certification | final readiness decision | ADR 0091 |

## Detailed Phase Plan

### Phase 46 - Conclusion Definition And Gap Audit

Purpose: freeze the conclusion target so remaining work does not drift.

Gap closed: the project has a working architecture, but no crisp definition of
what counts as "done" for the Claude-conversation target.

Scope:

- publish the conclusion definition as a versioned artifact;
- map every target capability to existing code, missing code, tests, docs, and
  schemas;
- classify gaps as architecture, implementation, research, product, benchmark,
  or adoption gaps;
- define minimum release bar for alpha, beta, and conclusion release;
- define what evidence labels are allowed at each release bar.

Deliverables:

- `docs/conclusion-definition.md`;
- `docs/conclusion-gap-audit.md`;
- machine-readable gap checklist;
- issue template for gap closure;
- release-bar matrix.

Exit criteria:

- every missing capability has an owner phase;
- no phase can introduce `PROVEN_INDUCTIVE` without a proof-producing backend;
- the roadmap and gap audit agree on phase and ADR numbering;
- CI checks the machine-readable gap checklist for unknown phase references.

Required ADR:

- ADR 0055: Conclusion definition, release bars, and evidence-label discipline.

### Phase 47 - Free-Form Intake And Controlled Rewrite

Purpose: support human requirement intake without trusting raw natural language.

Gap closed: the current gate accepts controlled DSL. The discussion target
requires natural-language requests with structural backpressure.

Scope:

- add a free-form intake artifact;
- generate proposed controlled-form rewrites;
- preserve original text, proposed controlled form, diff, prompt metadata, model
  metadata, and timestamp;
- require explicit approval before parsing;
- refuse raw free-form text when no approved controlled form exists;
- mark the entire translation path as untrusted until reviewed.

Deliverables:

- free-form intake schema;
- controlled rewrite proposal schema;
- approval schema;
- CLI commands:
  - `nlreq intake-draft`;
  - `nlreq intake-approve`;
  - `nlreq intake-diff`;
- tests for no-silent-rewrite behavior.

Exit criteria:

- parser never consumes unapproved LLM-rewritten text;
- package preserves original text and approved controlled form;
- output names exactly which text was approved;
- tests prove the diff is hash-linked into the final report.

Required ADR:

- ADR 0056: Free-form intake, controlled rewrite, and approval semantics.

### Phase 48 - Controlled Requirement DSL v3

Purpose: expand the controlled input grammar while staying bounded and
deterministic.

Gap closed: current DSL is useful for demos but too narrow for real requirement
intake.

Scope:

- support requirement classes:
  - authorization precondition;
  - state precondition;
  - state postcondition;
  - event/state correspondence;
  - numeric invariant;
  - bounded temporal property;
  - cross-module causal obligation;
- add canonical formatting rules;
- make source spans stable over canonical text;
- reject ambiguous grammar constructs;
- version the grammar independently from the IR.

Deliverables:

- grammar v3 file;
- parser migration notes;
- canonical formatter;
- golden fixtures for every requirement class;
- grammar compatibility tests.

Exit criteria:

- every grammar construct maps to a typed IR node;
- every parse result has stable source spans;
- unsupported constructs fail with structured next actions;
- grammar fixtures are byte-stable.

Required ADR:

- ADR 0057: Controlled requirement DSL v3 grammar, canonical form, and
  compatibility policy.

### Phase 49 - Requirement Review And Approval Workflow

Purpose: make human review a real state transition, not a comment.

Gap closed: current artifacts represent review in places, but the full intake
and translation path needs a consistent approval workflow.

Scope:

- define reviewer roles:
  - author;
  - requirement reviewer;
  - formal reviewer;
  - adapter/evidence reviewer;
  - self-audit reviewer;
- require checklist artifacts for approval;
- bind approvals to artifact hashes;
- support solo mode with delayed self-audit;
- prevent stale approvals after artifact changes.

Deliverables:

- approval workflow schema;
- review checklist;
- stale-review detector;
- CLI:
  - `nlreq review-open`;
  - `nlreq review-approve`;
  - `nlreq review-status`;
- docs for solo and team workflows.

Exit criteria:

- an approval cannot survive changes to the reviewed artifact;
- self-audit records delay and reviewer identity;
- final gate reports review status explicitly;
- tests cover stale approvals and self-audit.

Required ADR:

- ADR 0058: Requirement review, approval hash binding, and self-audit policy.

### Phase 50 - Product Refusal Surface

Purpose: make refusal actionable enough for normal users to iterate.

Gap closed: current reports expose blockers, but product-grade refusal requires
specific fragments, next actions, and correction paths.

Scope:

- unify refusal categories across parser, translator, self-consistency,
  coverage, trace, formal backend, producer, and closure stages;
- map every refusal to source spans when available;
- include next actions and likely owner;
- distinguish refused from unknown;
- add markdown and JSON renderers;
- support stable refusal codes.

Deliverables:

- refusal taxonomy schema;
- refusal renderer;
- CLI markdown output for requirement gate;
- docs with examples for accepted, refused, and unknown outcomes.

Exit criteria:

- every gate blocker has a stable refusal code;
- every refusal either has a source span or explains why no span exists;
- benchmark cases assert expected refusal codes;
- markdown and JSON outputs agree.

Required ADR:

- ADR 0059: Product refusal taxonomy, source-span mapping, and iteration loop.

### Phase 51 - Multi-Pass NL Translator Workbench

Purpose: build the untrusted NL-to-IR translator pipeline.

Gap closed: the current system has controlled parsing and structural translator
agreement, not a serious NL translation workbench.

Scope:

- run multiple translator strategies over the same approved text:
  - deterministic parser;
  - LLM semantic decomposition;
  - rule-based post-processor;
  - optional second-model audit;
- store all candidates;
- compare candidates before selecting one;
- classify disagreement;
- produce clarification prompts.

Deliverables:

- translator candidate schema;
- translator run schema;
- workbench CLI:
  - `nlreq translate-candidates`;
  - `nlreq translate-compare`;
  - `nlreq translate-select`;
- prompt registry;
- deterministic replay fixtures.

Exit criteria:

- candidate generation is reproducible enough to audit;
- no LLM candidate can be selected without review;
- disagreement blocks the gate unless explicitly resolved;
- translator workbench output feeds existing `translation-agreement`.

Required ADR:

- ADR 0060: Multi-pass translator workbench and untrusted candidate policy.

### Phase 52 - Bidirectional Provenance And Clarification

Purpose: make every formal fragment explainable back to requirement text.

Gap closed: current source spans exist, but deep clarification requires a
bidirectional map between text, IR nodes, formal fragments, and refusal reasons.

Scope:

- maintain text-to-IR and IR-to-text provenance;
- maintain IR-to-formal artifact provenance;
- generate clarification questions from disagreeing or unsupported fragments;
- support user corrections that target a source span;
- preserve clarification history.

Deliverables:

- provenance graph schema;
- clarification request schema;
- clarification response schema;
- CLI:
  - `nlreq clarify`;
  - `nlreq apply-clarification`;
- UI-ready JSON shape.

Exit criteria:

- translator disagreement can name exact source fragments;
- unsupported formal fragments can name exact IR nodes and text;
- clarification responses produce a new controlled-form version;
- previous versions remain auditable.

Required ADR:

- ADR 0061: Bidirectional provenance graph and clarification protocol.

### Phase 53 - Logical Translator Agreement

Purpose: move beyond structural equality into semantic agreement for supported
fragments.

Gap closed: structural comparison catches many issues but misses logically
equivalent rewrites and deeper semantic conflicts.

Scope:

- define supported equivalence checks:
  - normalized IR equality;
  - alpha-renaming equivalence;
  - commutative predicate equivalence;
  - SMT equivalence for simple predicates;
  - bounded trace equivalence for temporal fragments;
- preserve structural disagreement as a fallback;
- record equivalence method and limitations.

Deliverables:

- logical agreement report;
- equivalence checker modules;
- fixtures for equivalent but syntactically different requirements;
- fixtures for structurally similar but semantically different requirements.

Exit criteria:

- simple equivalent translations no longer require manual clarification;
- semantic conflicts still block;
- report states which equivalence method was used;
- unsupported equivalence remains `needs_review`, not `agreed`.

Required ADR:

- ADR 0062: Logical translator agreement and equivalence-method hierarchy.

### Phase 54 - Contradiction Taxonomy

Purpose: make self-consistency a first-class requirements analysis backend.

Gap closed: current self-consistency is narrow and deterministic. The target
needs ALICE-style contradiction detection over requirement fragments.

Scope:

- define contradiction categories:
  - direct opposite predicates;
  - impossible comparison;
  - mutually exclusive states;
  - overlapping conditions with opposite obligations;
  - temporal impossibility;
  - numeric bound conflict;
  - duplicate obligation conflict;
- implement deterministic checks first;
- route supported formulas to SMT;
- produce source-span grounded explanations.

Deliverables:

- contradiction taxonomy doc;
- self-consistency report schema;
- SMT encodings for supported contradiction classes;
- fixtures from real and synthetic requirements.

Exit criteria:

- contradictions are classified by stable code;
- every contradiction reports source spans;
- unknown contradiction classes are not silently accepted;
- benchmark includes at least ten contradiction fixtures.

Required ADR:

- ADR 0063: Requirement contradiction taxonomy and self-consistency semantics.

### Phase 55 - Requirement Corpus For Translation

Purpose: measure translator and clarification quality separately from backend
verification.

Gap closed: benchmark corpus currently measures end outcomes, not translation
semantic accuracy.

Scope:

- create a corpus of requirement texts with expected IR fragments;
- include clean controlled text, messy prose, ambiguous prose, incomplete prose,
  multilingual samples, and adversarial inputs;
- record expected clarification questions;
- measure syntactic validity, semantic match, clarification quality, and refusal
  correctness.

Deliverables:

- `benchmarks/requirements-translation/corpus.json`;
- expected IR fixtures;
- translator result evaluator;
- semantic accuracy metrics;
- CLI:
  - `nlreq benchmark-translation`.

Exit criteria:

- translator changes can be evaluated without running formal backends;
- false clarification and missed ambiguity are measured;
- corpus includes at least 100 cases before beta;
- every case has provenance and expected outcome.

Required ADR:

- ADR 0064: Requirement translation corpus, semantic accuracy, and
  clarification metrics.

### Phase 56 - Apalache Backend Production Integration

Purpose: make symbolic bounded TLA checking a reliable high-assurance producer.

Gap closed: TLA MVP exists, but not a production Apalache integration.

Scope:

- invoke Apalache through the model-checker runner;
- support invariant checks and bounded execution checks;
- parse Apalache outcomes;
- parse counterexamples into normalized format;
- record Apalache version, command, SMT options, bounds, and artifacts;
- map outcomes to evidence levels without overclaiming.

Deliverables:

- `ApalacheBackend`;
- Apalache result parser;
- Apalache counterexample normalizer;
- integration tests gated by tool availability;
- docs for local and CI installation.

Exit criteria:

- supported fixtures produce valid, counterexample, timeout, and unsupported
  outcomes;
- all BOUNDED_CHECKED results include bounds and command metadata;
- missing Apalache produces unsupported/tool-missing, not false success;
- producer registry recognizes Apalache as real only when metadata is complete.

Required ADR:

- ADR 0065: Apalache production backend, evidence mapping, and reproducibility.

### Phase 57 - TLC Backend Production Integration

Purpose: provide an explicit-state TLA backend alongside Apalache.

Gap closed: backend diversity is weak if only one real TLA execution path exists.

Scope:

- invoke TLC through the runner;
- generate `.cfg` files for supported specs;
- parse TLC success, invariant violation, deadlock, timeout, and configuration
  errors;
- normalize traces;
- compare TLC and Apalache overlap when both run.

Deliverables:

- `TlcBackend`;
- TLC parser;
- TLC counterexample normalizer;
- backend agreement fixtures;
- CI docs.

Exit criteria:

- TLC can check at least one supported fixture;
- TLC counterexamples map to the same normalized counterexample schema;
- Apalache/TLC agreement can be reported for overlapping fragments;
- TLC-specific unsupported conditions are explicit.

Required ADR:

- ADR 0066: TLC backend contract and explicit-state checking policy.

### Phase 58 - TLA Projection Semantics

Purpose: expand and specify the IR-to-TLA lowering semantics.

Gap closed: current lowering supports a narrow fragment. Real use needs a larger
documented subset and precise unsupported behavior.

Scope:

- define supported IR nodes for TLA projection;
- define temporal semantics for bounded obligations;
- define state, action, event, and invariant projection rules;
- define naming, module generation, config generation, and constants;
- define unsupported diagnostics.

Deliverables:

- TLA projection spec;
- lowering conformance tests;
- golden `.tla` outputs;
- unsupported diagnostics corpus;
- schema additions for projection metadata.

Exit criteria:

- every supported IR node has a documented lowering rule;
- unsupported nodes produce stable diagnostics;
- golden lowerings are byte-stable;
- Apalache and TLC backends consume the lowered artifacts.

Required ADR:

- ADR 0067: IR-to-TLA projection semantics.

### Phase 59 - Counterexample Normalization

Purpose: make formal failures actionable across backends.

Gap closed: current counterexamples exist but are not yet rich enough for product
debugging or cross-backend comparison.

Scope:

- define normalized counterexample trace schema;
- map backend states to IR nodes and source spans;
- identify violated invariant or obligation;
- include minimal reproducer command;
- support redaction for sensitive data;
- connect counterexamples to delta extraction.

Deliverables:

- counterexample schema;
- backend-specific parsers for Apalache and TLC;
- markdown renderer;
- delta extractor integration;
- benchmark fixtures.

Exit criteria:

- counterexample reports name requirement, source span, backend, command, and
  violated obligation;
- counterexamples are hash-linked to raw backend artifacts;
- product refusal surface embeds counterexample summaries;
- benchmark measures counterexample quality.

Required ADR:

- ADR 0068: Normalized counterexample traces and actionable refusal output.

### Phase 60 - Real `S and R` Composition

Purpose: check new requirement R against existing reviewed system spec S.

Gap closed: current system consistency is deterministic and marker/registry
based. The target requires actual composition.

Scope:

- define how system specs are selected from impact analysis;
- compose selected system spec S with requirement fragment R;
- generate combined TLA module or backend-specific composition artifact;
- preserve existing invariants;
- ask whether S and R is satisfiable without violating invariants;
- return valid, counterexample, timeout, unsupported, or needs-review.

Deliverables:

- composition artifact schema;
- `system-consistency-check`;
- combined TLA generator;
- invariant selection policy;
- fixtures for compatible and incompatible requirements.

Exit criteria:

- at least one non-toy system spec composes with a requirement;
- backend counterexample names the existing invariant violated;
- timeout is budgeted and explicit;
- closure gate consumes system consistency.

Required ADR:

- ADR 0069: `S and R` composition semantics and invariant preservation policy.

### Phase 61 - Proof-Level Evidence Boundary

Purpose: prevent bounded checks from being confused with inductive proof.

Gap closed: the taxonomy has `PROVEN_INDUCTIVE`, but no real proof-producing
integration or strict boundary.

Scope:

- define what counts as proof-level evidence;
- reserve TLAPS/Lean/Coq/Dafny proof integrations for proof-level evidence;
- mark proof obligations separately from bounded obligations;
- make bounded evidence insufficient where a policy requires proof;
- design proof artifact ingestion before implementing a full prover.

Deliverables:

- proof evidence policy;
- proof artifact schema;
- proof backend placeholder with strict unsupported behavior;
- closure policy tests for required proof-level evidence.

Exit criteria:

- no bounded result can satisfy a proof-required premise;
- proof-level evidence has a schema and producer contract;
- unsupported proof obligations produce unknown, not false refusal or success;
- future proof assistant integrations have a clear contract.

Required ADR:

- ADR 0070: Proof-level evidence boundary and inductive-proof producer policy.

### Phase 62 - Specula-Style Extraction Runner

Purpose: generate candidate formal specs for under-specified brownfield modules.

Gap closed: current spec extraction workbench is review-only and internal. The
target needs a real continuous extraction runner.

Scope:

- present affected code to an LLM/spec extractor through adapters;
- generate candidate formal specs;
- run syntax and structural checks;
- validate candidate specs against traces;
- mark candidates draft/unreviewed until human approval;
- never silently update reviewed specs.

Deliverables:

- extraction job schema;
- candidate spec schema;
- extractor prompt registry;
- validation pipeline;
- CLI:
  - `nlreq spec-extract-run`;
  - `nlreq spec-extract-validate`;
  - `nlreq spec-extract-promote`.

Exit criteria:

- a missing spec can produce a candidate spec and review task;
- candidate spec is rejected when traces do not match;
- reviewed spec promotion is explicit and hash-linked;
- closure gate blocks on unreviewed candidates.

Required ADR:

- ADR 0071: Specula-style extraction trust model and promotion workflow.

### Phase 63 - Code-To-Spec Manifest

Purpose: make coverage precise enough for brownfield requirements.

Gap closed: current spec coverage is registry-based and coarse.

Scope:

- map code modules, symbols, endpoints, events, and trace sources to spec
  modules;
- support many-to-many relationships;
- include confidence and reviewer status;
- include adapter-specific source locators without leaking them into IR;
- version the manifest.

Deliverables:

- manifest schema;
- migration from current registry;
- coverage evaluator;
- authoring guide;
- conformance tests.

Exit criteria:

- impact analysis can select spec modules through the manifest;
- missing mapping is a structured blocker;
- stale mapping is distinct from stale spec;
- manifest changes require review.

Required ADR:

- ADR 0072: Code-to-spec manifest and brownfield coverage semantics.

### Phase 64 - Spec Freshness Lockfile

Purpose: make spec freshness reproducible and CI-enforceable.

Gap closed: current drift checks exist, but do not yet behave like a formal
freshness lock.

Scope:

- compute hashes for code modules covered by each spec;
- record last successful trace validation and checker runs;
- record tool versions and command metadata;
- mark specs stale when code hashes change without revalidation;
- provide lockfile update command.

Deliverables:

- `spec-freshness.lock.json` schema;
- drift/freshness evaluator;
- CLI:
  - `nlreq spec-lock-check`;
  - `nlreq spec-lock-update`;
- CI examples.

Exit criteria:

- code changes stale the correct specs;
- successful validation refreshes lock entries;
- closure gate rejects stale specs;
- lockfile diffs are reviewable.

Required ADR:

- ADR 0073: Spec freshness lockfile and hash-based drift invariant.

### Phase 65 - Runtime Trace Extraction SDK

Purpose: make adapters produce real normalized traces instead of requiring
manually authored trace JSON.

Gap closed: trace schemas and replay exist, but real trace producers are
missing.

Scope:

- define trace producer SDK;
- define trace capture command contract;
- support adapters that wrap existing tools;
- validate trace producer metadata;
- add trace extraction to evidence producer mapping.

Deliverables:

- trace producer interface;
- command-runner based trace producer;
- trace source manifest;
- example Python trace producer;
- docs for adapter authors.

Exit criteria:

- at least one adapter extracts traces from an executable command;
- trace producer results include command, version, input hashes, and output
  hashes;
- trace extraction failure is explicit;
- trace replay consumes extracted traces without manual editing.

Required ADR:

- ADR 0074: Runtime trace extraction SDK and trace producer metadata.

### Phase 66 - Trace Normalization

Purpose: improve normalized traces for cross-runtime and cross-language use.

Gap closed: current normalized trace schema is useful but too shallow for
multi-language causal requirements.

Scope:

- support spans, events, state snapshots, state diffs, causality, clocks, actors,
  resources, and redaction metadata;
- support partial/lossy normalization warnings;
- support distributed trace ids and parent-child relationships;
- define minimum fields for formal replay;
- maintain backward compatibility or migration.

Deliverables:

- normalized trace schema;
- migration command;
- trace validation;
- trace replay;
- fixtures across Python, JavaScript, Solidity-like, and Go-like traces.

Exit criteria:

- lossy normalization is visible and blocks high-assurance trace claims where
  policy requires complete traces;
- cross-language trace stitching can use causal fields;
- existing v1 traces can be migrated or rejected with clear next actions;
- schemas and docs are updated.

Required ADR:

- ADR 0075: Normalized trace schema and lossy-normalization policy.

### Phase 67 - Solidity Adapter

Purpose: add a production transaction/event-oriented adapter.

Gap closed: current adapters do not cover the smart-contract/on-chain domain
that motivated much of the discussion.

Scope:

- parse Solidity project manifests;
- resolve symbols through compiler artifacts and/or static analysis;
- extract call graphs and event emitters;
- present canonical source/context for spec extraction;
- extract traces through Foundry/debug traces where available;
- emit normalized traces.

Deliverables:

- Solidity source adapter;
- Solidity trace producer;
- Solidity conformance fixtures;
- sample project fixture;
- adapter docs.

Exit criteria:

- adapter passes source conformance suite;
- resolves overloaded or ambiguous functions safely;
- trace extraction can capture function calls, events, reverts, and state-change
  summaries;
- requirement gate can close or refuse over a Solidity fixture.

Required ADR:

- ADR 0076: Solidity adapter scope, tooling, and trace semantics.

### Phase 68 - Go Adapter

Purpose: add a production compiled service adapter.

Gap closed: language agnosticism remains weak until a non-dynamic, compiled,
service-oriented ecosystem is supported.

Scope:

- parse Go module manifests;
- use Go tooling for symbol resolution;
- build call graphs;
- present canonical package/function context;
- extract traces through tests, runtime traces, or OpenTelemetry;
- normalize goroutine/thread/service metadata.

Deliverables:

- Go source adapter;
- Go trace producer;
- Go conformance fixtures;
- sample service fixture;
- docs.

Exit criteria:

- adapter passes conformance;
- call graph is stable over fixtures;
- trace producer emits normalized traces with causality where available;
- requirement gate can use Go impact and traces.

Required ADR:

- ADR 0077: Go adapter scope, tooling, and runtime trace semantics.

### Phase 69 - TypeScript Adapter

Purpose: support frontend and Node service requirements.

Gap closed: JavaScript source adapter exists, but production TypeScript needs
type-aware symbol and call graph behavior.

Scope:

- parse TypeScript project manifests;
- use TypeScript compiler API or language service;
- resolve types, symbols, exports, and imports;
- represent async/event-loop traces;
- support frontend route/component mapping where possible.

Deliverables:

- TypeScript adapter;
- TypeScript trace producer;
- fixture with Node service or frontend flow;
- typed call graph tests;
- docs.

Exit criteria:

- adapter passes conformance;
- type-aware resolution handles exported symbols and overload-like patterns;
- async trace metadata is normalized;
- cross-language demo can include TypeScript as a participant.

Required ADR:

- ADR 0078: TypeScript adapter and async trace normalization policy.

### Phase 70 - Rust Or Java Adapter

Purpose: pressure-test the adapter contract with a third materially different
ecosystem.

Gap closed: two production adapters can still accidentally fit one narrow shape.
A third ecosystem validates the interface.

Scope:

- choose Rust or Java based on target demo value;
- implement manifest parsing, symbol resolution, call graph, presentation, and
  trace extraction;
- compare conformance behavior against existing adapters;
- record interface changes required by the third ecosystem.

Deliverables:

- Rust or Java adapter;
- adapter selection note;
- conformance fixtures;
- interface-change report.

Exit criteria:

- third ecosystem passes conformance without language-specific IR leakage;
- any needed interface changes are documented and migrated;
- benchmark includes at least one case for the third ecosystem.

Required ADR:

- ADR 0079: Third production adapter selection and interface pressure-test.

### Phase 71 - Adapter Certification Suite

Purpose: make adapter validity externally testable.

Gap closed: conformance tests exist, but external adapter authors need a formal
certification suite and versioned compatibility levels.

Scope:

- define adapter capability levels:
  - static-only;
  - trace-producing;
  - spec-extraction-ready;
  - gate-ready;
  - cross-language-ready;
- publish fixtures and expected outputs;
- add certification reports;
- add semantic compatibility tests for normalized traces and impact analysis.

Deliverables:

- certification schema;
- `nlreq adapter-certify`;
- fixture suite;
- compatibility matrix;
- adapter authoring guide.

Exit criteria:

- each built-in adapter has a certification report;
- unsupported capabilities are explicit;
- external adapters can run the suite without private test infrastructure;
- gate policies can require capability levels.

Required ADR:

- ADR 0080: Adapter certification levels and conformance suite.

### Phase 72 - Cross-Language Proof Object

Purpose: close one proof object over evidence from multiple programming
language adapters.

Gap closed: the agnostic wedge exists, but true cross-language requirement
closure is still limited.

Scope:

- represent multi-adapter premises in dispatch plans;
- combine impact, traces, and coverage from multiple adapters;
- stitch causal traces across systems;
- allow adapter-specific evidence while preserving one IR spine;
- detect missing cross-system links.

Deliverables:

- proof object;
- cross-language dispatch plan;
- causal trace stitching report;
- cross-language closure gate policy;
- benchmark case.

Exit criteria:

- one requirement spanning at least two adapters can close;
- one missing cross-language premise refuses with source-span and trace context;
- proof object records which adapter discharged each premise;
- no adapter-specific facts leak into semantic IR.

Required ADR:

- ADR 0081: Cross-language proof object and causal evidence aggregation.

### Phase 73 - Evidence Artifact Store

Purpose: make evidence replayable after the CLI process exits.

Gap closed: artifacts are hash-linked, but not yet managed as a retention system.

Scope:

- define artifact store layout;
- support local filesystem store first;
- record raw and normalized artifacts;
- support garbage collection policy;
- support artifact lookup by hash;
- support export bundles.

Deliverables:

- artifact store schema;
- storage API;
- `nlreq artifact-put`;
- `nlreq artifact-get`;
- export bundle format;
- retention docs.

Exit criteria:

- final reports can resolve every artifact hash through the store;
- raw backend logs and normalized reports are both retained;
- benchmark runs can be reproduced from exported bundles;
- artifact missing is a first-class integrity failure.

Required ADR:

- ADR 0082: Evidence artifact store, retention, and replay bundle format.

### Phase 74 - Signed Evidence And Producer Attestation

Purpose: harden high-assurance evidence against forgery and tampering.

Gap closed: producer validation checks metadata but not signatures or strong
attestation.

Scope:

- sign evidence artifacts;
- sign producer mapping releases;
- record producer identity and key material policy;
- support local developer mode without signatures at low assurance;
- require signatures for high-assurance CI mode.

Deliverables:

- signed evidence envelope schema;
- signing/verification commands;
- producer key registry;
- CI policy examples;
- migration docs.

Exit criteria:

- high-assurance evidence can require signature verification;
- tampered artifacts fail verification;
- unsigned local evidence is labeled appropriately;
- proof closure records signature status.

Required ADR:

- ADR 0083: Signed evidence envelopes and producer attestation policy.

### Phase 75 - CI And PR Action Gate

Purpose: make the closure gate usable in normal engineering workflows.

Gap closed: CLI exists, but product adoption requires CI and PR integrations.

Scope:

- GitHub Actions workflow examples;
- PR comment renderer;
- required-check mode;
- report-only mode;
- soft-gate and hard-gate policy;
- artifact upload/download;
- failure summaries.

Deliverables:

- reusable GitHub Action;
- CI docs;
- PR markdown renderer;
- sample policies;
- adoption guide.

Exit criteria:

- repository can run requirement gate in report-only mode;
- repository can enable hard gate for selected requirement classes;
- PR comments include accepted/refused/unknown summaries and next actions;
- artifacts are uploaded and hash-linked.

Required ADR:

- ADR 0084: CI/PR action gate, report-only adoption, and hard-gate policy.

### Phase 76 - Benchmark Evaluation

Purpose: move from seed corpus to serious public evaluation.

Gap closed: Phase 45 corpus is small and illustrative.

Scope:

- expand to at least 250 cases;
- include real-world rewritten requirements where possible;
- include brownfield, greenfield, cross-language, timeout, drift, trace, backend
  disagreement, translator ambiguity, and contradiction cases;
- define stable train/test split if LLM translators are used;
- publish benchmark methodology.

Deliverables:

- benchmark corpus;
- benchmark methodology doc;
- benchmark runner improvements;
- public results format;
- regression dashboard data format.

Exit criteria:

- false closure rate is tracked and budgeted;
- benchmark detects regressions in translation, formal checking, traces, and
  adapters separately;
- every phase after this must include benchmark impact;
- public docs explain what the benchmark does and does not prove.

Required ADR:

- ADR 0085: Benchmark evaluation methodology and regression policy.

### Phase 77 - Performance And Caching

Purpose: make the tool fast enough for developer workflows.

Gap closed: real backends and trace extraction can be expensive.

Scope:

- cache parser, impact, lowering, backend, trace, and proof artifacts;
- key cache by input hashes and tool versions;
- support incremental re-checks;
- define cache invalidation;
- record cache hits in reports without weakening evidence.

Deliverables:

- cache schema;
- cache API;
- performance benchmarks;
- invalidation tests;
- docs.

Exit criteria:

- repeated gate runs reuse safe artifacts;
- cache never reuses artifacts across changed inputs or changed tool versions;
- reports disclose cache usage;
- benchmark tracks runtime improvements.

Required ADR:

- ADR 0086: Verification cache, invalidation, and evidence disclosure policy.

### Phase 78 - Policy And Waiver Governance

Purpose: support real adoption without normalizing unsafe bypasses.

Gap closed: gates need controlled exceptions for unknown and staged adoption.

Scope:

- define policy language for required evidence levels by requirement class;
- define waiver categories and expiration;
- require reviewer approval for waivers;
- disallow waivers for false-closure risks in hard-gate mode;
- make waiver use visible in reports and metrics.

Deliverables:

- policy schema;
- waiver schema;
- policy evaluator;
- waiver audit report;
- docs.

Exit criteria:

- waivers cannot silently make a blocked proof appear closed;
- expired waivers fail;
- closure report shows every waiver used;
- benchmark can measure waiver-dependent outcomes.

Required ADR:

- ADR 0087: Gate policy, waiver governance, and exception audit semantics.

### Phase 79 - Threat Model And TCB Audit

Purpose: name the trusted computing base and attack surfaces.

Gap closed: current docs discuss trust locally, but not as one end-to-end threat
model.

Scope:

- identify TCB components:
  - parser;
  - IR validator;
  - translator prompts;
  - formal backend adapters;
  - source adapters;
  - trace producers;
  - artifact store;
  - producer registry;
  - CI gate;
- analyze spoofing, tampering, replay, prompt injection, stale specs, forged
  evidence, and malicious adapters;
- define mitigations and residual risks.

Deliverables:

- threat model doc;
- TCB inventory;
- security checklist;
- red-team benchmark cases;
- audit-ready architecture diagrams.

Exit criteria:

- every high-assurance claim lists TCB assumptions;
- malicious adapter and tampered evidence scenarios are tested;
- prompt injection through requirement text is handled or explicitly out of
  scope;
- conclusion release has a security review checklist.

Required ADR:

- ADR 0088: Threat model, TCB boundary, and adversarial evidence policy.

### Phase 80 - Reference Brownfield Demo

Purpose: prove the system on one credible real codebase.

Gap closed: fixtures and synthetic benchmarks are not enough for credibility.

Scope:

- select a brownfield demo system;
- create or import reviewed formal specs;
- run impact, spec coverage, trace extraction, formal checking, proof closure,
  and CI gate;
- include at least one accepted requirement and one refused requirement with
  counterexample or trace mismatch;
- publish reproducible instructions.

Deliverables:

- reference demo repo or subdirectory;
- demo requirements;
- system specs;
- trace capture scripts;
- expected reports;
- walkthrough doc.

Exit criteria:

- new contributor can reproduce the demo locally;
- demo includes real code, real traces, and real formal backend output;
- demo has no hidden manual artifact edits;
- public benchmark includes demo-derived cases.

Required ADR:

- ADR 0089: Reference brownfield demo selection and reproducibility contract.

### Phase 81 - Public Documentation And SDK

Purpose: make external adoption possible.

Gap closed: internal docs exist, but not enough for adapter authors or
integrators.

Scope:

- publish getting-started guide;
- publish adapter SDK guide;
- publish formal backend guide;
- publish evidence producer guide;
- publish benchmark guide;
- publish API reference;
- publish troubleshooting guide.

Deliverables:

- docs site or docs directory overhaul;
- SDK examples;
- template adapter;
- template formal backend;
- example CI workflows;
- release notes.

Exit criteria:

- external user can run seed benchmark;
- external user can implement a static-only adapter from docs;
- external user can interpret accepted/refused/unknown reports;
- docs are versioned with schemas.

Required ADR:

- ADR 0090: Public SDK, documentation versioning, and external integration
  contract.

### Phase 82 - Conclusion Release Certification

Purpose: make a final readiness decision against the conclusion definition.

Gap closed: the program needs a formal stop condition.

Scope:

- run all unit, integration, benchmark, and demo checks;
- audit every conclusion criterion;
- publish known limitations;
- publish evidence-level claims;
- freeze schemas for the conclusion release;
- tag release.

Deliverables:

- conclusion certification report;
- release checklist;
- benchmark results;
- TCB audit summary;
- public limitations doc;
- release tag.

Exit criteria:

- every conclusion criterion is passed or explicitly scoped out;
- false closure rate on public benchmark is zero for hard-gated cases;
- all high-assurance evidence is producer-validated;
- reference demo reproduces;
- docs and schemas are consistent;
- release is tagged.

Required ADR:

- ADR 0091: Conclusion release criteria, certification process, and public claim
  boundaries.

## ADR Backlog

The following ADRs are still needed after ADR 0054:

| ADR | Title | Phase |
|---:|---|---:|
| 0055 | Conclusion definition, release bars, and evidence-label discipline | 46 |
| 0056 | Free-form intake, controlled rewrite, and approval semantics | 47 |
| 0057 | Controlled requirement DSL v3 grammar and canonical form | 48 |
| 0058 | Requirement review, approval hash binding, and self-audit policy | 49 |
| 0059 | Product refusal taxonomy and source-span iteration loop | 50 |
| 0060 | Multi-pass translator workbench and untrusted candidate policy | 51 |
| 0061 | Bidirectional provenance graph and clarification protocol | 52 |
| 0062 | Logical translator agreement and equivalence hierarchy | 53 |
| 0063 | Requirement contradiction taxonomy and self-consistency semantics | 54 |
| 0064 | Requirement translation corpus and semantic accuracy metrics | 55 |
| 0065 | Apalache production backend and evidence mapping | 56 |
| 0066 | TLC backend contract and explicit-state checking policy | 57 |
| 0067 | IR-to-TLA projection semantics | 58 |
| 0068 | Normalized counterexample traces and refusal output | 59 |
| 0069 | `S and R` composition semantics and invariant preservation | 60 |
| 0070 | Proof-level evidence boundary and inductive-proof producer policy | 61 |
| 0071 | Specula-style extraction trust model and promotion workflow | 62 |
| 0072 | Code-to-spec manifest and brownfield coverage semantics | 63 |
| 0073 | Spec freshness lockfile and hash-based drift invariant | 64 |
| 0074 | Runtime trace extraction SDK and trace producer metadata | 65 |
| 0075 | Normalized trace schema and lossy-normalization policy | 66 |
| 0076 | Solidity adapter scope, tooling, and trace semantics | 67 |
| 0077 | Go adapter scope, tooling, and runtime trace semantics | 68 |
| 0078 | TypeScript adapter and async trace normalization policy | 69 |
| 0079 | Third production adapter selection and interface pressure-test | 70 |
| 0080 | Adapter certification levels and conformance suite | 71 |
| 0081 | Cross-language proof object and causal evidence aggregation | 72 |
| 0082 | Evidence artifact store, retention, and replay bundle format | 73 |
| 0083 | Signed evidence envelopes and producer attestation policy | 74 |
| 0084 | CI/PR action gate, report-only adoption, and hard-gate policy | 75 |
| 0085 | Benchmark evaluation methodology and regression policy | 76 |
| 0086 | Verification cache, invalidation, and evidence disclosure policy | 77 |
| 0087 | Gate policy, waiver governance, and exception audit semantics | 78 |
| 0088 | Threat model, TCB boundary, and adversarial evidence policy | 79 |
| 0089 | Reference brownfield demo selection and reproducibility contract | 80 |
| 0090 | Public SDK, documentation versioning, and external integration contract | 81 |
| 0091 | Conclusion release criteria, certification process, and public claim boundaries | 82 |

## Dependency Map

Hard dependencies:

- Phase 47 depends on Phase 46.
- Phase 48 depends on Phase 47 if grammar changes affect controlled rewrite.
- Phase 51 depends on Phases 47-50.
- Phase 52 depends on Phase 51.
- Phase 53 depends on Phase 52.
- Phase 54 depends on Phase 48 and Phase 52.
- Phase 56 depends on current model-checker runner and TLA MVP.
- Phase 58 depends on Phases 56 and 57.
- Phase 60 depends on Phases 56, 58, 59, 63, and 64.
- Phase 62 depends on source adapters and trace validation.
- Phase 64 depends on Phase 63.
- Phase 66 depends on Phase 65.
- Phases 67-70 depend on Phase 71 certification definitions, but early adapter
  work can prototype before certification is frozen.
- Phase 72 depends on at least two production adapters and trace normalization.
- Phase 74 depends on Phase 73.
- Phase 75 depends on Phase 50, Phase 73, and Phase 78.
- Phase 76 should begin early but cannot stabilize until Phases 51-72 provide
  real cases.
- Phase 80 depends on Phases 60, 64, 65, 67 or 68, 73, and 75.
- Phase 82 depends on all previous phases.

Parallelizable tracks:

- Translator work (47-55) can run in parallel with formal backend work (56-61).
- Brownfield grounding (62-66) can run in parallel with adapter work (67-71).
- Evidence integrity (73-74) can begin once artifact shapes stabilize.
- Benchmark expansion (76) should continuously absorb fixtures from all tracks.

## Minimum Viable Conclusion Cut

If scope must be reduced, the minimum credible conclusion is:

- Phases 46-56;
- Phase 58;
- Phase 59;
- Phase 60;
- Phases 63-66;
- two production adapters from Phases 67-70;
- Phase 71;
- Phase 73;
- Phase 75;
- Phase 76;
- Phase 79;
- Phase 80;
- Phase 82.

This cut defers:

- TLC as second TLA backend;
- proof-level inductive evidence;
- signed evidence;
- full waiver governance;
- public SDK polish.

It cannot defer:

- safe intake;
- real formal backend;
- real `S and R` composition;
- spec freshness;
- real trace extraction;
- at least two real adapters;
- benchmark expansion;
- reference brownfield demo;
- threat model.

## Evidence Label Policy For Remaining Phases

Rules:

- `STATICALLY_RESOLVED` may be produced by source adapters and static symbol
  tools.
- `TYPE_CHECKED` may be produced by type/schema/interface adapters.
- `TEST_VALIDATED` may be produced by reproducible test runners.
- `TRACE_VALIDATED` may be produced only by registered trace producers plus
  trace replay/validation reports.
- `CONSISTENCY_CHECKED` may be produced by deterministic or SMT-backed
  consistency engines, but the report must name which one.
- `SMT_CHECKED` requires a real SMT solver invocation or proof object with
  command metadata.
- `BOUNDED_CHECKED` requires a real bounded checker run with bounds.
- `PROVEN_INDUCTIVE` requires a real proof-producing backend.
- LLM output alone produces no assurance level.

Any phase that changes this policy must update ADR 0055 or create a successor
ADR.

## Benchmark Expansion Requirements

Before Phase 82, the public benchmark must include:

- at least 250 total cases;
- at least 50 accepted cases;
- at least 50 refused cases;
- at least 30 unknown cases;
- at least 25 translation ambiguity cases;
- at least 25 self-contradiction cases;
- at least 25 trace mismatch cases;
- at least 15 backend disagreement cases;
- at least 15 stale spec cases;
- at least 10 timeout or budget exhaustion cases;
- at least 20 real-adapter cases;
- at least 10 cross-language cases;
- at least one reference brownfield demo subset.

Benchmark metrics required:

- closure rate;
- false closure rate;
- false refusal rate;
- unknown correctness rate;
- semantic translation accuracy;
- clarification usefulness;
- counterexample quality;
- trace grounding quality;
- adapter conformance coverage;
- runtime p50/p95;
- cache hit rate;
- waiver use rate.

## Release Readiness Checklist

Before declaring conclusion:

- all schemas regenerate with no drift;
- all phase docs exist;
- all ADRs 0055-0091 exist and are accepted/proposed consistently;
- all built-in adapters have certification reports;
- all high-assurance producers are registered;
- artifact store can replay a full gate run;
- public benchmark evaluation passes with zero false closures in hard-gated cases;
- reference brownfield demo reproduces from clean checkout;
- threat model is reviewed;
- CI action gate can run in report-only and hard-gate mode;
- docs explain evidence labels and limitations clearly;
- release tag includes benchmark results and certification report.

## Final Product Statement

At conclusion, the project should be describable in one grounded paragraph:

```text
The NL Attestation Layer is a programming-language-agnostic requirement gate. It
takes human requirements, forces ambiguous language into approved controlled
form, translates the approved requirement into compositional IR, checks the
requirement against itself, checks it against the current reviewed system specs,
grounds it against affected source modules and runtime traces, aggregates
evidence from real registered producers, and allows downstream engineering
actions only when the proof object closes. When it refuses or cannot decide, it
returns precise source-grounded next actions instead of vague review comments.
```

That statement is the bar for Phase 82.
