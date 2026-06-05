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
