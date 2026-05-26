from nlreq.models import EvidenceClaim, EvidenceLevel, EvidenceObject, FinalStatus, SourceSpan
from nlreq.status import decide_status


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
