from __future__ import annotations

import pytest
from pydantic import ValidationError

from nlreq.models import BackendResult, EvidenceLevel


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
    with pytest.raises(ValidationError, match="BOUNDED_CHECKED requires the bounds"):
        BackendResult(
            backend="tla-runner",
            status="valid",
            evidence_level=EvidenceLevel.BOUNDED_CHECKED,
            details={"tool_version": "tlc 1.0"},
        )


def test_bounded_checked_with_empty_bounds_is_rejected_at_construction() -> None:
    with pytest.raises(ValidationError, match="BOUNDED_CHECKED requires the bounds"):
        BackendResult(
            backend="tla-runner",
            status="valid",
            evidence_level=EvidenceLevel.BOUNDED_CHECKED,
            details={"bounds": {}},
        )


def test_bounded_checked_accepts_recorded_bounds() -> None:
    result = BackendResult(
        backend="tla-runner",
        status="valid",
        evidence_level=EvidenceLevel.BOUNDED_CHECKED,
        details={"bounds": {"max_depth": 8}},
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


def test_trace_validated_accepts_a_recorded_mapping() -> None:
    result = BackendResult(
        backend="trace",
        status="valid",
        evidence_level=EvidenceLevel.TRACE_VALIDATED,
        details={
            "trace_mapping": {
                "validator_id": "forbidden-event-absent",
                "observed_events": ["request", "settle"],
                "fragment": {"forbidden_events_absent": ["unauthorized_settle"]},
            }
        },
    )

    assert result.evidence_level == EvidenceLevel.TRACE_VALIDATED
