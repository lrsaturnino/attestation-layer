from nlreq.models import EvidenceClaim, EvidenceLevel, EvidenceObject, FinalStatus
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
    evidence = EvidenceObject(
        requirement_id="REQ-1",
        unbound_symbols=["authorized"],
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
