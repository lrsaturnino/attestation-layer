"""Zone 2 — the ``machine_agreement`` trust state + measurable-signal routing (three-zone §5).

This is a NEW trust state, not a policy over the approval-gated primitives (scope §3). The
existing ensemble/agreement primitives gate on PRIOR HUMAN APPROVAL: divergence is actionable
only for approved+audited candidates (``decomposition_client``), ``translator_agreement`` blocks
unapproved LLM candidates, and ``_is_trusted_candidate`` requires ``approval.status == "approved"``
plus a passing audit — else ``needs_review``. Auto-advance acts BEFORE human approval, so it
cannot reuse those unchanged. This module defines ``machine_agreement`` as a distinct trust state
that reuses the agreement *computation* (``formal_claim_signature`` / ``build_translation_agreement_report``)
but replaces the human-approval precondition with its own explicit requirements (≥2 cross-provider
members, ≥2 distinct provider families, passing audit verdicts, recorded provenance, refusal on
disagreement, deterministic shape pass).

Design — routing on MEASURABLE signals, never a model "confidence" (scope §5 / acceptance #7):

The drafting client returns only text (``llm_client``); there is no confidence scalar. Routing is
computed from concrete signals:

  * ``deterministic_shape_ok`` — parse / type / self-consistency / supported-claim SMT shape passed.
  * ``no_clarify_sentinel`` — the drafted controlled text carries no ``[[NLR-CLARIFY]]``.
  * ``agreement`` — the cross-provider ensemble agreed on the controlled text / IR shape (reusing
    the agreement *computation*, not its human-approval precondition).
  * provider diversity — ≥2 distinct provider families (``provider_family_for``, scope §3).
  * audit verdicts — every member's candidate passed audit.
  * calibration — the ensemble's measured false-acceptance is within the deterministically-derived
    threshold (AC9: derived from the committed ensemble-FA calibration, never a hand-set constant).
  * boundary disagreement — no partition boundary flag (one member merged what another split).
  * partition diversity — the Zone 1 partition was itself produced by a cross-provider ensemble of
    ≥2 distinct provider families, so the rule's BOUNDARY (not just its wording) was cross-checked;
    a deterministic or single-provider partition can never auto-advance (so that "no partition
    ensemble ran" is distinguishable from "the partition ensemble agreed", scope §4).

ALL signals satisfied → ``machine-pin``: emit a ``machine_agreement`` ``PinningProvenance`` record
(and the package builder suppresses the fabricated approved ``review.json``). ANY signal unmet →
HUMAN QUEUE, and NO pinning record is emitted (acceptance #7; HELPER iter-1 review). With the
policy OFF (the default), every rule routes to a human and no pinning record is emitted —
byte-identical to today (acceptance #1).
"""
from __future__ import annotations

import os
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .jsonutil import sha256_json, sha256_text
from .model_config import provider_family_for  # re-exported for callers (scope §3)
from .models import (
    EnsembleAgreementResult,
    EnsembleAuditVerdict,
    EnsembleEvidence,
    EnsembleMember,
    EvidenceLevel,
    PinningProvenance,
)

__all__ = [
    "EnsembleCalibrationConfiguration",
    "EnsembleFalseAcceptanceCalibration",
    "MachinePinPolicyRules",
    "MachinePinPolicy",
    "MachineRoutingInput",
    "MachineRoutingDecision",
    "MACHINE_PIN_ENV",
    "machine_pin_enabled",
    "derive_ensemble_fa_threshold",
    "measured_fa_for_configuration",
    "ensemble_fa_within_threshold",
    "policy_content_hash",
    "machine_pin_admits_changed_paths",
    "ChangedPathPolicy",
    "load_machine_pin_policy",
    "route_machine_pinning",
    "distinct_provider_families",
    "audit_verdicts_pass",
]


# The opt-in env var (scope §5: ``--machine-pin-policy`` / ``NLREQ_MACHINE_PIN``). When unset (the
# default), machine pinning is OFF and every rule routes to a human (byte-identical to today, AC1).
MACHINE_PIN_ENV = "NLREQ_MACHINE_PIN"


# ---------------------------------------------------------------------------
# Ensemble false-acceptance calibration + deterministic threshold derivation (AC9)
# ---------------------------------------------------------------------------


class EnsembleCalibrationConfiguration(BaseModel):
    """One measured ensemble configuration in a false-acceptance calibration.

    A configuration is identified by (ensemble_size, distinct_provider_families) — the two axes
    the diversity + agreement gates vary — and carries the measured false-acceptance rate over a
    labeled corpus (agreed-but-wrong / agreed) and the sample count that backs it. The
    deterministically-derived auto-advance threshold (``derive_ensemble_fa_threshold``) is a
    function of these rates, never a hand-set constant (AC9).
    """

    model_config = ConfigDict(extra="forbid")

    ensemble_size: int = Field(ge=1)
    distinct_provider_families: int = Field(ge=1)
    false_acceptance_rate: float = Field(ge=0.0, le=1.0)
    sample_count: int = Field(ge=0)  # validated >= 1 below (clearer message than a structural ge=1)

    @model_validator(mode="after")
    def _require_backed_by_samples(self) -> EnsembleCalibrationConfiguration:
        # Belt-and-suspenders alongside ``Field(ge=1)``: reject any zero-sample configuration with a
        # descriptive message (a structural ``ge=1`` refusal is less informative). A zero-sample
        # entry is an unmeasured configuration; letting it set the floor would derive the
        # auto-advance threshold from data that was never collected (AC9).
        if self.sample_count == 0:
            raise ValueError(
                f"EnsembleCalibrationConfiguration (size={self.ensemble_size}, "
                f"families={self.distinct_provider_families}) has sample_count=0; an ensemble-FA "
                "calibration configuration must be backed by samples (sample_count >= 1), "
                "otherwise an unmeasured entry could set the auto-advance threshold (AC9)"
            )
        return self


class EnsembleFalseAcceptanceCalibration(BaseModel):
    """The committed ensemble false-acceptance calibration the threshold is derived from (AC9).

    This is a SEPARATE calibration from the per-role ``RoleCalibrationReport`` (scope §3): the
    per-role calibration measures PER-MODEL false-acceptance/false-refusal on the translation
    corpus, which is NOT an ensemble auto-advance false-acceptance metric. This calibration
    measures the ENSEMBLE's agreed-but-wrong rate across (size, families) configurations. The
    auto-advance threshold is derived deterministically from ``configurations`` via
    ``derive_ensemble_fa_threshold`` — never a hand-set constant (AC9).
    """

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["0.1"] = "0.1"
    calibration_id: str
    configurations: list[EnsembleCalibrationConfiguration] = Field(default_factory=list)

    @model_validator(mode="after")
    def _require_unique_configurations(self) -> EnsembleFalseAcceptanceCalibration:
        # Two entries for the same (size, families) would make ``measured_fa_for_configuration``
        # ambiguous; the calibration must carry one measurement per configuration.
        seen: set[tuple[int, int]] = set()
        for config in self.configurations:
            key = (config.ensemble_size, config.distinct_provider_families)
            if key in seen:
                raise ValueError(
                    f"duplicate ensemble-FA calibration configuration for (size={key[0]}, "
                    f"families={key[1]}); a configuration must be measured exactly once"
                )
            seen.add(key)
        return self


def derive_ensemble_fa_threshold(
    calibration: EnsembleFalseAcceptanceCalibration | None,
) -> float | None:
    """Deterministically derive the auto-advance ensemble-FA threshold from calibration data.

    The threshold is the MINIMUM false-acceptance rate the calibration OBSERVED across its
    configurations — the calibration's empirical floor. Auto-advance is permitted only for a
    configuration whose measured FA is AT MOST that floor (``measured_fa_for_configuration <=
    threshold``), so for a calibration that includes a zero-FA configuration the floor is 0.0 and
    only zero-FA configurations auto-advance. The threshold is therefore a property of the
    committed calibration DATA, not an operator-tuned constant (AC9: no hand-set threshold
    constants). Returns ``None`` when the calibration carries no configurations (uncalibrated),
    which the router treats as "no configuration can be auto-advanced" (``fa_within_threshold``
    is None → never auto-advance).
    """
    if calibration is None or not calibration.configurations:
        return None
    return min(config.false_acceptance_rate for config in calibration.configurations)


def measured_fa_for_configuration(
    calibration: EnsembleFalseAcceptanceCalibration | None,
    *,
    ensemble_size: int,
    distinct_provider_families: int,
) -> float | None:
    """The measured ensemble-FA rate for a (size, families) configuration, or None when unmeasured.

    A candidate configuration not present in the calibration is NOT eligible for auto-advance
    (conservative — auto-advance only configurations the committed calibration measured, AC9).
    """
    if calibration is None:
        return None
    for config in calibration.configurations:
        if (
            config.ensemble_size == ensemble_size
            and config.distinct_provider_families == distinct_provider_families
        ):
            return config.false_acceptance_rate
    return None


def ensemble_fa_within_threshold(
    calibration: EnsembleFalseAcceptanceCalibration | None,
    members: list[EnsembleMember],
) -> bool | None:
    """Whether the ensemble's measured FA is within the derived threshold.

    Returns ``True`` iff the candidate's (size, families) configuration was measured by the
    calibration AND its measured FA is at most the derived threshold. Returns ``False`` when the
    configuration was measured but exceeds the threshold, OR when it was NOT measured (an
    unmeasured configuration is never auto-advance-eligible). Returns ``None`` when there is no
    calibration at all (uncalibrated → the router treats None as "cannot auto-advance"). The
    ``None`` vs ``False`` distinction is load-bearing: ``None`` means "uncalibrated, route to
    human"; ``False`` means "measured and over threshold, route to human".
    """
    if calibration is None:
        return None
    threshold = derive_ensemble_fa_threshold(calibration)
    if threshold is None:
        return None
    families = len(distinct_provider_families(members))
    measured = measured_fa_for_configuration(
        calibration,
        ensemble_size=len(members),
        distinct_provider_families=families,
    )
    if measured is None:
        return False
    return measured <= threshold


# ---------------------------------------------------------------------------
# Provider-family + audit helpers (the diversity / passing-audit predicates)
# ---------------------------------------------------------------------------


def distinct_provider_families(members: list[EnsembleMember]) -> list[str]:
    """The sorted distinct provider families across the ensemble (the diversity predicate input).

    A ``None``/blank family (an unresolvable wrapper) contributes nothing, so an ensemble with an
    unknown-family member cannot satisfy a ``required_distinct_provider_families >= 2`` requirement
    from that member — diversity is proven only by RESOLVED, distinct families (AC7).
    """
    families: set[str] = set()
    for member in members:
        if isinstance(member.provider_family, str) and member.provider_family.strip():
            families.add(member.provider_family.strip())
    return sorted(families)


def audit_verdicts_pass(verdicts: list[EnsembleAuditVerdict], members: list[EnsembleMember]) -> bool:
    """Whether every ensemble member has a present, passing audit verdict.

    Reuses the same 1:1 correspondence the ``EnsembleEvidence`` construction guard enforces
    (every member has exactly one verdict, no extras), but checks it for ROUTING — so a member
    with a failed or missing audit routes to the human queue BEFORE a pinning is attempted, never
    a construction error (acceptance #7). A divergent/failed audit is an unmet signal, not an
    exception.
    """
    verdict_by_member = {verdict.member_id: verdict.verdict for verdict in verdicts}
    if set(verdict_by_member) != {member.member_id for member in members}:
        return False
    return all(value == "passed" for value in verdict_by_member.values())


# ---------------------------------------------------------------------------
# Opt-in policy (the routing rules + calibration reference)
# ---------------------------------------------------------------------------


class ChangedPathPolicy(BaseModel):
    """The DEFAULT-DENY changed-path admission policy a machine pin is recorded under (scope §6).

    This is the per-path gate the scope assigns to the machine-pin policy (``--machine-pin-policy``
    declares the changed-path allow-list, scope §5/§6): a machine-pinned package is admitted ONLY
    for a change whose EVERY changed path matches an allow-list pattern AND none matches the
    block-list. It lives INSIDE ``MachinePinPolicyRules`` (the object ``policy_content_hash``
    stamps on every machine pin) so the pin's ``policy_hash`` proves WHICH path policy admitted
    it — closing the HELPER iter-2 gap where the stamped hash covered ensemble rules +
    calibration only and the path policy lived separately in ``GatePolicy.machine_pin``.

    Mirrors ``gate.GateMachinePinRules`` (the gate's own evaluation config): same field names and
    auth/funds block defaults, so the canonical policy (here, in the hashed object) and the gate's
    view stay aligned. ``enabled=False`` (the default) is default-deny on every path.
    """

    model_config = ConfigDict(extra="forbid")

    enabled: bool = False
    # fnmatch patterns for low-risk changed paths a machine pin MAY satisfy (e.g. 'docs/**',
    # 'tests/**'). A machine-pinned package is admitted iff EVERY changed path matches at least one
    # pattern here AND none matches ``block_changed_path_patterns``.
    allowed_changed_path_patterns: list[str] = Field(default_factory=list)
    # fnmatch patterns for sensitive paths a machine pin MUST NEVER satisfy, even if they also
    # match the allow-list (deny wins). Defaults to auth/funds surfaces; an operator widens it.
    block_changed_path_patterns: list[str] = Field(
        default_factory=lambda: [
            "**/auth/**",
            "**/authentication/**",
            "**/authz/**",
            "**/funds/**",
            "**/payments/**",
            "**/wallet/**",
            "**/transfer/**",
            "**/signing/**",
            "**/crypto/**",
        ]
    )


class MachinePinPolicyRules(BaseModel):
    """The enforceable routing rules of an opt-in machine-pin policy.

    Every field is a MEASURABLE constraint (scope §5 / acceptance #7): ensemble size, distinct
    provider families, the deterministic levels that must pass, and the calibration the threshold
    is derived from. There are NO model-confidence fields and NO hand-set threshold constants —
    the FA threshold is derived from ``calibration`` via ``derive_ensemble_fa_threshold`` (AC9).

    The ``changed_path_policy`` (scope §5/§6) is the default-deny per-path admission gate; it is
    part of THIS object (not a separate ``GatePolicy`` section) precisely so ``policy_content_hash``
    covers it and a stamped ``policy_hash`` proves which path policy admitted a pin (HELPER iter-2).
    """

    model_config = ConfigDict(extra="forbid")

    minimum_ensemble_size: int = Field(default=2, ge=2)
    required_distinct_provider_families: int = Field(default=2, ge=2)
    # The deterministic EvidenceLevels the package MUST pass to be machine-pinnable. Machine
    # pinning never SUBSTITUTES for a proof level (scope §6) — it records who pinned the meaning —
    # so these levels are required IN ADDITION to the pinning, never instead of. The router
    # enforces them against ``MachineRoutingInput.achieved_evidence_levels`` before constructing a
    # pin (HELPER iter-2: previously declared but never enforced).
    required_deterministic_levels: list[EvidenceLevel] = Field(default_factory=list)
    # The committed ensemble-FA calibration the threshold is derived from. Required for
    # auto-advance: a policy with no calibration cannot auto-advance anything (AC9).
    calibration: EnsembleFalseAcceptanceCalibration | None = None
    # The default-deny changed-path admission policy (scope §5/§6). Part of the hashed object so a
    # stamped pin records which path policy admitted it.
    changed_path_policy: ChangedPathPolicy = Field(default_factory=ChangedPathPolicy)

    @model_validator(mode="after")
    def _calibration_floor_is_zero_or_explicit(self) -> MachinePinPolicyRules:
        # Document (not enforce) that auto-advance is conservative: the derived threshold is the
        # calibration's floor. No structural refusal here — an empty calibration simply means the
        # router's fa_within_threshold is None and nothing auto-advances (the default-off posture).
        return self


class MachinePinPolicy(BaseModel):
    """An opt-in machine-pin policy (``--machine-pin-policy`` / ``NLREQ_MACHINE_PIN``).

    OFF by default (``machine_pin_enabled`` is False when neither the file nor the env var is set):
    every rule routes to a human and no pinning record is emitted — byte-identical to today (AC1).
    An operator opts in by pointing ``--machine-pin-policy`` (or ``NLREQ_MACHINE_PIN``) at a policy
    file; the router then evaluates the measurable signals and auto-advances only clean,
    cross-provider-agreed, calibrated configurations.
    """

    model_config = ConfigDict(extra="forbid")

    policy_id: str
    schema_version: str = "0.1"
    rules: MachinePinPolicyRules = Field(default_factory=MachinePinPolicyRules)

    @model_validator(mode="after")
    def _validate_schema_version(self) -> MachinePinPolicy:
        if self.schema_version != "0.1":
            raise ValueError(f"unsupported machine-pin policy schema_version: {self.schema_version}")
        return self


def machine_pin_enabled(*, policy_path: "object | None" = None) -> bool:
    """Whether machine pinning is opted in (a policy path OR the ``NLREQ_MACHINE_PIN`` env var set).

    OFF by default (AC1). The env var may point at a policy file (``NLREQ_MACHINE_PIN=path``) or
    be a bare enable flag (``NLREQ_MACHINE_PIN=1``); either form opts in. A ``policy_path``
    argument (``--machine-pin-policy``) opts in regardless of the env var.
    """
    if policy_path is not None:
        return True
    return bool(os.environ.get(MACHINE_PIN_ENV, "").strip())


def load_machine_pin_policy(path: "object | None" = None) -> MachinePinPolicy | None:
    """Load the opt-in machine-pin policy, or None when machine pinning is off.

    Resolution: explicit ``path`` (``--machine-pin-policy``) → ``NLREQ_MACHINE_PIN`` (a path) →
    None (off). A bare ``NLREQ_MACHINE_PIN=1`` (not a path) returns a default-rules policy so the
    opt-in is honored with the documented defaults (≥2 members, ≥2 families); an operator wanting
    non-default rules points the env var at a file. Never auto-discovers a policy (the same
    no-silent-opt-in invariant as the model config).
    """
    from pathlib import Path

    from .jsonutil import read_json

    resolved: object = path
    if resolved is None:
        env_value = os.environ.get(MACHINE_PIN_ENV, "").strip()
        if not env_value:
            return None
        # A bare enable flag (1/true/yes) opts in with default rules; anything else is treated as
        # a path. A path that does not exist is a structured error (raise), not a silent off.
        if env_value.lower() in {"1", "true", "yes", "on"}:
            return MachinePinPolicy(policy_id="nlreq-machine-pin-default")
        resolved = env_value
    resolved_path = Path(resolved)  # type: ignore[arg-type]
    if not resolved_path.is_file():
        raise FileNotFoundError(
            f"machine-pin policy file not found: {resolved_path} "
            f"(set via --machine-pin-policy or {MACHINE_PIN_ENV})"
        )
    return MachinePinPolicy.model_validate(read_json(resolved_path))


def policy_content_hash(policy: MachinePinPolicy) -> str:
    """The canonical content hash of a machine-pin policy — stamped on every machine pin.

    A machine pin records the policy it was recorded under (scope §2/§5: "the policy content
    hash"), so the pin is reproducibly bound to the exact rules (ensemble size, families,
    deterministic levels, calibration id, AND the changed-path admission policy) that admitted it
    — not just the policy's id. The changed-path policy is hashed HERE (inside ``rules``) so the
    stamped ``policy_hash`` proves which path policy admitted the pin (HELPER iter-2).
    """
    return sha256_json(policy)


def machine_pin_admits_changed_paths(
    policy: MachinePinPolicy, changed_paths: list[str]
) -> bool:
    """Whether a machine pin recorded under ``policy`` is ADMITTED by its changed-path gate.

    Evaluates the SAME ``changed_path_policy`` object that ``policy_content_hash`` stamps on the
    pin (scope §6 default-deny; HELPER iter-2). Returns True ONLY when ALL of:
      * the changed-path policy is ``enabled``;
      * there is at least one changed path (default-deny: an empty change set admits nothing);
      * EVERY changed path matches an allow-list pattern; AND
      * NO changed path matches a block-list pattern (deny wins).

    So an unmatched path, a mixed-risk change, and every auth/funds path require a human
    ``REVIEWED`` package — a machine pin never satisfies them (AC4). Mirrors the hard gate's
    ``_machine_pin_accepts`` but evaluates the policy the pin was actually recorded under, so the
    admission decision is consistent with the stamped ``policy_hash``.
    """
    from fnmatch import fnmatchcase

    from .gate import _normalize_path

    rules = policy.rules.changed_path_policy
    if not rules.enabled:
        return False
    if not changed_paths:
        return False
    for path in changed_paths:
        normalized = _normalize_path(path)
        if any(
            fnmatchcase(normalized, _normalize_path(pattern))
            for pattern in rules.block_changed_path_patterns
        ):
            return False
        if not any(
            fnmatchcase(normalized, _normalize_path(pattern))
            for pattern in rules.allowed_changed_path_patterns
        ):
            return False
    return True


# ---------------------------------------------------------------------------
# Routing input + decision
# ---------------------------------------------------------------------------


class MachineRoutingInput(BaseModel):
    """The measurable signals + ensemble composition the router evaluates (scope §5 / AC7).

    Every field is MEASURABLE (no model confidence scalar). The caller computes each signal
    concretely — runs the deterministic shape check, scans for the clarify sentinel, runs the
    agreement computation across the members, runs each member's audit, looks up the calibration,
    and reports the partition boundary flag — then the router decides pin-vs-human from them. The
    router NEVER re-derives a signal from the model; it only checks the provided facts against the
    policy, so no path depends on a model-reported confidence scalar (AC7).

    ``agreement`` is ``None`` when the ensemble DISAGREED (the ``EnsembleAgreementResult`` model
    requires ``agreed=True``, so a disagreement is represented by absence); the router treats
    ``agreement is None`` as the unmet ``ensemble_agreed`` signal. ``calibration`` overrides the
    policy's calibration when supplied (a per-call calibration ref); when None the policy's
    calibration is used.
    """

    model_config = ConfigDict(extra="forbid")

    members: list[EnsembleMember]
    audit_verdicts: list[EnsembleAuditVerdict]
    agreement: EnsembleAgreementResult | None = None
    deterministic_shape_ok: bool = False
    no_clarify_sentinel: bool = False
    boundary_disagreement: bool = False
    timestamp: str
    # Optional per-call calibration override; when None the policy's calibration is used.
    calibration: EnsembleFalseAcceptanceCalibration | None = None
    # The deterministic EvidenceLevels the package has ACHIEVED (HELPER iter-2: required for
    # enforcing ``required_deterministic_levels``). The router checks every required level is
    # present here before constructing a pin; an unmet level routes to the human queue. Derived
    # by the caller from the package's ``EvidenceObject.claims[].achieved_evidence`` (the same
    # source the hard gate's ``_missing_required_evidence`` uses) — a MEASURABLE signal (AC7).
    achieved_evidence_levels: list[EvidenceLevel] = Field(default_factory=list)
    # The change's affected paths (HELPER iter-3 #3: changed-path admission is load-bearing). The
    # router evaluates the SAME ``changed_path_policy`` object ``policy_content_hash`` stamps on
    # the pin (default-deny, scope §6) via ``machine_pin_admits_changed_paths`` BEFORE constructing
    # a pin, so the stampable ``policy_hash`` actually records which path policy admitted the pin
    # (closing the iter-3 gap where the hashed path policy was never consulted). Empty by default
    # → the default-deny gate admits nothing (no path is on an allow-list), so a caller that wants
    # to machine-pin MUST supply the change's paths and a policy whose allow-list matches them.
    changed_paths: list[str] = Field(default_factory=list)
    # The Zone 1 PARTITION ensemble's measured composition (scope §4). A machine pin requires the
    # rule's BOUNDARY to have been cross-checked by a cross-provider partition ensemble — not merely
    # its wording by the drafting ensemble — so a deterministic partition (where "no ensemble ran"
    # is otherwise indistinguishable from "the ensemble agreed", both yielding
    # ``boundary_disagreement=False``) or a single-provider partition can never auto-advance. The
    # orchestrator derives both from the REAL partition artifact
    # (``SpecPartitionArtifact.ensemble_members`` / ``ensemble_member_provenance``), a MEASURABLE
    # signal (AC7). Default 0/0 is the deterministic partition, which the router refuses below.
    partition_ensemble_size: int = 0
    partition_ensemble_families: int = 0


class MachineRoutingDecision(BaseModel):
    """The router's decision: auto-advance (a machine pin) or route to the human queue.

    ``pinning`` is a ``machine_agreement`` ``PinningProvenance`` iff EVERY measurable signal is
    satisfied; otherwise it is ``None`` and ``unmet_signals`` lists each failed signal with its
    reason (acceptance #7: no pinning record on any unmet signal). ``policy_off`` is True when the
    decision is "route to human because machine pinning is disabled" (the default, AC1) — distinct
    from "route to human because a signal failed under an opted-in policy".
    """

    model_config = ConfigDict(extra="forbid")

    auto_advance: bool
    pinning: PinningProvenance | None = None
    unmet_signals: list[str] = Field(default_factory=list)
    policy_off: bool = False


def route_machine_pinning(
    routing_input: MachineRoutingInput,
    *,
    policy: MachinePinPolicy | None,
) -> MachineRoutingDecision:
    """Route a requirement: machine-pin iff every measurable signal passes, else human queue.

    The single decision point for the ``machine_agreement`` trust state (scope §5). It reuses the
    agreement *computation* (the caller passes the already-computed ``agreement``) but NOT the
    human-approval precondition: the requirements here are ≥2 cross-provider members, ≥2 distinct
    provider families, a cross-provider partition ensemble of ≥2 distinct families (so the rule's
    boundary was cross-checked, scope §4), passing audit verdicts, the deterministic-shape pass, no
    clarify sentinel, no boundary disagreement, and the calibration-derived FA threshold. ANY unmet
    signal → human queue and NO pinning record (acceptance #7). Policy off (``policy is None``) → human queue for
    every rule and NO pinning record (AC1, byte-identical to today).

    The function is PURE: it constructs the ``PinningProvenance`` from the provided facts but
    performs no I/O and no model call. Raising on a malformed ensemble (e.g. an ``EnsembleEvidence``
    that violates the construction guard) is correct: the caller must supply a self-consistent
    ensemble, and a construction failure is a programmer error, not a routing outcome.
    """
    # Policy off → every rule routes to a human, no pinning record (AC1).
    if policy is None:
        return MachineRoutingDecision(
            auto_advance=False,
            pinning=None,
            policy_off=True,
            unmet_signals=["machine pinning is disabled (no --machine-pin-policy / NLREQ_MACHINE_PIN)"],
        )

    members = routing_input.members
    rules = policy.rules
    unmet: list[str] = []

    # --- diversity: ensemble size + distinct provider families (scope §3/§5) ---
    if len(members) < rules.minimum_ensemble_size:
        unmet.append(
            f"ensemble size {len(members)} is below the required minimum "
            f"{rules.minimum_ensemble_size}"
        )
    families = distinct_provider_families(members)
    if len(families) < rules.required_distinct_provider_families:
        unmet.append(
            f"only {len(families)} distinct provider family/families ({families}) is below the "
            f"required {rules.required_distinct_provider_families}; a same-family ensemble cannot "
            "satisfy the diversity requirement that catches correlated training bias"
        )

    # --- partition-ensemble presence + diversity (scope §4) ---
    # A machine pin requires the Zone 1 PARTITION to have been produced by a cross-provider ensemble
    # of ≥2 distinct provider families (the SAME diversity bar as the drafting ensemble), so the
    # rule's BOUNDARY — not just its wording — was cross-checked. A deterministic partition (size 0)
    # or a single-provider partition (size 1 / one family) routes to the human queue: "no partition
    # ensemble ran" must be DISTINGUISHABLE from "the partition ensemble agreed" (the prior gap where
    # both produced ``boundary_disagreement=False`` and an auto-advanceable candidate).
    if routing_input.partition_ensemble_size < rules.minimum_ensemble_size:
        unmet.append(
            f"the partition (Zone 1) was produced by {routing_input.partition_ensemble_size} "
            f"ensemble member(s), below the required minimum {rules.minimum_ensemble_size}; a "
            "deterministic or single-provider partition cannot be machine-pinned (the rule's "
            "boundary was not cross-checked by a partition ensemble)"
        )
    if routing_input.partition_ensemble_families < rules.required_distinct_provider_families:
        unmet.append(
            f"the partition (Zone 1) ensemble spans only "
            f"{routing_input.partition_ensemble_families} distinct provider family/families, below "
            f"the required {rules.required_distinct_provider_families}; a same-family or single-"
            "provider partition cannot satisfy the diversity requirement that catches a correlated "
            "boundary error"
        )

    # --- deterministic shape + clarify sentinel (the drafting side, scope §5) ---
    if not routing_input.deterministic_shape_ok:
        unmet.append(
            "deterministic shape check failed (parse / type / self-consistency / supported-claim "
            "SMT shape did not all pass)"
        )
    if not routing_input.no_clarify_sentinel:
        unmet.append(
            "drafted controlled text carries the [[NLR-CLARIFY]] sentinel (the drafting model could "
            "not confidently state the requirement)"
        )

    # --- required deterministic EvidenceLevels (scope §6; HELPER iter-2: enforced, not just
    #     declared). Machine pinning never SUBSTITUTES for a proof level — it records who pinned
    #     the meaning — so every level the policy requires must be present in the package's
    #     achieved evidence before a pin is constructed. An unmet level routes to the human queue.
    if rules.required_deterministic_levels:
        achieved = {level for level in routing_input.achieved_evidence_levels}
        missing_levels = [
            level for level in rules.required_deterministic_levels if level not in achieved
        ]
        if missing_levels:
            unmet.append(
                "required deterministic evidence level(s) not achieved: "
                + ", ".join(sorted(level.value for level in missing_levels))
                + " (machine pinning never substitutes for a deterministic proof level; it only "
                  "records who pinned the meaning)"
            )

    # --- ensemble agreement (reuses the agreement computation, not the approval precondition) ---
    if routing_input.agreement is None:
        unmet.append(
            "ensemble did not agree on the controlled text / IR shape (disagreement routes to the "
            "human queue, never a pin)"
        )

    # --- per-member audit verdicts (scope §5: passing audit verdicts) ---
    if not audit_verdicts_pass(routing_input.audit_verdicts, members):
        unmet.append(
            "one or more ensemble members failed audit or lack a present, passing audit verdict "
            "(every member's candidate must pass audit to pin)"
        )

    # --- partition boundary disagreement (scope §4/§5) ---
    if routing_input.boundary_disagreement:
        unmet.append(
            "partition ensemble reported a boundary disagreement (one member merged what another "
            "split); a boundary disagreement routes to the human queue"
        )

    # --- calibration-derived FA threshold (AC9) ---
    calibration = routing_input.calibration if routing_input.calibration is not None else rules.calibration
    fa_within = ensemble_fa_within_threshold(calibration, members)
    if fa_within is None:
        unmet.append(
            "no ensemble false-acceptance calibration is configured; the auto-advance threshold "
            "must be derived from a committed calibration (AC9), so an uncalibrated ensemble "
            "routes to the human queue"
        )
    elif not fa_within:
        unmet.append(
            "the ensemble's measured false-acceptance is above the calibration-derived threshold "
            "(or its configuration was not measured by the calibration); an over-threshold or "
            "unmeasured ensemble routes to the human queue"
        )

    # --- changed-path admission (scope §6 default-deny; HELPER iter-3 #3: load-bearing) ---
    # The pin's ``policy_hash`` covers the changed-path policy, so the router MUST evaluate that
    # SAME policy before stamping a pin — otherwise the hash claims a path admission that never
    # happened. ``machine_pin_admits_changed_paths`` returns True ONLY when the gate is enabled,
    # at least one path is supplied, EVERY path matches an allow-list pattern, and NO path matches
    # a block-list pattern. So a disabled gate, an empty change set, an unmatched path, a
    # mixed-risk change, and every auth/funds path route to the human queue (AC4 default-deny).
    if not machine_pin_admits_changed_paths(policy, routing_input.changed_paths):
        unmet.append(
            "the changed-path admission gate did not admit this change (the policy's "
            "changed_path_policy is disabled, no changed paths were supplied, or a changed path "
            "is not on the allow-list / matches the block-list); a machine pin is recorded only "
            "for a change whose every path the opted-in low-risk allow-list admits (default-deny, AC4)"
        )

    if unmet:
        return MachineRoutingDecision(auto_advance=False, pinning=None, unmet_signals=unmet)

    # Every measurable signal passed: construct the machine_agreement pinning record. The
    # EnsembleEvidence construction guard re-checks the diversity / audit / hash invariants, so a
    # self-inconsistent input raises (programmer error) rather than producing a malformed pin.
    assert routing_input.agreement is not None  # narrowed by the unmet check above
    evidence = EnsembleEvidence(
        members=list(members),
        agreement=routing_input.agreement,
        audit_verdicts=list(routing_input.audit_verdicts),
        policy_hash=policy_content_hash(policy),
    )
    pinning = PinningProvenance(
        kind="machine_agreement",
        ensemble=evidence,
        timestamp=routing_input.timestamp,
    )
    return MachineRoutingDecision(auto_advance=True, pinning=pinning)
