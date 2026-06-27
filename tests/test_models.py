from __future__ import annotations

import pytest
from pydantic import ValidationError

from nlreq.models import (
    BackendResult,
    EnsembleAgreementResult,
    EnsembleAuditVerdict,
    EnsembleEvidence,
    EnsembleMember,
    EvidenceLevel,
    FinalStatus,
    PinningProvenance,
    ReviewArtifact,
    ReviewChecklist,
    _is_placeholder_reviewer,
    is_real_human_review,
)


def _passing_checklist() -> ReviewChecklist:
    return ReviewChecklist(
        controlled_form_matches_intent="pass",
        claim_shape_matches_controlled_form="pass",
        source_spans_present="pass",
        assumptions_explicit="pass",
        bindings_justified="pass",
        evidence_level_appropriate="pass",
        unsupported_claims_hidden="pass",
    )


# Every placeholder reviewer the package builders fabricate an approved ``review.json`` under
# (``package._review`` phase0, and the per-language ``*_package.py`` builders phase2/7/10/13/14/
# 15/16/17). A real human review is attributed to a non-placeholder reviewer, so the full family
# is rejected at both the ``ReviewArtifact`` construction guard and the ``PinningProvenance``
# ``human_review`` backing guard (ADR 0206; acceptance #5).
PACKAGE_BUILDER_PLACEHOLDER_REVIEWERS = [
    "phase0@example.invalid",
    "phase2@example.invalid",
    "phase7@example.invalid",
    "phase10@example.invalid",
    "phase13@example.invalid",
    "phase14@example.invalid",
    "phase15@example.invalid",
    "phase16@example.invalid",
    "phase17@example.invalid",
]


# A well-formed, canonical ``sha256:<64 hex>`` digest (the shape ``jsonutil.sha256_json`` emits).
VALID_PROOF_HASH = "sha256:" + "a1" * 32

# The non-artifact backing a checked inductive proof must also record: which proof assistant
# accepted it and how it was invoked (so the claim is replayable). See
# ``BackendResult._validate_evidence_backing``.
PROOF_CHECK_BACKING = {"proof_assistant": "tlaps", "command": ["tlapm", "Proof.tla"]}


def test_proven_inductive_without_proof_artifact_is_rejected_at_construction() -> None:
    with pytest.raises(ValidationError, match="PROVEN_INDUCTIVE requires a checked-proof artifact"):
        BackendResult(
            backend="apalache",
            status="valid",
            evidence_level=EvidenceLevel.PROVEN_INDUCTIVE,
        )


def test_proven_inductive_rejects_a_placeholder_hash() -> None:
    # A label that is not a hash of anything ("sha256:checked-proof") must not stand in for a proof.
    with pytest.raises(ValidationError, match="PROVEN_INDUCTIVE requires a checked-proof artifact"):
        BackendResult(
            backend="tlaps",
            status="valid",
            evidence_level=EvidenceLevel.PROVEN_INDUCTIVE,
            details={"proof_artifact_sha256": "sha256:checked-proof"},
        )


def test_proven_inductive_rejects_a_non_checked_proof_artifact() -> None:
    # A theorem statement or proof script is not a *checked* proof; only a checked_proof entry backs
    # the claim, even with a well-formed hash.
    with pytest.raises(ValidationError, match="PROVEN_INDUCTIVE requires a checked-proof artifact"):
        BackendResult(
            backend="tlaps",
            status="valid",
            evidence_level=EvidenceLevel.PROVEN_INDUCTIVE,
            details={"proof_artifacts": [{"kind": "theorem_statement", "sha256": VALID_PROOF_HASH}]},
        )


def test_proven_inductive_rejects_a_non_valid_status() -> None:
    # A proof that did not check (timeout, counterexample, ...) is not an inductive proof.
    with pytest.raises(ValidationError, match="PROVEN_INDUCTIVE requires a 'valid' status"):
        BackendResult(
            backend="tlaps",
            status="timeout",
            evidence_level=EvidenceLevel.PROVEN_INDUCTIVE,
            details={"proof_artifact_sha256": VALID_PROOF_HASH},
        )


def test_proven_inductive_without_proof_assistant_is_rejected_at_construction() -> None:
    # A checked-proof artifact alone does not name the checker that accepted it; the claim must
    # record the proof assistant so it is traceable to a real producer.
    with pytest.raises(ValidationError, match="PROVEN_INDUCTIVE requires the proof assistant"):
        BackendResult(
            backend="tlaps",
            status="valid",
            evidence_level=EvidenceLevel.PROVEN_INDUCTIVE,
            details={"proof_artifact_sha256": VALID_PROOF_HASH, "command": ["tlapm", "Proof.tla"]},
        )


def test_proven_inductive_without_command_is_rejected_at_construction() -> None:
    # A checked proof must record how the checker was invoked so the result is replayable.
    with pytest.raises(ValidationError, match="PROVEN_INDUCTIVE requires the proof-check command"):
        BackendResult(
            backend="tlaps",
            status="valid",
            evidence_level=EvidenceLevel.PROVEN_INDUCTIVE,
            details={"proof_artifact_sha256": VALID_PROOF_HASH, "proof_assistant": "tlaps"},
        )


def test_proven_inductive_accepts_a_checked_proof_hash() -> None:
    result = BackendResult(
        backend="tlaps",
        status="valid",
        evidence_level=EvidenceLevel.PROVEN_INDUCTIVE,
        details={"proof_artifact_sha256": VALID_PROOF_HASH, **PROOF_CHECK_BACKING},
    )

    assert result.evidence_level == EvidenceLevel.PROVEN_INDUCTIVE


def test_proven_inductive_accepts_a_checked_proof_artifact_entry() -> None:
    result = BackendResult(
        backend="tlaps",
        status="valid",
        evidence_level=EvidenceLevel.PROVEN_INDUCTIVE,
        details={
            "proof_artifacts": [{"kind": "checked_proof", "sha256": VALID_PROOF_HASH}],
            **PROOF_CHECK_BACKING,
        },
    )

    assert result.evidence_level == EvidenceLevel.PROVEN_INDUCTIVE


def test_bounded_checked_without_bounds_is_rejected_at_construction() -> None:
    with pytest.raises(ValidationError, match="the bounds it searched"):
        BackendResult(
            backend="tla-runner",
            status="valid",
            evidence_level=EvidenceLevel.BOUNDED_CHECKED,
            details={"command": ["tlc2.TLC"], "tool_version": "tlc 1.0"},
        )


def test_bounded_checked_with_empty_bounds_is_rejected_at_construction() -> None:
    with pytest.raises(ValidationError, match="the bounds it searched"):
        BackendResult(
            backend="tla-runner",
            status="valid",
            evidence_level=EvidenceLevel.BOUNDED_CHECKED,
            details={"bounds": {}, "command": ["tlc2.TLC"], "tool_version": "tlc 1.0"},
        )


def test_bounded_checked_with_bounds_alone_is_rejected_at_construction() -> None:
    """Bounds alone is not bounded backing: the checker command and a run-recorded version are
    required too, so a result carrying only details['bounds'] cannot claim the level."""
    with pytest.raises(ValidationError, match="the checker command"):
        BackendResult(
            backend="tla-runner",
            status="valid",
            evidence_level=EvidenceLevel.BOUNDED_CHECKED,
            details={"bounds": {"max_depth": 8}},
        )


def test_bounded_checked_without_run_version_is_rejected_at_construction() -> None:
    """Bounds + command but no run-recorded version is still unbacked: a bounded verdict is not
    reproducible without the version of the checker that produced it."""
    with pytest.raises(ValidationError, match="a checker version recorded from the run"):
        BackendResult(
            backend="tla-runner",
            status="valid",
            evidence_level=EvidenceLevel.BOUNDED_CHECKED,
            details={"bounds": {"max_depth": 8}, "command": ["tlc2.TLC", "Model.tla"]},
        )


def test_bounded_checked_accepts_full_backing() -> None:
    result = BackendResult(
        backend="tla-runner",
        status="valid",
        evidence_level=EvidenceLevel.BOUNDED_CHECKED,
        details={
            "bounds": {"max_depth": 8},
            "command": ["tlc2.TLC", "-config", "Model.cfg", "Model.tla"],
            "tool_version": "tlc 2.18",
        },
    )

    assert result.evidence_level == EvidenceLevel.BOUNDED_CHECKED


def test_bounded_checked_accepts_nested_reproducibility_version() -> None:
    """The run version may be recorded nested under reproducibility (the solver-backed S ∧ R path
    records it there under exclude_none), not only top-level."""
    result = BackendResult(
        backend="solver_system_checker",
        status="valid",
        evidence_level=EvidenceLevel.BOUNDED_CHECKED,
        details={
            "bounds": {"max_depth": 6},
            "command": ["apalache-mc", "check", "Module.tla"],
            "reproducibility": {"tool_version": "apalache 0.58.0"},
        },
    )

    assert result.evidence_level == EvidenceLevel.BOUNDED_CHECKED


def test_lower_evidence_levels_need_no_high_assurance_backing() -> None:
    # The guard only constrains the high-assurance levels; an SMT_CHECKED or unlabeled result is
    # constructible with no bounds or proof artifact.
    smt = BackendResult(
        backend="core_smt",
        status="valid",
        evidence_level=EvidenceLevel.SMT_CHECKED,
    )
    unlabeled = BackendResult(backend="core_smt", status="needs_review")

    assert smt.evidence_level == EvidenceLevel.SMT_CHECKED
    assert unlabeled.evidence_level is None


def test_trace_validated_without_mapping_is_rejected_at_construction() -> None:
    with pytest.raises(ValidationError, match="TRACE_VALIDATED requires the observed"):
        BackendResult(
            backend="trace",
            status="valid",
            evidence_level=EvidenceLevel.TRACE_VALIDATED,
            details={"validator_id": "forbidden-event-absent"},
        )


def test_trace_validated_with_empty_mapping_is_rejected_at_construction() -> None:
    with pytest.raises(ValidationError, match="TRACE_VALIDATED requires the observed"):
        BackendResult(
            backend="trace",
            status="valid",
            evidence_level=EvidenceLevel.TRACE_VALIDATED,
            details={"trace_mapping": {}},
        )


def _valid_trace_mapping() -> dict:
    """A schema-complete observed→fragment mapping, the shape the trace producer emits.

    ``trace_source_hash`` is a non-canonical placeholder ("sha256:trace-source") on purpose: it is
    the digest the adapter recorded for the input trace, which the validator must accept as-is
    rather than re-deriving — the producer copies it verbatim.
    """
    return {
        "validator_id": "forbidden-event-absent",
        "requirement_id": "REQ-AUTH-001",
        "trace_hash": "sha256:" + "b2" * 32,
        "trace_source_hash": "sha256:trace-source",
        "observed_events": ["request", "settle"],
        "observed_event_ids": ["evt-1", "evt-2"],
        "fragment": {"forbidden_events_absent": ["unauthorized_settle"]},
    }


def _trace_validated(mapping: dict) -> BackendResult:
    return BackendResult(
        backend="trace",
        status="valid",
        evidence_level=EvidenceLevel.TRACE_VALIDATED,
        details={"trace_mapping": mapping},
    )


def test_trace_validated_accepts_a_schema_complete_mapping() -> None:
    result = _trace_validated(_valid_trace_mapping())

    assert result.evidence_level == EvidenceLevel.TRACE_VALIDATED


def test_trace_validated_accepts_an_empty_event_list_for_an_empty_trace() -> None:
    # A counterexample can be reached observing nothing (an empty trace); the mapping then records
    # zero concrete events honestly, rather than being rejected.
    mapping = _valid_trace_mapping()
    mapping["observed_event_ids"] = []
    result = BackendResult(
        backend="trace",
        status="counterexample",
        evidence_level=EvidenceLevel.TRACE_VALIDATED,
        details={"trace_mapping": mapping},
    )

    assert result.evidence_level == EvidenceLevel.TRACE_VALIDATED


def test_trace_validated_rejects_an_arbitrary_mapping() -> None:
    with pytest.raises(ValidationError, match="TRACE_VALIDATED requires the observed"):
        _trace_validated({"foo": "bar"})


def test_trace_validated_rejects_a_mapping_without_trace_hashes() -> None:
    # A mapping with no content/source digest cannot re-fetch the exact observations it validated.
    no_hash = _valid_trace_mapping()
    del no_hash["trace_hash"]
    with pytest.raises(ValidationError, match="TRACE_VALIDATED requires the observed"):
        _trace_validated(no_hash)

    no_source = _valid_trace_mapping()
    del no_source["trace_source_hash"]
    with pytest.raises(ValidationError, match="TRACE_VALIDATED requires the observed"):
        _trace_validated(no_source)


def test_trace_validated_rejects_a_mapping_without_concrete_event_ids() -> None:
    # Action strings alone are not event identities; the mapping must record concrete event ids.
    no_ids = _valid_trace_mapping()
    del no_ids["observed_event_ids"]
    with pytest.raises(ValidationError, match="TRACE_VALIDATED requires the observed"):
        _trace_validated(no_ids)

    non_string_ids = _valid_trace_mapping()
    non_string_ids["observed_event_ids"] = [1, 2]
    with pytest.raises(ValidationError, match="TRACE_VALIDATED requires the observed"):
        _trace_validated(non_string_ids)


def test_trace_validated_rejects_a_mapping_without_a_covered_fragment() -> None:
    no_fragment = _valid_trace_mapping()
    no_fragment["fragment"] = {}
    with pytest.raises(ValidationError, match="TRACE_VALIDATED requires the observed"):
        _trace_validated(no_fragment)


# ---------------------------------------------------------------------------
# Pinning provenance (ADR 0206) — construction guards.
#
# Machine pinning is a provenance axis DISTINCT from EvidenceLevel: it records WHO pinned a
# controlled requirement's meaning, not WHAT tool produced evidence. The construction guards make
# a machine_agreement record unrepresentable without its ensemble-evidence object, and a
# human_review record unrepresentable without a real review event (acceptance #5). These mirror
# the BackendResult backing guards above.
# ---------------------------------------------------------------------------


def _valid_ensemble_evidence() -> EnsembleEvidence:
    """A minimal valid cross-provider (>=2 distinct families) passing ensemble."""
    return EnsembleEvidence(
        members=[
            EnsembleMember(
                member_id="m1",
                resolved_model_id="claude-haiku-4-5",
                provider_family="anthropic",
            ),
            EnsembleMember(
                member_id="m2",
                resolved_model_id="gpt-5.4-mini",
                provider_family="openai",
            ),
        ],
        agreement=EnsembleAgreementResult(agreed=True, agreement_hash=VALID_PROOF_HASH),
        audit_verdicts=[
            EnsembleAuditVerdict(member_id="m1", verdict="passed"),
            EnsembleAuditVerdict(member_id="m2", verdict="passed"),
        ],
        policy_hash=VALID_PROOF_HASH,
    )


def _valid_machine_pin() -> PinningProvenance:
    return PinningProvenance(
        kind="machine_agreement",
        ensemble=_valid_ensemble_evidence(),
        timestamp="2026-06-26T05:22:13Z",
    )


def _valid_human_review_event() -> ReviewArtifact:
    # A REAL human review event: non-placeholder reviewer + review_origin="human" (the
    # ReviewArtifact construction guard makes this origin unrepresentable under a placeholder).
    return ReviewArtifact(
        review_id="RVW-REQ-1-001",
        reviewer="reviewer@example.org",
        decision="approved",
        reviewed_hashes={"requirement_ir": VALID_PROOF_HASH},
        checklist=_passing_checklist(),
        timestamp="2026-05-26T00:00:00Z",
        review_origin="human",
    )


def _valid_human_review_pin() -> PinningProvenance:
    return PinningProvenance(
        kind="human_review",
        review_event=_valid_human_review_event(),
        timestamp="2026-06-26T05:22:13Z",
    )


def test_machine_pinned_status_is_not_accepted_prefixed() -> None:
    # acceptance #3 at the schema level: the machine status deliberately does NOT start with
    # "ACCEPTED", so a prefix check can never silently treat it as human-accepted.
    assert FinalStatus.MACHINE_PINNED_PENDING_REVIEW.value == "MACHINE_PINNED_PENDING_REVIEW"
    assert not FinalStatus.MACHINE_PINNED_PENDING_REVIEW.value.startswith("ACCEPTED")


def test_machine_pin_unrepresentable_without_ensemble_evidence() -> None:
    with pytest.raises(ValidationError, match="unrepresentable without its ensemble-evidence"):
        PinningProvenance(kind="machine_agreement", timestamp="2026-06-26T05:22:13Z")


def test_machine_pin_rejects_single_member_ensemble() -> None:
    # A single model cannot satisfy the cross-provider agreement requirement.
    one = _valid_ensemble_evidence()
    one.members = [one.members[0]]
    one.audit_verdicts = [one.audit_verdicts[0]]
    with pytest.raises(ValidationError, match="at least 2 ensemble members"):
        EnsembleEvidence(
            members=one.members,
            agreement=one.agreement,
            audit_verdicts=one.audit_verdicts,
            policy_hash=one.policy_hash,
        )


def test_machine_pin_rejects_same_provider_family_ensemble() -> None:
    # Two distinct providers that resolve to the SAME family cannot satisfy the diversity
    # requirement (scope §3) — the correlated-training-bias failure mode an agreement gate exists
    # to catch.
    same_family = _valid_ensemble_evidence()
    same_family.members[1] = EnsembleMember(
        member_id="m2",
        resolved_model_id="claude-sonnet-4-5",
        provider_family="anthropic",
    )
    with pytest.raises(ValidationError, match="at least 2 distinct provider families"):
        same_family.model_validate(same_family.model_dump())


def test_machine_pin_rejects_divergent_ensemble_agreement() -> None:
    # A divergent ensemble (agreed=False) routes to the human queue, never a pin.
    with pytest.raises(ValidationError, match="must have agreed=True"):
        EnsembleAgreementResult(agreed=False, agreement_hash=VALID_PROOF_HASH)


def test_machine_pin_rejects_malformed_agreement_hash() -> None:
    with pytest.raises(ValidationError, match="agreement_hash must be a canonical sha256"):
        EnsembleAgreementResult(agreed=True, agreement_hash="sha256:checked-proof")


def test_machine_pin_rejects_a_failed_audit_verdict() -> None:
    # Every ensemble member's audit must pass for a machine pinning (scope §5).
    failed = _valid_ensemble_evidence()
    failed.audit_verdicts[1] = EnsembleAuditVerdict(member_id="m2", verdict="failed")
    with pytest.raises(ValidationError, match="every ensemble member's audit to pass"):
        failed.model_validate(failed.model_dump())


def test_machine_pin_rejects_missing_audit_verdict_for_a_member() -> None:
    missing = _valid_ensemble_evidence()
    missing.audit_verdicts = [missing.audit_verdicts[0]]
    with pytest.raises(ValidationError, match="audit verdict for every ensemble member"):
        missing.model_validate(missing.model_dump())


def test_machine_pin_rejects_malformed_policy_hash() -> None:
    bad_policy = _valid_ensemble_evidence()
    bad_policy.policy_hash = "not-a-hash"
    with pytest.raises(ValidationError, match="policy_hash must be a canonical sha256"):
        bad_policy.model_validate(bad_policy.model_dump())


def test_machine_pin_rejects_a_human_review_event() -> None:
    # Machine pinning and human review are mutually exclusive provenance kinds: a machine_agreement
    # pin must not carry a human review event (it carries its ensemble evidence instead).
    with pytest.raises(ValidationError, match="must not carry a human review event"):
        PinningProvenance(
            kind="machine_agreement",
            ensemble=_valid_ensemble_evidence(),
            review_event=_valid_human_review_event(),
            timestamp="2026-06-26T05:22:13Z",
        )


def test_human_review_pin_unrepresentable_without_review_event() -> None:
    with pytest.raises(ValidationError, match="unrepresentable without a real review event"):
        PinningProvenance(kind="human_review", timestamp="2026-06-26T05:22:13Z")


def test_human_review_pin_rejects_a_fabricated_package_builder_review_event() -> None:
    # A human_review pin must be backed by a REAL human review event (review_origin="human"). The
    # fabricated package-builder review (the default _review fabrication) is a valid ReviewArtifact
    # — its origin defaults to "package_builder" under a placeholder reviewer — but its origin is
    # not human, so it cannot pin a rule's meaning as human-reviewed (ADR 0206 §2; acceptance #5).
    fabricated = ReviewArtifact(
        review_id="RVW-REQ-1-001",
        reviewer="phase0@example.invalid",
        decision="approved",
        reviewed_hashes={"requirement_ir": VALID_PROOF_HASH},
        checklist=_passing_checklist(),
        timestamp="2026-05-26T00:00:00Z",
    )
    assert fabricated.review_origin == "package_builder"
    with pytest.raises(ValidationError, match="must be backed by a real human review event"):
        PinningProvenance(
            kind="human_review",
            review_event=fabricated,
            timestamp="2026-06-26T05:22:13Z",
        )


@pytest.mark.parametrize("decision", ["needs_review", "rejected"])
def test_human_review_pin_rejects_a_non_approved_human_review_event(decision: str) -> None:
    # A human_review pin records that the meaning was PINNED — accepted — by human review. A REAL
    # human review (review_origin="human", non-placeholder reviewer) whose decision is "rejected" or
    # "needs_review" did NOT approve the meaning, so it is unrepresentable as a human_review pin.
    # Without this guard a human rejection would back the pin and decide_status would resolve it to a
    # human-accepted status — a human rejection silently becoming a human acceptance (iter-5 gap).
    non_approving = ReviewArtifact(
        review_id="RVW-REQ-1-001",
        reviewer="reviewer@example.org",  # a real (non-placeholder) reviewer
        decision=decision,
        reviewed_hashes={"requirement_ir": VALID_PROOF_HASH},
        checklist=_passing_checklist(),
        timestamp="2026-05-26T00:00:00Z",
        review_origin="human",
    )
    assert is_real_human_review(non_approving) is True  # it IS a real human review — just not approved
    with pytest.raises(ValidationError, match="must be backed by an APPROVED human review"):
        PinningProvenance(
            kind="human_review",
            review_event=non_approving,
            timestamp="2026-06-26T05:22:13Z",
        )


def test_human_review_pin_rejects_ensemble_evidence() -> None:
    with pytest.raises(ValidationError, match="must not carry machine ensemble evidence"):
        PinningProvenance(
            kind="human_review",
            review_event=_valid_human_review_event(),
            ensemble=_valid_ensemble_evidence(),
            timestamp="2026-06-26T05:22:13Z",
        )


def test_valid_machine_agreement_pin_constructs() -> None:
    pin = _valid_machine_pin()
    assert pin.kind == "machine_agreement"
    assert pin.ensemble is not None
    assert len(pin.ensemble.members) == 2
    assert pin.review_id is None
    assert pin.reviewed_artifact_hash is None


def test_valid_human_review_pin_constructs() -> None:
    pin = _valid_human_review_pin()
    assert pin.kind == "human_review"
    assert pin.review_event is not None
    assert pin.review_event.review_origin == "human"
    assert pin.ensemble is None


def test_human_review_pin_derives_references_from_the_embedded_event() -> None:
    # scope §6's reference signals (review_id, reviewer, reviewed artifact hash) are read-only
    # accessors DERIVED from the embedded review event, so the pin and its backing event can never
    # disagree (ADR 0206; acceptance #5; HELPER iter-5 review: "validated against an actual
    # ReviewArtifact ... not just scalar fields").
    pin = _valid_human_review_pin()
    assert pin.review_id == pin.review_event.review_id == "RVW-REQ-1-001"
    assert pin.reviewer == pin.review_event.reviewer == "reviewer@example.org"
    assert pin.reviewed_artifact_hash == VALID_PROOF_HASH


def test_human_review_pin_is_not_constructible_from_loose_scalar_fields() -> None:
    # A human_review pin is backed by the actual ReviewArtifact, not loose scalars: review_id /
    # reviewer / reviewed_artifact_hash are derived accessors, not fields, so passing them as
    # construction kwargs is refused (extra inputs are forbidden). This closes the iter-5 gap —
    # "any non-placeholder reviewer plus any valid-looking hash passes" — because there is no
    # scalar-only construction path to pass with (ADR 0206 §2; acceptance #5).
    with pytest.raises(ValidationError):
        PinningProvenance(  # type: ignore[call-arg]
            kind="human_review",
            review_id="RVW-REQ-1-001",
            reviewer="reviewer@example.org",
            reviewed_artifact_hash=VALID_PROOF_HASH,
            timestamp="2026-06-26T05:22:13Z",
        )


@pytest.mark.parametrize("reviewer", PACKAGE_BUILDER_PLACEHOLDER_REVIEWERS)
def test_human_review_pin_rejects_every_package_builder_placeholder_review_event(
    reviewer: str,
) -> None:
    # A human_review pin must be backed by a real human review event. The fabricated package-builder
    # ``review.json`` is produced under a ``phase<N>@example.invalid`` placeholder reviewer
    # (``package._review`` phase0 and the per-language ``*_package.py`` builders), and its
    # ``review_origin`` is ``"package_builder"`` (the model-level default) — explicitly non-human.
    # NONE of these fabricated events can back a ``human_review`` pin: the provenance guard rejects
    # an event whose origin is not human, covering the FULL placeholder family (ADR 0206 §2;
    # acceptance #5; HELPER iter-5 review).
    fabricated = ReviewArtifact(
        review_id="RVW-REQ-1-001",
        reviewer=reviewer,
        decision="approved",
        reviewed_hashes={"requirement_ir": VALID_PROOF_HASH},
        checklist=_passing_checklist(),
        timestamp="2026-05-26T00:00:00Z",
    )
    assert fabricated.review_origin == "package_builder"  # the fabricated default
    with pytest.raises(ValidationError, match="must be backed by a real human review event"):
        PinningProvenance(
            kind="human_review",
            review_event=fabricated,
            timestamp="2026-06-26T05:22:13Z",
        )


def test_is_placeholder_reviewer_matches_the_full_package_builder_family() -> None:
    # The predicate is the negative image of the positive ``review_origin`` contract: it matches
    # every ``phase<N>@example.invalid`` placeholder and no real reviewer (ADR 0206; acceptance #5).
    for reviewer in PACKAGE_BUILDER_PLACEHOLDER_REVIEWERS:
        assert _is_placeholder_reviewer(reviewer) is True
    assert _is_placeholder_reviewer("reviewer@example.org") is False
    assert _is_placeholder_reviewer("solo@example.invalid") is False
    assert _is_placeholder_reviewer(None) is False


def test_review_artifact_defaults_to_explicitly_non_human_origin() -> None:
    # A legacy / fabricated ``review.json`` (one written before ``review_origin`` existed) defaults
    # to ``"package_builder"`` — explicitly NON-human, never silently a real human review event
    # (ADR 0206 §2; acceptance #5). This is the positive contract: the fabricated default is
    # honestly labeled, so ``is_real_human_review`` returns False for it.
    review = ReviewArtifact.model_validate(
        {
            "review_id": "RVW-REQ-1-001",
            "reviewer": "phase0@example.invalid",
            "decision": "approved",
            "reviewed_hashes": {"requirement_ir": VALID_PROOF_HASH},
            "checklist": {
                "controlled_form_matches_intent": "pass",
                "claim_shape_matches_controlled_form": "pass",
                "source_spans_present": "pass",
                "assumptions_explicit": "pass",
                "bindings_justified": "pass",
                "evidence_level_appropriate": "pass",
                "unsupported_claims_hidden": "pass",
            },
            "timestamp": "2026-05-26T00:00:00Z",
        }
    )
    assert review.review_origin == "package_builder"
    assert is_real_human_review(review) is False


@pytest.mark.parametrize("reviewer", PACKAGE_BUILDER_PLACEHOLDER_REVIEWERS)
def test_review_artifact_human_origin_is_unrepresentable_under_a_placeholder_reviewer(
    reviewer: str,
) -> None:
    # A real human review event (``review_origin="human"``) is UNREPRESENTABLE under a
    # package-builder placeholder reviewer — the construction-time guard (modeled on the proof
    # guards) refuses it, so a fabricated approval can never be relabeled human (ADR 0206 §2;
    # acceptance #5). Covers the FULL placeholder family, not just phase0.
    with pytest.raises(ValidationError, match="review_origin='human' is unrepresentable under a"):
        ReviewArtifact(
            review_id="RVW-REQ-1-001",
            reviewer=reviewer,
            decision="approved",
            reviewed_hashes={"requirement_ir": VALID_PROOF_HASH},
            checklist=_passing_checklist(),
            timestamp="2026-05-26T00:00:00Z",
            review_origin="human",
        )


def test_review_artifact_human_origin_is_representable_for_a_real_reviewer() -> None:
    # A real human review event — non-placeholder reviewer + ``review_origin="human"`` — IS
    # representable and counts as a real human review (the positive contract's satisfying case).
    review = ReviewArtifact(
        review_id="RVW-REQ-1-001",
        reviewer="reviewer@example.org",
        decision="approved",
        reviewed_hashes={"requirement_ir": VALID_PROOF_HASH},
        checklist=_passing_checklist(),
        timestamp="2026-05-26T00:00:00Z",
        review_origin="human",
    )
    assert review.review_origin == "human"
    assert is_real_human_review(review) is True


def test_machine_pin_review_event_accessors_are_none() -> None:
    # A machine_agreement pin has no review event, so the review reference accessors are None
    # (promotion to human_review is the only path that adds a review event; scope §6).
    pin = _valid_machine_pin()
    assert pin.review_event is None
    assert pin.review_id is None
    assert pin.reviewer is None
    assert pin.reviewed_artifact_hash is None


def test_machine_pin_rejects_duplicate_member_ids() -> None:
    # Two members sharing a member_id would let a single model masquerade as two ensemble voices,
    # inflating the diversity and agreement signals. The verdict_by_member dict previously
    # collapsed these; the tightened validator rejects them (ADR 0206; HELPER iter-1 review).
    duplicate = _valid_ensemble_evidence()
    duplicate.members[1] = EnsembleMember(
        member_id="m1",  # same id as members[0]
        resolved_model_id="gpt-5.4-mini",
        provider_family="openai",
    )
    with pytest.raises(ValidationError, match="unique ensemble member_ids"):
        duplicate.model_validate(duplicate.model_dump())


def test_machine_pin_rejects_duplicate_audit_verdict_ids() -> None:
    # Two verdicts for the same member would collapse one result; the tightened validator rejects
    # them instead of silently deduplicating (ADR 0206; HELPER iter-1 review).
    duplicate = _valid_ensemble_evidence()
    duplicate.audit_verdicts = [
        EnsembleAuditVerdict(member_id="m1", verdict="passed"),
        EnsembleAuditVerdict(member_id="m1", verdict="passed"),
    ]
    with pytest.raises(ValidationError, match="unique audit verdict member_ids"):
        duplicate.model_validate(duplicate.model_dump())


def test_machine_pin_rejects_an_audit_verdict_for_a_non_member() -> None:
    # A verdict for a member that does not exist breaks the 1:1 correspondence the passing-audit
    # requirement relies on; previously it was silently ignored as an "extra". Exact equality
    # between member ids and verdict ids is now required (ADR 0206; HELPER iter-1 review).
    extra = _valid_ensemble_evidence()
    extra.audit_verdicts = [
        EnsembleAuditVerdict(member_id="m1", verdict="passed"),
        EnsembleAuditVerdict(member_id="m2", verdict="passed"),
        EnsembleAuditVerdict(member_id="m3", verdict="passed"),
    ]
    with pytest.raises(ValidationError, match="verdicts for non-members"):
        extra.model_validate(extra.model_dump())


# --- blank / whitespace ensemble identifiers (HELPER iter-5 review; ADR 0206) ---


@pytest.mark.parametrize("blank", ["", "   ", "\t\n"])
def test_machine_pin_rejects_a_blank_or_whitespace_member_id(blank: str) -> None:
    # A blank/whitespace member_id would let a degenerate member satisfy the uniqueness and
    # member/verdict correspondence checks vacuously (ADR 0206; HELPER iter-5 review).
    with pytest.raises(ValidationError, match="member_id must be a non-empty, non-blank"):
        EnsembleMember(
            member_id=blank,
            resolved_model_id="claude-haiku-4-5",
            provider_family="anthropic",
        )


@pytest.mark.parametrize("blank", ["", "   "])
def test_machine_pin_rejects_a_blank_or_whitespace_resolved_model_id(blank: str) -> None:
    with pytest.raises(ValidationError, match="resolved_model_id must be a non-empty, non-blank"):
        EnsembleMember(
            member_id="m1",
            resolved_model_id=blank,
            provider_family="anthropic",
        )


@pytest.mark.parametrize("blank", ["", "   ", "\t"])
def test_machine_pin_rejects_a_blank_or_whitespace_provider_family(blank: str) -> None:
    # The core diversity-gap attack the iter-5 review flagged: a blank/whitespace provider_family
    # combined with a real family would satisfy the distinct-family count vacuously
    # (``{"", "anthropic"}`` is "2 distinct families"), letting a same-family ensemble masquerade
    # as cross-provider. The blank family is rejected at the member, so it can never reach the
    # family-count check.
    with pytest.raises(ValidationError, match="provider_family must be a non-empty, non-blank"):
        EnsembleMember(
            member_id="m1",
            resolved_model_id="claude-haiku-4-5",
            provider_family=blank,
        )


@pytest.mark.parametrize("blank", ["", "   "])
def test_machine_pin_rejects_a_blank_or_whitespace_audit_verdict_member_id(blank: str) -> None:
    with pytest.raises(ValidationError, match="EnsembleAuditVerdict.member_id must be a non-empty"):
        EnsembleAuditVerdict(member_id=blank, verdict="passed")


def test_machine_pin_provider_family_cannot_be_blank_to_inflate_diversity() -> None:
    # End-to-end guard against the diversity-inflation attack: even if a blank family somehow
    # reached the EnsembleEvidence, it is rejected at the member before the family-count check.
    # Here a blank-family member is rejected at construction, so the ensemble never forms.
    with pytest.raises(ValidationError, match="provider_family must be a non-empty, non-blank"):
        EnsembleEvidence(
            members=[
                EnsembleMember(
                    member_id="m1",
                    resolved_model_id="claude-haiku-4-5",
                    provider_family="anthropic",
                ),
                EnsembleMember(
                    member_id="m2",
                    resolved_model_id="gpt-5.4-mini",
                    provider_family="",  # the diversity-inflation attack
                ),
            ],
            agreement=EnsembleAgreementResult(agreed=True, agreement_hash=VALID_PROOF_HASH),
            audit_verdicts=[
                EnsembleAuditVerdict(member_id="m1", verdict="passed"),
                EnsembleAuditVerdict(member_id="m2", verdict="passed"),
            ],
            policy_hash=VALID_PROOF_HASH,
        )
