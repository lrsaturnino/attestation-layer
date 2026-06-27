# ADR 0208: The `machine_agreement` Trust State, Provider-Family Metadata, and Ensemble-FA Calibration

## Status

Accepted and shipped (three-zone scope P3, Zone 2). The module `src/nlreq/machine_agreement.py`
implements the `machine_agreement` trust state and the contracts this scope owns **beyond** the
per-role-model dependency: the provider-family grouping + "two distinct families" predicate, the
ensemble false-acceptance (FA) calibration, and the deterministic threshold-derivation algorithm.
This is the companion to ADR 0206 (the machine-pinning provenance axis and gate) and ADR 0207 (spec
partitioning); it records the third of the scope's three ADR seeds (§10). It is **off by default**.

## Context

This scope lands after the per-role-model scope (ADR 0202–0205) and consumes its cross-provider
transport and the `build_client_for_role` factory. But the per-role scope does **not** fully provide
what auto-advance needs, and the gap had to be owned here (scope §3):

1. **No provider-family predicate.** The per-role scope records the *provider* (the wrapper) and the
   resolved model id, and frames diversity as "two providers" / avoiding "same-family" correlated
   bias — but it defines no machine-readable provider-**family** grouping or a "two distinct families"
   predicate. Two distinct providers (wrappers) can still resolve to the same family (e.g. two
   wrappers both resolving to Anthropic models), which would defeat the diversity the gate exists to
   catch.

2. **No ensemble auto-advance FA metric.** The per-role calibration (`RoleCalibrationReport`) measures
   **per-model** false-acceptance / false-refusal on the translation corpus. That is not an
   **ensemble** auto-advance false-acceptance metric (the agreed-but-wrong rate of an ensemble of a
   given size and family count).

3. **No deterministic threshold-derivation algorithm.** The auto-advance threshold must be derived
   from committed calibration data, not hand-set (AC9).

4. **No `machine_agreement` trust state.** The existing ensemble/agreement primitives gate on **prior
   human approval**: divergence is actionable only for approved+audited candidates
   (`decomposition_client`), `translator_agreement` blocks unapproved LLM candidates, and
   `semantic_translation._is_trusted_candidate` requires `approval.status == "approved"` plus a
   passing audit, else `needs_review`. Auto-advance acts **before** human approval, so it cannot reuse
   these unchanged.

## Decision

### 1. `machine_agreement` is a NEW trust state, not a policy over the approval-gated primitives

It reuses the agreement **computation** (`formal_claim_signature` /
`build_translation_agreement_report`) but **replaces** the human-approval precondition with its own
explicit requirements: ≥2 cross-provider members, ≥2 distinct provider families, a cross-provider
partition ensemble of ≥2 families (so the rule's boundary was cross-checked, ADR 0207), passing audit
verdicts, the deterministic-shape pass, no clarify sentinel, no boundary disagreement, the required
deterministic evidence levels, the calibration-derived FA threshold, and changed-path admission.

### 2. Routing is computed from MEASURABLE signals only — never a model confidence scalar

The drafting client returns only text; there is no confidence scalar (AC7). `MachineRoutingInput`
carries only concrete, caller-computed facts: `deterministic_shape_ok`, `no_clarify_sentinel`, the
already-computed `agreement` (absent ⇒ the ensemble disagreed), the member set + audit verdicts, the
achieved evidence levels, the changed paths, the partition-ensemble size/family count, and the
`boundary_disagreement` flag. `route_machine_pinning` is the single, **pure** decision point: it
checks the provided facts against the policy and never re-derives a signal from the model. ANY unmet
signal ⇒ the human queue and **no** pinning record (`MachineRoutingDecision.unmet_signals` lists each
failure with its reason). Policy off (`policy is None`) ⇒ human queue for every rule, byte-identical
to today (acceptance #1).

### 3. Provider-family metadata + the "two distinct families" predicate

`model_config.provider_family_for` groups a resolved model into a provider **family** (distinct from
the wrapper), and `machine_agreement.distinct_provider_families(members)` returns the sorted distinct
families across an ensemble. A `None`/blank family (an unresolvable wrapper) contributes nothing, so
an unknown-family member cannot prop up a `required_distinct_provider_families >= 2` requirement —
diversity is proven only by RESOLVED, distinct families. The `EnsembleEvidence` construction guard
(ADR 0206) re-checks ≥2 distinct families at construction, so a same-family ensemble is
unrepresentable as machine-pin evidence.

### 4. Ensemble-FA calibration is a SEPARATE artifact from the per-role calibration

`EnsembleFalseAcceptanceCalibration` carries one `EnsembleCalibrationConfiguration` per
`(ensemble_size, distinct_provider_families)` configuration — the two axes the diversity + agreement
gates vary — each with the measured `false_acceptance_rate` (agreed-but-wrong / agreed) over a
labeled corpus and the `sample_count` that backs it. A zero-sample configuration is refused (an
unmeasured entry must never set the threshold), and `(size, families)` keys must be unique (so
`measured_fa_for_configuration` is unambiguous). This is explicitly **not** the per-role
`RoleCalibrationReport` (which is per-model FA/FR on the translation corpus).

### 5. The auto-advance threshold is derived deterministically from the committed calibration (AC9)

`derive_ensemble_fa_threshold(calibration)` is the **minimum** false-acceptance rate the calibration
observed across its configurations — the calibration's empirical floor. Auto-advance is permitted
only for a configuration the calibration measured **and** whose measured FA is at most that floor
(`ensemble_fa_within_threshold`). The threshold is therefore a property of the committed calibration
**data**, never an operator-tuned constant — there are no hand-set threshold fields anywhere in
`MachinePinPolicyRules`. The `None` vs `False` distinction is load-bearing: `None` (no calibration, or
configuration unmeasured) ⇒ "cannot auto-advance, route to human"; `False` ⇒ "measured and over
threshold, route to human".

### 6. The opt-in policy carries the default-deny changed-path gate inside its hashed object

`MachinePinPolicy` (`--machine-pin-policy` / `NLREQ_MACHINE_PIN`) is OFF by default and is never
auto-discovered. Its `MachinePinPolicyRules` hold every measurable constraint (minimum ensemble size,
required distinct families, required deterministic levels, the calibration reference) **and** the
default-deny `ChangedPathPolicy`. The path policy lives inside the rules — not in a separate
`GatePolicy` section — precisely so `policy_content_hash` (stamped on every pin) covers it, and the
stamped `policy_hash` proves which path policy admitted the pin. `route_machine_pinning` evaluates
that same path policy (via `machine_pin_admits_changed_paths`) before constructing a pin, so the
admission decision is consistent with the hash.

## Alternatives Considered

- **A policy over the existing approval-gated ensemble/agreement primitives.** Rejected (scope §3):
  `decomposition_client`, `translator_agreement`, and `semantic_translation._is_trusted_candidate` all
  require `approval.status == "approved"` plus a passing audit, else `needs_review`. Auto-advance acts
  before approval, so reusing them unchanged is impossible. `machine_agreement` reuses only the
  agreement computation and supplies its own pre-approval requirements.

- **A hand-set false-acceptance threshold constant.** Rejected (AC9): an operator-tuned constant is
  not anchored to measured data. The threshold is derived deterministically from the committed
  calibration's empirical floor; an uncalibrated or unmeasured configuration never auto-advances.

- **Reuse the per-role per-model calibration (`RoleCalibrationReport`).** Rejected: it measures
  per-model FA/FR, not the ensemble's agreed-but-wrong rate across `(size, families)` configurations,
  which is the quantity auto-advance is gated on.

- **Define diversity by distinct providers rather than distinct families.** Rejected (scope §3): two
  distinct providers (wrappers) can resolve to the same family, leaving the ensemble dominated by
  correlated training bias. Diversity is proven only by ≥2 distinct, resolved families.

- **Use a model-reported confidence scalar as a routing signal.** Rejected (AC7): the drafting client
  returns only text, and a self-reported confidence is not a measurable property. Every routing signal
  is computed from concrete facts (parse, sentinel, agreement computation, family count, audit
  verdicts, achieved evidence levels, calibration lookup, boundary flag, changed paths).

## Consequences

- A clean, cross-provider-agreed, calibrated rule whose every measurable signal passes auto-advances
  to a `machine_agreement` `PinningProvenance` record (ADR 0206); any unmet signal routes it to the
  human queue with the failure reason, and emits no pinning record.
- A same-family ensemble, an uncalibrated or over-threshold ensemble, an ensemble whose configuration
  the calibration never measured, a deterministic or single-family partition, a failed/missing audit,
  a clarify sentinel, a boundary disagreement, an unmet required evidence level, and any non-admitted
  changed path each route to the human queue — `route_machine_pinning` is the single place these are
  decided.
- The auto-advance threshold is reproducible from the committed calibration data alone, so there is no
  hand-set constant a future change could quietly loosen.
- The pin records the full ensemble composition (members, resolved model ids, provider families,
  agreement result, per-member audit verdicts) and the policy content hash, so a machine pin is
  reproducibly bound to the exact rules — ensemble, calibration, and changed-path policy — that
  admitted it.
