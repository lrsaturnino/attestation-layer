from nlreq.models import (
    EnsembleAgreementResult,
    EnsembleAuditVerdict,
    EnsembleEvidence,
    EnsembleMember,
    EvidenceClaim,
    EvidenceLevel,
    EvidenceObject,
    FinalStatus,
    PinningProvenance,
    ReviewArtifact,
    ReviewChecklist,
    SourceSpan,
)
from nlreq.status import HUMAN_ACCEPTED_STATUSES, decide_status, is_human_accepted


_VALID_HASH = "sha256:" + "a1" * 32


def _satisfied_evidence() -> EvidenceObject:
    return EvidenceObject(
        requirement_id="REQ-1",
        claims=[
            EvidenceClaim(
                id="C1",
                description="claim",
                required_evidence=EvidenceLevel.SMT_CHECKED,
                achieved_evidence=EvidenceLevel.SMT_CHECKED,
            )
        ],
    )


def _machine_pin() -> PinningProvenance:
    return PinningProvenance(
        kind="machine_agreement",
        ensemble=EnsembleEvidence(
            members=[
                EnsembleMember(
                    member_id="m1", resolved_model_id="claude-haiku-4-5", provider_family="anthropic"
                ),
                EnsembleMember(
                    member_id="m2", resolved_model_id="gpt-5.4-mini", provider_family="openai"
                ),
            ],
            agreement=EnsembleAgreementResult(agreed=True, agreement_hash=_VALID_HASH),
            audit_verdicts=[
                EnsembleAuditVerdict(member_id="m1", verdict="passed"),
                EnsembleAuditVerdict(member_id="m2", verdict="passed"),
            ],
            policy_hash=_VALID_HASH,
        ),
        timestamp="2026-06-26T05:22:13Z",
    )


def test_accepts_when_required_evidence_is_satisfied() -> None:
    evidence = EvidenceObject(
        requirement_id="REQ-1",
        claims=[
            EvidenceClaim(
                id="C1",
                description="claim",
                required_evidence=EvidenceLevel.SMT_CHECKED,
                achieved_evidence=EvidenceLevel.SMT_CHECKED,
            )
        ],
    )

    assert decide_status(evidence).status == FinalStatus.ACCEPTED_WITH_EVIDENCE


def test_refuses_unbound_symbols_before_missing_evidence() -> None:
    span = SourceSpan(
        document="controlled",
        start_char=32,
        end_char=58,
        text="operator is not authorized",
    )
    evidence = EvidenceObject(
        requirement_id="REQ-1",
        unbound_symbols=["authorized"],
        unbound_symbol_spans={"authorized": span},
        claims=[
            EvidenceClaim(
                id="C1",
                description="claim",
                required_evidence=EvidenceLevel.SMT_CHECKED,
            )
        ],
    )

    decision = decide_status(evidence)

    assert decision.status == FinalStatus.REFUSED_UNBOUND_SYMBOLS
    assert "authorized" in decision.reason
    assert decision.source_span == span


def test_refuses_ambiguous_symbols_before_unbound_symbols() -> None:
    span = SourceSpan(
        document="controlled",
        start_char=32,
        end_char=65,
        text="ambiguous_actor is not authorized",
    )
    evidence = EvidenceObject(
        requirement_id="REQ-1",
        ambiguous=True,
        ambiguous_symbols=["ambiguous_actor"],
        ambiguous_symbol_spans={"ambiguous_actor": span},
        unbound_symbols=["missing_symbol"],
    )

    decision = decide_status(evidence)

    assert decision.status == FinalStatus.REFUSED_AMBIGUOUS
    assert "ambiguous_actor" in decision.reason
    assert decision.source_span == span


def test_review_status_for_missing_evidence() -> None:
    evidence = EvidenceObject(
        requirement_id="REQ-1",
        claims=[
            EvidenceClaim(
                id="C1",
                description="claim",
                required_evidence=EvidenceLevel.TRACE_VALIDATED,
                achieved_evidence=EvidenceLevel.SMT_CHECKED,
            )
        ],
    )

    decision = decide_status(evidence)

    assert decision.status == FinalStatus.ACCEPTED_FOR_IMPLEMENTATION_WITH_REVIEW
    assert "C1" in decision.next_actions[0]


# ---------------------------------------------------------------------------
# Machine pinning (ADR 0206) — decide_status branch + is_human_accepted.
# ---------------------------------------------------------------------------


def test_machine_pinning_resolves_to_machine_pinned_pending_review_when_evidence_satisfied() -> None:
    # A machine-pinned package whose evidence is fully satisfied resolves to a status that does
    # NOT start with "ACCEPTED" (acceptance #3), never to ACCEPTED_WITH_EVIDENCE.
    decision = decide_status(_satisfied_evidence(), pinning=_machine_pin())

    assert decision.status == FinalStatus.MACHINE_PINNED_PENDING_REVIEW
    assert not decision.status.value.startswith("ACCEPTED")


def test_machine_pinning_does_not_bypass_evidence_gaps() -> None:
    # Machine pinning never substitutes for a deterministic proof level (scope §6): a
    # machine-pinned package with an evidence gap still SURFACES that gap in next_actions — but
    # acceptance #3 is unconditional, so the status is the non-ACCEPTED machine-pinned status,
    # never ACCEPTED_FOR_IMPLEMENTATION_WITH_REVIEW. A human reviewer still sees the gap; the
    # status just never starts with "ACCEPTED" and is not human-accepted.
    evidence = EvidenceObject(
        requirement_id="REQ-1",
        claims=[
            EvidenceClaim(
                id="C1",
                description="claim",
                required_evidence=EvidenceLevel.TRACE_VALIDATED,
                achieved_evidence=EvidenceLevel.SMT_CHECKED,
            )
        ],
    )

    decision = decide_status(evidence, pinning=_machine_pin())

    assert decision.status == FinalStatus.MACHINE_PINNED_PENDING_REVIEW
    assert not decision.status.value.startswith("ACCEPTED")
    assert is_human_accepted(decision.status) is False
    # The evidence gap is NOT hidden: the missing-evidence claim is still surfaced for a human.
    assert any("C1" in action for action in decision.next_actions)


def test_machine_pinning_does_not_bypass_refusals() -> None:
    # Refusals take precedence over pinning: a machine-pinned ambiguous rule still refuses.
    evidence = EvidenceObject(
        requirement_id="REQ-1",
        ambiguous=True,
        ambiguous_symbols=["ambiguous_actor"],
    )

    decision = decide_status(evidence, pinning=_machine_pin())

    assert decision.status == FinalStatus.REFUSED_AMBIGUOUS


def test_no_pinning_is_byte_identical_to_default() -> None:
    # With pinning=None (the default), a satisfied package resolves to ACCEPTED_WITH_EVIDENCE —
    # the pre-machine-pinning behavior is unchanged (acceptance #1).
    assert decide_status(_satisfied_evidence()).status == FinalStatus.ACCEPTED_WITH_EVIDENCE
    assert decide_status(_satisfied_evidence(), pinning=None).status == FinalStatus.ACCEPTED_WITH_EVIDENCE


def test_human_review_pinning_still_resolves_to_accepted_with_evidence() -> None:
    # A human_review pin IS a human-reviewed package, so it resolves to ACCEPTED_WITH_EVIDENCE
    # when evidence is satisfied — only machine_agreement resolves to the non-ACCEPTED status.
    # The pin is backed by an actual human review event (review_origin="human").
    human_pin = PinningProvenance(
        kind="human_review",
        review_event=ReviewArtifact(
            review_id="RVW-REQ-1-001",
            reviewer="reviewer@example.org",
            decision="approved",
            reviewed_hashes={"requirement_ir": _VALID_HASH},
            checklist=ReviewChecklist(
                controlled_form_matches_intent="pass",
                claim_shape_matches_controlled_form="pass",
                source_spans_present="pass",
                assumptions_explicit="pass",
                bindings_justified="pass",
                evidence_level_appropriate="pass",
                unsupported_claims_hidden="pass",
            ),
            timestamp="2026-06-26T05:22:13Z",
            review_origin="human",
        ),
        timestamp="2026-06-26T05:22:13Z",
    )

    decision = decide_status(_satisfied_evidence(), pinning=human_pin)

    assert decision.status == FinalStatus.ACCEPTED_WITH_EVIDENCE


def test_human_accepted_statuses_is_exactly_the_two_accepted_values() -> None:
    # The explicit acceptance category is the two human-accepted statuses — no more, no less.
    assert HUMAN_ACCEPTED_STATUSES == frozenset(
        {
            FinalStatus.ACCEPTED_WITH_EVIDENCE.value,
            FinalStatus.ACCEPTED_FOR_IMPLEMENTATION_WITH_REVIEW.value,
        }
    )


def test_is_human_accepted_distinguishes_machine_pinned_from_human_accepted() -> None:
    # The two human-accepted statuses are accepted; the machine-pinned status and every refusal
    # are not — for both FinalStatus members and plain (JSON-loaded) strings.
    accepted = [
        FinalStatus.ACCEPTED_WITH_EVIDENCE,
        FinalStatus.ACCEPTED_FOR_IMPLEMENTATION_WITH_REVIEW,
    ]
    not_accepted = [
        FinalStatus.MACHINE_PINNED_PENDING_REVIEW,
        FinalStatus.REFUSED_AMBIGUOUS,
        FinalStatus.REFUSED_UNBOUND_SYMBOLS,
        FinalStatus.REFUSED_UNSUPPORTED_CLAIM,
        FinalStatus.REFUSED_FAILED_CHECK,
        FinalStatus.REFUSED_TIMEOUT,
        FinalStatus.NEEDS_SPEC_COVERAGE,
    ]
    for status in accepted:
        assert is_human_accepted(status) is True
        assert is_human_accepted(status.value) is True
    for status in not_accepted:
        assert is_human_accepted(status) is False
        assert is_human_accepted(status.value) is False


def test_is_human_accepted_rejects_non_status_values() -> None:
    assert is_human_accepted(None) is False
    assert is_human_accepted(123) is False
    assert is_human_accepted("ACCEPTED_WITH_EVIDENCE_BUT_MALFORMED") is False
