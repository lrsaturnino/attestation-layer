from __future__ import annotations

import pytest
from pydantic import ValidationError

from nlreq.models import BackendResult, EvidenceLevel


def test_proven_inductive_without_proof_artifact_is_rejected_at_construction() -> None:
    with pytest.raises(ValidationError, match="PROVEN_INDUCTIVE requires a checked-proof artifact"):
        BackendResult(
            backend="apalache",
            status="valid",
            evidence_level=EvidenceLevel.PROVEN_INDUCTIVE,
        )


def test_proven_inductive_accepts_a_proof_artifact_hash() -> None:
    result = BackendResult(
        backend="tlaps",
        status="valid",
        evidence_level=EvidenceLevel.PROVEN_INDUCTIVE,
        details={"proof_artifact_sha256": "sha256:checked-proof"},
    )

    assert result.evidence_level == EvidenceLevel.PROVEN_INDUCTIVE


def test_proven_inductive_accepts_a_non_empty_proof_artifacts_list() -> None:
    result = BackendResult(
        backend="tlaps",
        status="valid",
        evidence_level=EvidenceLevel.PROVEN_INDUCTIVE,
        details={"proof_artifacts": [{"kind": "checked_proof", "sha256": "sha256:p"}]},
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
