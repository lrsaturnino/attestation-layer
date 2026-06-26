# ADR 0204: Cross-Provider Ensemble/Audit Policy, Per-Role Calibration, And Wrapper-Side §6 Contract

## Status

Accepted (policy); Calibration EXECUTED across BOTH transports:
- **Anthropic SDK drafting** (2026-06-25) on the 66-case English corpus AND the 63-case
  multilingual corpus (en + pt, both meeting the §5 per-language ≥30 floor).
- **Cross-provider CLI drafting** (2026-06-25) on the 66-case English corpus via TWO DISTINCT
  §6-eligible operator wrappers: `run-claude` (anthropic) + `run-gpt` (openai) — the
  cross-provider dimension acceptance #5 requires.
- **Cross-provider CLI non-drafting roles** (2026-06-25, iter 4) — all four non-drafting roles
  (decomposition / impact / extraction / audit) run LIVE through `benchmark-role --run
  --llm-client cli:<wrapper>:tiny` across the same two providers; 8 per-(role, model) FA/FR
  reports committed under `benchmarks/role-calibration/live-calibration/` on 12-case
  role-specific discriminator corpora. The §5 per-domain ≥30 floor is met ONLY by drafting
  (English 2×33 + multilingual 30 en/33 pt); the non-drafting live run is a 12-case
  non-vacuity discriminator, an explicit owner-pending deviation from the §5 floor-sized
  standard (see §4.1), NOT a fully-closed floor-sized calibration.

**Operator wrapper-side §6: EXECUTED for `run-claude` + `run-gpt`** (2026-06-25) — both emit
the `<output>.meta.json` sidecar and honor the pure-completion profile (no tools, no cwd/repo
context, no silent fallback) under `NLREQ_ATTESTATION=1`. `run-oss` / `run-oss-local` /
`run-gemini` are **attestation-ineligible** (pi requires ≥1 tool; gemini has no verified
no-tools knob) and refuse upfront in attestation mode (zero egress). The real two-provider
ensemble artifact (acceptance #2) and the cross-provider FA/FR calibration (acceptance #5) are
both committed in this repo.

### Update (2026-06-25, iter 3) — non-drafting role calibration is NO LONGER future scope

The non-drafting dimension of acceptance #5 (decomposition / impact / extraction / audit) had
its HARNESS + recorded-discriminator evidence CLOSED in iter 3 (the LIVE per-role/per-model run
followed in iter 4 — see the iter-4 update below; until then the live dimension remained
operator-side). Each non-drafting role has its own role-specific corpus + harness
(`src/nlreq/role_calibration.py`, `benchmark-role --role <role>`), distinct from the translation
corpus (which calibrates only drafting). The committed **recorded-discriminator** reports under
`benchmarks/role-calibration/calibration/` prove each harness DISCRIMINATES (planted FA → FA,
planted FR → FR, faithful → match; FA=4 / FR=4 / matched=4 over a 12-case, 2-domain corpus — the
expected non-zero signal that a constant-zero instrument could not produce). The live FA/FR
measurement WAS operator-side as of iter 3 (`benchmark-role --run --llm-client <scheme>`),
exactly as with drafting; the harness is role-parameterizable + self-describing, so closing the
live dimension was a one-command operator action per role/model — EXECUTED in iter 4 (see the
iter-4 update below). `benchmark-translation --role <non-drafting>` is
still refused (the translation corpus is drafting-only) but now POINTS at `benchmark-role`.
Accordingly, every "future scope / `--role <non-drafting>` is refused" statement below about the
non-drafting roles is SUPERSEDED by this update + §4.1 — they remain accurate only for the
multilingual-CLI sub-dimension (the live-operator-run was subsequently EXECUTED in iter 4), not
for the existence of the harness/corpus or the live per-role/per-model run.

### Update (2026-06-25, iter 4) — LIVE non-drafting role calibration EXECUTED (12-case discriminator; §5 floor-sized measurement pending — see §4.1)

The live-operator-run sub-dimension flagged as remaining in the iter-3 update is now CLOSED.
All four non-drafting roles were run LIVE through the cross-provider CLI transport
(`benchmark-role --run --llm-client cli:<wrapper>:tiny`) against TWO DISTINCT §6-eligible
operator wrappers — `run-claude` (anthropic, claude-haiku-4-5) + `run-gpt` (openai,
gpt-5.4-mini) — producing 8 self-describing per-(role, model) FA/FR reports committed under
`benchmarks/role-calibration/live-calibration/` and guarded by
`tests/test_role_calibration.py` (schema/provenance validity + exact-count drift guards + the
cross-provider-per-role diversity guard). The per-role/per-model tables + operating-point
decision are in §4.1. **One clear status:** the non-drafting dimension of acceptance #5 — harness, discriminator, AND
a live per-role/per-model FA/FR run — is committed as REAL EVIDENCE on a 12-case role-specific
discriminator corpus per role. This is NOT the §5 per-domain ≥30 floor-sized calibration (that
floor is met ONLY by drafting, §4); the non-drafting 12-case discriminator is an explicit
owner-pending deviation from the floor-sized standard, not a fully-closed floor-sized calibration.
The only additional non-drafting sub-dimension is an optional multilingual CLI run (the committed
corpora are English/single-language). The iter-4 code fix also made `CliTransportError` propagate out of
`run_role_calibration` (a transport-contract violation now refuses at `benchmark-role` exit 2,
never a silent false-refusal in the report) and added `--results` corpus-match validation
(missing/duplicate/extra case ids refuse at exit 2, never zeroed FA/FR rates).

## Context

ADR 0202 introduced the per-role model configuration and resolution ladder; ADR 0203 added the
CLI transport (`CliLlmClient`) under the pure-completion contract with sidecar provenance. Work
Item 3 of the scope completes the picture: the `cli:` ensemble/audit scheme, the audit CLI
transport, live-client exposure on the impact and spec-extraction command paths, and a
cross-provider ensemble/audit policy with per-role calibrated operating points.

Two dimensions of Work Item 3 are scoped here with rationale, so they are not silently dropped:

1. **Per-role FA/FR calibration.** The scope (§5) calls for running the existing translation
   benchmark corpus (`src/nlreq/translation_benchmark.py`, `src/nlreq/benchmark_corpus.py`,
   `src/nlreq/benchmark_reporting.py`, and the `benchmark-translation` CLI command) per candidate
   model per role, recording false-acceptance / false-refusal, and committing the chosen per-role
   operating points in config + ADR. This requires REAL model outputs. BOTH executable transports
   have been calibrated against real model outputs:
   - the Anthropic SDK path (`live:<model>`) on the English + multilingual corpora (no sidecar
     needed, executable in this environment); AND
   - the cross-provider CLI path (`cli:<wrapper>:tiny`) on the English corpus via `run-claude`
     (anthropic) + `run-gpt` (openai), now that the operator landed §6 for both (ADR 0204 §5).
   What remained future scope was the non-drafting roles (the translation corpus measures only
   the drafting front-half); CLOSED iter 3 (§4.1) with role-specific corpora + the `benchmark-role`
   harness, and the LIVE per-(role, model) run was EXECUTED iter 4 (§4.1, cross-provider CLI on
   all four roles x two providers). The harness (self-describing FA/FR report + per-role
   selector) is complete and proven executable end-to-end against real model outputs on both
   transports for drafting AND against real model outputs across all five roles (iter 4), plus
   recorded-discriminator corpora across all five roles.

2. **Operator wrapper-side §6 changes.** The wrappers (`run-claude` / `run-gpt` / `run-gemini` /
   `run-oss` / `run-oss-local`) live in a separate operator repository, not this one. nlreq's side
   of the contract — requiring the `<output>.meta.json` sidecar, enforcing `route == requested`,
   `tools_active is False`, and every provenance-critical field (fail-closed) — is implemented and
   pinned by the offline echo-wrapper conformance suite (`tests/test_cli_llm_client.py`). The
   operator landed §6 for `run-claude` + `run-gpt` (sidecar + pure-completion profile) on
   2026-06-25; `run-oss` / `run-oss-local` / `run-gemini` are marked attestation-ineligible (they
   refuse upfront under `NLREQ_ATTESTATION=1`, §5 below).

## Decision

### 1. Cross-provider ensemble and audit policy

- **Same-provider ensembles are the weak form.** An agreement gate that compares two models from
  the same family cannot catch correlated training bias — exactly the failure mode an agreement
  gate exists to catch. `live:claude-sonnet-4-6` + `live:claude-haiku-4-5` is a same-family
  ensemble; it is permitted but is documented as weak.
- **The recommended decomposition operating point is two providers.** `cli:run-claude` +
  `cli:run-gpt` (or any two distinct providers) is the recommended configuration; the package
  records two distinct providers, resolved model ids, wrapper hashes, and prompt versions
  (`ensemble_candidate_provenances`, acceptance #2). The single-provider `anthropic` default
  remains when unconfigured (ADR 0202's default-transport decision).
- **The audit transport diversifies the same way.** `--audit-client cli:<wrapper>` runs the audit
  on a different provider than the decomposition; `AuditVerdict.model_id` records which provider
  audited. A same-provider audit is the weak form, just as with the ensemble.
- **Disagreement remains a refusal — unchanged.** The ensemble trust check is unaltered: any
  divergence that is approved + audited triggers `REFUSED_AMBIGUOUS`; unaudited/unapproved
  divergence yields `needs_review`. The policy adds *which providers to compare*, not a new
  acceptance path.

### 2. Audit CLI transport (completed)

`CliLlmClient` implements the `AuditClient` protocol (`audit_decomposition`), so `--audit-client
cli:<wrapper>[:<tier>]` runs a cross-provider audit. The verdict's `model_id` is the
sidecar-resolved model id; an unparseable/schema-invalid response is a conservative failure
(mirrors `AnthropicAuditClient`). The verdict carries FULL CLI-transport provenance
(`client_kind`, `provider`, `route`, `wrapper`, `wrapper_hash`, `cli_version`, populated from
the validated sidecar) — no longer deferred. These fields are byte-stable (optional, None-default,
`exclude_none` serialization), so anthropic/recorded audit artifacts are unchanged; the full
verdict is content-addressed by the provenance graph node's `artifact_hash` and serialized in the
report's `ensemble_candidate_audit_verdicts`. The previously-deferred widening was subsequently
implemented (documented in ADR 0205); the resolved model id is no longer the only audit
provenance.

### 3. Live-client exposure (completed)

`--llm-client <scheme>` (live / recorded / cli, via the shared `_resolve_client_scheme` parser
and the per-role factory) is exposed on `intake-draft` (drafting), `spec-extract` and
`specula-extract` (extraction), and `python-source-impact-production` (impact). After a successful
cli call, `CliLlmClient.last_call_provenance()` is merged into the produced artifact's metadata
(resolved_model / provider / route / wrapper / wrapper_hash / prompt_version), recording the
sidecar-resolved model id rather than the tier (scope §4, acceptance #4). Default/anthropic/
recorded paths are untouched (byte-stability, acceptance #1).

### 4. Per-role calibration (BOTH transports EXECUTED 2026-06-25; non-drafting harness CLOSED iter 3)

The calibration ROUTING is wired (since iter 3): `benchmark-translation --run --llm-client <scheme>
[--model-config ...] [--role <role>]` builds the drafter through the per-role factory
(`_resolve_client_scheme` → `build_client_for_role`) and passes it to
`run_translation_corpus(corpus, client=...)`, so each case is drafted by that client instead of
its recorded output. `--role` selects the role under calibration (default `drafting`; ONLY `drafting` is
calibratable by THIS corpus — it measures the drafting front-half, so impact/extraction/decomposition/
audit are refused HERE and redirected to `benchmark-role` (§4.1); stamping a non-drafting role onto a
drafting measurement would be false provenance, previously masked only because every role's
prompt version was "0.1"). The report carries a self-describing
`calibration` block (role / client_kind / provider / resolved_model / wrapper identity /
prompt_version / transport_source) so the FA/FR tables stand alone without external filenames or
prose (recommended action #2).

**The Anthropic SDK drafting calibration was RUN (2026-06-25)** through `live:<model>` (the
`anthropic` transport, executable without a sidecar), against TWO corpora — the 66-case English
corpus (`corpus.json`, 2 domains × 33) and the 63-case multilingual corpus
(`multilingual.corpus.json`, 30 en + 33 pt — both meeting the §5 per-language ≥30 floor). Two
candidate models were measured on each.

**The cross-provider CLI drafting calibration was RUN (2026-06-25)** through `cli:<wrapper>:tiny`
(the `cli` transport, now executable once the operator landed §6 for `run-claude` + `run-gpt`),
against the 66-case English corpus via TWO DISTINCT providers: `run-claude` (anthropic,
claude-haiku-4-5) and `run-gpt` (openai, gpt-5.4-mini). Six self-describing reports are committed
under `benchmarks/translation-corpus/calibration/`:

Anthropic SDK transport, English corpus (66 cases, en only):

| model (drafting, anthropic)        | FA  | FR  | syntactic_validity | semantic_match | result |
|------------------------------------|-----|-----|--------------------|----------------|--------|
| `claude-haiku-4-5-20251001`        |  54 |   8 |              0.818 |          0.000 | failed |
| `claude-sonnet-4-5-20250929`       |   0 |  60 |              0.000 |          0.000 | failed |
| recorded release corpus (control)  |   0 |   0 |              1.000 |          1.000 | passed |

Cross-provider CLI transport, English corpus (66 cases, en only) — two DISTINCT providers:

| wrapper     | provider  | resolved model   | FA  | FR  | semantic_match | result |
|-------------|-----------|------------------|-----|-----|----------------|--------|
| `run-claude`| anthropic | claude-haiku-4-5 |  12 |  48 |          0.000 | failed |
| `run-gpt`   | openai    | gpt-5.4-mini     |  54 |   9 |          0.000 | failed |

(English per-domain — Anthropic SDK: haiku — procurement-approval FA=27/FR=4, protocol-safety
FA=27/FR=4; sonnet — procurement-approval FA=0/FR=30, protocol-safety FA=0/FR=30. Cross-provider
CLI: run-claude — procurement-approval FA=3/FR=27, protocol-safety FA=9/FR=21; run-gpt —
procurement-approval FA=26/FR=6, protocol-safety FA=28/FR=3. The recorded control is the existing
release corpus run; it confirms the harness discriminates — it is not a constant-zero instrument.)

Multilingual corpus (63 cases, en + pt, floor-satisfying), per-language FA/FR — Anthropic SDK transport:

| model                       | en cases | en FA | en FR | pt cases | pt FA | pt FR | semantic_match | result |
|-----------------------------|----------|-------|-------|----------|-------|-------|----------------|--------|
| `claude-haiku-4-5-20251001` |       30 |    26 |     4 |       33 |    28 |     2 |          0.000 | failed |
| `claude-sonnet-4-5-20250929`|       30 |     0 |    30 |       33 |     0 |    30 |          0.000 | failed |

(The multilingual corpus is a single-domain corpus; its pt slice now has 33 cases, meeting the
§5 per-language ≥30 floor — a full per-language calibration, no longer a below-floor spike. The
cross-provider CLI calibration is English-only — the floor-satisfying corpus; a multilingual CLI
run is optional future evidence.)

**Finding.** Under drafting-prompt v0.1 NO live model is a viable production drafter, on EITHER
transport or corpus. The failure modes are transport-characteristic and now calibrated across
providers:

- **Anthropic SDK + haiku** re-expresses claims in parseable-but-divergent predicate vocabulary
  (~82% false-acceptance en; ~86% en+pt multilingual): the alpha/commutative-normalised
  FormalClaim signature of a re-expressed draft diverges from the gold's exact predicate
  vocabulary, so the gate flags every re-expression as a wrong claim — the failure is
  language-independent.
- **Anthropic SDK + sonnet** ignores the DSL v3 grammar and emits "SHALL"-style natural-language
  prose (0% syntactic validity → ~91–100% false-refusal en+pt).
- **CLI + run-gpt (gpt-5.4-mini)** re-expresses claims (FA=54, 82% — the SAME re-expression
  failure mode as SDK haiku, now observed in a second provider family, confirming the failure is
  prompt-driven, not model-specific).
- **CLI + run-claude (claude-haiku-4-5 via the claude CLI `--bare` profile)** shifts toward
  false-refusal (FA=12/FR=48): the claude CLI transport produces output that parses less readily
  than the SDK path (FA 54→12, FR 8→48 for the same model family) — a real cross-TRANSPORT
  finding (the CLI `--bare` profile's formatting/system-prompt differs from the SDK path), and
  exactly the kind of transport-divergence evidence the cross-provider calibration exists to
  surface.

All four live configurations produce 0% semantic match. This is real, actionable calibration
evidence: the drafting prompt needs a format-eliciting revision (e.g. a concrete DSL v3 worked
example / few-shot) before live drafting can be calibrated to a viable operating point, and the
revision must be re-run across BOTH transports (the SDK and CLI profiles diverge).

**Operating-point decision.** Live drafting is NOT released: no model + prompt-v0.1 combination
meets a viable FA/FR budget on any transport or corpus (the release bar requires FA=0; every live
configuration exceeds it). The shipped default transport stays `anthropic` (ADR 0202) and the
release corpus remains recorded-only (the recorded path is the release-validated one). A
drafting-prompt revision is the tracked follow-up that MUST re-run this calibration (across both
transports) to a viable FA/FR budget before live drafting is released; that re-run is a
one-command operator action now that the harness is self-describing, role-parameterizable, and
cross-provider.

What remains future scope (cannot be executed against this corpus):

- **The decomposition / impact / extraction / audit roles** are not exercised by the translation
  corpus (it measures only the drafting front-half). **CLOSED iter 3 (harness + discriminator) and
  iter 4 (live run):** each non-drafting role has its OWN role-specific corpus + harness
  (`benchmark-role --role <role>`), committed recorded-discriminator evidence (iter 3), AND a
  committed LIVE per-(role, model) FA/FR run across two providers (iter 4, §4.1). The earlier
  scope-reduction framing (role-specific corpora as future scope, `--role <non-drafting>` refused)
  is SUPERSEDED — `benchmark-translation --role <non-drafting>` is still refused (the translation
  corpus is drafting-only) but redirects to `benchmark-role`. The methodological point stands
  — each non-drafting role has a different input/output/gold-standard shape (decomposition:
  IR-vs-gold; impact: module-set-vs-gold; extraction: invariant-vs-gold; audit: verdict-vs-gold)
  that the translation corpus does not contain — which is exactly WHY the role-specific corpora
  + harness in §4.1 were built rather than reusing the translation corpus.
- **The chosen per-role operating point (drafting only)** is the zero-config anthropic default —
  no live model met the bar, so no `nlreq-models.toml` role section is activated (the commented
  default IS the accepted operating-point record; activating a section would change no behaviour
  but would imply a viable live model, which the calibration contradicts). When a prompt revision
  produces a viable operating point, it is appended here and the role section is activated.

### 4.1 Non-drafting role calibration harness (CLOSED iter 3 harness + discriminator; LIVE run EXECUTED iter 4)

`src/nlreq/role_calibration.py` + the `benchmark-role` CLI command calibrate the four
non-drafting roles against role-specific discriminator corpora
(`benchmarks/role-calibration/<role>.corpus.json`, 12 cases each, 2 domains × [2 faithful +
2 FA + 2 FR], generated by `benchmarks/role-calibration/build_corpora.py`). The recorded run
replays each case's planted output offline and is the non-vacuity proof the harness discriminates:

| role          | input → output                  | false-acceptance             | false-refusal                |
|---------------|---------------------------------|------------------------------|------------------------------|
| decomposition | controlled → IR → FormalClaim sig | divergent signature accepted | IR refuses lowering          |
| audit         | (controlled, IR summary) → verdict | passed a faulty decomposition | failed a correct decomposition |
| impact        | (prose, symbols) → module set   | over-claimed a module        | missed a gold module         |
| extraction    | (module, code) → invariants     | invented an invariant        | missed a gold invariant      |

Committed recorded-discriminator reports (`benchmarks/role-calibration/calibration/`):
FA=4 / FR=4 / matched=4 / result=failed per role — the EXPECTED non-zero signal (a
constant-zero instrument would pass vacuously). The LIVE per-(role, model) FA/FR run was
EXECUTED iter 4 (`benchmark-role --run --llm-client cli:<wrapper>:tiny`, cross-provider CLI on
all four roles x two providers; reports under `benchmarks/role-calibration/live-calibration/`),
gated by `tests/test_role_calibration.py` (discriminator non-vacuity, corpus round-trip,
committed-report drift guards for BOTH the recorded discriminator and the live reports, CLI
provenance stamping + structured refusals + the iter-4 `CliTransportError`-propagation /
`--results`-validation guards). The zero-config default (anthropic, pinned models) remains the
shipped operating point for all five roles; no live non-drafting model is activated — every
role x provider exceeds the FA=0 / exact-match bar under prompt v0.1 (decomposition is the
closest, run-claude 11/12 matched; extraction the furthest, 0/12).

**`cli:<wrapper>:model=<id>` is verification-only by design (accepted narrowing).** The per-call
`cli:` scheme's `model=<id>` suffix is a fail-closed VERIFICATION guard — the sidecar must report
exactly that resolved model, else the call is refused — NOT per-call model selection. Per-call
model pinning needs wrapper-specific env-var knowledge (e.g. `CLAUDE_TINY_MODEL` vs
`GPT_TINY_MODEL`), which is the config/env `model_env` rung's job (`_CliSpec.model_env`,
ADR 0203); the per-call scheme deliberately does not hardcode wrapper internals. Provenance
always records the sidecar-resolved id, never the tier (scope §4). This is the accepted
closure of the scope's `cli:<wrapper>[:<tier-or-model>]` wording: `:<tier>` selects;
`:model=<id>` OR a bare `:<model-id>` verifies (the original grammar's shorthand — iter 2 made
the bare model suffix the same fail-closed verification guard rather than an ambiguous refusal).

This folds into Workstream 1 of `docs/operational-real-evidence-gap-closure-plan.md` (the
translation evidence run) — the calibration is existing open scope, now executable across BOTH
the Anthropic SDK transport AND the cross-provider CLI transport, and proven against real model
outputs. **Acceptance criterion #5 — split status (iter 2 revision):**
- **Drafting — CLOSED at the §5 floor.** The harness emits per-(model, transport) FA/FR tables
  for drafting on the English corpus (2 domains × 33 = 66, meeting the §5 per-domain ≥30 floor)
  AND the multilingual corpus (30 en + 33 pt, both meeting the §5 per-language ≥30 floor), on
  BOTH transports (Anthropic SDK + cross-provider CLI, §4). The chosen drafting operating point
  is committed in `nlreq-models.toml` + this ADR.
- **Non-drafting (decomposition / impact / extraction / audit) — discriminator + 12-case live
  run committed; floor-sized measurement PENDING (explicit owner-pending deviation).** The
  harness emits per-(role, model) FA/FR tables for all four non-drafting roles on 12-case
  role-specific discriminator corpora (2 domains × [2 faithful + 2 FA + 2 FR]) — a NON-VACUITY
  proof (planted FA→FA, planted FR→FR), NOT the §5 per-domain ≥30 floor-sized FA/FR measurement.
  The role-specific corpora exist and `benchmark-translation --role <non-drafting>` redirects to
  `benchmark-role`; there is no "needs role-specific corpora" gap, but the floor-sized
  (per-domain ≥30) non-drafting live measurement is NOT yet executed and is the remaining gap
  before the non-drafting dimension is closed WITHOUT deviation. Closing it is an operator
  action: expand each role-specific corpus to per-domain ≥30 and re-run `benchmark-role --run
  --llm-client cli:<wrapper>:tiny` across both providers.

**LIVE non-drafting role calibration — EXECUTED 2026-06-25 (iter 4)** (single-run snapshots,
temperature=0; low reasoning effort for run-gpt). 8 self-describing reports committed under
`benchmarks/role-calibration/live-calibration/` (12-case corpus per role, 2 domains ×
[2 faithful + 2 FA + 2 FR]) and guarded by `tests/test_role_calibration.py` (exact-count drift
guards + the cross-provider-per-role diversity guard):

| role          | wrapper     | provider  | resolved model   | matched | FA  | FR  | result |
|---------------|-------------|-----------|------------------|---------|-----|-----|--------|
| decomposition | run-claude  | anthropic | claude-haiku-4-5 |      11 |   0 |   1 | failed |
| decomposition | run-gpt     | openai    | gpt-5.4-mini     |      10 |   0 |   2 | failed |
| impact        | run-claude  | anthropic | claude-haiku-4-5 |       4 |   1 |   8 | failed |
| impact        | run-gpt     | openai    | gpt-5.4-mini     |       2 |   0 |  10 | failed |
| extraction    | run-claude  | anthropic | claude-haiku-4-5 |       0 |  12 |  12 | failed |
| extraction    | run-gpt     | openai    | gpt-5.4-mini     |       0 |  11 |  12 | failed |
| audit         | run-claude  | anthropic | claude-haiku-4-5 |       4 |   0 |   8 | failed |
| audit         | run-gpt     | openai    | gpt-5.4-mini     |       4 |   0 |   8 | failed |

(The wrapper hashes — run-claude `5524a2ab…`, run-gpt `0dd5aa27…` — match the drafting CLI
calibration + the committed ensemble artifact, so the non-drafting and drafting evidence share
provenance. `matched` for the set-valued roles (impact/extraction) means exact set equality; FA
and FR are not mutually exclusive there, so extraction's FA=11/12 AND FR=12/12 means every case
both invented and missed an invariant. `result=failed` is the expected non-viable signal under
prompt v0.1, exactly as with drafting — NOT a harness defect.)

**Finding (per-role, cross-provider).** Under each role's prompt v0.1 NO live model is a viable
production role-client on either provider (the release bar requires matched=all / FA=0):
- **decomposition is the strongest role** (run-claude 11/12, run-gpt 10/12 matched; FA=0) — the
  re-expression prompt elicits parseable DSL v3 that reproduces the gold FormalClaim signature in
  most cases; the only failures are 1–2 FR (a re-expression that did not lower). It is the closest
  role to a viable live operating point.
- **audit** is 4/12 matched with FA=0 but FR=8 on both providers — the auditor false-alarms correct
  decompositions (over-strict under prompt v0.1); it never passes a faulty decomposition.
- **impact** is mostly FR (missed modules): run-claude 4/12, run-gpt 2/12 matched; the estimator
  under-claims the affected set.
- **extraction is the weakest role** (0/12 matched on both providers, high FA AND FR) — the
  extractor both invents and misses invariants on every case; it needs the most prompt work.
The failure modes are prompt-driven and largely provider-independent (run-claude and run-gpt
agree on which role is strong/weak), confirming the cross-provider calibration surfaces
prompt-level signal rather than model-specific noise.

**Operating-point decision (non-drafting).** No live non-drafting model is activated — every
role × provider exceeds the FA=0 / exact-match bar under prompt v0.1. The zero-config default
(anthropic, pinned models) remains the shipped operating point for all five roles (the recorded
path is the release-validated one). decomposition is the tracked first-releasable live role: a
decomposition-prompt revision that closes the 1–2 FR cases (re-run across both providers via
`benchmark-role --run --llm-client cli:<wrapper>:tiny`) could make it the first viable live
role-client. extraction is the furthest and needs the most prompt work. The chosen per-role
operating points are recorded in `nlreq-models.toml` (no role section activated — the commented
default IS the accepted record; activating a section would imply a viable live model, which the
calibration contradicts).

### 5. Operator wrapper-side §6 contract (EXECUTED for run-claude + run-gpt; others ineligible)

The operator repository MUST, for each wrapper, emit `<output>.meta.json` with the
provenance-critical fields (`provider`, `resolved_model`, `route`, `tools_active`, `wrapper`,
`wrapper_hash`, `cli_version`, `duration_s`) and honor the pure-completion profile (no tools, no
cwd/repo context, no silent fallback — `OSS_SOFT_FALLBACK=0`). nlreq's fail-closed sidecar
validation refuses any wrapper that omits a field or reports `tools_active=true` / a route
mismatch, so an ineligible wrapper cannot produce an accepted draft.

**Status (empirically verified 2026-06-25):**

- **`run-claude` — §6-ELIGIBLE.** Under `NLREQ_ATTESTATION=1` it runs `claude --bare --tools ""`
  (no CLAUDE.md/hooks/auto-memory/keychain/plugin-sync context; `--tools ""` disables ALL built-in
  tools — verified, a random-token file is NOT leaked), sources the operator `.env` for API-key
  auth, and emits `<output>.meta.json` (provider=anthropic, resolved_model, route=official,
  tools_active=false, wrapper_hash). The caller's scratch empty cwd defeats any residual
  cwd-context auto-load. Round-trips through `CliLlmClient` (real-wrapper test, opt-in).
- **`run-gpt` — §6-ELIGIBLE.** Under `NLREQ_ATTESTATION=1` it runs `codex exec` with every
  tool-bearing feature disabled (`shell_tool` / `unified_exec` / `browser_use` / `computer_use`
  — verified, the model reports "no shell execution tool is available"), read-only sandbox
  (defence in depth), `--ignore-rules` / `--ignore-user-config` (no project/user context), low
  reasoning effort (attestation calls are pure completions, not agentic reasoning), and emits the
  sidecar (provider=openai, resolved_model, route=official, tools_active=false, wrapper_hash).
  Round-trips through `CliLlmClient` (real-wrapper test, opt-in).
- **`run-oss` / `run-oss-local` — attestation-INELIGIBLE.** pi-based and agentic: pi requires at
  least one tool per request (DashScope rejects empty tools arrays; `--no-tools` was removed), so
  the no-tools contract CANNOT be honored. Under `NLREQ_ATTESTATION=1` they refuse UPFRONT (exit
  2, clear stderr, zero egress, no model call) — nlreq's `CliLlmClient` raises
  `CliTransportError` (a structured refusal, acceptance #3).
- **`run-gemini` — attestation-INELIGIBLE.** Agentic (`--approval-mode=yolo`) with no verified
  no-tools/no-context pure-completion knob. Under `NLREQ_ATTESTATION=1` it refuses UPFRONT
  (exit 2, zero egress). Eligibility can be added later if a real gemini no-tools/no-context knob
  is verified and a sidecar emitted.

The agentic legacy paths (NLREQ_ATTESTATION unset) are byte-unchanged — the sidecar + pure
profile are opt-in per call, so ralph/ACP are unaffected. The in-repo closure of acceptance #2 is
the committed real two-provider ensemble artifact
(`benchmarks/cross-provider-ensemble/20260625134538-cross-provider-ensemble-run-claude-run-gpt.json`,
two distinct providers anthropic+openai, resolved model ids, wrapper hashes, prompt versions),
guarded by `tests/test_cli_llm_client.py::test_committed_cross_provider_ensemble_evidence_records_two_distinct_providers`;
the opt-in real-wrapper tests assert the live round-trips for both eligible wrappers and the
two-provider ensemble.

## Alternatives Considered

- **Ship a default `cli` transport.** Rejected (ADR 0202): wrappers are operator-private, not
  shipped; the API default carries exact snapshot ids (highest-precision provenance). Operators
  make `cli` their effective default via machine-level config/env.
- **Run calibration now with recorded fixtures.** Rejected: recorded fixtures replay canned
  outputs — they cannot measure a live model's FA/FR, which is the point of calibration. The
  measurement is only meaningful against real model outputs (now executed on both transports).
- **Widen `AuditVerdict` to record full wrapper identity.** Initially rejected as a byte-stability
  risk for existing audit artifacts; subsequently IMPLEMENTED (documented in ADR 0205):
  `AuditVerdict` now carries `client_kind`/`provider`/`route`/`wrapper`/
  `wrapper_hash`/`cli_version` (optional, None-default, `exclude_none` serialization —
  anthropic/recorded artifacts unchanged), populated from the validated sidecar by
  `CliLlmClient.audit_decomposition`. The resolved model id is no longer the only audit
  provenance; a cross-provider audit records WHICH provider audited and under which wrapper
  identity.
- **Make run-oss/run-oss-local/run-gemini eligible by passing a single harmless tool.** Rejected:
  the pure-completion contract is "no tools"; a tool-bearing call reports `tools_active=true` and
  is refused by the fail-closed sidecar guard. The honest outcome is the upfront ineligibility
  refusal (zero egress), not a faked `tools_active=false`.

## Consequences

- The cross-provider ensemble and audit are reachable, policy-documented, and calibrated;
  same-provider is the explicitly weak form, two providers is the recommended operating point.
- **Acceptance #2 is MET:** the committed real `cli:run-claude` + `cli:run-gpt` ensemble artifact
  records two distinct providers (anthropic + openai), resolved model ids, wrapper hashes, and
  prompt versions.
- **Calibration is EXECUTED on both transports, not deferred:** per-(model, transport) FA/FR
  tables for the English corpus (Anthropic SDK + cross-provider CLI) and the multilingual corpus
  (Anthropic SDK) are committed under `benchmarks/translation-corpus/calibration/` and guarded by
  a regression test (incl. exact-count drift guards, recommended action #4); the chosen drafting
  operating point (the zero-config anthropic default — no live model met the bar on any transport)
  is recorded in `nlreq-models.toml` and here.
- **Wrapper-side §6 is landed for `run-claude` + `run-gpt`** (sidecar + pure-completion profile);
  `run-oss` / `run-oss-local` / `run-gemini` are attestation-ineligible and refuse upfront. The
  nlreq side of the contract (self-describing, role-parameterizable harness + fail-closed sidecar
  validation) is in place and tested on both transports.
- **Future scope (not silently missing):** (1) the floor-sized (per-domain ≥30) non-drafting
  live calibration — the 12-case discriminator corpora are an explicit owner-pending deviation
  from the §5 floor (§4.1), not a fully-closed floor-sized measurement; and (2) an optional
  multilingual CLI calibration run (the committed drafting + non-drafting corpora are
  English/single-language). The LIVE non-drafting role calibration run is EXECUTED iter 4 (§4.1,
  on the 12-case discriminator); the recorded-discriminator harness + corpora are CLOSED iter 3.
  When a prompt revision (drafting or any non-drafting role) produces a viable operating point,
  it is re-run across both transports / both providers via `benchmark-translation` /
  `benchmark-role` (expanded to the §5 floor for non-drafting) and appended here + activated in
  `nlreq-models.toml`.

## Calibration results

**Anthropic SDK drafting calibration — EXECUTED 2026-06-25** (single-run snapshots, temperature=0).
Self-describing reports committed under `benchmarks/translation-corpus/calibration/` and guarded
by `tests/test_translation_corpus.py` (schema/provenance/language coverage + exact-count drift
guards).

English corpus (66 cases, 2 domains × 33, en only):

| role     | transport | model                        | FA  | FR  | syntactic | semantic_match | viable? |
|----------|-----------|------------------------------|-----|-----|-----------|----------------|---------|
| drafting | anthropic | claude-haiku-4-5-20251001    |  54 |   8 |     0.818 |          0.000 | NO      |
| drafting | anthropic | claude-sonnet-4-5-20250929   |   0 |  60 |     0.000 |          0.000 | NO      |
| drafting | recorded  | (release corpus control)     |   0 |   0 |     1.000 |          1.000 | YES (release) |

**Cross-provider CLI drafting calibration — EXECUTED 2026-06-25** (single-run snapshots,
temperature=0; low reasoning effort for run-gpt). English corpus (66 cases, en only), two
DISTINCT providers:

| role     | transport | wrapper     | provider  | resolved model   | FA  | FR  | semantic_match | viable? |
|----------|-----------|-------------|-----------|------------------|-----|-----|----------------|---------|
| drafting | cli       | run-claude  | anthropic | claude-haiku-4-5 |  12 |  48 |          0.000 | NO      |
| drafting | cli       | run-gpt     | openai    | gpt-5.4-mini     |  54 |   9 |          0.000 | NO      |

(The CLI transport records the sidecar-resolved model id — the tier-resolved id from
`models.env`, not the API's full snapshot id; that is the CLI transport's provenance precision,
distinct from the SDK transport's exact snapshot id. The wrapper hashes — run-claude
`5524a2ab…`, run-gpt `0dd5aa27…` — match the committed ensemble artifact, so the calibration and
the ensemble share provenance. run-gpt's FA=54 reproduces the SDK-haiku re-expression failure in
a second provider family; run-claude's FR=48 surfaces a transport-divergence: the claude CLI
`--bare` profile parses less readily than the SDK path for the same model family.)

Multilingual corpus (63 cases, 30 en + 33 pt, Anthropic SDK transport), per-language:

| role     | model                        | en FA | en FR | pt FA | pt FR | semantic_match | viable? |
|----------|------------------------------|-------|-------|-------|-------|----------------|---------|
| drafting | claude-haiku-4-5-20251001    |    26 |     4 |    28 |     2 |          0.000 | NO      |
| drafting | claude-sonnet-4-5-20250929   |     0 |    30 |     0 |    30 |          0.000 | NO      |

(The pt slice now has 33 cases, meeting the §5 per-language ≥30 floor — a full per-language
calibration, no longer a below-floor spike. Haiku's pt FA rate (0.848) tracks its en rate (0.867):
the re-expression failure is language-independent. Sonnet's pt FR (0.91) is slightly below its en
FR (1.0): a few pt drafts happened to parse.)

**Operating point chosen:** the zero-config anthropic default (ADR 0202), with the release
corpus recorded-only. No live model + drafting-prompt v0.1 combination is viable on ANY transport
or corpus (SDK haiku ~86% FA en+pt; SDK sonnet ~91–100% FR en+pt; CLI run-gpt 82% FA; CLI run-claude
73% FR; all 0% semantic match). Live drafting is NOT released; a drafting-prompt revision must
re-run this calibration (across BOTH transports) to a viable FA/FR budget before release. The
chosen drafting operating point is recorded in `nlreq-models.toml` (no role section activated —
the commented default IS the accepted record).

**Remaining (future scope):** (1) the floor-sized (per-domain ≥30) non-drafting live calibration
— the committed non-drafting evidence is a 12-case discriminator per role, an explicit
owner-pending deviation from the §5 floor (§4.1), not a floor-sized measurement; and (2) an
optional multilingual CLI calibration run (the committed corpora are English/single-language).
The LIVE non-drafting role calibration run is EXECUTED iter 4 (§4.1, cross-provider CLI on all
four roles × two providers, on the 12-case discriminator); the recorded-discriminator harness +
corpora are CLOSED iter 3. The harness is complete, self-describing, and proven executable
against real model outputs on both the Anthropic SDK and cross-provider CLI transports (drafting,
floor-sized) and against real model outputs across all five roles (drafting + the four
non-drafting roles, the latter on the 12-case discriminator), plus recorded-discriminator corpora
across all five roles.
