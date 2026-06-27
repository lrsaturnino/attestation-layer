"""Tests for Zone 3 — the ``attest-spec`` orchestrator (three-zone scope §7; HELPER iter-2 #4/#10).

``attest-spec`` is the PRODUCTION WIRING of the ``machine_agreement`` trust state: it loads the
opt-in ``MachinePinPolicy`` and calls ``route_machine_pinning`` with REAL routing input derived
from each candidate (partition boundary flags, drafting-ensemble agreement, per-member audit
verdicts, deterministic-shape pass, achieved evidence levels, calibration threshold). These tests
pin:

  * AC1 — policy OFF (the default) → every rule routes to the human queue, no pin emitted;
  * AC2/#4 — policy ON + every measurable signal passes → the candidate is machine-pinned with a
    ``machine_agreement`` ``PinningProvenance``;
  * any unmet signal (shape fail) → human queue, no pin;
  * the consolidated queue carries the reason(s) and stage for each flagged item.

All CI-safe: deterministic partition + recorded drafting clients + an inline shape check.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from nlreq.attest import attest_spec_document
from nlreq.llm_client import RecordedLlmClient
from nlreq.machine_agreement import (
    ChangedPathPolicy,
    EnsembleCalibrationConfiguration,
    EnsembleFalseAcceptanceCalibration,
    MachinePinPolicy,
    MachinePinPolicyRules,
)
from nlreq.models import EvidenceLevel, FinalStatus

_DOC = (
    "# Payments\n"
    "\n"
    "The system shall reject unauthorized transfers.\n"
)

_AGREED_CONTROLLED = (
    "For every operation if the caller is unauthorized then the operation must be rejected."
)

_DRAFTING_PROV = [
    {"role": "drafting", "provider_family": "anthropic", "resolved_model": "claude-x"},
    {"role": "drafting", "provider_family": "openai", "resolved_model": "gpt-x"},
]

# A clean Zone 1 partition ensemble: ≥2 cross-provider members spanning ≥2 distinct provider
# families (scope §4). Machine pinning requires the rule's BOUNDARY to have been cross-checked by
# such an ensemble — a deterministic / single-provider partition can never auto-advance — so every
# test that expects a pin drives this agreeing ensemble alongside the drafting ensemble. The
# deterministic-partition refusal is exercised separately
# (``test_clean_draft_with_no_partition_ensemble_does_not_machine_pin``).
_PARTITION_PROV = [
    {"role": "partition", "provider_family": "anthropic", "resolved_model": "claude-p"},
    {"role": "partition", "provider_family": "openai", "resolved_model": "gpt-p"},
]


def _drafter(text: str) -> RecordedLlmClient:
    return RecordedLlmClient(fixture=text)


def _partition_clients(
    rule: str = "The system shall reject unauthorized transfers.",
) -> list[RecordedLlmClient]:
    """A 2-member cross-provider partition ensemble that AGREES (both propose the same rule).

    Both members replay the same candidate-rule proposal for every behavioral segment, so the
    ensemble agrees with no boundary disagreement and contributes the rule as the candidate. The
    default rule matches ``_DOC``'s behavioral sentence so the candidate text is unchanged from the
    deterministic partition (keeping the real source-fidelity audit grounded)."""
    import json

    fixture = json.dumps([{"rule": rule}])
    return [
        RecordedLlmClient(fixture="", partition_fixture=fixture),
        RecordedLlmClient(fixture="", partition_fixture=fixture),
    ]


def _policy() -> MachinePinPolicy:
    return MachinePinPolicy(
        policy_id="attest-test",
        rules=MachinePinPolicyRules(
            calibration=EnsembleFalseAcceptanceCalibration(
                calibration_id="ens-fa-1",
                configurations=[
                    EnsembleCalibrationConfiguration(
                        ensemble_size=2,
                        distinct_provider_families=2,
                        false_acceptance_rate=0.0,
                        sample_count=50,
                    )
                ],
            ),
            # The changed-path admission gate is load-bearing in routing (HELPER iter-3 #3): a
            # machine pin is recorded only for a change whose every path the opted-in low-risk
            # allow-list admits (default-deny, AC4). Tests that expect a pin supply a matching
            # ``changed_paths``; default-deny refusal is exercised separately.
            changed_path_policy=ChangedPathPolicy(
                enabled=True,
                allowed_changed_path_patterns=["src/**"],
            ),
        ),
    )


# A changed path on the policy's allow-list (src/**); passed to every test that expects a pin.
_ALLOWED_CHANGED_PATHS = ["src/module.py"]


def _shape_pass(_text: str) -> tuple[bool, list[EvidenceLevel]]:
    return True, [EvidenceLevel.TYPE_CHECKED, EvidenceLevel.SMT_CHECKED]


def _shape_fail(_text: str) -> tuple[bool, list[EvidenceLevel]]:
    return False, []


def _audit_pass(_text: str, _source: str | None = None) -> tuple[bool, str]:
    """An injected per-member audit pass (the audit is DISTINCT from the shape check, HELPER iter-1
    #3): tests that decouple from real parsing (the ``_AGREED_CONTROLLED`` fixture does not parse)
    inject this just as they inject ``_shape_pass``. The orchestrator passes the candidate's source
    prose as the second argument (HELPER iter-2 #4), which this injected pass ignores; the
    production CLI supplies the REAL ``deterministic_decomposition_audit_for_controlled_text``.
    Without an ``audit_check`` the orchestrator produces NO audit verdict (never a fabricated pass),
    so the candidate routes to a human — exercised by ``test_no_audit_check_routes_to_human_with_no_pin``."""
    return True, "test audit pass"


# ---------------------------------------------------------------------------
# AC1: policy off → every rule routes to the human queue, no pin
# ---------------------------------------------------------------------------


def test_policy_off_routes_every_candidate_to_human_with_no_pin() -> None:
    report = attest_spec_document(
        _DOC,
        drafting_clients=[_drafter(_AGREED_CONTROLLED), _drafter(_AGREED_CONTROLLED)],
        drafting_member_provenance=_DRAFTING_PROV,
        partition_clients=_partition_clients(),
        partition_member_provenance=_PARTITION_PROV,
        policy=None,  # machine pinning OFF (the default)
        shape_check=_shape_pass,
        audit_check=_audit_pass,
    )
    assert report.policy_off is True
    assert report.policy_id is None
    assert report.machine_pinned == []
    assert report.human_queue
    for item in report.human_queue:
        assert item.stage == "routing"
        assert any("disabled" in r for r in item.reasons)


# ---------------------------------------------------------------------------
# AC2 / #4: policy on + all signals pass → machine-pinned
# ---------------------------------------------------------------------------


def test_policy_on_with_clean_ensemble_machine_pins_the_candidate() -> None:
    report = attest_spec_document(
        _DOC,
        drafting_clients=[_drafter(_AGREED_CONTROLLED), _drafter(_AGREED_CONTROLLED)],
        drafting_member_provenance=_DRAFTING_PROV,
        partition_clients=_partition_clients(),
        partition_member_provenance=_PARTITION_PROV,
        policy=_policy(),
        shape_check=_shape_pass,
        audit_check=_audit_pass,
        changed_paths=_ALLOWED_CHANGED_PATHS,
    )
    assert report.policy_off is False
    assert report.policy_id == "attest-test"
    assert len(report.machine_pinned) == 1
    pin = report.machine_pinned[0]
    assert pin.controlled_text == _AGREED_CONTROLLED
    assert pin.pinning.kind == "machine_agreement"
    ensemble = pin.pinning.ensemble
    assert ensemble is not None
    assert {m.provider_family for m in ensemble.members} == {"anthropic", "openai"}
    assert all(v.verdict == "passed" for v in ensemble.audit_verdicts)
    # The pinning is the production wiring of route_machine_pinning (#4): the policy hash binds it
    # to the exact policy (ensemble rules + calibration + changed-path policy) that admitted it.
    assert ensemble.policy_hash


def test_a_machine_pinned_candidate_is_not_in_the_human_queue() -> None:
    report = attest_spec_document(
        _DOC,
        drafting_clients=[_drafter(_AGREED_CONTROLLED), _drafter(_AGREED_CONTROLLED)],
        drafting_member_provenance=_DRAFTING_PROV,
        partition_clients=_partition_clients(),
        partition_member_provenance=_PARTITION_PROV,
        policy=_policy(),
        shape_check=_shape_pass,
        audit_check=_audit_pass,
        changed_paths=_ALLOWED_CHANGED_PATHS,
    )
    pinned_indices = {pin.candidate_index for pin in report.machine_pinned}
    queued_indices = {item.candidate_index for item in report.human_queue}
    assert pinned_indices.isdisjoint(queued_indices)


# ---------------------------------------------------------------------------
# An unmet signal (shape fail) → human queue, no pin
# ---------------------------------------------------------------------------


def test_shape_failure_routes_to_human_with_no_pin() -> None:
    report = attest_spec_document(
        _DOC,
        drafting_clients=[_drafter(_AGREED_CONTROLLED), _drafter(_AGREED_CONTROLLED)],
        drafting_member_provenance=_DRAFTING_PROV,
        partition_clients=_partition_clients(),
        partition_member_provenance=_PARTITION_PROV,
        policy=_policy(),
        shape_check=_shape_fail,
        # Supply a passing audit + an allow-listed path so the ONLY unmet signal is the shape failure
        # (isolating the test's intent; without these the audit/changed-path gates would also refuse,
        # masking the signal).
        audit_check=_audit_pass,
        changed_paths=_ALLOWED_CHANGED_PATHS,
    )
    assert report.machine_pinned == []
    assert report.human_queue
    # The shape-fail signal is reported among the unmet signals for the routed candidate.
    joined = " ".join(reason for item in report.human_queue for reason in item.reasons)
    assert "deterministic shape" in joined


# ---------------------------------------------------------------------------
# A drafting disagreement routes the candidate to the human queue (no pin)
# ---------------------------------------------------------------------------


def test_drafting_disagreement_routes_to_human_with_no_pin() -> None:
    report = attest_spec_document(
        _DOC,
        drafting_clients=[
            _drafter(_AGREED_CONTROLLED),
            _drafter("For every operation if the caller is unauthorized then it must be allowed."),
        ],
        drafting_member_provenance=_DRAFTING_PROV,
        partition_clients=_partition_clients(),
        partition_member_provenance=_PARTITION_PROV,
        policy=_policy(),
        shape_check=_shape_pass,
        audit_check=_audit_pass,
    )
    assert report.machine_pinned == []
    assert any(item.stage == "drafting" for item in report.human_queue)


# ---------------------------------------------------------------------------
# A single drafting voice (no ensemble agreement) never machine-pins
# ---------------------------------------------------------------------------


def test_single_drafter_never_machine_pins() -> None:
    # A single drafting client records a controlled_text but NO agreement hash → routing routes to
    # human (machine pinning requires a cross-provider-agreed draft).
    report = attest_spec_document(
        _DOC,
        drafting_clients=[_drafter(_AGREED_CONTROLLED)],
        drafting_member_provenance=_DRAFTING_PROV[:1],
        policy=_policy(),
        shape_check=_shape_pass,
        audit_check=_audit_pass,
    )
    assert report.machine_pinned == []
    assert report.human_queue


# ---------------------------------------------------------------------------
# The machine-pinned pin resolves to the non-ACCEPTED status (AC3)
# ---------------------------------------------------------------------------


def test_machine_pinned_pin_resolves_to_machine_pinned_status() -> None:
    from nlreq.models import EvidenceObject
    from nlreq.status import decide_status, is_human_accepted

    report = attest_spec_document(
        _DOC,
        drafting_clients=[_drafter(_AGREED_CONTROLLED), _drafter(_AGREED_CONTROLLED)],
        drafting_member_provenance=_DRAFTING_PROV,
        partition_clients=_partition_clients(),
        partition_member_provenance=_PARTITION_PROV,
        policy=_policy(),
        shape_check=_shape_pass,
        audit_check=_audit_pass,
        changed_paths=_ALLOWED_CHANGED_PATHS,
    )
    pin = report.machine_pinned[0]
    status = decide_status(EvidenceObject(requirement_id="REQ-1"), pin.pinning)
    assert status.status is FinalStatus.MACHINE_PINNED_PENDING_REVIEW
    assert not status.status.value.startswith("ACCEPTED")
    assert is_human_accepted(status.status) is False


# ---------------------------------------------------------------------------
# HELPER iter-3 #1: the REAL (non-injected) deterministic shape check admits a parseable
# requirement, so the production ``attest-spec`` path can machine-pin without a test-injected
# ``shape_check`` (closing the iter-3 gap where the CLI never supplied one).
# ---------------------------------------------------------------------------


def test_real_shape_check_machine_pins_a_parseable_requirement_without_injection() -> None:
    from nlreq.attest import (
        deterministic_decomposition_audit_for_controlled_text,
        deterministic_shape_for_controlled_text,
    )

    # A genuinely parseable controlled requirement (the authorization_precondition fixture):
    # the REAL shape check parses + binds + evidences it (shape_ok=True, achieved levels), so the
    # production path machine-pins it WITHOUT injecting a fake ``shape_check``.
    parseable = (
        "For every operation request:\n"
        "  if actor is not authorized\n"
        "  then operation must be rejected before state_change.\n"
    )
    # Sanity: the real shape check actually admits this text (parse + bind + evidence pass).
    shape_ok, achieved = deterministic_shape_for_controlled_text(parseable)
    assert shape_ok is True
    assert achieved  # the deterministic levels the package's claims achieve (MEASURABLE, AC7)

    report = attest_spec_document(
        _DOC,
        drafting_clients=[_drafter(parseable), _drafter(parseable)],
        drafting_member_provenance=_DRAFTING_PROV,
        partition_clients=_partition_clients(),
        partition_member_provenance=_PARTITION_PROV,
        policy=_policy(),
        # NO injected checks: the orchestrator is given the REAL production shape + audit checks.
        shape_check=deterministic_shape_for_controlled_text,
        audit_check=deterministic_decomposition_audit_for_controlled_text,
        changed_paths=_ALLOWED_CHANGED_PATHS,
    )
    assert report.policy_off is False
    assert len(report.machine_pinned) == 1
    pin = report.machine_pinned[0]
    assert pin.controlled_text == parseable
    assert pin.pinning.kind == "machine_agreement"


def test_real_shape_check_refuses_an_unparseable_requirement() -> None:
    from nlreq.attest import (
        deterministic_decomposition_audit_for_controlled_text,
        deterministic_shape_for_controlled_text,
    )

    # An unparseable controlled text: the real shape check returns shape_ok=False, so routing
    # refuses (deterministic-shape signal unmet) and no pin is emitted — never a crash.
    unparseable = "this is not valid controlled dsl at all"
    shape_ok, achieved = deterministic_shape_for_controlled_text(unparseable)
    assert shape_ok is False
    assert achieved == []

    report = attest_spec_document(
        _DOC,
        drafting_clients=[_drafter(unparseable), _drafter(unparseable)],
        drafting_member_provenance=_DRAFTING_PROV,
        partition_clients=_partition_clients(),
        partition_member_provenance=_PARTITION_PROV,
        policy=_policy(),
        shape_check=deterministic_shape_for_controlled_text,
        audit_check=deterministic_decomposition_audit_for_controlled_text,
        changed_paths=_ALLOWED_CHANGED_PATHS,
    )
    assert report.machine_pinned == []
    joined = " ".join(reason for item in report.human_queue for reason in item.reasons)
    assert "deterministic shape" in joined


# ---------------------------------------------------------------------------
# HELPER iter-3 #3: changed-path admission is load-bearing — a path NOT on the allow-list, or no
# paths at all, routes to the human queue (default-deny, AC4); the stampable policy hash now
# records the path policy that actually admitted the pin.
# ---------------------------------------------------------------------------


def test_changed_path_not_on_allow_list_routes_to_human_default_deny() -> None:
    report = attest_spec_document(
        _DOC,
        drafting_clients=[_drafter(_AGREED_CONTROLLED), _drafter(_AGREED_CONTROLLED)],
        drafting_member_provenance=_DRAFTING_PROV,
        partition_clients=_partition_clients(),
        partition_member_provenance=_PARTITION_PROV,
        policy=_policy(),
        shape_check=_shape_pass,
        audit_check=_audit_pass,
        # A path NOT on the src/** allow-list → the default-deny gate refuses the machine pin.
        changed_paths=["contracts/wallet/Transfer.sol"],
    )
    assert report.machine_pinned == []
    joined = " ".join(reason for item in report.human_queue for reason in item.reasons)
    assert "changed-path admission gate" in joined


def test_no_changed_paths_routes_to_human_default_deny() -> None:
    report = attest_spec_document(
        _DOC,
        drafting_clients=[_drafter(_AGREED_CONTROLLED), _drafter(_AGREED_CONTROLLED)],
        drafting_member_provenance=_DRAFTING_PROV,
        partition_clients=_partition_clients(),
        partition_member_provenance=_PARTITION_PROV,
        policy=_policy(),
        shape_check=_shape_pass,
        audit_check=_audit_pass,
        # No changed paths supplied → the default-deny gate admits nothing.
        changed_paths=None,
    )
    assert report.machine_pinned == []
    joined = " ".join(reason for item in report.human_queue for reason in item.reasons)
    assert "changed-path admission gate" in joined


# ---------------------------------------------------------------------------
# HELPER iter-3 #2: Zone 3 — the downstream artifact graph. The orchestrator DETERMINISTICALLY
# produces IR v0.2 + lowering + requirement-set-consistency for every agreed candidate, runs the
# coverage gate when registry+impact are supplied, and runs S&R for a single-candidate change when
# all four artifacts are supplied. Blockers route to the human queue; absent external artifacts are
# recorded informationally (never a faked pass).
# ---------------------------------------------------------------------------


# A genuinely parseable controlled requirement (the authorization_precondition fixture): the only
# form the orchestrator can lower to IR v0.2 + the lowered artifact.
_PARSEABLE_CONTROLLED = (
    "For every operation request:\n"
    "  if actor is not authorized\n"
    "  then operation must be rejected before state_change.\n"
)


def _coverage_registry(tmp_path: Path):  # type: ignore[no-untyped-def]
    """A system-spec registry covering only the ``redemption`` module (mirrors test_coverage)."""
    from nlreq.system_spec import SystemSpecRegistry

    specs = tmp_path / "specs"
    specs.mkdir(exist_ok=True)
    (specs / "Redemption.tla").write_text("---- MODULE Redemption ----\n====\n")
    return SystemSpecRegistry.model_validate(
        {
            "schema_version": "0.1",
            "specs": [
                {
                    "spec_id": "spec:redemption",
                    "module_ids": ["redemption"],
                    "formalism": "tla",
                    "path": "specs/Redemption.tla",
                    "version": "1",
                    "review_status": "reviewed",
                    "freshness": "fresh",
                }
            ],
        }
    )


def _coverage_impact(modules: list[str]):  # type: ignore[no-untyped-def]
    from nlreq.impact import ImpactAnalysisArtifact

    return ImpactAnalysisArtifact(
        adapter_id="python-source",
        language="python",
        input_symbols=["finalize_redemption"],
        affected_modules=modules,
    )


def test_zone3_produces_ir_v2_and_set_consistency_for_a_parseable_candidate() -> None:
    report = attest_spec_document(
        _DOC,
        drafting_clients=[_drafter(_PARSEABLE_CONTROLLED), _drafter(_PARSEABLE_CONTROLLED)],
        drafting_member_provenance=_DRAFTING_PROV,
        partition_clients=_partition_clients(),
        partition_member_provenance=_PARTITION_PROV,
        policy=_policy(),
        shape_check=_shape_pass,
        audit_check=_audit_pass,
        changed_paths=_ALLOWED_CHANGED_PATHS,
    )
    # The candidate is machine-pinned (clean ensemble + parseable + allow-listed path).
    assert len(report.machine_pinned) == 1
    # Zone 3 produced IR v0.2 + a lowered artifact for it (deterministic, always).
    assert len(report.downstream) == 1
    entry = report.downstream[0]
    assert entry.ir_v2_produced is True
    assert entry.ir_v2_hash  # a real IR v0.2 content hash
    assert entry.lowered_status is not None  # lowering ran ("refused" for the migrated IR)
    # HELPER iter-1 #1: the report EMBEDS the real artifact OBJECTS, not only hashes/status. The IR
    # v0.2 round-trips its hash and the lowered artifact carries its refusal diagnostics (honest).
    assert entry.ir_v2 is not None and entry.ir_v2.ir_version == "0.2"
    from nlreq.jsonutil import sha256_json

    assert sha256_json(entry.ir_v2) == entry.ir_v2_hash
    assert entry.lowered is not None and entry.lowered.status == entry.lowered_status
    if entry.lowered.status == "refused":
        assert entry.lowered.diagnostics  # the refusal reason is surfaced, never hidden
    # The full set-consistency report is embedded too (not just the queue-routing summary).
    assert report.set_consistency_report is not None
    assert report.set_consistency_report.result == "valid"
    # The whole Zone 1 partition manifest is embedded (the completeness oracle).
    assert report.partition is not None and report.partition.segments
    # requirement-set-consistency ran over the (single) IR-v0.2 set → valid, no contradictions.
    assert report.set_consistency is not None
    assert report.set_consistency.result == "valid"
    assert report.set_consistency.contradiction_count == 0


def test_zone3_records_explicit_prerequisites_when_external_artifacts_absent() -> None:
    # No registry/impact supplied → the coverage gate + system-consistency + S&R cannot run. The
    # orchestrator records EXPLICIT, ACTIONABLE prerequisites (impact + registry, each with the
    # command to produce it), NOT a vague ``needs_downstream_artifacts`` note (HELPER iter-1 #2).
    report = attest_spec_document(
        _DOC,
        drafting_clients=[_drafter(_PARSEABLE_CONTROLLED), _drafter(_PARSEABLE_CONTROLLED)],
        drafting_member_provenance=_DRAFTING_PROV,
        partition_clients=_partition_clients(),
        partition_member_provenance=_PARTITION_PROV,
        policy=_policy(),
        shape_check=_shape_pass,
        audit_check=_audit_pass,
        changed_paths=_ALLOWED_CHANGED_PATHS,
    )
    assert len(report.downstream) == 1
    entry = report.downstream[0]
    # IR v0.2 + the lowered artifact were PRODUCED and EMBEDDED (HELPER iter-1 #1), not discarded.
    assert entry.ir_v2_produced is True
    assert entry.ir_v2 is not None and entry.ir_v2.ir_version == "0.2"
    assert entry.lowered is not None and entry.lowered.status == entry.lowered_status
    # The stage stays ``ir_v2_produced`` — the missing external inputs are surfaced as explicit
    # prerequisites, not by silently mutating the stage to ``needs_downstream_artifacts``.
    assert entry.stage.value == "ir_v2_produced"
    assert entry.system_consistency is None  # cannot be produced without registry + impact
    assert entry.s_and_r_result is None
    # The explicit prerequisites name impact + registry, each with the command to produce it.
    artifacts = {prerequisite.artifact for prerequisite in report.prerequisites}
    assert artifacts == {"impact", "registry"}
    for prerequisite in report.prerequisites:
        assert prerequisite.command  # an actionable next-step command, never blank
    # No coverage / S&R queue items were emitted (no actionable blocker — only missing inputs).
    assert not any(item.stage in ("needs_coverage", "s_and_r") for item in report.human_queue)
    assert report.coverage_gate is None
    assert report.coverage_report is None


def test_zone3_coverage_gate_queues_unspecified_modules(tmp_path: Path) -> None:
    report = attest_spec_document(
        _DOC,
        drafting_clients=[_drafter(_PARSEABLE_CONTROLLED), _drafter(_PARSEABLE_CONTROLLED)],
        drafting_member_provenance=_DRAFTING_PROV,
        partition_clients=_partition_clients(),
        partition_member_provenance=_PARTITION_PROV,
        policy=_policy(),
        shape_check=_shape_pass,
        audit_check=_audit_pass,
        changed_paths=_ALLOWED_CHANGED_PATHS,
        # registry covers only ``redemption``; the change also touches ``wallet`` → unspecified.
        registry=_coverage_registry(tmp_path),
        impact=_coverage_impact(["redemption", "wallet"]),
        project_root=tmp_path,
    )
    # The coverage gate ran and found ``wallet`` unspecified.
    assert report.coverage_gate is not None
    assert report.coverage_gate.result == "needs_spec_coverage"
    assert report.coverage_gate.unspecified_modules == ["wallet"]
    # The unspecified module routes to the human queue for specula-extract (never a pass).
    coverage_items = [item for item in report.human_queue if item.stage == "needs_coverage"]
    assert len(coverage_items) == 1
    assert coverage_items[0].candidate_text == "wallet"


def test_zone3_coverage_gate_passes_when_every_module_is_specified(tmp_path: Path) -> None:
    report = attest_spec_document(
        _DOC,
        drafting_clients=[_drafter(_PARSEABLE_CONTROLLED), _drafter(_PARSEABLE_CONTROLLED)],
        drafting_member_provenance=_DRAFTING_PROV,
        partition_clients=_partition_clients(),
        partition_member_provenance=_PARTITION_PROV,
        policy=_policy(),
        shape_check=_shape_pass,
        audit_check=_audit_pass,
        changed_paths=_ALLOWED_CHANGED_PATHS,
        registry=_coverage_registry(tmp_path),
        impact=_coverage_impact(["redemption"]),  # every affected module has a spec
        project_root=tmp_path,
    )
    assert report.coverage_gate is not None
    assert report.coverage_gate.result == "covered"
    assert not any(item.stage == "needs_coverage" for item in report.human_queue)


def test_zone3_produces_system_consistency_and_s_and_r_from_its_own_lowered(tmp_path: Path) -> None:
    # When registry + impact are supplied the orchestrator PRODUCES the S∧R system-consistency from
    # its OWN lowered artifact and the S∧R composition report (HELPER iter-1 #2: never caller-
    # supplied). The v0.1→v0.2 migration's lowering REFUSES (migration-shape limitation), so the
    # produced consistency is honestly ``unsupported`` and the produced S∧R is ``unsupported`` —
    # surfaced via the embedded artifacts + the report's ``limitations``. HELPER iter-2 #3: an
    # unverified S∧R stage must NOT let a machine-pinned candidate appear clean, so ``unsupported``
    # is now an unresolved downstream blocker — it routes the candidate to the human queue AND
    # reverts the machine pin to attention_required (distinct from a counterexample, which DISPROVES
    # the rule; ``unsupported`` means "could not be validated", recorded as such).
    report = attest_spec_document(
        _DOC,
        drafting_clients=[_drafter(_PARSEABLE_CONTROLLED), _drafter(_PARSEABLE_CONTROLLED)],
        drafting_member_provenance=_DRAFTING_PROV,
        partition_clients=_partition_clients(),
        partition_member_provenance=_PARTITION_PROV,
        policy=_policy(),
        shape_check=_shape_pass,
        audit_check=_audit_pass,
        changed_paths=_ALLOWED_CHANGED_PATHS,
        registry=_coverage_registry(tmp_path),
        impact=_coverage_impact(["redemption"]),
        project_root=tmp_path,
    )
    assert len(report.downstream) == 1
    entry = report.downstream[0]
    # The orchestrator PRODUCED + EMBEDDED the system-consistency and S∧R composition artifacts.
    assert entry.system_consistency is not None
    assert entry.s_and_r is not None
    # The migration-shape limitation makes the produced lowering refuse → consistency/S∧R unsupported.
    assert entry.system_consistency.result.status == "unsupported"
    assert entry.s_and_r_result == "unsupported"
    # HELPER iter-2 #3: ``unsupported`` is an unresolved downstream blocker — it routes the candidate
    # to the human queue with a "could not be validated" reason (distinct from a disproof).
    s_and_r_items = [item for item in report.human_queue if item.stage == "s_and_r"]
    assert len(s_and_r_items) == 1
    assert "unsupported" in " ".join(s_and_r_items[0].reasons)
    # The machine pin is REVERTED to attention_required (it keeps its provenance, but is no longer a
    # clean, no-attention pin), and its candidate is in the human queue (HELPER iter-2 #2/#3).
    assert len(report.machine_pinned) == 1
    pin = report.machine_pinned[0]
    assert pin.attention_required is True
    assert any("unsupported" in reason for reason in pin.attention_reasons)
    assert pin.candidate_index in {item.candidate_index for item in report.human_queue}
    assert report.limitations
    # No external prerequisites remain (registry + impact were both supplied).
    assert report.prerequisites == []


def test_single_candidate_coverage_gap_does_not_duplicate_attention_reasons(tmp_path: Path) -> None:
    # A single candidate whose change has BOTH a coverage gap (an unspecified affected module) and an
    # ``unsupported`` S&R result must record each distinct downstream blocker exactly once on its
    # pin. Coverage attribution lives in exactly one place (the document-wide block), so the coverage
    # reason is NOT recorded twice even though the single-candidate S&R path also runs.
    report = attest_spec_document(
        _DOC,
        drafting_clients=[_drafter(_PARSEABLE_CONTROLLED), _drafter(_PARSEABLE_CONTROLLED)],
        drafting_member_provenance=_DRAFTING_PROV,
        partition_clients=_partition_clients(),
        partition_member_provenance=_PARTITION_PROV,
        policy=_policy(),
        shape_check=_shape_pass,
        audit_check=_audit_pass,
        changed_paths=_ALLOWED_CHANGED_PATHS,
        # registry covers only ``redemption``; the change touches ``wallet`` → a coverage gap.
        registry=_coverage_registry(tmp_path),
        impact=_coverage_impact(["wallet"]),
        project_root=tmp_path,
    )
    assert len(report.machine_pinned) == 1
    pin = report.machine_pinned[0]
    assert pin.attention_required is True
    # No duplicate reason strings: the human report never shows the same blocker sentence twice.
    assert len(pin.attention_reasons) == len(set(pin.attention_reasons))
    # Both distinct blockers are present exactly once: the coverage gap and the unsupported S&R.
    coverage_reasons = [r for r in pin.attention_reasons if "a coverage gap is never a pass" in r]
    assert len(coverage_reasons) == 1
    s_and_r_reasons = [r for r in pin.attention_reasons if "unsupported" in r]
    assert len(s_and_r_reasons) == 1


# ---------------------------------------------------------------------------
# HELPER iter-1 #3: the audit is a REAL computation DISTINCT from the shape check — never fabricated
# from ``shape_ok``. Without an ``audit_check`` NO verdict is produced (the candidate routes to a
# human); with one, the pin's provenance records the AUDIT verdict's own detail.
# ---------------------------------------------------------------------------


def test_no_audit_check_routes_to_human_with_no_pin() -> None:
    # shape passes + every other signal is satisfiable, but NO audit_check is supplied → the
    # orchestrator produces NO audit verdict (it no longer fabricates one from shape_ok), so the
    # audit signal is unmet and the candidate routes to the human queue with no pin.
    report = attest_spec_document(
        _DOC,
        drafting_clients=[_drafter(_AGREED_CONTROLLED), _drafter(_AGREED_CONTROLLED)],
        drafting_member_provenance=_DRAFTING_PROV,
        partition_clients=_partition_clients(),
        partition_member_provenance=_PARTITION_PROV,
        policy=_policy(),
        shape_check=_shape_pass,
        # NO audit_check supplied.
        changed_paths=_ALLOWED_CHANGED_PATHS,
    )
    assert report.machine_pinned == []
    joined = " ".join(reason for item in report.human_queue for reason in item.reasons)
    assert "audit" in joined


def test_audit_verdict_in_pin_provenance_is_distinct_from_shape() -> None:
    # When pinned, the pin's ensemble audit verdicts carry the AUDIT's own detail string — proving
    # the verdict came from the audit computation, not from reusing the shape result.
    def _audit(_text: str, _source: str | None = None) -> tuple[bool, str]:
        return True, "ensemble decomposition audit: covered all clauses"

    report = attest_spec_document(
        _DOC,
        drafting_clients=[_drafter(_AGREED_CONTROLLED), _drafter(_AGREED_CONTROLLED)],
        drafting_member_provenance=_DRAFTING_PROV,
        partition_clients=_partition_clients(),
        partition_member_provenance=_PARTITION_PROV,
        policy=_policy(),
        shape_check=_shape_pass,
        audit_check=_audit,
        changed_paths=_ALLOWED_CHANGED_PATHS,
    )
    assert len(report.machine_pinned) == 1
    ensemble = report.machine_pinned[0].pinning.ensemble
    assert ensemble is not None
    # One verdict per member, each carrying the audit's distinct detail (not the shape result).
    assert len(ensemble.audit_verdicts) == len(ensemble.members)
    assert all(
        verdict.detail == "ensemble decomposition audit: covered all clauses"
        for verdict in ensemble.audit_verdicts
    )


def test_real_deterministic_audit_fails_a_vacuous_decomposition() -> None:
    # The real deterministic audit is a genuine, falsifiable computation distinct from the shape
    # check: a controlled text that does not parse to a non-vacuous premise+obligation FAILS the
    # audit (returns (False, reason)), never a fabricated pass.
    from nlreq.attest import deterministic_decomposition_audit_for_controlled_text

    ok, detail = deterministic_decomposition_audit_for_controlled_text("not a controlled rule")
    assert ok is False
    assert "decomposition audit failed" in detail


# ---------------------------------------------------------------------------
# HELPER iter-1 #1: the CLI fans the produced graph artifacts out to --out-dir as standalone files
# (the dedicated commands consume them), in addition to embedding them in the consolidated report.
# ---------------------------------------------------------------------------


def test_cli_attest_spec_writes_artifact_bundle(tmp_path: Path) -> None:
    import json

    from nlreq.cli import main

    document = tmp_path / "spec.md"
    document.write_text(_DOC)
    out = tmp_path / "report.json"
    out_dir = tmp_path / "artifacts"

    # Policy OFF (the default): the CLI still PRODUCES + EMITS the downstream graph artifacts for
    # every agreed candidate; only the machine-pin routing is disabled. With no drafting clients the
    # deterministic partition yields a candidate whose plain text is the controlled text, which the
    # real shape/audit checks parse — so IR v0.2 + lowering are produced and fanned out.
    exit_code = main(
        [
            "attest-spec",
            str(document),
            "--out",
            str(out),
            "--out-dir",
            str(out_dir),
        ]
    )
    assert exit_code == 0
    # The consolidated report embeds the partition manifest.
    report = json.loads(out.read_text())
    assert report["partition"]["segments"]
    # The artifact bundle was written with the partition manifest as a standalone file.
    assert (out_dir / "partition.json").is_file()
    bundle_partition = json.loads((out_dir / "partition.json").read_text())
    assert bundle_partition["document_hash"] == report["document_hash"]


def test_artifact_fan_out_writes_every_produced_graph_artifact(tmp_path: Path) -> None:
    # The per-candidate fan-out (HELPER iter-1 #1) needs DRAFTED candidates (a controlled text to
    # lower), which the offline CLI cannot produce without a live transport. Drive the orchestrator
    # with recorded drafters + registry/impact so the produced graph carries IR v0.2 + lowering +
    # system-consistency + S&R, then exercise the CLI fan-out helper directly and assert every
    # produced artifact is written as a standalone file.
    from nlreq.cli import _write_attest_artifacts

    report = attest_spec_document(
        _DOC,
        drafting_clients=[_drafter(_PARSEABLE_CONTROLLED), _drafter(_PARSEABLE_CONTROLLED)],
        drafting_member_provenance=_DRAFTING_PROV,
        partition_clients=_partition_clients(),
        partition_member_provenance=_PARTITION_PROV,
        policy=_policy(),
        shape_check=_shape_pass,
        audit_check=_audit_pass,
        changed_paths=_ALLOWED_CHANGED_PATHS,
        registry=_coverage_registry(tmp_path),
        impact=_coverage_impact(["redemption"]),
        project_root=tmp_path,
    )
    out_dir = tmp_path / "bundle"
    written = _write_attest_artifacts(out_dir, report)
    requirement_id = report.downstream[0].requirement_id
    # Each produced artifact is a standalone, replayable file the dedicated commands consume.
    assert (out_dir / "partition.json").is_file()
    assert (out_dir / "set-consistency.json").is_file()
    assert (out_dir / "coverage.json").is_file()
    assert (out_dir / "ir-v2" / f"{requirement_id}.json").is_file()
    assert (out_dir / "lowered" / f"{requirement_id}.json").is_file()
    assert (out_dir / "system-consistency" / f"{requirement_id}.json").is_file()
    assert (out_dir / "s-and-r" / f"{requirement_id}.json").is_file()
    assert written >= 7  # partition + set-consistency + coverage + 4 per-candidate artifacts


# ---------------------------------------------------------------------------
# HELPER iter-2 #4: the deterministic audit is STRENGTHENED to check source-span fidelity, not only
# non-vacuous syntax — a parseable, non-vacuous rewrite that drifted from its source prose FAILS.
# ---------------------------------------------------------------------------


def test_real_audit_fails_a_rewrite_ungrounded_in_its_source() -> None:
    from nlreq.attest import deterministic_decomposition_audit_for_controlled_text

    # A parseable, NON-VACUOUS controlled rule (it passes the decomposition floor) whose subject is
    # UNRELATED to the source prose → the source-span fidelity floor catches it: the rewrite shares
    # no salient content term with its source (content invented relative to the source span).
    controlled = _PARSEABLE_CONTROLLED
    source = "The cache must be flushed every hour for performance."
    ok, detail = deterministic_decomposition_audit_for_controlled_text(controlled, source)
    assert ok is False
    assert "source" in detail  # the failure cites source-span fidelity, not vacuity


def test_real_audit_passes_a_faithful_paraphrase_of_its_source() -> None:
    from nlreq.attest import deterministic_decomposition_audit_for_controlled_text

    # The source prose shares salient domain terms (reject/unauthorized) with the rewrite — a
    # legitimate paraphrase grounds (``reject``→``rejected``), so the fidelity floor passes.
    controlled = _PARSEABLE_CONTROLLED
    source = "The system shall reject unauthorized transfers."
    ok, detail = deterministic_decomposition_audit_for_controlled_text(controlled, source)
    assert ok is True
    assert "fidelity" in detail  # the pass records that source-span fidelity was checked


def test_real_audit_without_source_runs_only_the_decomposition_floor() -> None:
    from nlreq.attest import deterministic_decomposition_audit_for_controlled_text

    # With no source prose the fidelity floor is skipped (it cannot ground against nothing); only the
    # decomposition floor runs, so a parseable non-vacuous rule passes and an unparseable one fails.
    ok, _ = deterministic_decomposition_audit_for_controlled_text(_PARSEABLE_CONTROLLED)
    assert ok is True
    bad, detail = deterministic_decomposition_audit_for_controlled_text("not a controlled rule")
    assert bad is False
    assert "decomposition audit failed" in detail


# ---------------------------------------------------------------------------
# HELPER iter-2 #1: attest-spec PRODUCES the source-impact artifact (it does not only consume
# --impact); the orchestrator invokes the producer, embeds the impact, records its provenance, and
# runs the coverage gate against it. A supplied --impact takes precedence as a replay/override.
# ---------------------------------------------------------------------------


def test_attest_produces_and_embeds_impact_via_producer(tmp_path: Path) -> None:
    produced = _coverage_impact(["redemption", "wallet"])
    calls: list[int] = []

    def _producer():  # type: ignore[no-untyped-def]
        calls.append(1)
        return produced

    report = attest_spec_document(
        _DOC,
        drafting_clients=[_drafter(_PARSEABLE_CONTROLLED), _drafter(_PARSEABLE_CONTROLLED)],
        drafting_member_provenance=_DRAFTING_PROV,
        partition_clients=_partition_clients(),
        partition_member_provenance=_PARTITION_PROV,
        policy=_policy(),
        shape_check=_shape_pass,
        audit_check=_audit_pass,
        changed_paths=_ALLOWED_CHANGED_PATHS,
        registry=_coverage_registry(tmp_path),
        impact_producer=_producer,  # NO --impact: the orchestrator PRODUCES it
        project_root=tmp_path,
    )
    assert calls == [1]  # the producer was invoked exactly once
    assert report.impact_provenance == "produced"
    assert report.impact is not None
    assert report.impact.affected_modules == ["redemption", "wallet"]
    # The produced impact drove the coverage gate (wallet is unspecified, never a pass).
    assert report.coverage_gate is not None
    assert report.coverage_gate.unspecified_modules == ["wallet"]
    # No impact prerequisite remains (it was produced) — only registry was absent.
    artifacts = {prerequisite.artifact for prerequisite in report.prerequisites}
    assert "impact" not in artifacts


def test_attest_supplied_impact_takes_precedence_over_producer(tmp_path: Path) -> None:
    supplied = _coverage_impact(["redemption"])

    def _producer():  # type: ignore[no-untyped-def]
        raise AssertionError("the producer must not run when --impact is supplied")

    report = attest_spec_document(
        _DOC,
        drafting_clients=[_drafter(_PARSEABLE_CONTROLLED), _drafter(_PARSEABLE_CONTROLLED)],
        drafting_member_provenance=_DRAFTING_PROV,
        partition_clients=_partition_clients(),
        partition_member_provenance=_PARTITION_PROV,
        policy=_policy(),
        shape_check=_shape_pass,
        audit_check=_audit_pass,
        changed_paths=_ALLOWED_CHANGED_PATHS,
        registry=_coverage_registry(tmp_path),
        impact=supplied,
        impact_producer=_producer,
        project_root=tmp_path,
    )
    assert report.impact_provenance == "supplied"
    assert report.impact is not None
    assert report.impact.affected_modules == ["redemption"]


def test_cli_attest_spec_produces_impact_from_manifest(tmp_path: Path) -> None:
    import json

    from nlreq.cli import main

    # A minimal REAL Python source tree + manifest: the impact producer maps the changed symbol to
    # affected modules through the real (ast-backed) call graph, so attest-spec PRODUCES impact
    # end-to-end from --manifest/--symbol (HELPER iter-2 #1 / AC8).
    src = tmp_path / "src"
    src.mkdir()
    (src / "auth.py").write_text(
        "from state import state_change\n\n"
        "def operation(actor):\n"
        "    return state_change()\n"
    )
    (src / "state.py").write_text("def state_change():\n    return 'changed'\n")
    manifest = tmp_path / "manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "schema_version": "0.1",
                "adapter": "python-source",
                "language": "python",
                "runtime": "cpython",
                "modules": [
                    {"module_id": "auth", "path": "src/auth.py", "symbols": ["operation"]},
                    {"module_id": "state", "path": "src/state.py", "symbols": ["state_change"]},
                ],
            }
        )
    )
    document = tmp_path / "spec.md"
    document.write_text(_DOC)
    out = tmp_path / "report.json"
    out_dir = tmp_path / "artifacts"

    exit_code = main(
        [
            "attest-spec",
            str(document),
            "--manifest",
            str(manifest),
            "--symbol",
            "operation",
            "--project-root",
            str(tmp_path),
            "--out",
            str(out),
            "--out-dir",
            str(out_dir),
        ]
    )
    assert exit_code == 0
    report = json.loads(out.read_text())
    # attest-spec PRODUCED the impact artifact (not consumed via --impact) and embedded it.
    assert report["impact_provenance"] == "produced"
    assert report["impact"] is not None
    assert "auth" in report["impact"]["affected_modules"]
    # No impact prerequisite remains (it was produced).
    assert "impact" not in {prerequisite["artifact"] for prerequisite in report["prerequisites"]}
    # The produced impact is fanned out as a standalone, replayable file.
    assert (out_dir / "impact.json").is_file()
    bundle_impact = json.loads((out_dir / "impact.json").read_text())
    assert bundle_impact["affected_modules"] == report["impact"]["affected_modules"]


def test_cli_attest_spec_manifest_without_symbol_is_a_usage_error(tmp_path: Path) -> None:
    from nlreq.cli import main

    manifest = tmp_path / "manifest.json"
    manifest.write_text("{}")
    document = tmp_path / "spec.md"
    document.write_text(_DOC)
    # --manifest with no --symbol cannot produce impact → fail-fast usage error (never a silent
    # no-op that drops to a prerequisite).
    exit_code = main(
        [
            "attest-spec",
            str(document),
            "--manifest",
            str(manifest),
            "--out",
            str(tmp_path / "report.json"),
        ]
    )
    assert exit_code == 2


# ---------------------------------------------------------------------------
# HELPER iter-2 #2/#3: the post-graph reconciliation marks a pinned candidate attention_required and
# lists it in the human queue when a downstream blocker pertains to it. The S&R-unsupported path is
# exercised end-to-end above; these unit tests pin the reconciliation helper's branches directly
# (including the coverage-only case where the candidate is not otherwise candidate-keyed in queue).
# ---------------------------------------------------------------------------


def _machine_pin(candidate_index: int = 0):  # type: ignore[no-untyped-def]
    from nlreq.attest import AttestMachinePin
    from nlreq.models import (
        EnsembleAgreementResult,
        EnsembleAuditVerdict,
        EnsembleEvidence,
        EnsembleMember,
        PinningProvenance,
    )

    members = [
        EnsembleMember(member_id="m1", resolved_model_id="claude-x", provider_family="anthropic"),
        EnsembleMember(member_id="m2", resolved_model_id="gpt-x", provider_family="openai"),
    ]
    evidence = EnsembleEvidence(
        members=members,
        agreement=EnsembleAgreementResult(agreed=True, agreement_hash="sha256:" + "a" * 64),
        audit_verdicts=[
            EnsembleAuditVerdict(member_id="m1", verdict="passed", detail="ok"),
            EnsembleAuditVerdict(member_id="m2", verdict="passed", detail="ok"),
        ],
        policy_hash="sha256:" + "b" * 64,
    )
    return AttestMachinePin(
        candidate_index=candidate_index,
        candidate_text="some rule",
        controlled_text="controlled",
        pinning=PinningProvenance(
            kind="machine_agreement", ensemble=evidence, timestamp="2026-06-26T00:00:00Z"
        ),
    )


def test_reconcile_machine_pin_flags_and_queues_on_downstream_blocker() -> None:
    from nlreq.attest import AttestHumanQueueItem, _reconcile_machine_pins_with_downstream

    pin = _machine_pin(candidate_index=0)
    human_queue: list[AttestHumanQueueItem] = []  # the candidate is NOT yet candidate-keyed in queue
    reasons = ["coverage gap: module wallet has no registered system spec S"]
    reconciled = _reconcile_machine_pins_with_downstream([pin], {0: reasons}, human_queue)
    assert len(reconciled) == 1
    assert reconciled[0].attention_required is True
    assert reconciled[0].attention_reasons == reasons
    # The flagged pin is listed in the human queue as a downstream_blocker item (so every
    # attention-required pin is in the actionable queue).
    assert len(human_queue) == 1
    assert human_queue[0].candidate_index == 0
    assert human_queue[0].stage == "downstream_blocker"
    assert human_queue[0].reasons == reasons


def test_reconcile_does_not_duplicate_when_candidate_already_queued() -> None:
    from nlreq.attest import AttestHumanQueueItem, _reconcile_machine_pins_with_downstream

    pin = _machine_pin(candidate_index=2)
    human_queue = [
        AttestHumanQueueItem(
            candidate_index=2, candidate_text="r", stage="s_and_r", reasons=["already queued"]
        )
    ]
    reconciled = _reconcile_machine_pins_with_downstream(
        [pin], {2: ["s_and_r unsupported"]}, human_queue
    )
    assert reconciled[0].attention_required is True
    # No duplicate item is added: the candidate is already candidate-keyed in the queue.
    assert len(human_queue) == 1
    assert human_queue[0].stage == "s_and_r"


def test_reconcile_leaves_clean_pins_untouched() -> None:
    from nlreq.attest import _reconcile_machine_pins_with_downstream

    pin = _machine_pin(candidate_index=0)
    human_queue: list = []
    reconciled = _reconcile_machine_pins_with_downstream([pin], {}, human_queue)
    assert reconciled[0].attention_required is False
    assert reconciled[0].attention_reasons == []
    assert human_queue == []


# ---------------------------------------------------------------------------
# HELPER iter-3 followup #1: machine pinning requires the Zone 1 PARTITION to have been produced by a
# cross-provider ensemble of ≥2 distinct provider families (scope §4) — so the rule's BOUNDARY, not
# only its wording, was cross-checked. A clean drafting ensemble over a DETERMINISTIC partition (no
# partition ensemble ran) must NOT machine-pin: "no partition ensemble ran" is now distinguishable
# from "the partition ensemble agreed".
# ---------------------------------------------------------------------------


def test_clean_draft_with_no_partition_ensemble_does_not_machine_pin() -> None:
    # Policy ON, a clean cross-provider DRAFTING ensemble, a passing shape + audit + an allow-listed
    # path — every signal EXCEPT the partition ensemble is satisfiable. With NO partition clients the
    # partition is deterministic (0 members, 0 families), so the candidate routes to the human queue
    # with NO pin (the rule's boundary was never cross-checked by a partition ensemble).
    report = attest_spec_document(
        _DOC,
        drafting_clients=[_drafter(_AGREED_CONTROLLED), _drafter(_AGREED_CONTROLLED)],
        drafting_member_provenance=_DRAFTING_PROV,
        # NO partition_clients / partition_member_provenance → deterministic partition.
        policy=_policy(),
        shape_check=_shape_pass,
        audit_check=_audit_pass,
        changed_paths=_ALLOWED_CHANGED_PATHS,
    )
    assert report.policy_off is False
    assert report.machine_pinned == []
    assert report.human_queue
    joined = " ".join(reason for item in report.human_queue for reason in item.reasons)
    # The unmet signal names the partition (Zone 1) — the boundary was not cross-checked.
    assert "partition (Zone 1)" in joined


def test_single_provider_partition_ensemble_does_not_machine_pin() -> None:
    # A partition ensemble that ran (two clients) but whose provenance spans only ONE provider family
    # cannot satisfy the ≥2-distinct-family partition-diversity requirement. The
    # ``partition_document_with_ensemble`` diversity gate refuses a same-family ensemble outright, so
    # a same-family partition is a misconfiguration that never even produces a partition — verifying
    # the routing-level guard requires the orchestrator-derived family count, which a single-family
    # partition cannot reach. Here we drive a SINGLE partition client (a single voice): the partition
    # records one member / one family, below the required two, so the candidate routes to human.
    report = attest_spec_document(
        _DOC,
        partition_clients=_partition_clients()[:1],  # a single partition voice (size 1, 1 family)
        partition_member_provenance=_PARTITION_PROV[:1],
        drafting_clients=[_drafter(_AGREED_CONTROLLED), _drafter(_AGREED_CONTROLLED)],
        drafting_member_provenance=_DRAFTING_PROV,
        policy=_policy(),
        shape_check=_shape_pass,
        audit_check=_audit_pass,
        changed_paths=_ALLOWED_CHANGED_PATHS,
    )
    assert report.machine_pinned == []
    joined = " ".join(reason for item in report.human_queue for reason in item.reasons)
    assert "partition (Zone 1)" in joined


# ---------------------------------------------------------------------------
# HELPER iter-3 followup #2: Zone 3 runs S&R PER CANDIDATE — a MULTI-rule spec must not leave any
# agreed candidate's S&R stage silently skipped while its machine pin stays clean. With registry +
# impact supplied, every agreed candidate gets its own S∧R run; the migration-shape limitation makes
# each ``unsupported``, which reverts each pin to attention_required and queues each candidate.
# ---------------------------------------------------------------------------


_DOC_TWO = (
    "# Payments\n"
    "\n"
    "The system shall reject unauthorized transfers.\n"
    "\n"
    "The system shall reject expired refund requests.\n"
)


def test_two_candidate_spec_runs_s_and_r_per_candidate_and_reverts_pins(tmp_path: Path) -> None:
    report = attest_spec_document(
        _DOC_TWO,
        partition_clients=_partition_clients(),
        partition_member_provenance=_PARTITION_PROV,
        drafting_clients=[_drafter(_PARSEABLE_CONTROLLED), _drafter(_PARSEABLE_CONTROLLED)],
        drafting_member_provenance=_DRAFTING_PROV,
        policy=_policy(),
        shape_check=_shape_pass,
        audit_check=_audit_pass,
        changed_paths=_ALLOWED_CHANGED_PATHS,
        registry=_coverage_registry(tmp_path),
        impact=_coverage_impact(["redemption"]),
        project_root=tmp_path,
    )
    # The two-behavioral-segment document yields two agreed candidates.
    assert report.total_candidates == 2
    assert len(report.downstream) == 2
    # S&R ran for EACH candidate (not absent for the second): every candidate produced a system-
    # consistency result and an S∧R result (``unsupported`` under the migration-shape limitation).
    for entry in report.downstream:
        assert entry.system_consistency is not None
        assert entry.s_and_r is not None
        assert entry.s_and_r_result == "unsupported"
    # Both pins were reverted to attention_required (no candidate stays a clean pin while its S&R
    # stage was unverified), and both candidates are queued at the s_and_r stage.
    assert len(report.machine_pinned) == 2
    assert all(pin.attention_required is True for pin in report.machine_pinned)
    s_and_r_indices = {item.candidate_index for item in report.human_queue if item.stage == "s_and_r"}
    assert s_and_r_indices == {0, 1}


# ---------------------------------------------------------------------------
# HELPER iter-3 followup #3: attest-spec selects the source-impact adapter from the manifest's
# DECLARED language (python / javascript) — matching the dedicated source-impact commands — and
# fails fast for an unsupported adapter instead of silently using the Python adapter.
# ---------------------------------------------------------------------------


def test_attest_spec_selects_impact_adapter_from_manifest_language(tmp_path: Path) -> None:
    import json

    from nlreq.cli import _source_impact_adapter_for_manifest
    from nlreq.javascript_source_adapter import JavaScriptSourceLanguageAdapter
    from nlreq.python_source_adapter import PythonSourceLanguageAdapter

    py_manifest = tmp_path / "py.json"
    py_manifest.write_text(
        json.dumps(
            {"schema_version": "0.1", "adapter": "python-source", "language": "python", "modules": []}
        )
    )
    js_manifest = tmp_path / "js.json"
    js_manifest.write_text(
        json.dumps(
            {
                "schema_version": "0.1",
                "adapter": "javascript-source",
                "language": "javascript",
                "modules": [],
            }
        )
    )
    # The adapter is chosen from the manifest's declared adapter, never silently Python.
    assert _source_impact_adapter_for_manifest(py_manifest) is PythonSourceLanguageAdapter
    assert _source_impact_adapter_for_manifest(js_manifest) is JavaScriptSourceLanguageAdapter


def test_cli_attest_spec_unsupported_manifest_adapter_fails_fast(tmp_path: Path) -> None:
    import json

    from nlreq.cli import main

    # A manifest declaring an unsupported adapter is a fail-fast usage error (exit 2), never a
    # mis-parse of the source tree under the Python adapter.
    manifest = tmp_path / "manifest.json"
    manifest.write_text(
        json.dumps(
            {"schema_version": "0.1", "adapter": "rust-source", "language": "rust", "modules": []}
        )
    )
    document = tmp_path / "spec.md"
    document.write_text(_DOC)
    exit_code = main(
        [
            "attest-spec",
            str(document),
            "--manifest",
            str(manifest),
            "--symbol",
            "operation",
            "--out",
            str(tmp_path / "report.json"),
        ]
    )
    assert exit_code == 2
