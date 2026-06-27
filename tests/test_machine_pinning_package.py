"""Tests for the machine-pinning PACKAGE stamping path (three-zone scope §6; AC2 / AC1).

A machine-pinned package (built with a ``machine_agreement`` ``PinningProvenance``) MUST:
  * emit a ``pinning-provenance.json`` artifact carrying the ``machine_agreement`` record (AC2);
  * carry a ``needs_review`` review, NOT the fabricated ``approved`` package-builder review (AC2 —
    a machine pin never fakes human approval);
  * resolve under ``decide_status`` (via ``validate_package``) to ``MACHINE_PINNED_PENDING_REVIEW``,
    a status that does NOT start with ``ACCEPTED`` (AC3).

A default package (no pinning) MUST stay byte-identical to the pre-pinning pipeline (AC1): no
``pinning-provenance.json``, the fabricated approved review, and the human-accepted status.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from nlreq.jsonutil import read_json, sha256_text
from nlreq.models import (
    EnsembleAgreementResult,
    EnsembleAuditVerdict,
    EnsembleEvidence,
    EnsembleMember,
    FinalStatus,
    PinningProvenance,
    ReviewArtifact,
    is_real_human_review,
)
from nlreq.package import PINNING_PROVENANCE_FILENAME, build_package, validate_package


_FIXTURES = Path(__file__).parent / "fixtures" / "requirements"
_VALID_HASH = "sha256:" + "0" * 64
# The controlled text the machine pin is bound to (HELPER iter-2: the pin's agreement_hash MUST
# equal the canonical hash of the PACKAGED controlled text, not a dummy all-zero hash). The
# parser normalizes (dedents) the controlled text before storing it on the IR, so the binding is
# to the NORMALIZED form (what ``bound_ir.source.controlled_text`` and validate_package see).
_CONTROLLED_TEXT = (_FIXTURES / "authorization_precondition.nlreq").read_text()
from nlreq.parser import normalize_controlled_text  # noqa: E402

_AGREEMENT_HASH = sha256_text(normalize_controlled_text(_CONTROLLED_TEXT))


def _machine_pin() -> PinningProvenance:
    return PinningProvenance(
        kind="machine_agreement",
        ensemble=EnsembleEvidence(
            members=[
                EnsembleMember(member_id="a", resolved_model_id="claude-x", provider_family="anthropic"),
                EnsembleMember(member_id="b", resolved_model_id="gpt-x", provider_family="openai"),
            ],
            agreement=EnsembleAgreementResult(agreed=True, agreement_hash=_AGREEMENT_HASH),
            audit_verdicts=[
                EnsembleAuditVerdict(member_id="a", verdict="passed"),
                EnsembleAuditVerdict(member_id="b", verdict="passed"),
            ],
            policy_hash=_VALID_HASH,
        ),
        timestamp="2026-06-26T00:00:00Z",
    )


def _build(tmp_path: Path, *, pinning: PinningProvenance | None = None) -> Path:
    out = tmp_path / "REQ-MP-001"
    build_package(
        controlled_text=_CONTROLLED_TEXT,
        output_dir=out,
        requirement_id="REQ-MP-001",
        title="Unauthorized operation is rejected before state changes",
        claim_kind="authorization_precondition",
        pinning=pinning,
    )
    return out


# --- AC2: a machine-pinned package emits the pinning record + a needs_review review ---


def test_machine_pinned_package_writes_pinning_provenance_json(tmp_path: Path) -> None:
    out = _build(tmp_path, pinning=_machine_pin())
    pinning_path = out / PINNING_PROVENANCE_FILENAME
    assert pinning_path.is_file()
    record = PinningProvenance.model_validate(read_json(pinning_path))
    assert record.kind == "machine_agreement"
    assert record.ensemble is not None
    assert {m.provider_family for m in record.ensemble.members} == {"anthropic", "openai"}
    assert all(v.verdict == "passed" for v in record.ensemble.audit_verdicts)
    assert record.ensemble.policy_hash == _VALID_HASH


def test_machine_pinned_package_carries_needs_review_not_approved(tmp_path: Path) -> None:
    out = _build(tmp_path, pinning=_machine_pin())
    review = ReviewArtifact.model_validate(read_json(out / "review.json"))
    # AC2: a machine pin never fakes human approval — the review is needs_review, not approved.
    assert review.decision == "needs_review"
    assert is_real_human_review(review) is False


def test_machine_pinned_package_resolves_to_machine_pinned_status(tmp_path: Path) -> None:
    out = _build(tmp_path, pinning=_machine_pin())
    status = read_json(out / "status.json")
    assert status["status"] == FinalStatus.MACHINE_PINNED_PENDING_REVIEW.value
    assert not status["status"].startswith("ACCEPTED")


def test_machine_pinned_package_validates(tmp_path: Path) -> None:
    # validate_package re-runs decide_status WITH the loaded pinning record and checks the
    # machine-pinning integrity (needs_review review + pinning-provenance.json present).
    out = _build(tmp_path, pinning=_machine_pin())
    ir, evidence, status = validate_package(out)
    assert status.status is FinalStatus.MACHINE_PINNED_PENDING_REVIEW


# --- AC1: a default package is byte-identical to the pre-pinning pipeline ---


def test_default_package_writes_no_pinning_provenance(tmp_path: Path) -> None:
    out = _build(tmp_path)  # no pinning
    assert not (out / PINNING_PROVENANCE_FILENAME).is_file()


def test_default_package_carries_the_fabricated_approved_review(tmp_path: Path) -> None:
    out = _build(tmp_path)
    review = ReviewArtifact.model_validate(read_json(out / "review.json"))
    assert review.decision == "approved"
    assert review.review_origin == "package_builder"
    assert is_real_human_review(review) is False


def test_default_package_validates_to_accepted_with_evidence(tmp_path: Path) -> None:
    out = _build(tmp_path)
    ir, evidence, status = validate_package(out)
    assert status.status is FinalStatus.ACCEPTED_WITH_EVIDENCE


def test_default_and_machine_pinned_reviews_differ_only_in_decision(tmp_path: Path) -> None:
    # The only review.json difference between a default and a machine-pinned package is the
    # ``decision`` (approved vs needs_review). Everything else is byte-identical, so the
    # machine-pinning stamping path does not perturb the package-builder review shape.
    default_review = read_json(_build(tmp_path / "d") / "review.json")
    machine_review = read_json(_build(tmp_path / "m", pinning=_machine_pin()) / "review.json")
    assert set(default_review) == set(machine_review)
    assert default_review["decision"] == "approved"
    assert machine_review["decision"] == "needs_review"
    default_review["decision"] = "needs_review"
    assert default_review == machine_review


# --- integrity: a machine-pinned package with a tampered approved review fails validation ---


def test_machine_pinned_package_with_a_fabricated_approved_review_fails_validation(
    tmp_path: Path,
) -> None:
    out = _build(tmp_path, pinning=_machine_pin())
    # Tamper: restore the fabricated approved decision on a machine-pinned package. validate_package
    # must refuse — a machine pin must never carry an approved review (it would fake human approval).
    tampered = read_json(out / "review.json")
    tampered["decision"] = "approved"
    (out / "review.json").write_text(json.dumps(tampered, indent=2, sort_keys=True) + "\n")
    with pytest.raises(ValueError, match="needs_review review, not the fabricated"):
        validate_package(out)


def test_machine_pinned_package_missing_pinning_artifact_fails_validation(
    tmp_path: Path,
) -> None:
    out = _build(tmp_path, pinning=_machine_pin())
    (out / PINNING_PROVENANCE_FILENAME).unlink()
    # Without the pinning record, validate_package loads pinning=None and decides ACCEPTED — but
    # the on-disk status.json still says MACHINE_PINNED, so the status-decision mismatch is caught.
    with pytest.raises(ValueError, match="status.json does not match"):
        validate_package(out)


# --- HELPER iter-2: a machine pin is BOUND to the package's actual controlled text ---


def test_build_package_refuses_a_pin_whose_agreement_hash_is_not_bound(tmp_path: Path) -> None:
    # A pin whose agreement_hash does not match the controlled text being packaged is refused at
    # build time — the pin can never be detached from the meaning it claims to pin (the pin records
    # the content hash of the meaning the ensemble agreed on, which must equal the packaged text).
    wrong = PinningProvenance(
        kind="machine_agreement",
        ensemble=EnsembleEvidence(
            members=[
                EnsembleMember(member_id="a", resolved_model_id="claude-x", provider_family="anthropic"),
                EnsembleMember(member_id="b", resolved_model_id="gpt-x", provider_family="openai"),
            ],
            agreement=EnsembleAgreementResult(agreed=True, agreement_hash=_VALID_HASH),
            audit_verdicts=[
                EnsembleAuditVerdict(member_id="a", verdict="passed"),
                EnsembleAuditVerdict(member_id="b", verdict="passed"),
            ],
            policy_hash=_VALID_HASH,
        ),
        timestamp="2026-06-26T00:00:00Z",
    )
    with pytest.raises(ValueError, match="must equal the canonical hash of the controlled text"):
        build_package(
            controlled_text=_CONTROLLED_TEXT,
            output_dir=tmp_path / "REQ-MISMATCH",
            requirement_id="REQ-MISMATCH",
            title="Unauthorized operation is rejected before state changes",
            claim_kind="authorization_precondition",
            pinning=wrong,
        )


def test_validate_package_refuses_a_pin_whose_agreement_hash_drifted_from_the_text(
    tmp_path: Path,
) -> None:
    # Build a correctly-bound pin, then tamper the on-disk pin's agreement_hash so it no longer
    # matches the packaged controlled text. validate_package must refuse — the pin is not bound to
    # the package's actual meaning (tampering the IR text instead would break the review's IR hash
    # first; this directly exercises the agreement_hash binding check).
    import json

    out = _build(tmp_path, pinning=_machine_pin())
    record = json.loads((out / PINNING_PROVENANCE_FILENAME).read_text())
    record["ensemble"]["agreement"]["agreement_hash"] = _VALID_HASH
    (out / PINNING_PROVENANCE_FILENAME).write_text(
        json.dumps(record, indent=2, sort_keys=True) + "\n"
    )
    with pytest.raises(ValueError, match="not bound to this package's actual meaning"):
        validate_package(out)


# ---------------------------------------------------------------------------
# HELPER iter-3 #4: the human promotion path. A machine-pinned package is PROMOTED to
# ``human_review`` after a REAL human review: the pin becomes a human_review record backed by the
# real review event (bound to the package's IR hash), the status re-resolves to a human-accepted
# status, and validate_package continues to pass.
# ---------------------------------------------------------------------------


def _real_human_review(ir_hash: str, *, decision: str = "approved") -> ReviewArtifact:
    """A REAL human review event (review_origin='human', non-placeholder reviewer) bound to an IR.

    ``decision`` defaults to ``"approved"`` (the only decision that promotes a machine pin upward);
    pass ``"rejected"`` / ``"needs_review"`` to build a real-origin human review that did NOT approve
    the meaning (used by the upward-only promotion-refusal regression tests).
    """
    from nlreq.models import ReviewChecklist

    return ReviewArtifact(
        review_id="RVW-HUMAN-001",
        reviewer="alice@example.com",  # a non-placeholder reviewer (not phase<N>@example.invalid)
        decision=decision,
        reviewed_hashes={"requirement_ir": ir_hash},
        checklist=ReviewChecklist(
            controlled_form_matches_intent="pass",
            claim_shape_matches_controlled_form="pass",
            source_spans_present="pass",
            assumptions_explicit="pass",
            bindings_justified="pass",
            evidence_level_appropriate="pass",
            unsupported_claims_hidden="pass",
        ),
        timestamp="2026-06-26T12:00:00Z",
        review_origin="human",
    )


def test_promote_machine_pinned_package_upgrades_to_human_review(tmp_path: Path) -> None:
    from nlreq.jsonutil import sha256_json
    from nlreq.models import RequirementIR
    from nlreq.package import promote_machine_pinned_package
    from nlreq.status import is_human_accepted

    out = _build(tmp_path, pinning=_machine_pin())
    ir = RequirementIR.model_validate_json((out / "requirement.ir.json").read_text())
    ir_hash = sha256_json(ir)

    status = promote_machine_pinned_package(out, review_event=_real_human_review(ir_hash))

    # The status re-resolved to a HUMAN-accepted status (the machine pin was promoted upward).
    assert is_human_accepted(status.status) is True
    assert status.status.value.startswith("ACCEPTED")

    # The on-disk pinning-provenance.json is now a human_review record backed by the real review.
    record = PinningProvenance.model_validate(read_json(out / PINNING_PROVENANCE_FILENAME))
    assert record.kind == "human_review"
    assert record.ensemble is None  # human_review carries a review event, not ensemble evidence
    assert record.review_event is not None
    assert is_real_human_review(record.review_event) is True
    assert record.reviewed_artifact_hash == ir_hash  # bound to the package's IR

    # The on-disk review.json is now the REAL human review (not the fabricated needs_review).
    review = ReviewArtifact.model_validate(read_json(out / "review.json"))
    assert review.review_origin == "human"
    assert review.decision == "approved"


def test_promoted_package_still_validates_as_human_accepted(tmp_path: Path) -> None:
    from nlreq.jsonutil import sha256_json
    from nlreq.models import RequirementIR
    from nlreq.package import promote_machine_pinned_package
    from nlreq.status import is_human_accepted

    out = _build(tmp_path, pinning=_machine_pin())
    ir = RequirementIR.model_validate_json((out / "requirement.ir.json").read_text())
    ir_hash = sha256_json(ir)
    promote_machine_pinned_package(out, review_event=_real_human_review(ir_hash))

    # validate_package re-runs decide_status with the human_review pin and the integrity checks
    # pass (the review's IR hash matches, the status matches decide_status(evidence, human_pin)).
    ir, evidence, status = validate_package(out)
    assert is_human_accepted(status.status) is True


def test_promote_refuses_a_non_machine_pinned_package(tmp_path: Path) -> None:
    from nlreq.package import promote_machine_pinned_package

    # A DEFAULT package (no pinning) cannot be promoted — promotion is upward from machine pin only.
    out = _build(tmp_path, pinning=None)
    with pytest.raises(ValueError, match="requires a machine-pinned package"):
        promote_machine_pinned_package(out, review_event=_real_human_review("sha256:x"))


def test_promote_refuses_a_review_not_bound_to_the_package_ir(tmp_path: Path) -> None:
    from nlreq.package import promote_machine_pinned_package

    out = _build(tmp_path, pinning=_machine_pin())
    # A real human review whose requirement_ir hash does NOT match the package's IR → refused
    # (the human_review pin must be bound to the package's actual meaning).
    with pytest.raises(ValueError, match="does not match this package's IR"):
        promote_machine_pinned_package(out, review_event=_real_human_review("sha256:wrong"))


def test_promote_refuses_a_fabricated_review(tmp_path: Path) -> None:
    from nlreq.jsonutil import sha256_json
    from nlreq.models import RequirementIR, ReviewChecklist
    from nlreq.package import promote_machine_pinned_package

    out = _build(tmp_path, pinning=_machine_pin())
    ir = RequirementIR.model_validate_json((out / "requirement.ir.json").read_text())
    ir_hash = sha256_json(ir)
    # A fabricated review (review_origin='package_builder', the default) cannot back a human pin.
    fabricated = ReviewArtifact(
        review_id="RVW-FAKE",
        reviewer="phase0@example.invalid",
        decision="approved",
        reviewed_hashes={"requirement_ir": ir_hash},
        checklist=ReviewChecklist(
            controlled_form_matches_intent="pass",
            claim_shape_matches_controlled_form="pass",
            source_spans_present="pass",
            assumptions_explicit="pass",
            bindings_justified="pass",
            evidence_level_appropriate="pass",
            unsupported_claims_hidden="pass",
        ),
        timestamp="2026-06-26T12:00:00Z",
        # review_origin defaults to 'package_builder'
    )
    with pytest.raises(ValueError, match="not a real human review"):
        promote_machine_pinned_package(out, review_event=fabricated)


# ---------------------------------------------------------------------------
# HELPER iter-3 #4 (production CLI surface): the ``promote-machine-pin`` command drives the
# promotion end-to-end. The library function is tested above; THESE tests prove the actual
# ``main(["promote-machine-pin", ...])`` handler wires the review file → promotion → exit code,
# so the production promotion path (not just the library call) is exercised.
# ---------------------------------------------------------------------------


def test_promote_machine_pin_cli_promotes_to_human_accepted(tmp_path: Path) -> None:
    from nlreq.cli import main
    from nlreq.jsonutil import sha256_json
    from nlreq.models import RequirementIR
    from nlreq.status import is_human_accepted

    out = _build(tmp_path, pinning=_machine_pin())
    ir = RequirementIR.model_validate_json((out / "requirement.ir.json").read_text())
    ir_hash = sha256_json(ir)
    review_path = tmp_path / "human-review.json"
    review_path.write_text(_real_human_review(ir_hash).model_dump_json())

    exit_code = main(["promote-machine-pin", str(out), "--review", str(review_path)])
    assert exit_code == 0

    # The package now validates as human-accepted with a human_review pin (promotion is upward).
    _ir, _evidence, status = validate_package(out)
    assert is_human_accepted(status.status) is True
    record = PinningProvenance.model_validate(read_json(out / PINNING_PROVENANCE_FILENAME))
    assert record.kind == "human_review"


def test_promote_machine_pin_cli_refuses_a_review_not_bound_to_the_ir(tmp_path: Path) -> None:
    from nlreq.cli import main

    out = _build(tmp_path, pinning=_machine_pin())
    # A real human review bound to the WRONG IR → the CLI exits 2 and leaves the package unchanged.
    review_path = tmp_path / "wrong-review.json"
    review_path.write_text(_real_human_review("sha256:wrong").model_dump_json())

    exit_code = main(["promote-machine-pin", str(out), "--review", str(review_path)])
    assert exit_code == 2
    # The refusal raised BEFORE any write, so the package is still the original machine pin.
    record = PinningProvenance.model_validate(read_json(out / PINNING_PROVENANCE_FILENAME))
    assert record.kind == "machine_agreement"


# ---------------------------------------------------------------------------
# Promotion is upward only on an APPROVAL (iter-5 HELPER gap): a REAL human review whose decision is
# ``needs_review`` or ``rejected`` is NOT an upward step. It must be refused without modifying the
# machine-pinned package — a human rejection can never become a human acceptance. Tested at the
# library boundary, the production CLI handler, and on-disk validation (review.json drift).
# ---------------------------------------------------------------------------


def _package_snapshot(package_dir: Path) -> dict[str, str]:
    """The raw on-disk text of the artifacts a refused promotion must leave untouched."""
    return {
        name: (package_dir / name).read_text()
        for name in ("review.json", PINNING_PROVENANCE_FILENAME, "status.json", "implementation-spec.md")
    }


@pytest.mark.parametrize("decision", ["needs_review", "rejected"])
def test_promote_refuses_a_non_approved_human_review(tmp_path: Path, decision: str) -> None:
    from nlreq.jsonutil import sha256_json
    from nlreq.models import RequirementIR
    from nlreq.package import promote_machine_pinned_package

    out = _build(tmp_path, pinning=_machine_pin())
    ir = RequirementIR.model_validate_json((out / "requirement.ir.json").read_text())
    ir_hash = sha256_json(ir)
    before = _package_snapshot(out)

    # A REAL human review (review_origin='human', non-placeholder reviewer) bound to THIS IR, but
    # which did NOT approve the meaning. Promotion is upward only — it must be refused.
    review = _real_human_review(ir_hash, decision=decision)
    with pytest.raises(ValueError, match="promotion is upward only"):
        promote_machine_pinned_package(out, review_event=review)

    # The package is byte-identical to before the refused promotion (no write happened).
    assert _package_snapshot(out) == before
    record = PinningProvenance.model_validate(read_json(out / PINNING_PROVENANCE_FILENAME))
    assert record.kind == "machine_agreement"


@pytest.mark.parametrize("decision", ["needs_review", "rejected"])
def test_promote_machine_pin_cli_refuses_a_non_approved_human_review(
    tmp_path: Path, decision: str
) -> None:
    from nlreq.cli import main
    from nlreq.jsonutil import sha256_json
    from nlreq.models import RequirementIR

    out = _build(tmp_path, pinning=_machine_pin())
    ir = RequirementIR.model_validate_json((out / "requirement.ir.json").read_text())
    ir_hash = sha256_json(ir)
    before = _package_snapshot(out)

    review_path = tmp_path / "non-approved-review.json"
    review_path.write_text(_real_human_review(ir_hash, decision=decision).model_dump_json())

    exit_code = main(["promote-machine-pin", str(out), "--review", str(review_path)])
    assert exit_code == 2
    # The package is unchanged — a non-approving human review never mutates the machine pin.
    assert _package_snapshot(out) == before
    record = PinningProvenance.model_validate(read_json(out / PINNING_PROVENANCE_FILENAME))
    assert record.kind == "machine_agreement"


def test_promoted_package_with_diverged_review_json_fails_validation(tmp_path: Path) -> None:
    from nlreq.jsonutil import sha256_json
    from nlreq.models import RequirementIR
    from nlreq.package import promote_machine_pinned_package

    out = _build(tmp_path, pinning=_machine_pin())
    ir = RequirementIR.model_validate_json((out / "requirement.ir.json").read_text())
    ir_hash = sha256_json(ir)
    promote_machine_pinned_package(out, review_event=_real_human_review(ir_hash))

    # Tamper the on-disk review.json so it diverges from the human pin's embedded review event (a
    # different review_id). The IR-hash binding still holds, so only the pin↔review.json equality
    # cross-check catches the drift: a promoted package must not drift between the two artifacts.
    drifted = read_json(out / "review.json")
    drifted["review_id"] = "RVW-TAMPERED"
    (out / "review.json").write_text(json.dumps(drifted, indent=2, sort_keys=True) + "\n")
    with pytest.raises(ValueError, match="must equal the package's review.json"):
        validate_package(out)
