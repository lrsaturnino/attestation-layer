"""Tests for Zone 2 — the ``machine_agreement`` trust state + measurable-signal routing.

Three-zone scope §5 / Work Item 2 (acceptance criteria #2, #7, #9). The router must:

  * emit a ``machine_agreement`` ``PinningProvenance`` iff EVERY measurable signal passes (AC2);
  * emit NO pinning record when ANY signal is unmet — parse fail, clarify, disagreement,
    sub-floor ensemble, single-family, failed audit, boundary disagreement, over-threshold /
    uncalibrated FA — routing each to the human queue instead (AC7);
  * derive the auto-advance FA threshold deterministically from the committed ensemble-FA
    calibration, with no hand-set threshold constants (AC9);
  * route EVERY rule to the human queue with NO pinning record when the policy is off (AC1).

All tests are CI-safe: the agreement / audit / calibration inputs are constructed directly, never
a live model.
"""
from __future__ import annotations

import pytest

from nlreq.machine_agreement import (
    ChangedPathPolicy,
    EnsembleCalibrationConfiguration,
    EnsembleFalseAcceptanceCalibration,
    MachinePinPolicy,
    MachinePinPolicyRules,
    MachineRoutingInput,
    derive_ensemble_fa_threshold,
    distinct_provider_families,
    ensemble_fa_within_threshold,
    measured_fa_for_configuration,
    policy_content_hash,
    route_machine_pinning,
)
from nlreq.models import (
    EnsembleAgreementResult,
    EnsembleAuditVerdict,
    EnsembleMember,
    FinalStatus,
    PinningProvenance,
)

_VALID_HASH = "sha256:" + "0" * 64
_FA_RATE = 0.0  # the calibration floor for a 2/2 config


def _members(*, families: tuple[str, ...] = ("anthropic", "openai")) -> list[EnsembleMember]:
    return [
        EnsembleMember(
            member_id=f"m{i}",
            resolved_model_id=f"model-{family}",
            provider_family=family,
        )
        for i, family in enumerate(families)
    ]


def _agreement() -> EnsembleAgreementResult:
    return EnsembleAgreementResult(agreed=True, agreement_hash=_VALID_HASH)


def _verdicts(members: list[EnsembleMember], *, failed: set[str] | None = None) -> list[EnsembleAuditVerdict]:
    failed = failed or set()
    return [
        EnsembleAuditVerdict(
            member_id=member.member_id,
            verdict="failed" if member.member_id in failed else "passed",
        )
        for member in members
    ]


def _calibration(
    *, configurations=(("2", "2", 0.0, 50),)
) -> EnsembleFalseAcceptanceCalibration:
    return EnsembleFalseAcceptanceCalibration(
        calibration_id="ens-fa-1",
        configurations=[
            EnsembleCalibrationConfiguration(
                ensemble_size=int(size),
                distinct_provider_families=int(families),
                false_acceptance_rate=rate,
                sample_count=samples,
            )
            for size, families, rate, samples in configurations
        ],
    )


def _policy(*, calibration: EnsembleFalseAcceptanceCalibration | None = None) -> MachinePinPolicy:
    return MachinePinPolicy(
        policy_id="test-machine-pin",
        rules=MachinePinPolicyRules(
            calibration=calibration if calibration is not None else _calibration(),
            # The changed-path admission gate is load-bearing in routing (HELPER iter-3 #3):
            # enable it with an allow-list so a clean input that supplies a matching changed path
            # (see ``_clean_input``) can advance. Default-deny still holds: a path NOT on this
            # allow-list, or any block-listed auth/funds path, routes to the human queue.
            changed_path_policy=ChangedPathPolicy(
                enabled=True,
                allowed_changed_path_patterns=["src/**"],
            ),
        ),
    )


def _clean_input(members: list[EnsembleMember] | None = None) -> MachineRoutingInput:
    members = members or _members()
    return MachineRoutingInput(
        members=members,
        audit_verdicts=_verdicts(members),
        agreement=_agreement(),
        deterministic_shape_ok=True,
        no_clarify_sentinel=True,
        boundary_disagreement=False,
        timestamp="2026-06-26T00:00:00Z",
        # A changed path on the policy's allow-list (src/**), so the load-bearing admission gate
        # admits a clean input. Tests that want to assert default-deny refusal override this.
        changed_paths=["src/module.py"],
        # A clean Zone 1 partition ensemble: ≥2 cross-provider members, ≥2 distinct families (scope
        # §4), so the rule's boundary was cross-checked. Tests asserting the partition-diversity
        # refusal override these (a deterministic / single-provider partition routes to human).
        partition_ensemble_size=2,
        partition_ensemble_families=2,
    )


# ---------------------------------------------------------------------------
# AC1: policy off → every rule routes to a human, no pinning record
# ---------------------------------------------------------------------------


def test_policy_off_routes_every_rule_to_human_with_no_pinning_record() -> None:
    decision = route_machine_pinning(_clean_input(), policy=None)
    assert decision.auto_advance is False
    assert decision.pinning is None
    assert decision.policy_off is True
    assert decision.unmet_signals


def test_policy_off_emits_no_pinning_record_even_for_a_clean_rule() -> None:
    # A clean, cross-provider-agreed rule still routes to the human queue when the policy is off
    # (the default) — byte-identical to today (AC1).
    decision = route_machine_pinning(_clean_input(), policy=None)
    assert decision.pinning is None


# ---------------------------------------------------------------------------
# AC2: all signals satisfied → machine_agreement pinning record
# ---------------------------------------------------------------------------


def test_clean_cross_provider_agreed_rule_is_machine_pinned() -> None:
    decision = route_machine_pinning(_clean_input(), policy=_policy())
    assert decision.auto_advance is True
    assert decision.unmet_signals == []
    assert decision.pinning is not None
    assert decision.pinning.kind == "machine_agreement"
    ensemble = decision.pinning.ensemble
    assert ensemble is not None
    assert {m.provider_family for m in ensemble.members} == {"anthropic", "openai"}
    assert ensemble.agreement.agreed is True
    assert all(v.verdict == "passed" for v in ensemble.audit_verdicts)
    # The pin records the policy content hash it was admitted under (scope §2/§5).
    assert ensemble.policy_hash == policy_content_hash(_policy())


def test_machine_pin_record_carries_the_resolved_model_ids_and_families() -> None:
    decision = route_machine_pinning(_clean_input(), policy=_policy())
    assert decision.pinning is not None
    ensemble = decision.pinning.ensemble
    assert {m.resolved_model_id for m in ensemble.members} == {"model-anthropic", "model-openai"}
    assert distinct_provider_families(ensemble.members) == ["anthropic", "openai"]


# ---------------------------------------------------------------------------
# AC7: ANY unmet signal → human queue, NO pinning record (one test per signal)
# ---------------------------------------------------------------------------


def test_parse_fail_routes_to_human_with_no_pin() -> None:
    inp = _clean_input()
    inp.deterministic_shape_ok = False
    decision = route_machine_pinning(inp, policy=_policy())
    assert decision.auto_advance is False
    assert decision.pinning is None
    assert any("deterministic shape" in s for s in decision.unmet_signals)


def test_clarify_sentinel_routes_to_human_with_no_pin() -> None:
    inp = _clean_input()
    inp.no_clarify_sentinel = False
    decision = route_machine_pinning(inp, policy=_policy())
    assert decision.auto_advance is False
    assert decision.pinning is None
    assert any("NLR-CLARIFY" in s for s in decision.unmet_signals)


def test_ensemble_disagreement_routes_to_human_with_no_pin() -> None:
    inp = _clean_input()
    inp.agreement = None  # the ensemble disagreed
    decision = route_machine_pinning(inp, policy=_policy())
    assert decision.auto_advance is False
    assert decision.pinning is None
    assert any("did not agree" in s for s in decision.unmet_signals)


def test_single_family_ensemble_routes_to_human_with_no_pin() -> None:
    # Two members, same family → cannot satisfy the distinct-family requirement.
    members = _members(families=("anthropic", "anthropic"))
    inp = _clean_input(members=members)
    decision = route_machine_pinning(inp, policy=_policy())
    assert decision.auto_advance is False
    assert decision.pinning is None
    assert any("distinct provider family" in s for s in decision.unmet_signals)


def test_sub_floor_ensemble_size_routes_to_human_with_no_pin() -> None:
    members = _members(families=("anthropic",))  # only one member
    inp = _clean_input(members=members)
    decision = route_machine_pinning(inp, policy=_policy())
    assert decision.auto_advance is False
    assert decision.pinning is None
    assert any("below the required minimum" in s for s in decision.unmet_signals)


def test_failed_audit_routes_to_human_with_no_pin() -> None:
    members = _members()
    inp = _clean_input(members=members)
    inp.audit_verdicts = _verdicts(members, failed={"m1"})
    decision = route_machine_pinning(inp, policy=_policy())
    assert decision.auto_advance is False
    assert decision.pinning is None
    assert any("audit" in s for s in decision.unmet_signals)


def test_boundary_disagreement_routes_to_human_with_no_pin() -> None:
    inp = _clean_input()
    inp.boundary_disagreement = True
    decision = route_machine_pinning(inp, policy=_policy())
    assert decision.auto_advance is False
    assert decision.pinning is None
    assert any("boundary disagreement" in s for s in decision.unmet_signals)


def test_deterministic_partition_routes_to_human_with_no_pin() -> None:
    # A deterministic partition (no LLM ensemble ran): size 0, 0 families. Even though every OTHER
    # signal is clean, the rule's BOUNDARY was never cross-checked by a partition ensemble, so it
    # routes to the human queue — "no partition ensemble ran" is distinguishable from "the partition
    # ensemble agreed" (scope §4). NO pinning record.
    inp = _clean_input()
    inp.partition_ensemble_size = 0
    inp.partition_ensemble_families = 0
    decision = route_machine_pinning(inp, policy=_policy())
    assert decision.auto_advance is False
    assert decision.pinning is None
    assert any("partition (Zone 1)" in s for s in decision.unmet_signals)


def test_single_family_partition_routes_to_human_with_no_pin() -> None:
    # A partition ensemble that ran ≥2 members but spans only ONE provider family (correlated
    # boundary bias) cannot satisfy the partition-diversity requirement → human queue, no pin.
    inp = _clean_input()
    inp.partition_ensemble_size = 2
    inp.partition_ensemble_families = 1
    decision = route_machine_pinning(inp, policy=_policy())
    assert decision.auto_advance is False
    assert decision.pinning is None
    # The partition-diversity refusal is reported (distinct from the drafting-diversity message,
    # which passes here because the drafting members span two families).
    assert any(
        "partition (Zone 1)" in s and "distinct provider family/families" in s
        for s in decision.unmet_signals
    )


def test_over_threshold_fa_routes_to_human_with_no_pin() -> None:
    # A calibration whose floor is non-zero: a config measured at the floor auto-advances, but a
    # config measured ABOVE the floor does not. Here the policy's calibration measures the 2/2
    # config at 0.10 and the 3/3 config at 0.0 (the floor). A 2-member ensemble's measured FA is
    # 0.10 > floor 0.0 → over threshold → human.
    calibration = _calibration(configurations=(("2", "2", 0.10, 100), ("3", "3", 0.0, 100)))
    inp = _clean_input()  # 2 members, 2 families
    decision = route_machine_pinning(inp, policy=_policy(calibration=calibration))
    assert decision.auto_advance is False
    assert decision.pinning is None
    assert any("above the calibration-derived threshold" in s for s in decision.unmet_signals)


def test_over_threshold_floor_config_does_advance_when_at_floor() -> None:
    # Same calibration, but the ensemble is 3 members / 3 families, measured at the floor 0.0.
    calibration = _calibration(configurations=(("2", "2", 0.10, 100), ("3", "3", 0.0, 100)))
    members = _members(families=("anthropic", "openai", "google"))
    inp = _clean_input(members=members)
    decision = route_machine_pinning(inp, policy=_policy(calibration=calibration))
    assert decision.auto_advance is True
    assert decision.pinning is not None


def test_unmeasured_configuration_routes_to_human_with_no_pin() -> None:
    # The 2/2 config is in the calibration, but the ensemble is 4 members / 4 families (unmeasured).
    calibration = _calibration(configurations=(("2", "2", 0.0, 50),))
    members = _members(families=("anthropic", "openai", "google", "meta"))
    inp = _clean_input(members=members)
    decision = route_machine_pinning(inp, policy=_policy(calibration=calibration))
    assert decision.auto_advance is False
    assert decision.pinning is None
    assert any("not measured" in s for s in decision.unmet_signals)


def test_uncalibrated_policy_routes_to_human_with_no_pin() -> None:
    # A policy with NO calibration cannot derive a threshold → nothing auto-advances (AC9).
    policy = MachinePinPolicy(policy_id="uncalibrated", rules=MachinePinPolicyRules(calibration=None))
    decision = route_machine_pinning(_clean_input(), policy=policy)
    assert decision.auto_advance is False
    assert decision.pinning is None
    assert any("no ensemble false-acceptance calibration" in s for s in decision.unmet_signals)


# ---------------------------------------------------------------------------
# HELPER iter-2: required_deterministic_levels is enforced (scope §6)
# ---------------------------------------------------------------------------


def test_required_deterministic_level_not_achieved_routes_to_human_with_no_pin() -> None:
    # A policy that requires a deterministic EvidenceLevel the package has NOT achieved routes to
    # the human queue — machine pinning never substitutes for a proof level (HELPER iter-2: the
    # field was previously declared but never enforced).
    from nlreq.models import EvidenceLevel

    policy = MachinePinPolicy(
        policy_id="requires-smt",
        rules=MachinePinPolicyRules(
            calibration=_calibration(),
            required_deterministic_levels=[EvidenceLevel.SMT_CHECKED],
        ),
    )
    inp = _clean_input()  # no achieved_evidence_levels → SMT_CHECKED not achieved
    decision = route_machine_pinning(inp, policy=policy)
    assert decision.auto_advance is False
    assert decision.pinning is None
    assert any("required deterministic evidence level" in s for s in decision.unmet_signals)
    assert any("smt_checked" in s.lower() for s in decision.unmet_signals)


def test_required_deterministic_level_achieved_advances() -> None:
    # When every required level IS achieved, the deterministic-levels signal is met and the rule
    # machine-pins (the proof levels are required IN ADDITION to the pin, never instead of).
    from nlreq.models import EvidenceLevel

    policy = MachinePinPolicy(
        policy_id="requires-smt",
        rules=MachinePinPolicyRules(
            calibration=_calibration(),
            required_deterministic_levels=[EvidenceLevel.SMT_CHECKED, EvidenceLevel.TYPE_CHECKED],
            # Enable the changed-path admission gate so the achieved-levels test isolates the
            # deterministic-levels signal (otherwise the default-deny path gate would refuse).
            changed_path_policy=ChangedPathPolicy(
                enabled=True, allowed_changed_path_patterns=["src/**"]
            ),
        ),
    )
    inp = _clean_input()
    inp.achieved_evidence_levels = [EvidenceLevel.SMT_CHECKED, EvidenceLevel.TYPE_CHECKED]
    decision = route_machine_pinning(inp, policy=policy)
    assert decision.auto_advance is True
    assert decision.pinning is not None


def test_multiple_unmet_signals_are_all_reported() -> None:
    # Every unmet signal is reported (not just the first) — the human queue item carries the full
    # reason set.
    inp = _clean_input()
    inp.deterministic_shape_ok = False
    inp.no_clarify_sentinel = False
    inp.agreement = None
    decision = route_machine_pinning(inp, policy=_policy())
    assert decision.auto_advance is False
    joined = " ".join(decision.unmet_signals)
    assert "deterministic shape" in joined
    assert "NLR-CLARIFY" in joined
    assert "did not agree" in joined


# ---------------------------------------------------------------------------
# AC9: deterministic threshold derivation, no hand-set constants
# ---------------------------------------------------------------------------


def test_derive_threshold_is_the_calibration_floor() -> None:
    calibration = _calibration(configurations=(("2", "2", 0.05, 100), ("3", "3", 0.0, 100)))
    # The floor is the minimum observed FA rate (0.0 here) — derived from data, not a constant.
    assert derive_ensemble_fa_threshold(calibration) == 0.0


def test_derive_threshold_is_none_for_an_empty_calibration() -> None:
    empty = EnsembleFalseAcceptanceCalibration(calibration_id="empty", configurations=[])
    assert derive_ensemble_fa_threshold(empty) is None
    assert derive_ensemble_fa_threshold(None) is None


def test_measured_fa_looks_up_the_exact_configuration() -> None:
    calibration = _calibration(configurations=(("2", "2", 0.0, 50), ("3", "3", 0.2, 50)))
    assert measured_fa_for_configuration(calibration, ensemble_size=2, distinct_provider_families=2) == 0.0
    assert measured_fa_for_configuration(calibration, ensemble_size=3, distinct_provider_families=3) == 0.2
    # An unmeasured configuration returns None (never auto-advance-eligible).
    assert measured_fa_for_configuration(calibration, ensemble_size=4, distinct_provider_families=4) is None


def test_ensemble_fa_within_threshold_distinguishes_none_vs_false() -> None:
    # None = uncalibrated; False = measured-and-over (or unmeasured config); True = within floor.
    members = _members()
    assert ensemble_fa_within_threshold(None, members) is None
    assert ensemble_fa_within_threshold(_calibration(configurations=(("2", "2", 0.0, 50),)), members) is True
    over = _calibration(configurations=(("2", "2", 0.5, 100), ("3", "3", 0.0, 100)))
    assert ensemble_fa_within_threshold(over, members) is False


def test_calibration_rejects_a_duplicate_configuration() -> None:
    with pytest.raises(ValueError, match="duplicate ensemble-FA calibration configuration"):
        EnsembleFalseAcceptanceCalibration(
            calibration_id="dup",
            configurations=[
                EnsembleCalibrationConfiguration(ensemble_size=2, distinct_provider_families=2, false_acceptance_rate=0.0, sample_count=10),
                EnsembleCalibrationConfiguration(ensemble_size=2, distinct_provider_families=2, false_acceptance_rate=0.1, sample_count=10),
            ],
        )


def test_calibration_rejects_a_nonzero_rate_with_zero_samples() -> None:
    with pytest.raises(ValueError, match="backed by samples"):
        EnsembleCalibrationConfiguration(
            ensemble_size=2, distinct_provider_families=2, false_acceptance_rate=0.1, sample_count=0
        )


def test_calibration_rejects_a_zero_rate_zero_sample_floor() -> None:
    # HELPER iter-2: even a zero-FA ("no observed false accepts") entry must be backed by samples —
    # otherwise an unmeasured configuration could set the auto-advance floor.
    with pytest.raises(ValueError, match="backed by samples"):
        EnsembleCalibrationConfiguration(
            ensemble_size=2, distinct_provider_families=2, false_acceptance_rate=0.0, sample_count=0
        )


# ---------------------------------------------------------------------------
# HELPER iter-2: the changed-path admission policy is part of the stamped policy hash
# ---------------------------------------------------------------------------


def test_policy_hash_covers_the_changed_path_policy() -> None:
    # Two policies identical except for the changed_path_policy MUST hash differently, so a stamped
    # ``policy_hash`` proves WHICH path policy admitted a pin (HELPER iter-2: previously the path
    # policy lived separately in GatePolicy.machine_pin and was not covered by the hash).
    from nlreq.machine_agreement import ChangedPathPolicy

    base_rules = MachinePinPolicyRules(calibration=_calibration())
    policy_a = MachinePinPolicy(
        policy_id="path-a",
        rules=base_rules.model_copy(
            update={"changed_path_policy": ChangedPathPolicy(enabled=True, allowed_changed_path_patterns=["docs/**"])}
        ),
    )
    policy_b = MachinePinPolicy(
        policy_id="path-b",
        rules=base_rules.model_copy(
            update={"changed_path_policy": ChangedPathPolicy(enabled=True, allowed_changed_path_patterns=["tests/**"])}
        ),
    )
    assert policy_content_hash(policy_a) != policy_content_hash(policy_b)


def test_machine_pin_admits_changed_paths_is_default_deny() -> None:
    # Default-deny: disabled → never admits; enabled but empty allow-list → never admits; enabled
    # with an allow-list admits only all-allowed, no-blocked changes (scope §6 / AC4).
    from nlreq.machine_agreement import ChangedPathPolicy, machine_pin_admits_changed_paths

    policy = MachinePinPolicy(policy_id="admit", rules=MachinePinPolicyRules(calibration=_calibration()))
    # Disabled (default) → never admits, even for an allow-listed path.
    assert machine_pin_admits_changed_paths(policy, ["docs/a.md"]) is False
    # Empty change set → never admits (no paths to validate).
    enabled_empty = policy.model_copy(
        update={"rules": policy.rules.model_copy(update={"changed_path_policy": ChangedPathPolicy(enabled=True)})}
    )
    assert machine_pin_admits_changed_paths(enabled_empty, []) is False
    # All-allowed, no-blocked → admits.
    enabled_docs = policy.model_copy(
        update={
            "rules": policy.rules.model_copy(
                update={"changed_path_policy": ChangedPathPolicy(enabled=True, allowed_changed_path_patterns=["docs/**"])}
            )
        }
    )
    assert machine_pin_admits_changed_paths(enabled_docs, ["docs/a.md", "docs/b.md"]) is True
    # An unmatched path → default-deny (rejected).
    assert machine_pin_admits_changed_paths(enabled_docs, ["docs/a.md", "src/main.py"]) is False
    # An auth path (block-list wins even when allow-listed) → rejected.
    enabled_all = policy.model_copy(
        update={
            "rules": policy.rules.model_copy(
                update={
                    "changed_path_policy": ChangedPathPolicy(
                        enabled=True, allowed_changed_path_patterns=["**"]
                    )
                }
            )
        }
    )
    assert machine_pin_admits_changed_paths(enabled_all, ["src/auth/login.py"]) is False


# ---------------------------------------------------------------------------
# The constructed pin resolves to the non-ACCEPTED machine-pinned status
# ---------------------------------------------------------------------------


def test_machine_pin_status_is_not_accepted_prefixed() -> None:
    # A machine-pinned package (the pin the router emits) resolves under decide_status to a status
    # that does NOT start with ACCEPTED, so the former prefix-check consumers never treat it as
    # human-accepted (acceptance #3).
    from nlreq.models import EvidenceObject
    from nlreq.status import decide_status, is_human_accepted

    decision = route_machine_pinning(_clean_input(), policy=_policy())
    assert decision.pinning is not None
    evidence = EvidenceObject(requirement_id="REQ-1")
    status = decide_status(evidence, decision.pinning)
    assert status.status is FinalStatus.MACHINE_PINNED_PENDING_REVIEW
    assert not status.status.value.startswith("ACCEPTED")
    assert is_human_accepted(status.status) is False
    assert isinstance(decision.pinning, PinningProvenance)
