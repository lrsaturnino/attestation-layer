# Gap-Closure Plan C — Source Adapters & Verticals (the codebase grounding)

**Date (UTC):** 2026-06-03 · **Status:** Implementation spec, v2 (task-level, decisions inline)
**Pillar:** C of 3 (parallel capability pillars). Companions: `gap-closure-plan-A-translation-and-intake.md`, `gap-closure-plan-B-system-consistency-and-formal-backends.md`.
**Closes gaps (from `docs/vision-gap-spec.md`):** GAP-C2, GAP-C3, GAP-B4, GAP-B5, GAP-B6, GAP-X3; the **programming-language axis of GAP-X5 + the cross-language capstone**; extends GAP-C1. (GAP-X5 tri-axis: NL → Plan A; formal-language → Plan B; programming-language + capstone → this plan.)
**Supersedes for this pillar:** phases 21, 24, 35–39, 62–72, 131–149, 164–185 (which built the capability contract + regex stand-ins).
**First verticals (user-selected, 1+2):** **Solidity** (Slither + Foundry — both installed on this machine) and **Go** (gopls/go-callgraph + runtime/trace + Specula).
**Format:** each work item is a full task spec — **Decision (inline)** (no separate ADR files), **Touches**, **Changes**, **Tasks** (`PC-n.Tk`), **Tests**, **Acceptance (real-evidence)**, **Depends on**. Research-grade items carry **Spike** + **Decision gate**.

---

## 0. Shared context & integration contract (identical across Plans A/B/C)

**Central finding driving all three plans.** The repository implements the *shape* of the vision to high quality — the compositional IR spine, the adapter capability contract, the 9-level evidence taxonomy, the immutable package format, the refusal/gating surface, and the proof-object closure schema all exist. What does not exist is the *verification muscle* behind those contracts. Three load-bearing components are simulated, structural-only, or absent:

- The **NL→formal translator** has no LLM and lowers every predicate to `TRUE` in the TLA path (`translator.py:223`, `_tla_skeleton`) → tautology (`metadata={"evidence":"not_checked"}`). The structural `FormalClaim` lowering (`formal_claim.py:145`) is real but is a canonical-string serialization that does not reach a backend.
- The **`S ∧ R` system-consistency check** runs by marker-grep (`system_checker.py:94`) and composes `SystemSpecAssumptions == TRUE` (`system_checker.py:314`) so `S` is never conjoined.
- The **source adapters** for all seven languages are regex stand-ins (`production_source_adapters.py`, `analysis:"regex-static"`) that ingest externally-supplied traces.

**Therefore every task is "wire a real producer behind an existing contract," not "add representation."** New schema/report surface is out of scope unless a real producer needs it.

**Strategy: three parallel capability pillars, integrated at frozen contracts.** Integration risk is controlled by freezing the cross-pillar contracts first (SP1) and never changing them mid-flight without a joint version bump.

**The five cross-pillar contracts (freeze at SP1):**

| Contract artifact | Source file | Producer → Consumer | Role |
|---|---|---|---|
| `RequirementIRV2` / `SemanticNode` | `models.py`, `compositional_ir.py` | A owns → all | The IR spine. |
| `FormalClaim` | `formal_claim.py` | **A produces → B consumes** | The translated requirement a backend checks. *Today: gate-stage only (`end_to_end_gate.py:54`).* |
| `SystemSpecRegistry` / `SystemSpecEntry` | `system_spec.py` | **C populates → B consumes** | Coverage + the verified spec `S`. |
| `NormalizedTraceArtifact` | `trace_normalization.py` | **C produces → A/B consume** | Real code-execution traces for grounding. |
| `ProofObject` | `proof_closure.py` | **A+B+C aggregate** | The convergence; closure gates downstream action. |

**Synchronization points:** **SP1 — Contract freeze** (version + freeze the five contracts; each decision is recorded inline in the owning task, not a separate ADR; gate: every pillar compiles against frozen contracts with a stub on the other side). **SP2 — Independent real evidence** (A = a non-vacuous lowering Z3 discharges; B = a real Apalache `S ∧ R` counterexample; C = a real Slither call graph + a real Foundry trace). **SP3 — Capstone** (one real requirement spanning two languages closes one `ProofObject` that gates action — "the loop closes").

**Discipline (do not regress):** evidence-level non-conflation (`BOUNDED_CHECKED` ≠ `PROVEN_INDUCTIVE`), byte-stable golden outputs, hashed reproducibility metadata, refusal-with-source-span over silent acceptance, LLM-as-untrusted. Fixed evidence levels: `TYPE_CHECKED, CONSISTENCY_CHECKED, STATICALLY_RESOLVED, SMT_CHECKED, TEST_VALIDATED, TRACE_VALIDATED, BOUNDED_CHECKED, PROVEN_INDUCTIVE, REVIEWED`.

**Effort tiers:** [S] days · [M] 1–2 wks · [L] multi-wk · [R] research (spike first). **FIX** = correctness repair (sequence first). **Numbering:** items `PC-n`; tasks `PC-n.Tk`; phase numbers 193+ on scheduling; **all design decisions are inline — no separate ADR files.**

---

## 1. Pillar C scope
Graduate two language adapters from regex stand-ins to real tool-backed verticals (Solidity, Go), so the system can answer "what does this requirement touch?", "is that code formally specified and fresh?", and "do the real code's traces satisfy the requirement?" — populating the `SystemSpecRegistry` and `NormalizedTraceArtifact` contracts Pillar B consumes, and delivering the cross-language capstone (X5).

## 2. Current empirical state

**Direct answer to "do we have TypeScript / Python / Rust in place?":** Yes — and Go, Java, Solidity, JavaScript too. All seven exist as `RegexProductionSourceAdapter` subclasses (`production_source_adapters.py:282–453`) conforming to the v2.0 capability contract. But all are regex stand-ins → *graduation candidates*, not real verticals.

| Area | State | Evidence |
|---|---|---|
| `LanguageAdapter` interface (v2.0) | Real — preserve & extend | `source_adapter.py:111` `AdapterCapabilityContract`: `resolve_symbol`/`call_graph`/`extract_traces`/`present_to_llm`/`parse_manifest`/`capability_contract` |
| Capability ladder | Defined; **mislabeled in use** | `source_adapter.py:15` `manifest_only → static_resolution → trace_capable → production_candidate`; all regex adapters claim the top rung while doing only `regex-static` |
| 7 language adapters | **Regex/lexical** | `production_source_adapters.py`; `call_graph` → `analysis:"regex-static"`; `extract_traces` *ingests* supplied JSON from `module.trace_sources` (`:157`); `present_to_llm` returns raw snippets |
| Real ecosystem tooling | **Not driven** | Slither (`~/.local/bin/slither`) + Foundry (`~/.foundry/bin/forge`) installed but unused; no gopls/rust-analyzer/tsserver; Solidity limitations mark inheritance "static depth" + "external trace producer" (`production_source_adapters.py:297,303`) |
| NormalizedTrace | Schema real; not produced | `trace_normalization.py`; populated only by ingestion |
| Impact analysis | Declaration/author-driven | `impact.py`/`source_impact.py`/`routing.py` globs; no call-graph-derived set |
| Spec coverage + Specula | **Plumbing only; candidate is vacuous** | `coverage_alignment.py`/`spec_freshness.py`; `_candidate_tla_content` emits `CandidateInvariant == TRUE` (`spec_extraction.py:359`) |
| Code↔spec trace validation | Different question | `trace_validation.py` validates traces vs claims; not Specula-style "spec reproduces the binary's traces" |
| Continuous freshness | Rollups only | `continuous.py`/`spec_drift.py` hashing; no commit-triggered re-validation against `S` |
| Cross-language wedge | Schema only | `cross_language.py`/`system_composition.py`; no real two-language unified proof |

## 3. Work breakdown

### PC-1 · Honest capability level — [FIX, S] — GAP-C1
**Decision (inline).** Demote regex adapters from `production_candidate` to `static_resolution` (they resolve statically, do not extract traces, do not drive real tools). Reserve `trace_capable`/`production_candidate` for adapters that pass the conformance suite **with recorded real-tool evidence** (a captured tool version + a real artifact hash). The conformance/certification suite enforces the gate.
**Touches.** `production_source_adapters.py:56` (`capability_level`); `source_conformance.py`; `adapter_certification.py`.
**Tasks.** `PC-1.T1` set regex adapters to `static_resolution`; `PC-1.T2` conformance asserts a `trace_capable` claim requires a recorded trace producer + tool-version evidence.
**Tests.** `tests/test_source_adapter_conformance.py`: a regex adapter claiming `trace_capable` without trace evidence fails certification.
**Acceptance.** No adapter claims a capability it cannot evidence.
**Depends on.** none.

### PC-2 · Freeze C-side contracts for SP1 — [NEW, S] — GAP-C3, B1
**Decision (inline).** Version and freeze `NormalizedTraceArtifact`, `SystemSpecEntry` (incl. the `init_op`/`next_op`/`invariants` fields PB-1 adds), and the `call_graph`/`source_impact` output shapes as the frozen B↔C / A↔C contracts. Lossy-trace-normalization rules (EVM vs Go) are documented inline on `NormalizedTrace` (PC-3/PC-7 populate them).
**Touches.** `trace_normalization.py`; `system_spec.py`; `source_impact.py`.
**Tasks.** `PC-2.T1` version-stamp + freeze the three schemas; `PC-2.T2` publish a C-side stub so Pillar B compiles against frozen `SystemSpecRegistry`+`NormalizedTrace`.
**Tests.** schema-drift test: the frozen schemas match committed JSON Schemas.
**Acceptance.** Pillar B builds against frozen C contracts with a stub.
**Depends on.** coordinate with PB-1 (the `SystemSpecEntry` field additions).

### PC-3 · Solidity symbol resolution + call graph via Slither — [NEW, L] — GAP-C2, B4
**Decision (inline).** `SoliditySourceAdapter.resolve_symbol`/`call_graph` are backed by Slither (`slither <target> --json -`), giving inheritance-aware resolution and a real call graph — resolving `solidity-overload-ambiguity` + `solidity-inheritance-static-depth` (`production_source_adapters.py:291,297`). Slither runs as a pinned subprocess (like the model-checker harness); ambiguous resolution → `REFUSED_UNBOUND_SYMBOLS`. Regex stays as a fallback only when Slither is unavailable, and then the adapter reports `static_resolution`, not `trace_capable`.
**Touches.** `production_source_adapters.py:282` `SoliditySourceAdapter`; new `slither_client.py` (subprocess + JSON parse).
**Tasks.** `PC-3.T1` `slither_client` (pinned, version-recorded, JSON parse); `PC-3.T2` Slither-backed `resolve_symbol` across inheritance; `PC-3.T3` Slither-backed `call_graph`; `PC-3.T4` ambiguous → `REFUSED_UNBOUND_SYMBOLS`.
**Tests.** against a checked-in small Solidity project with inheritance + overloads: an inherited/overloaded symbol resolves correctly; the call graph matches Slither's; Slither absent → `static_resolution` + recorded skip-reason.
**Acceptance (SP2-C, part 1).** A real Slither call graph for an inherited/overloaded symbol — not regex edges.
**Depends on.** PC-1, PC-2.

### PC-4 · Solidity trace extraction via Foundry — [NEW, L] — GAP-C2, C3, B6
**Decision (inline).** `extract_traces` runs `forge test --json` / `cast run` / `debug_traceTransaction` and normalizes call paths, revert/success, emitted events, and decoded params into `NormalizedTraceArtifact` — resolving `solidity-external-trace-producer` (`:303`). The adapter *produces* traces; it no longer depends on pre-supplied JSON. Lossy-normalization rules (opcode-level → call-level) documented on the schema (PC-2).
**Touches.** `production_source_adapters.py` `extract_traces` (`:155`); new `foundry_client.py`.
**Tasks.** `PC-4.T1` `foundry_client` (run + parse traces, pinned); `PC-4.T2` EVM→`NormalizedTrace` projection; `PC-4.T3` events/params/reverts mapped to `TraceEvent` fields.
**Tests.** a real `forge test` populates a `NormalizedTraceArtifact` the adapter produced; the trace answers a sample claim (event emitted before state change).
**Acceptance (SP2-C, part 2).** A real Foundry-extracted normalized trace, not ingested JSON.
**Depends on.** PC-1, PC-2.

### PC-5 · Solidity Specula-equivalent — [NEW, L, R] — GAP-B5
**Decision (inline).** Slither + LLM (Pillar A's `LlmClient`) + trace validation (PC-4) extract candidate TLA+/SMT `S` for a Solidity module — **replacing the vacuous `CandidateInvariant == TRUE` placeholder (`spec_extraction.py:359`) with real extracted invariants**. The trace-validation guard is mandatory: a candidate `S` is promotable to `reviewed` only if it reproduces real Foundry traces (`claude-convo.md:118,150`). Candidates land in `SystemSpecRegistry` as `draft` for human promotion.
**Open question.** Can an LLM, gated by trace validation, extract invariants that are both non-trivial and trace-reproducing for a real contract — or does it reproduce the whitepaper, not the code? Unknown without building it (the vision flags Solidity Specula as not existing publicly).
**Spike.** On one tBTC contract: extract candidate invariants, run them against real Foundry traces, hand-label trace-reproducing vs. paper-only.
**Decision gate.** Proceed only if ≥1 non-trivial, trace-reproducing invariant is extractable and the guard rejects paper-only candidates; else keep `S` hand-written (PB-5) and revisit.
**Touches.** `spec_extraction.py:359` `_candidate_tla_content`; `slither_client.py`; `llm_client.py`; `trace_replay.py`.
**Depends on.** PC-3, PC-4, PA-4.

### PC-6 · Go symbol resolution + call graph — [NEW, L] — GAP-C2, B4
**Decision (inline).** Implement `GoSourceAdapter.resolve_symbol`/`call_graph` over `gopls` + `golang.org/x/tools/go/callgraph` (pinned subprocess). Regex fallback → `static_resolution` only.
**Touches.** `production_source_adapters.py:322` `GoSourceAdapter`; new `go_client.py`.
**Tasks.** `PC-6.T1` `go_client` (gopls/callgraph, pinned); `PC-6.T2` real `resolve_symbol`; `PC-6.T3` real `call_graph`.
**Tests.** symbols + call graph for a real Go package (e.g., a keep-core off-chain component) match the tool output.
**Acceptance.** A real Go call graph, not regex.
**Depends on.** PC-1, PC-2.

### PC-7 · Go trace extraction — [NEW, L] — GAP-C3, B6
**Decision (inline).** `extract_traces` over `runtime/trace` + OpenTelemetry → `NormalizedTraceArtifact`, preserving goroutine/interleaving metadata in `TraceEvent.metadata`. Lossy-normalization rules (runtime trace → call-level) documented on the schema.
**Touches.** `production_source_adapters.py` Go `extract_traces`; `go_client.py`.
**Tasks.** `PC-7.T1` capture `runtime/trace`; `PC-7.T2` Go→`NormalizedTrace` projection; `PC-7.T3` goroutine metadata preserved.
**Tests.** a real Go execution populates the trace artifact; goroutine info survives normalization.
**Acceptance.** A real Go-extracted normalized trace.
**Depends on.** PC-6, PC-2.

### PC-8 · Wire Specula for Go `S` extraction — [NEW, M] — GAP-B5
**Decision (inline).** Specula already works for Go; integrate it to produce candidate `S` for Go modules under the same trace-validation-guarded review/promote flow as PC-5 — likewise replacing the shared vacuous `CandidateInvariant == TRUE` (`spec_extraction.py:359`) with real extracted invariants.
**Touches.** `spec_extraction.py`; `go_client.py`; `trace_replay.py`.
**Tasks.** `PC-8.T1` Specula→candidate `S` for Go; `PC-8.T2` trace-validation guard; `PC-8.T3` draft→reviewed promotion.
**Tests.** a candidate Go `S` is extracted, trace-validated, and promotable; a paper-only candidate is rejected.
**Acceptance.** A real, trace-validated Go candidate `S`.
**Depends on.** PC-6, PC-7.

### PC-9 · Real impact analysis — [NEW, M] — GAP-B4
**Decision (inline).** Affected-module set = call-graph reachability (PC-3/PC-6) from the requirement's bound symbols, cross-validated with a semantic (LLM, Pillar A) estimate; disagreement is surfaced (not silently resolved) as a review flag.
**Touches.** `source_impact.py`; `impact.py`; `llm_client.py`.
**Tasks.** `PC-9.T1` call-graph reachability → affected set; `PC-9.T2` semantic estimate; `PC-9.T3` disagreement flag.
**Tests.** the affected set is call-graph-derived; a planted LLM/call-graph disagreement is surfaced.
**Acceptance.** Impact is call-graph-derived + cross-validated.
**Depends on.** PC-3, PC-6, PA-4.

### PC-10 · Spec-coverage tracking + gating — [NEW, M] — GAP-B5
**Decision (inline).** A per-module coverage metric from the registry; a requirement touching an unspec'd module returns `NEEDS_SPEC_COVERAGE` and queues a Specula extraction (PC-5/PC-8). No `S ∧ R` runs against an unspec'd module.
**Touches.** `coverage_alignment.py`; `system_spec.py`; `end_to_end_gate.py`.
**Tasks.** `PC-10.T1` coverage metric per module; `PC-10.T2` `NEEDS_SPEC_COVERAGE` gating; `PC-10.T3` queue extraction.
**Tests.** a requirement against an unspec'd module blocks with `NEEDS_SPEC_COVERAGE` until extraction is reviewed+promoted.
**Acceptance.** Unspec'd modules block requirements until covered.
**Depends on.** PC-9, PC-5/PC-8.

### PC-11 · Code↔spec trace validation — [NEW, L] — GAP-B6
**Decision (inline).** Beyond `trace_validation.py`'s claim-vs-trace check, validate that the registered `S` reproduces the module's real traces (Specula's discipline), classifying as satisfies / violates-with-delta / no-coverage. A spec that cannot reproduce the code's traces is not a spec of the code.
**Touches.** `trace_validation.py`; `trace_replay.py`; `system_spec.py`.
**Tasks.** `PC-11.T1` replay real traces against `S`; `PC-11.T2` three-way classification; `PC-11.T3` delta report.
**Tests.** a spec describing the "paper system" but not the code is caught (cannot reproduce traces).
**Acceptance.** Spec↔code alignment is verified against real traces.
**Depends on.** PC-4/PC-7, PC-5/PC-8.

### PC-12 · Continuous freshness — [NEW, M] — GAP-X3
**Decision (inline).** Hash-based staleness (Cargo.lock-style): a commit touching a covered module recomputes its hash; if it differs and trace re-validation has not re-run, `S` is marked stale and requirements against it are blocked (Pillar B already refuses `unsupported` on a stale spec, `system_checker.py:73`).
**Touches.** `spec_freshness.py`; `spec_drift.py`; `continuous.py`; a CI hook.
**Tasks.** `PC-12.T1` per-module hash invariant; `PC-12.T2` commit-triggered re-validation; `PC-12.T3` stale → block.
**Tests.** editing a covered module marks its `S` stale and blocks `S ∧ R`.
**Acceptance.** Spec staleness tracks code changes and blocks until revalidated.
**Depends on.** PC-10, PC-11.

### PC-13 · Cross-language wedge — [NEW, L] — GAP-X5 (prog-lang axis), SP3 capstone
**Decision (inline).** One requirement whose premises span the Solidity contract and the Go coordinator is validated as a single `ProofObject`: A decomposes it, C resolves symbols + extracts traces in both languages and supplies both `S` specs, B runs `S ∧ R` per language and aggregates premises. tBTC is *one suggested instance*; the capstone is worded against "a real system spanning two languages," and the agnosticism claim additionally requires a second vehicle from a **different domain** (not DeFi) per Plan A PA-9 / the expansion note below.
**Touches.** `cross_language.py`; `system_composition.py`; `proof_closure.py`.
**Tasks.** `PC-13.T1` cross-language requirement + both `S`; `PC-13.T2` per-language `S ∧ R`; `PC-13.T3` aggregate into one `ProofObject`; `PC-13.T4` closure gates a downstream action.
**Tests.** a cross-language requirement closes one `ProofObject` with premises discharged across both verticals.
**Acceptance (SP3).** One cross-language requirement closes one `ProofObject` — "the loop closes."
**Depends on.** PC-3..C-11, PB-7, PB-8, PA-2.

### PC-14 · Graduate remaining adapters — [M, follow-on] — GAP-C2, X5
**Decision (inline).** Promote TypeScript (tsserver/ts-morph), Python (pyright/`ast`), Rust (rust-analyzer), Java (Eclipse JDT) from `static_resolution` to real-tool-backed, each gated by the conformance suite + recorded evidence (PC-1's gate). Add at least one **non-DeFi** vehicle here to substantiate application/domain agnosticism.
**Touches.** `production_source_adapters.py` (per-language); per-language client modules.
**Tasks.** one sub-task per language (mirror PC-3/PC-6); a non-DeFi demo vehicle.
**Tests.** each promoted adapter passes conformance at `trace_capable` with a real trace producer.
**Acceptance.** Capability level reflects reality; agnosticism shown on a non-DeFi domain.
**Depends on.** PC-3, PC-6 (the patterns).

## 4. Risks & mitigations
- **External tool friction (Slither/Foundry/gopls versions, headless CI).** → pin + checksum each tool; adapter records tool version in capability evidence; missing tool → `static_resolution`/`missing_trace_source`, never a fabricated trace.
- **Specula's failure mode (spec of the paper, not the code).** → trace-validation is a mandatory promotion guard (PC-5/PC-8/PC-11); no candidate `S` promotable unless it reproduces real traces.
- **Trace normalization loses verifier-relevant data.** → lossy-normalization rules documented per ecosystem on the frozen schema (PC-2); a vertical fails DoD if the normalized trace cannot answer the requirement's claim.
- **tBTC over-anchoring / domain leak.** → tBTC lives only above the adapter line (a Solidity adapter, a tBTC `SystemSpecRegistry` entry, a tBTC corpus); the agnostic core stays domain-free (enforced by the core-purity boundary test, Plan B §5); agnosticism is substantiated by a second non-DeFi vehicle (PC-14, PA-9).
- **Parallel-pillar integration drift.** → C freezes its contracts at PC-2 (SP1); B builds against the frozen `SystemSpecRegistry`/`NormalizedTrace` with a stub.

## 5. Definition of Done (Pillar C)
Solidity and Go adapters drive real ecosystem tooling (Slither/Foundry, gopls/runtime-trace), resolve symbols + call graphs that match the tools, and extract real traces into `NormalizedTraceArtifact`; impact analysis is call-graph-derived and cross-validated; requirements touching unspec'd modules are blocked until a trace-validated `S` is extracted, reviewed, and promoted; a covered-module edit marks `S` stale and blocks `S ∧ R`; and one cross-language requirement closes a single `ProofObject` (SP3). Regex adapters carry an honest capability level; a non-DeFi vehicle substantiates application agnosticism.

## 6. What NOT to rebuild (preserve)
The `AdapterCapabilityContract` v2.0 interface, the conformance/certification suite, the `NormalizedTraceArtifact` + `SourceManifest` schemas, the coverage/freshness representations, and the cross-language composition schema. Wire real tools behind them and raise the capability level honestly.
