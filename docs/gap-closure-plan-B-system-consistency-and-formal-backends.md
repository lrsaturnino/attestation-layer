# Gap-Closure Plan B — System-Consistency & Formal Backends (the core)

**Date (UTC):** 2026-06-03 · **Status:** Implementation spec, v2 (task-level, decisions inline)
**Pillar:** B of 3 (parallel capability pillars). Companions: `gap-closure-plan-A-translation-and-intake.md`, `gap-closure-plan-C-source-adapters-and-verticals.md`.
**Closes gaps (from `docs/vision-gap-spec.md`):** GAP-B1, GAP-B2, GAP-C4, GAP-X1, GAP-X2, GAP-X4; the **formal-language axis of GAP-X5**.
**Supersedes for this pillar:** phases 20, 25–28, 30–34, 56–61, 124–130, 157–163, 190 (which defined backend *contracts and runners*).
**Format:** every work item below is a full task spec — **Decision (inline)** (the design decision is made here; no separate ADR files), **Touches**, **Changes**, **Tasks** (`PB-n.Tk`, each a coherent commit), **Tests**, **Acceptance (real-evidence)**, **Depends on**. Research-grade items carry **Spike** + **Decision gate** instead of fabricated task certainty.

> **This pillar contains the single most important correction in the whole effort.** The vision names `S ∧ R` *"the actual core"* (`claude-convo.md:124`). Today it is fixture-driven: the integrated gate decides by marker-grep (`system_checker.py:94`) and the solver path never conjoins `S` (`system_checker.py:314`). PB-1 fixes it and is a composition rewrite, not research.

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

**Effort tiers:** [S] days · [M] 1–2 wks · [L] multi-wk · [R] research (spike first). **FIX** = correctness repair (sequence first). **Numbering:** items `PB-n`; tasks `PB-n.Tk`; phase numbers 193+ on scheduling; **all design decisions are inline — no separate ADR files.**

---

## 1. Pillar B scope
Make system-consistency a real `S ∧ R` against a real reviewed `S`, run by a real symbolic checker, producing real counterexamples and honestly-labeled evidence; lower the IR into ≥2 formal backends; aggregate per-premise results into a `ProofObject` whose closure gates downstream action.

## 2. Current empirical state

| Area | State | Evidence |
|---|---|---|
| System spec `S` registry | Real (registry only) | `system_spec.py` `SystemSpecEntry` (formalism/review/freshness/recorded_hash) |
| `S` conjoined into the check | **No — `S` is a hash comment** | `system_checker.py:301` `_composed_tla_module` → `SystemSpecAssumptions == TRUE` |
| `S ∧ R` — integrated gate | **Marker-grep** | `end_to_end_gate.py:248` → `check_system_consistency` (`system_checker.py:85-116`): `valid` unless spec text has `NLREQ_COUNTEREXAMPLE:<id>`/`NLREQ_TIMEOUT` |
| `S ∧ R` — solver path | Real harness, opt-in, tool absent | `check_solver_backed_system_consistency` (`:119`) → `run_model_checker`; default cmd `tlc2.TLC`; **Apalache/TLC not installed** (java is) |
| IR→TLA+ lowering | **Vacuous** | `translator.py:223` predicates→`TRUE` |
| SMT backend | Propositional only | `smt.py:138` `smt2_for_ir` encodes only `authorized/not_authorized/approved/not_approved` as Bools; comparisons/numerics not encoded |
| Formal backends | Command templates + harness | `formal_backend.py` `ApalacheBackend` (`["apalache-mc","check","--length={depth}","{module}"]`), `TlcProductionBackend`; no Alloy/Lean |
| Multi-backend dispatch | Single backend, hardcoded | `adapter.py:134` one `core_smt` task; `build_proof_dispatch_plan(backend_id="system_checker")` routes every premise to the marker checker (`proof_closure.py:250`) |
| Proof object closure | Real schema; stub producers | `proof_closure.py:121` `ProofObject` + producer registry (`apalache`/`tlc`/`tlaps`/`core_smt`/`trace_validation`) |
| Closure-as-action-gate | Softened to package policy | `gate.py` enforces package/status/evidence policy, not a closed multi-premise proof |
| Evidence producers | Lower levels real; high levels unbacked | `STATICALLY_RESOLVED`/`CONSISTENCY_CHECKED`/`SMT_CHECKED` real; `BOUNDED_CHECKED` only via opt-in command; `PROVEN_INDUCTIVE` has no producer |

## 3. Tracer-bullet slice (build this first → produces SP2-B)
The smallest path to the first real `S ∧ R` counterexample, formalism-only (no source adapter, no LLM). Ordered: **PB-3.T1** (install Apalache) → **PA-1** (Pillar A: one claim kind lowers non-vacuously) → **PB-1** (conjoin `S`) → **PB-2** (default gate → solver) → **PB-5.T1** (one hand-written reviewed `S` + retained counterexample). Everything else in this pillar builds outward from that.

## 4. Work breakdown

### PB-1 · Conjoin `S` into the `S ∧ R` composition — [FIX, M] — GAP-B2 (the core)
**Decision (inline).** The composed module must include the reviewed spec's real `Init`, `Next`, and named invariants, and check **`Spec => []Inv_R_preserved`** where the requirement projection `R` constrains the transition relation. `SystemSpecAssumptions` is replaced by the spec's actual assumptions/constants. Namespacing rule (resolving `system_composition.py:92`): the requirement projection is emitted under a `R_` prefix; the system spec's operators keep their names; on operator-name collision the composition **refuses** (`unsupported`, reason `operator_name_collision`) rather than silently overriding. `S` is referenced by content hash in a comment *and* its operators are textually included.
**Touches.** `system_checker.py:301` `_composed_tla_module`; `system_checker.py:119-214` `check_solver_backed_system_consistency`; `system_composition.py:92` (namespace policy text → enforced).
**Changes.** Rewrite `_composed_tla_module(module_name, lowered, spec_texts)` to (1) parse each `spec_text` for its `MODULE` body, `INIT`/`NEXT`/invariant operator names (read from the `SystemSpecEntry.metadata` keys `init_op`/`next_op`/`invariants` — add these fields to `SystemSpecEntry`), (2) `EXTENDS`/inline them, (3) emit `R == <lowered.content body>` and `SystemAndRequirement == Spec => [](Inv_1 /\ ... /\ Inv_n)` where the requirement narrows `Next`. Add `operator_name_collision` to the refusal reasons.
**Tasks.**
- `PB-1.T1` Add `init_op`/`next_op`/`invariants: list[str]` to `SystemSpecEntry` (`system_spec.py`); regenerate schema; migrate fixtures.
- `PB-1.T2` Rewrite `_composed_tla_module` to conjoin `S` per the decision; add collision refusal.
- `PB-1.T3` Update `system_composition._preserved_invariants` to read the real invariant names from the spec, not the hardcoded `["RequirementHolds"]` fallback (`system_composition.py:159`).
**Tests.** `tests/test_system_checker.py`: golden `_composed_tla_module` output for a 1-invariant spec (byte-stable); a spec whose `invariants` is empty yields `unsupported` (no vacuous pass); colliding operator names yield `operator_name_collision`. Fixture spec under `tests/fixtures/specs/`.
**Acceptance (real-evidence).** Omitting `S`, or an `S` with no declared invariants, **cannot** yield `valid`; the composed `.tla` textually contains the spec's invariant operators (not just a hash comment).
**Depends on.** PA-1 (a non-vacuous `R` to conjoin), PB-3 (a checker to run it), SP1 (frozen `SystemSpecEntry`).

### PB-2 · Default gate runs the solver path, not marker-grep — [FIX, S] — GAP-B2
**Decision (inline).** `end_to_end_gate` calls `check_solver_backed_system_consistency` by default. `check_system_consistency` (marker mode) is retained only behind an explicit `mode="fixture"` parameter for offline tests and is renamed `check_system_consistency_fixture` to make misuse obvious. The `NLREQ_COUNTEREXAMPLE`/`NLREQ_TIMEOUT` marker handling stays only in the fixture function.
**Touches.** `end_to_end_gate.py:248`; `system_checker.py:51-116`; callers in `cli.py`, `proof_closure.py`, tests.
**Changes.** Rename + repoint; `end_to_end_gate.build_*` passes the `FormalBackendExecution` through.
**Tasks.** `PB-2.T1` rename marker fn + update all call sites (grep `check_system_consistency`); `PB-2.T2` repoint `end_to_end_gate` to the solver path with a configurable execution.
**Tests.** `tests/test_end_to_end_gate.py`: the default gate on a spec containing `NLREQ_COUNTEREXAMPLE:` does **not** return `counterexample` from a string match (it runs the checker); the fixture fn still does, for offline tests.
**Acceptance.** Default `nlreq` end-to-end gate no longer decides `S ∧ R` from a string in the spec file.
**Depends on.** PB-1, PB-3.

### PB-3 · Install + pin Apalache and TLC — [NEW, M] — GAP-B2
**Decision (inline).** Apalache (`apalache-mc`) and `tla2tools` (TLC) are external pinned binaries, not Python deps: pin exact versions + SHA-256 in `docs/formal-backend-guide.md` and a `scripts/install_formal_backends.sh` (download + checksum-verify). `FormalBackendExecution.tool_version_command` is always set so every run records the real version; missing tool keeps degrading to `tool_error` (already correct, `model_checker_runner.py:142`).
**Touches.** new `scripts/install_formal_backends.sh`; `docs/formal-backend-guide.md`; `formal_backend.py` (default `tool_version_command`).
**Tasks.** `PB-3.T1` install script + checksums (Apalache primary, TLC reserve); `PB-3.T2` wire `tool_version_command` defaults; `PB-3.T3` CI job marks the vertical `tool-unavailable` (not pass) when binaries absent.
**Tests.** `tests/test_model_checker_runner.py`: against a checked-in known-good and known-bad toy `.tla`, `run_model_checker` returns real `valid`/`counterexample` with `reproducibility.executable_resolved` populated and `tool_version` non-null (skipped with a recorded skip-reason when the binary is absent — never silently passed).
**Acceptance.** Real Apalache returns `valid` on a sat toy and `counterexample` on an unsat toy, with recorded version + command line.
**Depends on.** none (environment).

### PB-4 · Real IR→TLA+ lowering consumed by the checker — [NEW, L] — GAP-C4, B2
**Decision (inline).** The checker consumes Pillar A's `FormalClaim` (not the legacy `translator._tla_skeleton`). Mapping per `FormalClaimFragment.kind`: `predicate`→uninterpreted boolean relation over its operands; `comparison`→`<`/`<=`/`=`/`#` over `Int`; `membership`→`\in`; `state_invariant`→an invariant operator conjoined into `Inv`; `post_state`→a `Next`-relation constraint; `event_emission`/`causal_transition`→bounded-temporal (PA-3). Identifiers become `CONSTANTS`/`VARIABLES` per role. No fragment lowers to `TRUE`.
**Touches.** new `formal_lowering.py` (IR/`FormalClaim` → TLA+ module body), consumed by `system_checker._composed_tla_module`; deprecates `translator._tla_skeleton` for the checker path.
**Tasks.** `PB-4.T1` lowering for `predicate`+`comparison`+`membership` (covers `authorization_precondition`, `numeric_invariant`); `PB-4.T2` `post_state`/`state_invariant`; `PB-4.T3` deprecate `_tla_skeleton` in the checker path (keep for back-compat tests, flagged).
**Tests.** golden TLA+ bodies per fragment kind; **discrimination test**: a requirement and its negation lower to modules whose `Inv` Apalache distinguishes (one `valid`, one `counterexample`).
**Acceptance.** A requirement and its negation produce distinct checker outcomes against the same `S`.
**Depends on.** PA-1/PA-2 (the `FormalClaim`), SP1.

### PB-5 · Retained real `S ∧ R` runs over a reviewed spec — [NEW, L] — GAP-B2, X4
**Decision (inline).** Retained artifacts live under `benchmarks/s-and-r/<spec-id>/` and are committed (small) or content-addressed: the composed `.tla`+`.cfg`, the Apalache stdout/stderr, the normalized counterexample, the `ModelCheckerRunResult` JSON, and a `run.json` with version+command+bounds+hashes. Each outcome class (valid / counterexample / timeout / unsupported / missing-tool) has at least one retained instance.
**Touches.** `benchmarks/`; `counterexample_normalization.py`; a `nlreq s-and-r --retain` CLI flag.
**Tasks.** `PB-5.T1` hand-write one small reviewed `S` (one module, ≥1 invariant) under `benchmarks/s-and-r/` (formalism-only; Pillar C replaces it with an extracted `S` later); `PB-5.T2` author a requirement that violates the invariant + its compatible sibling; `PB-5.T3` retain all five outcome-class artifacts; `PB-5.T4` a replay test re-runs the retained command and diffs the normalized counterexample (golden).
**Tests.** `tests/test_milestone_group11.py` (extend): the violating requirement yields a counterexample naming the invariant; the sibling yields `valid`; replay is byte-stable.
**Acceptance (SP2-B).** A requirement that contradicts a real `S` invariant yields a **retained, replayable Apalache counterexample naming the invariant**; closes the "retained Apalache/TLC runs" blocker (`claude-convo-real-evidence-gap-assessment.md:41`) for one vertical.
**Depends on.** PB-1, PB-3, PB-4.

### PB-6 · SMT-with-theories + a second backend — [NEW, L] — GAP-C4
**Decision (inline).** Upgrade `smt.py` from propositional to Z3 with `Int`/`Real`/`Array` theories so `comparison`/`membership`/numeric `state_invariant` fragments are encoded (today `smt2_for_ir` drops them, `smt.py:143`). Add one structural backend (CVC5 or Alloy) behind the `FormalBackend` protocol for membership/relational premises. A **cross-backend agreement check** asserts the SMT and model-checker projections of one requirement do not disagree on a shared sat/unsat question.
**Touches.** `smt.py` (`smt2_for_ir`, `smt_check_requirement`, `check_self_consistency`); new `cvc5_backend.py` or `alloy_backend.py`; `backend_agreement.py` (exists — wire it).
**Tasks.** `PB-6.T1` encode comparisons/numerics into Z3 with theories; `PB-6.T2` second backend behind `FormalBackend`; `PB-6.T3` cross-backend agreement gate.
**Tests.** a numeric-invariant claim is `SMT_CHECKED` by Z3-with-theories; a disagreement between two backends on a planted case fails the agreement gate.
**Acceptance.** The same `FormalClaim` projects into ≥2 backends; a planted cross-backend disagreement is caught.
**Depends on.** PB-4, SP1.

### PB-7 · Multi-backend dispatcher + aggregated `ProofObject` — [NEW, M] — GAP-X1
**Decision (inline).** Replace the single `core_smt` task (`adapter.py:134`) and the hardcoded `build_proof_dispatch_plan(backend_id="system_checker")` (`proof_closure.py:250`). Routing rule (per premise role/kind): authorization/propositional → `core_smt`; numeric/comparison → SMT-with-theories; state/temporal/`state_invariant` → Apalache `S ∧ R`; trace-grounded obligations → `trace_validation`. Each premise produces one `ProofObject` entry tagged with the discharging producer.
**Touches.** `proof_closure.py:250` `build_proof_dispatch_plan`; `adapter.py:130` `generate_tasks`; `proof_closure.backend_results_from_system_consistency` (`:368`).
**Tasks.** `PB-7.T1` per-premise router (role/kind → backend); `PB-7.T2` populate `ProofObject` one entry per premise + producer; `PB-7.T3` retire the single-backend default.
**Tests.** a 3-premise requirement (authorization + numeric + temporal) yields a `ProofObject` with three entries discharged by `core_smt`, SMT-theories, and Apalache respectively.
**Acceptance.** Multi-premise requirement closes across ≥2 backends into one `ProofObject`.
**Depends on.** PB-4, PB-6.

### PB-8 · Closure-as-action-gate — [NEW, M] — GAP-X2
**Decision (inline).** Downstream action requires a **closed** `ProofObject` (every premise discharged at its required level). Enforced on the existing shadow→soft→hard ladder (`gate.py`): shadow reports, soft warns, hard blocks. An un-closed proof emits `REFUSED_FAILED_CHECK` naming the open premise(s).
**Touches.** `gate.py`; `proof_closure.py` (a `ProofObject.is_closed` predicate); `end_to_end_gate.py`.
**Tasks.** `PB-8.T1` `is_closed` + open-premise enumeration; `PB-8.T2` wire into the gate ladder; `PB-8.T3` CLI surfaces the open premises on refusal.
**Tests.** a requirement with one undischarged premise blocks at hard-gate naming that premise; passes at shadow with a report.
**Acceptance.** Nothing un-closed flows past hard-gate.
**Depends on.** PB-7.

### PB-9 · Evidence-producer honesty — [FIX, M] — GAP-X4
**Decision (inline).** A static map `producer → allowed evidence levels` is enforced at emission: `BOUNDED_CHECKED` requires recorded bounds + checker version; `PROVEN_INDUCTIVE` requires a real inductive proof artifact (Apalache `check --inductive-invariant` or a TLAPS obligation) — **until that producer exists, `PROVEN_INDUCTIVE` is never emitted**. `TRACE_VALIDATED` requires a non-lossy trace mapping.
**Touches.** `proof_closure.py` (`EvidenceProducer.allowed_evidence_levels` — already a field, enforce it); `models.py` (a validator); `formal_backend.py`.
**Tasks.** `PB-9.T1` enforce `allowed_evidence_levels` at `BackendResult` construction; `PB-9.T2` forbid `PROVEN_INDUCTIVE` without a proof-artifact hash; `PB-9.T3` require bounds on `BOUNDED_CHECKED`.
**Tests.** constructing a result that emits `PROVEN_INDUCTIVE` without a proof artifact raises; `BOUNDED_CHECKED` without bounds raises.
**Acceptance.** No emitted level lacks a real backing producer + metadata.
**Depends on.** PB-3 (bounds), PB-7.

### PB-10 · Verification budget + counterexample normalization — [NEW, M] — GAP-B2, X4
**Decision (inline).** A per-requirement budget (timeout, max-depth, max-states) is passed into every `S ∧ R` run; a budget exhaustion maps to `REFUSED_TIMEOUT` / `UNVERIFIED` (never `valid`). Counterexamples normalize to a stable schema (`counterexample_normalization.py`) so two runs render identically.
**Touches.** `verification_budget.py`; `counterexample_normalization.py`; `system_checker._runner_budget` (`:350`); `_solver_status_for_runner` (`:366`).
**Tasks.** `PB-10.T1` thread budget from requirement → `ModelCheckerBudget`; `PB-10.T2` `timeout`→`REFUSED_TIMEOUT`; `PB-10.T3` golden normalized counterexample.
**Tests.** a deliberately-tiny budget yields `REFUSED_TIMEOUT`, not `valid`; a counterexample is byte-identical across two runs.
**Acceptance.** Timeout is a first-class non-approving status; counterexamples are stable.
**Depends on.** PB-3, PB-5.

## 5. Risks & mitigations
- **State-space explosion on real `S ∧ R`.** → Apalache symbolic + explicit budget (PB-10); `timeout → UNVERIFIED`; compositional/assume-guarantee deferred but slotted.
- **Checking against a drifted/fictional `S`.** → `S ∧ R` only runs against a `fresh` + `reviewed` spec (`system_checker.py:73`); freshness is Pillar C (PC-12).
- **Over-claiming `PROVEN_INDUCTIVE`.** → PB-9 forbids it without a proof artifact.
- **External tool unavailability in CI.** → PB-3 pin+checksum; missing tool → `tool_error`/`UNVERIFIED`, CI marks "tool-unavailable" (never pass).
- **Core-purity drift toward a domain/language.** → the agnostic core (`models`/`parser`/`status`/`smt`/`proof_closure`/`formal_backend`/`compositional_ir`) must contain no domain/language string and import no adapter module; add a boundary test (`tests/test_core_purity.py`) that fails the build on leakage. (Empirically clean today.)

## 6. Definition of Done (Pillar B)
The default end-to-end gate runs a real `S ∧ R` that genuinely conjoins a fresh, reviewed `S` and executes a pinned Apalache/TLC, returning real valid/counterexample/timeout with retained replayable artifacts; the IR lowers into ≥2 backends with a cross-backend agreement check; premises aggregate into a `ProofObject` whose closure gates action on the shadow→soft→hard ladder; every emitted evidence level is backed by a real producer with reproducibility metadata, and `PROVEN_INDUCTIVE` is emitted only with a real proof.

## 7. What NOT to rebuild (preserve)
`SystemSpecRegistry` + freshness/review gating, the `FormalBackend*` abstraction and `model_checker_runner` subprocess harness (it degrades honestly), the `ProofObject` schema + producer registry, the 9-level taxonomy, `verification_budget`/`counterexample_normalization` schemas. Wire real producers behind them.
