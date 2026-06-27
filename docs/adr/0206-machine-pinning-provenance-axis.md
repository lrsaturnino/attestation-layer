# ADR 0206: Machine Pinning as a Provenance Axis

## Status

Accepted and shipped (three-zone scope P1–P4). The machine-pinning provenance axis is fully
implemented: the `PinningProvenance` model and its construction guards, the
`MACHINE_PINNED_PENDING_REVIEW` status category, the replacement of the six
`status.startswith("ACCEPTED")` prefix checks with an explicit acceptance category, the opt-in
routing + stamping path (`machine_agreement.route_machine_pinning` →
`package.build_package(pinning=...)`, which emits a `machine_agreement` record and a `needs_review`
review instead of a fabricated `approved` `review.json`), the default-deny per-path hard gate
(`gate.GateMachinePinRules` / `gate._machine_pin_accepts`), and the upward-only promotion path
(`package.promote_machine_pinned_package`). All of it is OFF by default: with no
`--machine-pin-policy` / `NLREQ_MACHINE_PIN` configured the pipeline is byte-identical to the
pre-machine-pinning pipeline (acceptance #1).

The companion decisions this scope owns beyond the per-role dependency are recorded in ADR 0207
(spec partitioning as proposal-only with deterministic total segmentation and the `partition`
role) and ADR 0208 (the `machine_agreement` trust state, provider-family metadata, ensemble-FA
calibration, and deterministic threshold derivation).

## Context

The three-zone spec-attestation automation scope (v3, "nlreq — Three-Zone Spec-Attestation
Automation + Machine-Pinning Provenance") lets the automation advance a rule past the human
approval gate when an ensemble of independent, cross-provider models agrees and all deterministic
checks pass — but records that rule as **machine-pinned**, a provenance kind strictly distinct from
human review and from any deterministic `EvidenceLevel`. The objective is *less* human intervention,
not zero: a one-command pipeline that emits a single human queue containing only ambiguous,
contradictory, low-agreement, or unmodeled-legacy rules, while clean rules flow through under an
explicit machine-pinning provenance.

An independent read-only vet (fugu-ultra, report at
`01-claude-filebin/reviews-and-audits/20260624205936-three-zone-spec-vet-fugu-ultra.md`) rejected the
prior v2 design on two concrete, code-verified grounds:

1. **`EvidenceLevel` is an exact-match label set, not an assurance ladder** (`models.py`:
   `EvidenceLevel` enum; `decide_status` equality at `status.py:60-78`). Adding a `MACHINE_DRAFTED`
   member "ordered below `REVIEWED`" had no operational effect and conflated *who pinned the meaning*
   with *what tool produced evidence*.

2. **An `ACCEPTED`-prefixed machine status is silently treated as accepted** by six existing
   consumers that check `status.startswith("ACCEPTED")` (`agent_workflow.py:374,465,498`;
   `continuous.py:680`; `adoption.py:548,723`).

This ADR records the corrected design and the conscious, opt-in-only supersession of two prior
invariants it entails.

## Decision

### 1. Machine pinning is a provenance axis DISTINCT from `EvidenceLevel`

A new `PinningProvenance` record (`models.py`) carries `kind ∈ {human_review, machine_agreement}`.
For `machine_agreement` it carries the ensemble-evidence object (`EnsembleEvidence`: the member set,
resolved model ids, provider families, agreement result, per-member audit verdicts, and the policy
content hash). It does **not** live inside `EvidenceLevel`; the deterministic evidence labels
(`SMT_CHECKED`, `PROVEN_INDUCTIVE`, `BOUNDED_CHECKED`, …) are untouched. Machine pinning concerns
only *who pinned the meaning* of a controlled requirement; it never substitutes for a deterministic
proof level (scope non-goal).

### 2. No faked human review

A machine-pinned package MUST NOT carry the default fabricated `approved` `review.json`
(`package.py:_review`, `phase<N>@example.invalid`). The `PinningProvenance` record is the honest
carrier instead. A construction-time guard (modeled on `_has_proof_artifact` /
`_has_proof_assistant_identity`) makes a `machine_agreement` record unrepresentable without its
ensemble-evidence object, and a `human_review` record unrepresentable without a REAL review event —
the actual `ReviewArtifact` that performed the review, carried INLINE as `review_event` and
required to carry `review_origin="human"` (so `is_real_human_review` is True). Carrying the event
INLINE (symmetric with the inline `ensemble` on a machine pin) makes scalar-only construction
(`review_id` + `reviewer` + a hash with no event) unrepresentable: `review_id` / `reviewer` /
`reviewed_artifact_hash` are read-only accessors DERIVED from the embedded event, so the pin's
references and its backing event can never disagree. The `ReviewArtifact` construction guard makes
a `review_origin="human"` event unrepresentable under a placeholder reviewer
(`phase<N>@example.invalid`, via `_is_placeholder_reviewer`), so no fabricated per-language approval
can be represented as real human-review provenance. The two kinds are mutually exclusive.

The companion positive contract lives on `ReviewArtifact` itself: a `review_origin` field
(`"human"` | `"package_builder"`) labels every fabricated package-builder `review.json` as
`"package_builder"` (explicitly non-human — the default, so legacy reviews are honestly non-human
too), and a construction guard makes a `"human"` origin unrepresentable under a placeholder
reviewer. `is_real_human_review(review)` is the positive predicate consumers use. Acceptance #5 is
therefore fully satisfied at BOTH axes — a fabricated package-builder review can neither be labeled
human (`ReviewArtifact`) nor back a `human_review` pin (`PinningProvenance`), and a `human_review`
pin cannot be held without the real review event itself (not merely a reference to one).

**AC1 byte-identity (acceptance #1).** `review_origin` is carried at the MODEL level (a
`ReviewArtifact` default of `"package_builder"`), NOT serialized by the default package builders,
so the default pipeline output is byte-identical to the pre-machine-pinning pipeline — loading a
fabricated `review.json` yields the explicitly non-human origin without changing the default
output bytes. The four committed `requirements/*/review.json` therefore carry no `review_origin`
key, and a byte-drift regression test (`tests/test_review_provenance.py`) pins the pre-P1 shape so
a future iteration cannot silently reintroduce the default-off byte drift.

**Category-2 review checks — AC1 baseline (not a deferral).** The review-required paths
(`hard-gate`, `adoption`, `agent_workflow`) gate on `review["decision"] == "approved"` rather than
`is_real_human_review`. Tightening them would break the default path: every default package
carries the fabricated package-builder approval, and requiring `is_real_human_review` would reject
it — a direct violation of acceptance #1 (the default pipeline must pass byte-identically). This
is the PERMANENT AC1 baseline posture, not a deferral: the scope (§2) preserves the default
fabricated-approval path and only forbids MACHINE packages from faking review. The genuine
concern — a machine pin backed by a fabricated approval — is enforced at the load-bearing
provenance axis, not at these gate sites: a machine-pinned package carries a `needs_review`
review (never `approved`), and `validate_package` REFUSES a machine-pinned package with an
`approved` review (§2), so a machine pin can never exploit the category-2 check. The AC1 baseline
is pinned by a regression test (`tests/test_machine_pinning_gate.py`) and documented at each of
the five call sites (`gate.py`, `adoption.py` ×3, `agent_workflow.py`).

**Machine pin bound to the packaged meaning.** A `machine_agreement` pin's
`EnsembleAgreementResult.agreement_hash` MUST equal the canonical hash of the package's
controlled text (the parser-normalized form). `build_package` refuses a pin whose hash does not
match at build time, and `validate_package` re-checks the binding on load, so a pin can never be
stamped on (or silently drift from) a package whose meaning differs from what the ensemble agreed
on.

**Changed-path policy in the stamped policy hash.** The default-deny changed-path admission
policy (scope §6) lives inside `MachinePinPolicyRules.changed_path_policy`, so the `policy_hash`
stamped on a pin covers BOTH the ensemble/calibration rules AND the path policy that admitted it
— the pin records exactly which path policy admitted it, not just the ensemble rules.

### 3. A distinct, non-`ACCEPTED` status

`decide_status` (`status.py`) is extended with an optional `pinning: PinningProvenance | None = None`
parameter (default `None`, so every existing caller is byte-identical). When a package is
machine-pinned it resolves to `MACHINE_PINNED_PENDING_REVIEW` — a `FinalStatus` member that
deliberately does **not** start with `ACCEPTED` — in BOTH non-refusal branches: the all-evidence-
satisfied branch (which would otherwise be `ACCEPTED_WITH_EVIDENCE`) and the evidence-gap /
pending-review branch (which would otherwise be `ACCEPTED_FOR_IMPLEMENTATION_WITH_REVIEW`). The
evidence gap is still surfaced in `next_actions` (machine pinning never substitutes for a proof
level, so the gap is not hidden), only the status is non-`ACCEPTED`. Deterministic refusals are
unchanged: a machine-pinned package with an ambiguous / unbound / unsupported / failed / timeout /
needs-coverage signal still refuses exactly as a human-reviewed package would (those statuses do
not start with `ACCEPTED`). Acceptance #3 is therefore unconditional: a machine-pinned package is
NEVER resolved to a status that starts with `ACCEPTED`. `ACCEPTED_WITH_EVIDENCE` is kept
exclusively for human-reviewed / deterministically-closed packages.

### 4. Replace the six prefix checks with an explicit acceptance category

The six `status.startswith("ACCEPTED")` sites are converted to `nlreq.status.is_human_accepted`, an
explicit `frozenset` membership check over exactly `{ACCEPTED_WITH_EVIDENCE,
ACCEPTED_FOR_IMPLEMENTATION_WITH_REVIEW}`. A machine-pinned status is not in the set, so the six
consumers never silently treat it as human-accepted — *and* a future `ACCEPTED`-prefixed machine
status could not slip through a prefix check. Per-call-site regression tests
(`tests/test_machine_pinning_acceptance.py`) pin this for each of the six sites (acceptance #3).

### 5. Default-deny per-path gate

`hard-gate` accepts a machine-pinned status (`MACHINE_PINNED_PENDING_REVIEW`) **only** for a change
whose EVERY changed path matches an explicit low-risk allow-list pattern AND none matches the
block-list (auth / funds / other sensitive surfaces). This is the default-deny per-path gate
`gate.GateMachinePinRules` / `gate._machine_pin_accepts`: an unmatched path, a mixed-risk change,
and every auth/funds path require a human `REVIEWED` package (acceptance #4). Evidence-level
requirements are unchanged — machine pinning never substitutes for a deterministic proof level, so
the `minimum_evidence` check still runs on a machine-pinned package.

The gate is OFF by default: `GateMachinePinRules.enabled` defaults to `False`, which blocks a
machine-pinned status on EVERY path (the safe floor), and the `GatePolicy.allowed_statuses` default
remains `[ACCEPTED_WITH_EVIDENCE]`. A machine pin is admitted ONLY per-path via the dedicated
`machine_pin` section, NEVER globally via `allowed_statuses`: a `GatePolicyRules` validator REFUSES
`MACHINE_PINNED_PENDING_REVIEW` in `allowed_statuses`, so an operator cannot blanket-allow it across
every path (which would bypass the per-path allow-list that keeps it off sensitive surfaces). The
disabled-default posture is regression-tested in `tests/test_machine_pinning_gate.py` (the validator
refusal + the status blocked on generic, auth, and funds paths); the enabled per-path behavior
(allow-listed accept, unmatched / mixed / auth / funds block) is tested end-to-end against REAL
machine-pinned packages in `tests/test_machine_pin_default_deny_gate.py`.

### 6. Promotion only upward

A human may later review a machine-pinned rule to `human_review` / `REVIEWED`; the reverse never
happens. Promotion is upward only in BOTH senses: machine→human, and only on an **approval**. The
production promotion path is `promote-machine-pin` (`package.promote_machine_pinned_package`):
given an **approved** real human `ReviewArtifact` (`review_origin="human"`, non-placeholder reviewer,
`decision="approved"`) whose `requirement_ir` hash matches the package's IR, it constructs a
`human_review` pin bound to that IR hash, re-resolves the status (a fully-evidenced package resolves
to `ACCEPTED_WITH_EVIDENCE`), and rewrites the package's `pinning-provenance.json` / `review.json` /
`status.json`. A `rejected` or `needs_review` human review is refused and leaves the package
machine-pinned, unchanged — a human rejection never resolves to a human acceptance. This invariant is
enforced at three layers: the `PinningProvenance(kind="human_review")` construction guard (a
non-approved review cannot back the pin), the `promote_machine_pinned_package` precondition (a
no-write refusal), and `validate_package` (the on-disk `review.json` must equal the pin's embedded
event and be an approved real human review, catching post-hoc drift). The machine-pin
policy's changed-path admission gate is load-bearing at routing time: `route_machine_pinning` calls
`machine_pin_admits_changed_paths` before constructing a pin, so the stampable `policy_hash`
records which path policy admitted the pin.

### 7. Partition span contract — BOTH code-point and UTF-8 byte spans

`SpecPartitionArtifact` segments carry **two** spans: a code-point span (`[start, end)`) and a UTF-8
byte span (`[byte_start, byte_end)`). The scope's acceptance criterion 6 phrases totality as "every
**byte** in exactly one segment"; an earlier revision recorded the operative unit as the code point
only (because `document[start:end] == segment.text` and `str` indexing are code-point-based, and you
cannot slice a `str` by byte offsets). That left AC6's literal "byte" wording unmet for
byte-oriented consumers. The resolution carries BOTH units rather than choosing one:

- the **code-point** span keeps the in-process `str` round-trip exact (`document[start:end] ==
  segment.text`), and
- the **byte** span makes AC6 literally provable — the union of every `[byte_start, byte_end)` is
  exactly `[0, len(document.encode("utf-8")))`, so EVERY BYTE is in exactly one classified segment,
  and `segment_text_from_bytes(document, segment)` (the byte-offset round-trip helper) recovers the
  same text the code-point span yields.

For ASCII documents the two spans coincide; for multibyte text `byte_end - byte_start >= end -
start`. `test_segmentation_totality_and_round_trip_hold_for_non_ascii` pins BOTH totalities and BOTH
round-trips with a CJK + accented-Latin + emoji document whose byte length strictly exceeds its
character length. Candidate-rule spans remain code-point offsets (a candidate is located inside a
segment by `str` search for the human to jump to; byte totality is a property of the *segmentation*,
which is the completeness oracle AC6 names).

## Supersession of prior invariants (opt-in only)

This scope consciously relaxes — **for the opt-in path only** — two prior invariants:

- **README invariant** (`README.md:79`): "The LLM **never produces evidence, never decides a status,
  and never approves anything.**" Under the opt-in machine-pin policy, an ensemble of LLMs *pins the
  meaning* of an unambiguous rule (a provenance act, recorded as `machine_agreement`), and
  `decide_status` resolves the package to `MACHINE_PINNED_PENDING_REVIEW`. The LLM still never
  produces evidence and never decides a status in the sense the invariant guards: every *evidence*
  verdict still comes from deterministic tools (the Lark parser, Z3, cvc5, Apalache, real test
  runners, real trace readers), and the machine status is deliberately non-`ACCEPTED` so it is never
  an approval. But "never … approves anything" is superseded for the opt-in path in the narrow sense
  that machine pinning advances a rule past the human approval gate without a human review event.

- **Per-role non-goal** (ADR 0203:120): "LLM output remains proposal-only on every transport; no
  auto-acceptance anywhere." The opt-in `machine_agreement` trust state is an auto-advance *of the
  pinning of meaning*, gated on ≥2 cross-provider families agreeing, passing audit verdicts, all
  deterministic checks, and a default-deny path allow-list — never an auto-acceptance of evidence or
  of a high-risk path.

Both supersessions are **opt-in only**: with machine pinning disabled (the default), the pipeline is
byte-identical to today — every rule routes to a human, no pinning record is emitted, and both
invariants hold unchanged (acceptance #1). This ADR is the explicit record of the supersession
against both statements, as the scope (§2, §10) requires.

## What this ADR records (P1–P4)

- `FinalStatus.MACHINE_PINNED_PENDING_REVIEW` (non-`ACCEPTED`-prefixed).
- `_is_content_hash` helper + `_PHASE0_PLACEHOLDER_REVIEWER` constant + `EnsembleMember`,
  `EnsembleAgreementResult`, `EnsembleAuditVerdict`, `EnsembleEvidence`, `PinningProvenance` models
  with construction guards. The `human_review` guard requires the actual `ReviewArtifact` carried
  inline as `review_event` with `review_origin="human"` (scalar-only construction is
  unrepresentable; `review_id`/`reviewer`/`reviewed_artifact_hash` are derived read-only accessors);
  `EnsembleMember` / `EnsembleAuditVerdict` reject blank/whitespace identifiers (a blank
  `provider_family` could otherwise inflate the distinct-family count); `EnsembleEvidence` requires
  unique member ids, unique audit-verdict member ids, and exact 1:1 correspondence between them
  (no silent dict collapse of duplicates or extras).
- `decide_status(evidence, pinning=None)` extension (a machine-pinned package resolves to
  `MACHINE_PINNED_PENDING_REVIEW` in BOTH non-refusal branches) + `HUMAN_ACCEPTED_STATUSES` /
  `is_human_accepted`.
- The six prefix-check replacements in `adoption.py`, `continuous.py`, `agent_workflow.py`.
- The opt-in routing + stamping path: `machine_agreement.route_machine_pinning` decides
  machine-pin-vs-human from the measurable signals and constructs the `machine_agreement` record;
  `package.build_package(pinning=...)` stamps it onto a package alongside a `needs_review` review
  (never a fabricated `approved` one) and binds the pin's `agreement_hash` to the packaged
  controlled text; `package.validate_package` re-checks that binding and refuses a machine pin
  carrying an `approved` review. (The contracts the routing depends on — provider-family metadata,
  the ensemble-FA calibration, and deterministic threshold derivation — are recorded in ADR 0208.)
- The default-deny per-path hard gate `gate.GateMachinePinRules` / `gate._machine_pin_accepts`, and
  the `GatePolicyRules` validator that REFUSES `MACHINE_PINNED_PENDING_REVIEW` in `allowed_statuses`
  so a machine pin is admitted ONLY per-path (never blanket-allowed globally).
- The upward-only promotion path `package.promote_machine_pinned_package`: a real human
  `ReviewArtifact` (`review_origin="human"`, non-placeholder reviewer) whose IR hash matches the
  package promotes a `machine_agreement` pin to `human_review` and re-resolves the status; the
  reverse never happens.
- Regenerated JSON schemas (`gate-policy.schema.json`, `status-decision.schema.json`, and the
  committed `pinning-provenance.schema.json`) — the new status appears in the `FinalStatus` enum;
  the gate's default allow-set is unchanged. `pinning-provenance.schema.json` is registered in
  `scripts/generate_schema.py` and asserted in `tests/test_schema.py` so future schema drift is
  caught.
- Tests: construction guards including the placeholder-reviewer rejection and the tightened
  ensemble validation (`tests/test_models.py`), the `decide_status` branch (both non-refusal
  branches resolve to the non-`ACCEPTED` status) + `is_human_accepted` (`tests/test_status.py`),
  the six per-call-site regressions (`tests/test_machine_pinning_acceptance.py`), the package
  stamping path (`tests/test_machine_pinning_package.py`), the AC5 fabricated-review provenance
  guards (`tests/test_review_provenance.py`), the disabled-default gate posture
  (`tests/test_machine_pinning_gate.py`), and the enabled per-path default-deny gate against real
  machine-pinned packages (`tests/test_machine_pin_default_deny_gate.py`).

## Alternatives Considered

- **`MACHINE_DRAFTED` as a member of `EvidenceLevel` + an `ACCEPTED_MACHINE_DRAFTED` status (v2).**
  Rejected by the vet (see Context): `EvidenceLevel` is an exact-match label set, not an assurance
  ladder, so "ordered below `REVIEWED`" had no operational effect and conflated provenance with
  evidence; and an `ACCEPTED`-prefixed status is silently accepted by the six prefix-check consumers.

- **A policy over the existing approval-gated ensemble/agreement primitives.** Rejected (scope §3):
  the existing primitives gate on *prior human approval* (`decomposition_client`, `translator_agreement`,
  `semantic_translation._is_trusted_candidate` all require `approval.status == "approved"` plus a
  passing audit, else `needs_review`). Auto-advance acts *before* human approval, so it cannot reuse
  them unchanged. `machine_agreement` is a distinct trust state that reuses only the agreement
  *computation*, replacing the human-approval precondition with its own explicit requirements.

- **Ship a usable-but-uncalibrated machine-pin tier up front.** Rejected (scope §10): the axis
  landed first as a schema reservation with no stamping path precisely because legitimate machine
  pinning needs the cross-provider transport and ensemble-FA calibration. Shipping a tier before
  calibration would let uncalibrated ensembles pin meanings; the stamping path was wired only once
  the calibration and deterministic threshold derivation (ADR 0208) existed, and `route_machine_pinning`
  refuses to auto-advance any ensemble whose configuration the committed calibration did not measure.

- **Widen `EvidenceLevel` with the ensemble-evidence object.** Rejected: it would conflate *who
  pinned the meaning* with *what tool produced evidence* (the vet's first rejection ground) and
  complicate the exact-match label set.

## Consequences

- The machine-pinning provenance axis is implemented with construction guards that make an
  evidence-less machine pinning impossible to hold in memory, and a fabricated package-builder
  review impossible to represent as real human-review provenance at EITHER axis (acceptance #5):
  the `ReviewArtifact` honestly labels every fabricated `review.json` `review_origin="package_builder"`
  (non-human, carried at the model level so the default output stays byte-identical — acceptance
  #1), and a `human_review` pin is unrepresentable without the real `ReviewArtifact` carried inline
  with `review_origin="human"` (not merely a scalar reference).
- A machine-pinned package resolves to a non-`ACCEPTED` status in BOTH non-refusal branches, and all
  six former prefix-check consumers treat it as not-human-accepted (acceptance #3), with per-call-site
  regression tests.
- The hard gate is default-deny per-path: `gate._machine_pin_accepts` admits a machine-pinned status
  only when the `machine_pin` section is enabled AND every changed path is on the low-risk allow-list
  and none on the block-list, so an unmatched, mixed-risk, auth, or funds path requires a human
  `REVIEWED` package (acceptance #4). With the section disabled (the default) the status is blocked
  on every path, and a `GatePolicyRules` validator refuses `MACHINE_PINNED_PENDING_REVIEW` in
  `allowed_statuses` so it can never be blanket-allowed globally — both pinned by regression tests.
- The default pipeline is byte-identical to today (acceptance #1): with no machine-pin policy
  configured `pinning=None` everywhere, no production path constructs a pin, and the gate's default
  allow-set is unchanged.
- The README and per-role invariants are superseded for the opt-in path only; this ADR is the
  explicit record. The pieces a usable machine-pin tier required have all shipped: the ensemble-FA
  calibration and deterministic threshold derivation (ADR 0208), the default-deny per-path gate, and
  the `ReviewArtifact` / `build_package` fabrication guard (a machine package emits a `machine_agreement`
  record plus a `needs_review` review, never a fake `approved` one). The `machine_agreement` record is
  now constructible by production code (`route_machine_pinning`), gated on the full measurable-signal
  set.
- The category-2 review-check posture is PERMANENT, not a deferral (§2, "Category-2 review checks —
  AC1 baseline"). The review-required paths (`hard-gate`, `adoption`, `agent_workflow`) gate on
  `review["decision"] == "approved"`, NOT on `is_real_human_review`, because every default package
  carries the fabricated package-builder approval and tightening these sites would reject it — a
  direct AC1 violation. The genuine concern (a machine pin backed by a fabricated approval) is
  enforced at the load-bearing provenance axis instead: a machine-pinned package carries a
  `needs_review` review and `validate_package` refuses a machine pin with an `approved` review. The
  permanent baseline is pinned by `tests/test_machine_pinning_gate.py`
  (`test_category2_review_check_accepts_the_fabricated_package_builder_baseline`), which does NOT flip.
- Zone 1 `partition-spec` (ADR 0207), Zone 2 `machine_agreement` routing + provider-family metadata +
  ensemble-FA calibration + deterministic threshold derivation (ADR 0208), and the Zone 3
  `attest-spec` orchestrator build on this provenance axis.
