"""Hard-gate regression tests for the machine-pin gate's DISABLED-DEFAULT posture (ADR 0206 §5; scope §6; AC4).

These tests pin the hard gate's behavior when no machine-pin policy is enabled (the default). With
the ``GatePolicy.machine_pin`` section disabled (``enabled=False``, the default), a machine-pinned
status (``MACHINE_PINNED_PENDING_REVIEW``) is blocked by the hard gate on EVERY path, because
(a) it is not in the default ``allowed_statuses`` (``[ACCEPTED_WITH_EVIDENCE]``) and (b) a
``GatePolicyRules`` validator forbids an operator from blanket-allowing it via ``allowed_statuses``
(a machine pin is accepted ONLY per-path via the dedicated ``machine_pin`` section, never globally).
These tests pin both, and that the status is blocked on generic, auth, and funds changed paths while
the per-path gate is disabled. The ENABLED per-path default-deny behavior (allow-listed accept,
unmatched / mixed / auth / funds block) is exercised end-to-end in
``test_machine_pin_default_deny_gate.py``.
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest
from pydantic import ValidationError

from nlreq.gate import GatePolicy, GatePolicyRules, build_hard_gate_report, _raw_hard_gate_findings
from nlreq.jsonutil import read_json, write_json
from nlreq.models import FinalStatus, ReviewArtifact, StatusDecision, is_real_human_review
from nlreq.package import build_package


_FIXTURES = Path(__file__).parent / "fixtures" / "requirements"
_MACHINE = FinalStatus.MACHINE_PINNED_PENDING_REVIEW.value
_ACCEPTED = FinalStatus.ACCEPTED_WITH_EVIDENCE.value


# --- AC4: the validator forbids blanket-allowing the machine status via allowed_statuses ---


def test_gate_policy_rules_rejects_machine_pinned_status_in_allowed_statuses() -> None:
    # An operator MUST NOT be able to blanket-allow MACHINE_PINNED_PENDING_REVIEW through
    # allowed_statuses: a machine pin is accepted ONLY per-path via the dedicated machine_pin
    # default-deny section, never globally. This validator enforces that at the schema level.
    with pytest.raises(ValidationError, match="MACHINE_PINNED_PENDING_REVIEW is not allowed"):
        GatePolicyRules(allowed_statuses=[FinalStatus.MACHINE_PINNED_PENDING_REVIEW])


def test_default_gate_policy_does_not_allow_machine_pinned_status() -> None:
    # The default allow-set is exactly [ACCEPTED_WITH_EVIDENCE] — the machine status is not in it,
    # so a machine-pinned package is blocked by the status check when the per-path machine_pin gate
    # is disabled (the default); per-path acceptance is opt-in and tested separately.
    rules = GatePolicyRules()
    assert rules.allowed_statuses == [FinalStatus.ACCEPTED_WITH_EVIDENCE]
    assert FinalStatus.MACHINE_PINNED_PENDING_REVIEW not in rules.allowed_statuses


def test_gate_policy_allows_other_statuses_alongside_the_default() -> None:
    # Non-machine statuses remain configurable (the validator is scoped to the machine status only).
    rules = GatePolicyRules(
        allowed_statuses=[
            FinalStatus.ACCEPTED_WITH_EVIDENCE,
            FinalStatus.ACCEPTED_FOR_IMPLEMENTATION_WITH_REVIEW,
        ]
    )
    assert FinalStatus.ACCEPTED_FOR_IMPLEMENTATION_WITH_REVIEW in rules.allowed_statuses


# --- AC4 floor, part 2: the gate flags a machine-pinned status (clean, hand-crafted package) ---


def _gate_package(status: str) -> dict:
    # A valid, approved package whose only varying field is the status — so the sole finding the
    # gate produces is the status finding (no validation / review / evidence noise).
    return {
        "path": "requirements/REQ-1",
        "validation_status": "valid",
        "validation_errors": [],
        "status": status,
        "review": {"decision": "approved"},
        "evidence": {"pending_reviews": [], "unsupported_claims": []},
    }


def test_raw_hard_gate_findings_flags_machine_pinned_status() -> None:
    policy = GatePolicy(policy_id="machine-pin-disabled-default")

    findings = _raw_hard_gate_findings(["REQ-1"], {"REQ-1": _gate_package(_MACHINE)}, policy)

    categories = [finding["category"] for finding in findings]
    assert "status" in categories
    status_finding = next(finding for finding in findings if finding["category"] == "status")
    assert "MACHINE_PINNED_PENDING_REVIEW" in str(status_finding["message"])


def test_raw_hard_gate_findings_does_not_flag_human_accepted_status() -> None:
    # Contrast: a human-accepted, valid, approved package produces no status finding.
    policy = GatePolicy(policy_id="machine-pin-disabled-default")

    findings = _raw_hard_gate_findings(["REQ-1"], {"REQ-1": _gate_package(_ACCEPTED)}, policy)

    assert "status" not in [finding["category"] for finding in findings]


# --- AC4 floor, part 3: the full hard-gate report blocks a machine-pinned package on every path ---


def test_hard_gate_blocks_machine_pinned_package_on_auth_funds_and_unmatched_paths(
    tmp_path: Path,
) -> None:
    # End-to-end through ``build_hard_gate_report`` with the per-path machine_pin gate DISABLED (the
    # default). The status is a focused fixture — a real valid package whose ``status.json`` is
    # overwritten with a machine-pinned decision — so the only finding under test is the ``status``
    # finding (the real stamping path, ``build_package(pinning=...)``, is exercised end-to-end in
    # ``test_machine_pin_default_deny_gate.py``). The overwrite also makes the gate's recompute flag
    # a stale_evidence finding (an honest artifact of the fixture); the finding under test here is
    # the ``status`` finding, which fires because the machine status is not allow-listed. With the
    # per-path gate disabled the machine status is blocked on EVERY path, including auth and funds.
    packages_dir = tmp_path / "requirements"
    build_package(
        controlled_text=(_FIXTURES / "authorization_precondition.nlreq").read_text(),
        output_dir=packages_dir / "REQ-AUTH-001",
        requirement_id="REQ-AUTH-001",
        title="Unauthorized operation is rejected before state changes",
        claim_kind="authorization_precondition",
    )
    # Simulate a machine-pinned status landing on the package (a focused fixture; the real stamping
    # path is ``build_package(pinning=...)``, exercised in ``test_machine_pin_default_deny_gate.py``).
    write_json(
        packages_dir / "REQ-AUTH-001" / "status.json",
        StatusDecision(
            status=FinalStatus.MACHINE_PINNED_PENDING_REVIEW,
            reason="Simulated machine pinning for the disabled-default gate regression.",
            next_actions=["A human may review this machine-pinned rule."],
        ),
    )

    sensitive_changed_paths = [
        "src/auth/login.py",
        "src/funds/transfer.py",
        "src/unmatched/other.py",
    ]
    report = build_hard_gate_report(
        packages_dir,
        requirement_ids=["REQ-AUTH-001"],
        policy=GatePolicy(policy_id="machine-pin-disabled-default"),
        changed_paths=sensitive_changed_paths,
        now=datetime(2026, 6, 26, tzinfo=timezone.utc),
    )

    # The gate is blocked, and the blocking is attributable to the machine-pinned status (not only
    # to the stale_evidence simulation artifact).
    assert report["result"] == "blocked"
    status_findings = [
        finding
        for finding in report["findings"]
        if finding["category"] == "status" and finding["enforcement"] == "blocking"
    ]
    assert status_findings, "a machine-pinned status must produce a blocking status finding"
    assert "MACHINE_PINNED_PENDING_REVIEW" in str(status_findings[0]["message"])


# --- AC1 baseline: the category-2 review check accepts the fabricated package-builder approval ---


def test_category2_review_check_accepts_the_fabricated_package_builder_baseline(tmp_path: Path) -> None:
    # AC1 BASELINE (ADR 0206 §2, "category-2 review checks"): the review-required paths (hard
    # gate / adoption / agent_workflow) gate on ``review["decision"] == "approved"``, NOT on
    # ``is_real_human_review``, because the Phase 0 package builder FABRICATES an approved
    # ``review.json`` (``review_origin="package_builder"``, ``decision="approved"``) on EVERY
    # default package, and AC1 requires the default pipeline to pass byte-identically. Tightening
    # these sites to ``is_real_human_review`` would block every default package — a direct AC1
    # violation and a change to the Phase 0 baseline this scope explicitly preserves (scope §2:
    # only MACHINE packages are forbidden from faking review; the default fabricated approval is
    # kept). The genuine concern — a MACHINE pin backed by a fabricated approval — is enforced at
    # the load-bearing provenance axis instead: a machine-pinned package carries a ``needs_review``
    # review (never ``approved``) and ``validate_package`` REFUSES a machine-pinned package with an
    # ``approved`` review, so a machine pin can never exploit the category-2 check. This test PINS
    # that permanent AC1 baseline posture (it is NOT a deferral that will flip).
    out = tmp_path / "REQ-AUTH-001"
    build_package(
        controlled_text=(_FIXTURES / "authorization_precondition.nlreq").read_text(),
        output_dir=out,
        requirement_id="REQ-AUTH-001",
        title="Unauthorized operation is rejected before state changes",
        claim_kind="authorization_precondition",
    )
    review = ReviewArtifact.model_validate(read_json(out / "review.json"))
    # The fabricated package-builder approval: explicitly non-human, yet decision="approved".
    assert review.review_origin == "package_builder"
    assert review.decision == "approved"
    assert is_real_human_review(review) is False

    # A human-accepted status + the fabricated approval produces NO review (pending_reviews) or
    # status finding: the fabricated approval satisfies the category-2 review check (AC1 baseline).
    package = {
        "path": "requirements/REQ-AUTH-001",
        "validation_status": "valid",
        "validation_errors": [],
        "status": _ACCEPTED,
        "review": {"decision": "approved"},  # the fabricated package-builder approval
        "evidence": {"pending_reviews": [], "unsupported_claims": []},
    }
    findings = _raw_hard_gate_findings(
        ["REQ-AUTH-001"], {"REQ-AUTH-001": package}, GatePolicy(policy_id="ac1-baseline")
    )
    categories = [finding["category"] for finding in findings]
    assert "pending_reviews" not in categories  # AC1 baseline: fabricated approval accepted
    assert "status" not in categories
