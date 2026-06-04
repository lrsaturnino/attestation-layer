# Gap-Closure Plan A — Translation & Intake (the front door)

**Date (UTC):** 2026-06-03 · **Status:** Implementation spec, v2 (task-level, decisions inline)
**Pillar:** A of 3 (parallel capability pillars). Companions: `gap-closure-plan-B-system-consistency-and-formal-backends.md`, `gap-closure-plan-C-source-adapters-and-verticals.md`.
**Closes gaps (from `docs/vision-gap-spec.md`):** GAP-A1, GAP-A2, GAP-A4, GAP-A5, GAP-B3; the **natural-language axis of GAP-X5**; extends GAP-A3. (GAP-X5 is tri-axis: NL → this plan; formal-language → Plan B; programming-language + capstone → Plan C.)
**Supersedes for this pillar:** phases 22–23, 47–55, 83–88, 117–123, 151–156 (which built the representation/provenance shell).
**Format:** each work item is a full task spec — **Decision (inline)** (no separate ADR files), **Touches**, **Changes**, **Tasks** (`PA-n.Tk`), **Tests**, **Acceptance (real-evidence)**, **Depends on**. Research-grade items carry **Spike** + **Decision gate**.

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

**Effort tiers:** [S] days · [M] 1–2 wks · [L] multi-wk · [R] research (spike first). **FIX** = correctness repair (sequence first). **Numbering:** items `PA-n`; tasks `PA-n.Tk`; phase numbers 193+ on scheduling; **all design decisions are inline — no separate ADR files.**

---

## 1. Pillar A scope
Turn the front door from "deterministic parse of already-controlled text + structural echo" into a real, measured, untrusted-LLM-assisted translator that emits formal claims with genuine semantics and refuses on disagreement — feeding the frozen `FormalClaim` contract Pillar B checks. **Tracer-bullet contribution:** PA-1 (one claim kind lowers non-vacuously) is the Pillar-A half of SP2-B.

## 2. Current empirical state

| Area | State | Evidence |
|---|---|---|
| Compositional IR spine | Real — preserve & extend | `compositional_ir.py` typed `SemanticNode` tree + bidirectional flat↔tree migration |
| DSL v2/v3 input grammar | Real but narrow | `dsl_v2.py`, `dsl_v3.py`, `*.lark`; bounded vocabulary/claim classes |
| Free-NL → controlled drafting | **Absent (provenance shell)** | `intake.py:205` `create_controlled_rewrite_proposal` takes `proposed_controlled_text` as a parameter; every package: *"No LLM rewrite was used."* |
| NL→IR decomposition | Deterministic parse only | `semantic_translation.py:83` parses DSL v3 → relabels AST; no LLM, no multi-pass |
| IR→formal lowering (TLA path) | **Vacuous** | `translator.py:223` `_tla_skeleton`: predicates→`TRUE`, ids→`0`, `Within(…)==event` |
| IR→formal lowering (claim path) | Real but structural; unrouted | `formal_claim.py:145` typed canonical-string fragments + refusal; not consumed by a backend |
| Self-consistency (single claim) | Real but narrow | `smt.py:17` `check_self_consistency` propositional Z3 over one claim's conditions |
| Self-consistency (cross-req) | **Toy** | `system_checker.py:220` hardcoded 6-entry opposites table |
| Temporal / LTL | **Absent** | declared `bounded_temporal` kind; `Within` is a passthrough |

## 3. Work breakdown

### PA-1 · Non-vacuous lowering for one claim kind — [FIX, M] — GAP-A4 (tracer bullet, SP2-B half)
**Decision (inline).** Lowering produces real semantics, never `TRUE`/`0`. For `authorization_precondition` (the first kind): each `predicate` node lowers to an uninterpreted boolean relation `Pred_<name>(<args>)` declared over typed constants; the obligation `rejects_before(action, state)` lowers to a `Next`-relation constraint "no transition performs `action` while `Pred_authorized` is false". The output is the TLA+ module body consumed by `PB-4`/`system_checker`. The legacy `_tla_skeleton` stays only for back-compat tests, flagged deprecated.
**Touches.** `translator.py:144` `lower_ir_v2_to_tla`, `:223` `_tla_skeleton`, `:263` `_node_expr`; new `formal_lowering.py` shared with Pillar B (PB-4).
**Changes.** Replace `_node_expr`'s `predicate → "TRUE"` and `_identifiers → "{name} == 0"` with typed declarations + real relations; keep `LoweredFormalArtifact` shape (`status/content/content_hash/temporal_bounds/metadata`) but set `metadata={"evidence":"lowered","semantics":"non_vacuous"}`.
**Tasks.**
- `PA-1.T1` Typed identifier/relation declarations from `_identifiers`/`_predicates` (no `== 0`/`== TRUE`).
- `PA-1.T2` `authorization_precondition` obligation → real `Next` constraint.
- `PA-1.T3` Deprecate `_tla_skeleton` for the live path; keep behind a flag for old golden tests.
**Tests.** `tests/test_translator.py`: golden non-vacuous module for an `authorization_precondition`; a **discrimination test** — the requirement and its negation lower to bodies whose invariant Apalache distinguishes (hook to PB-4 test).
**Acceptance (real-evidence).** The lowered module for `authorized(u)` contains a real relation, not `TRUE`; requirement vs. negation are checker-distinguishable.
**Depends on.** SP1 (frozen `FormalClaim`/`RequirementIRV2`). Pairs with PB-4.

### PA-2 · Route `FormalClaim` into the backend boundary — [NEW, M] — GAP-A4, X1
**Decision (inline).** `formal_claim.build_formal_claim` output becomes the canonical input to Pillar B's dispatcher (today it is only the `end_to_end_gate.py:54` stage `"formal_claim": {"lowered","passed"}`). Each `FormalClaimFragment` (kind ∈ `predicate/comparison/membership/post_state/event_emission/state_invariant/causal_transition`) maps to a dispatch premise consumed by `proof_closure.build_proof_dispatch_plan` (PB-7).
**Touches.** `formal_claim.py:145`; `proof_closure.py:250`; `end_to_end_gate.py:54`.
**Changes.** Add `FormalClaim → list[ProofPremiseRoute]` adapter; the gate consumes premises, not just a stage flag.
**Tasks.** `PA-2.T1` fragment→premise mapping; `PA-2.T2` feed premises to the dispatcher; `PA-2.T3` `FormalClaim` fragments appear as `ProofObject` entries.
**Tests.** a lowered `FormalClaim` produces N dispatch premises = N fragments; each appears in the `ProofObject`.
**Acceptance.** `FormalClaim` fragments are discharged premises in a `ProofObject`, not a passed stage.
**Depends on.** PA-1, PB-7, SP1.

### PA-3 · Temporal / LTL semantics — [NEW, L] — GAP-A5
**Decision (inline).** `within`/`bounded_temporal` lowers to TLA+ bounded-temporal (a step-counter variable + `[]( trigger => <>_{<=k} response )` encoded as a bounded reachability invariant), with the bound carried into `ModelCheckerBudget.max_depth`. No `Within(...) == event` passthrough.
**Touches.** `formal_lowering.py` (PA-1); `translator._temporal_bounds` (`:209`); `system_checker._runner_budget` (PB-10).
**Tasks.** `PA-3.T1` bounded-temporal lowering; `PA-3.T2` bound → budget depth; `PA-3.T3` `BOUNDED_CHECKED(k)` records the bound.
**Tests.** "redemption within 6h" lowers to a bounded-temporal module; a violating trace yields a counterexample; result is `BOUNDED_CHECKED` with the bound, never `valid` by passthrough.
**Acceptance.** A temporal requirement is genuinely checked with a recorded bound.
**Depends on.** PA-1, PB-3, PB-4.

### PA-4 · Free-NL → controlled drafting (real LLM behind the provenance shell) — [NEW, L] — GAP-A2
**Decision (inline).** Implement the drafting capability `intake.py` only records today. An `LlmClient` interface (sync `propose_controlled_rewrite(prose, grammar_summary) -> str`) has two impls: a real SDK client and a `RecordedLlmClient` (replays fixtures, for offline/golden tests). The LLM proposes; the existing approval/diff/hash/model-metadata machinery (`intake.create_controlled_rewrite_proposal`) gates it; **no parser runs until explicit human approval** (`semantic_translation.py:94` already enforces the hash binding). The LLM never decides — it drafts.
**Touches.** new `llm_client.py`; `intake.py:205` (call the client to *produce* `proposed_controlled_text`); `cli.py` `draft`/`intake-draft` (`:479,495`) wire `--method llm`.
**Tasks.** `PA-4.T1` `LlmClient` interface + `RecordedLlmClient`; `PA-4.T2` real SDK impl (key from `.claude/.env`, never hardcoded); `PA-4.T3` wire `intake` drafting + provenance (`method="llm"`, model, prompt hash); `PA-4.T4` CLI `nlreq intake-draft --method llm`.
**Tests.** offline: `RecordedLlmClient` prose→controlled→diff→approval→hash-bound translation; rejecting the diff blocks the parser.
**Acceptance.** Prose enters only via gated, human-approved LLM drafting with full provenance.
**Depends on.** SP1; PA-1 (so the approved controlled text lowers non-vacuously).

### PA-5 · Multi-pass decomposition with disagreement-as-refusal — [NEW, L, R] — GAP-A4
**Decision (inline).** Treat the translator as untrusted: ≥2 independent LLM decompositions of the same controlled requirement into the IR; compare via `formal_claim.formal_claim_signature(claim, alpha_identifiers=True, commutative=True)` (`formal_claim.py:258`); on signature disagreement, **refuse** (`REFUSED_AMBIGUOUS`) with a clarification mapped to the diverging `source_span`.
**Open question.** What signature-equivalence threshold and normalization (alpha-renaming, commutativity, predicate synonymy) catches genuine ambiguity without over-refusing paraphrases? Unknown without data.
**Spike.** On a 30-item controlled-requirement set, run 3 decompositions each; measure agreement rate and hand-label false-agreement (different meaning, same signature) and false-disagreement (same meaning, different signature).
**Decision gate.** Proceed to production if false-agreement ≤ target on the spike set; otherwise tighten the signature/normalization and re-spike. Record the chosen normalization inline here after the spike.
**Touches.** new `translator_ensemble.py`; `formal_claim.formal_claim_signature`; `semantic_translation.py` (refusal path).
**Depends on.** PA-4, PA-9 (corpus).

### PA-6 · LLM trust boundary + audit gate — [NEW, M] — GAP-A2, A4
**Decision (inline).** Every LLM-discharged step is tagged in provenance; a second model+prompt audits each LLM decomposition against a structured rubric (does the IR cover every controlled clause? any invented premise?); the audit verdict is a gate. LLM is never a proof authority.
**Touches.** `provenance.py`; `review_workflow.py`; `llm_client.py`.
**Tasks.** `PA-6.T1` provenance tags LLM vs deterministic per fragment; `PA-6.T2` audit rubric + second-model gate; `PA-6.T3` package records audit verdict.
**Tests.** a planted invented-premise decomposition is caught by the audit gate; a clean one passes.
**Acceptance.** Packages record which fragments were LLM-derived and the audit verdict.
**Depends on.** PA-4.

### PA-7 · ALICE-style contradiction taxonomy — [NEW, M] — GAP-B3
**Decision (inline).** Replace the 6-entry opposites table (`system_checker.py:220`, `smt.py:158`) with the seven-question decision tree over typed `FormalClaim` fragments: negation, mutual exclusion, conditional overlap, quantifier-scope conflict, numeric-range disjointness, temporal conflict, action/order conflict. Each detected contradiction carries its type + both source spans.
**Touches.** new `contradiction_taxonomy.py` (a `contradiction-taxonomy.md` already documents the taxonomy — implement it); `system_checker.check_requirement_set_consistency` (`:217`).
**Tasks.** `PA-7.T1` the seven checks over fragments; `PA-7.T2` numeric-range + temporal via SMT (PB-6); `PA-7.T3` typed contradiction report with spans.
**Tests.** each contradiction class has a positive + negative fixture; numeric-range disjointness (`x>10` ∧ `x<5`) is caught (today's table misses it).
**Acceptance.** Contradictions beyond literal `authorized/not_authorized` are detected with type + spans.
**Depends on.** PA-1, PB-6 (SMT theories for numeric/temporal).

### PA-8 · Cross-requirement-set consistency — [NEW, M] — GAP-B3
**Decision (inline).** SMT over the conjunction of all claims' premises/obligations in a declared requirement set (set = per-feature manifest). Mutually inconsistent members are flagged jointly before any system check.
**Touches.** `system_checker.check_requirement_set_consistency` (`:217`); `smt.py` (conjunction encoding, PB-6).
**Tasks.** `PA-8.T1` requirement-set manifest; `PA-8.T2` conjunction SMT; `PA-8.T3` joint-inconsistency report.
**Tests.** requirement A and Z individually satisfiable but jointly contradictory are flagged.
**Acceptance.** Joint inconsistency across a set is detected.
**Depends on.** PA-7, PB-6.

### PA-9 · Labeled translation corpus + metrics — [NEW, L] — GAP-A1, A4
**Decision (inline).** A corpus of `(prose, approved-controlled, gold-IR)` triples across **≥2 unrelated domains** (not DeFi-only — e.g., a procurement-approval flow and a protocol-safety property), measuring the **LLM front-half** (PA-4/PA-5): false-acceptance (wrong claim accepted) and false-refusal (correct claim refused). The deterministic DSL→IR parser is *not* measured this way (it parses or refuses); the corpus measures prose→controlled→IR inference.
**Touches.** new `benchmarks/translation-corpus/`; `translation_benchmark.py` (exists — wire it).
**Tasks.** `PA-9.T1` corpus (≥2 domains, ≥30 items each); `PA-9.T2` harness computes both rates per domain; `PA-9.T3` CI fails if false-acceptance > budget.
**Tests.** harness reports both rates; a regression past budget fails CI.
**Acceptance.** A reproducible per-domain report; CI-enforced false-acceptance budget.
**Depends on.** PA-4, PA-5.

### PA-10 · Refusal UX hardening — [S] — GAP-A1
**Decision (inline).** Every refusal across A carries `next_actions` + `source_span` (extend `semantic_translation.py` refusal codes); the CLI renders the offending fragment inline.
**Touches.** `semantic_translation.py`; `refusal.py`; `cli.py`.
**Tasks.** `PA-10.T1` ensure all A refusals carry spans+next_actions; `PA-10.T2` CLI rendering.
**Tests.** each refusal mode renders the offending fragment.
**Acceptance.** No bare "broken, try again" refusals.
**Depends on.** PA-1.

### PA-11 · Multilingual NL intake, corpus, metrics, refusal — [NEW, M, R] — GAP-X5 (NL axis)
**Decision (inline).** Non-English prose flows through the same PA-4 drafting path (the IR is language-neutral; the LLM handles other languages with a fixed output schema). Provenance records `source_language`. Merchant/identifier strings stay verbatim in the original language. Low-confidence cross-language fragments **refuse** with a clarification rather than guess.
**Open question.** Do non-English decompositions hit the same false-acceptance budget as English, or does idiom inflate it? Unknown without data.
**Spike.** Author the same 20 requirements in English + Portuguese; run PA-4/PA-5; compare per-language false-acceptance/false-refusal and English↔Portuguese signature equivalence.
**Decision gate.** Claim "NL-agnostic" only if non-English rates are within the English budget on the spike; else scope the claim to the languages that pass and record it here.
**Touches.** `llm_client.py` (language param); `intake.py` (`source_language`); `benchmarks/translation-corpus/` (multilingual slice).
**Depends on.** PA-4, PA-9.

## 4. Risks & mitigations
- **LLM nondeterminism breaks golden tests.** → `RecordedLlmClient` for offline goldens; live-LLM tests are a separate budgeted suite.
- **"Measured accuracy" overclaim.** → report both rates, never a single "accuracy"; corpus measures the front-half only (PA-9).
- **Lowering leaks backend specifics into the spine.** → IR stays formalism-neutral; lowering lives in `formal_lowering.py` (the backend-facing layer); enforced by the core-purity boundary test (see Plan B §5).
- **Multilingual idiom mistranslation.** → low-confidence cross-language fragments refuse, not guess (PA-11).

## 5. Definition of Done (Pillar A)
A controlled requirement produces a non-vacuous `FormalClaim` that Pillar B discharges into a `ProofObject` premise; prose enters only via gated, human-approved LLM drafting with full provenance and a second-model audit; ambiguous/contradictory requirements (intra- and cross-set) are refused with source spans; temporal claims carry real bounds; translator front-half accuracy is measured across ≥2 domains with a CI-enforced false-acceptance budget; and at least one non-English language flows through with per-language metrics.

## 6. What NOT to rebuild (preserve)
The compositional IR spine, source-span provenance, the package approval/diff/hash machinery, the DSL v3 parser, and the refusal-code surface. Extend; do not replace.
