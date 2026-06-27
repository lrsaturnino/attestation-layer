"""End-to-end hard-gate tests for the DEFAULT-DENY machine-pin policy (three-zone §6; AC4).

A machine-pinned package (``MACHINE_PINNED_PENDING_REVIEW``) is accepted by the hard gate ONLY on a
change whose EVERY changed path matches the policy's explicit low-risk allow-list AND none matches
the block-list. Unmatched paths, mixed-risk changes, and every auth/funds path require a human
``REVIEWED`` package — a machine pin never satisfies them. These tests build REAL machine-pinned
packages (via ``build_package(pinning=...)``) and run the full ``build_hard_gate_report``.
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

from nlreq.gate import (
    GateMachinePinRules,
    GatePolicy,
    build_hard_gate_report,
    _machine_pin_accepts,
)
from nlreq.jsonutil import write_json
from nlreq.models import (
    EnsembleAgreementResult,
    EnsembleAuditVerdict,
    EnsembleEvidence,
    EnsembleMember,
    FinalStatus,
    PinningProvenance,
    StatusDecision,
)
from nlreq.package import build_package
from nlreq.parser import normalize_controlled_text
from nlreq.jsonutil import sha256_text

_FIXTURES = Path(__file__).parent / "fixtures" / "requirements"
_VALID_HASH = "sha256:" + "0" * 64
# The controlled text the machine pin is bound to (HELPER iter-2: the pin's agreement_hash MUST
# equal the canonical hash of the PACKAGED controlled text — the parser-normalized form).
_CONTROLLED_TEXT = (_FIXTURES / "authorization_precondition.nlreq").read_text()
_AGREEMENT_HASH = sha256_text(normalize_controlled_text(_CONTROLLED_TEXT))
_MACHINE = FinalStatus.MACHINE_PINNED_PENDING_REVIEW.value
_ACCEPTED = FinalStatus.ACCEPTED_WITH_EVIDENCE.value


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


def _build_machine_package(packages_dir: Path) -> None:
    build_package(
        controlled_text=_CONTROLLED_TEXT,
        output_dir=packages_dir / "REQ-MP-001",
        requirement_id="REQ-MP-001",
        title="Unauthorized operation is rejected before state changes",
        claim_kind="authorization_precondition",
        pinning=_machine_pin(),
    )


def _low_risk_policy() -> GatePolicy:
    return GatePolicy(
        policy_id="machine-pin-default-deny",
        machine_pin=GateMachinePinRules(
            enabled=True,
            allowed_changed_path_patterns=["docs/**", "tests/**", "**/*.md"],
        ),
    )


# --- AC4: default-deny — a machine pin is accepted ONLY on allow-listed paths ---


def test_machine_pin_disabled_blocks_machine_pinned_on_every_path(tmp_path: Path) -> None:
    # The default policy (machine_pin.enabled=False) blocks a machine-pinned package on every path,
    # including low-risk ones — the operator must opt into the per-path gate.
    packages_dir = tmp_path / "requirements"
    _build_machine_package(packages_dir)
    report = build_hard_gate_report(
        packages_dir,
        requirement_ids=["REQ-MP-001"],
        policy=GatePolicy(policy_id="disabled"),
        changed_paths=["docs/a.md"],
        now=datetime(2026, 6, 26, tzinfo=timezone.utc),
    )
    assert report["result"] == "blocked"
    assert any(
        f["category"] == "status" and f["enforcement"] == "blocking"
        for f in report["findings"]
    )


def test_machine_pin_accepted_on_allow_listed_paths(tmp_path: Path) -> None:
    packages_dir = tmp_path / "requirements"
    _build_machine_package(packages_dir)
    report = build_hard_gate_report(
        packages_dir,
        requirement_ids=["REQ-MP-001"],
        policy=_low_risk_policy(),
        changed_paths=["docs/guide.md", "tests/test_x.py"],
        now=datetime(2026, 6, 26, tzinfo=timezone.utc),
    )
    # The change touches only allow-listed paths → the machine pin is accepted (not blocked).
    assert report["result"] == "pass"
    assert not any(
        f["category"] in {"status", "pending_reviews"} and f["enforcement"] == "blocking"
        for f in report["findings"]
    )


def test_machine_pin_blocked_on_unmatched_path(tmp_path: Path) -> None:
    packages_dir = tmp_path / "requirements"
    _build_machine_package(packages_dir)
    report = build_hard_gate_report(
        packages_dir,
        requirement_ids=["REQ-MP-001"],
        policy=_low_risk_policy(),
        changed_paths=["src/core/engine.py"],  # not on the allow-list
        now=datetime(2026, 6, 26, tzinfo=timezone.utc),
    )
    assert report["result"] == "blocked"
    assert any(
        f["category"] == "status" and f["enforcement"] == "blocking"
        for f in report["findings"]
    )


def test_machine_pin_blocked_on_mixed_risk_change(tmp_path: Path) -> None:
    # A mixed-risk change (one allow-listed + one unmatched) is default-deny: the machine pin is
    # blocked because NOT every changed path is allow-listed.
    packages_dir = tmp_path / "requirements"
    _build_machine_package(packages_dir)
    report = build_hard_gate_report(
        packages_dir,
        requirement_ids=["REQ-MP-001"],
        policy=_low_risk_policy(),
        changed_paths=["docs/a.md", "src/core/engine.py"],
        now=datetime(2026, 6, 26, tzinfo=timezone.utc),
    )
    assert report["result"] == "blocked"


@pytest.mark.parametrize(
    "sensitive_path",
    [
        "src/auth/login.py",
        "src/funds/transfer.py",
        "src/payments/charge.py",
        "src/wallet/balance.py",
        "src/signing/keys.py",
    ],
)
def test_machine_pin_blocked_on_every_auth_funds_path(
    tmp_path: Path, sensitive_path: str
) -> None:
    # AC4: every auth/funds path requires a human REVIEWED package — a machine pin never satisfies
    # them, even when the allow-list is broad ("**"). The block-list (deny) wins.
    packages_dir = tmp_path / "requirements"
    _build_machine_package(packages_dir)
    broad_policy = GatePolicy(
        policy_id="broad-allow",
        machine_pin=GateMachinePinRules(enabled=True, allowed_changed_path_patterns=["**"]),
    )
    report = build_hard_gate_report(
        packages_dir,
        requirement_ids=["REQ-MP-001"],
        policy=broad_policy,
        changed_paths=[sensitive_path],
        now=datetime(2026, 6, 26, tzinfo=timezone.utc),
    )
    assert report["result"] == "blocked"


def test_machine_pin_blocked_on_empty_changed_paths(tmp_path: Path) -> None:
    # Default-deny: an empty change set has no paths to validate against the allow-list, so a
    # machine pin is not accepted (it needs at least one allow-listed path).
    packages_dir = tmp_path / "requirements"
    _build_machine_package(packages_dir)
    assert _machine_pin_accepts(_MACHINE, [], _low_risk_policy()) is False
    report = build_hard_gate_report(
        packages_dir,
        requirement_ids=["REQ-MP-001"],
        policy=_low_risk_policy(),
        changed_paths=[],
        now=datetime(2026, 6, 26, tzinfo=timezone.utc),
    )
    assert report["result"] == "blocked"


# --- AC4 + AC3: a human-accepted package is unaffected by the machine-pin gate ---


def test_human_accepted_package_passes_regardless_of_machine_pin_policy(tmp_path: Path) -> None:
    # The default-deny machine-pin gate is scoped to the machine status: a human-accepted package
    # passes on any path (the per-path gate never applies to it).
    packages_dir = tmp_path / "requirements"
    build_package(
        controlled_text=(_FIXTURES / "authorization_precondition.nlreq").read_text(),
        output_dir=packages_dir / "REQ-H-001",
        requirement_id="REQ-H-001",
        title="Unauthorized operation is rejected before state changes",
        claim_kind="authorization_precondition",
    )
    report = build_hard_gate_report(
        packages_dir,
        requirement_ids=["REQ-H-001"],
        policy=_low_risk_policy(),
        changed_paths=["src/auth/login.py"],  # a sensitive path
        now=datetime(2026, 6, 26, tzinfo=timezone.utc),
    )
    assert report["result"] == "pass"


# --- the gate policy schema still forbids MACHINE_PINNED in allowed_statuses ---


def test_machine_pinned_status_still_forbidden_in_allowed_statuses() -> None:
    # A machine pin is accepted ONLY per-path, never globally — listing it in allowed_statuses is a
    # loud refusal even with the default-deny gate present.
    from pydantic import ValidationError

    from nlreq.gate import GatePolicyRules

    with pytest.raises(ValidationError, match="not allowed in rules.allowed_statuses"):
        GatePolicyRules(allowed_statuses=[FinalStatus.MACHINE_PINNED_PENDING_REVIEW])
