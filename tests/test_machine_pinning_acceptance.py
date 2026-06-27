"""Per-call-site regression tests for the machine-pinning acceptance-category replacement (ADR 0206).

The six former ``status.startswith("ACCEPTED")`` consumers (scope §6; acceptance #3) must treat a
machine-pinned status (``MACHINE_PINNED_PENDING_REVIEW``) as NOT human-accepted — i.e. behave
exactly as they do for a refused status — while still treating the two human-accepted statuses as
accepted. Each of the six call sites is exercised directly with a machine-pinned status:

  1. ``adoption._index_summary``            (former site at adoption.py:548)
  2. ``adoption._soft_gate_findings``        (former site at adoption.py:723)
  3. ``continuous._accepted``                (former site at continuous.py:680)
  4. ``agent_workflow._implementation_task_blockers``  (former site at agent_workflow.py:374)
  5. ``agent_workflow._retry_payloads``      (former site at agent_workflow.py:465)
  6. ``agent_workflow._retry_reason``        (former site at agent_workflow.py:498)

All six now route through ``nlreq.status.is_human_accepted`` (an explicit frozenset membership
check, not a prefix), so a machine-pinned package can never be silently treated as human-accepted,
and a future ACCEPTED-prefixed machine status could not slip through a prefix check.
"""
from __future__ import annotations

from pathlib import Path

from nlreq.adoption import _index_summary, _soft_gate_findings
from nlreq.agent_workflow import (
    _implementation_task_blockers,
    _retry_payloads,
    _retry_reason,
)
from nlreq.continuous import _accepted
from nlreq.models import FinalStatus
from nlreq.package import build_package


_FIXTURES = Path(__file__).parent / "fixtures" / "requirements"

_MACHINE = FinalStatus.MACHINE_PINNED_PENDING_REVIEW.value
_ACCEPTED = FinalStatus.ACCEPTED_WITH_EVIDENCE.value


# --- minimal package-dict builders (only the keys each call site reads) ---


def _index_package(status: str) -> dict:
    return {
        "status": status,
        "validation_status": "valid",
        "evidence": {
            "needs_spec_coverage": False,
            "unbound_symbols": [],
            "ambiguous_symbols": [],
            "failed_checks": [],
            "unsupported_claims": [],
            "pending_reviews": [],
        },
        "review": {"decision": "approved"},
    }


def _soft_gate_package(status: str) -> dict:
    return {
        "path": "requirements/REQ-1",
        "validation_status": "valid",
        "validation_errors": [],
        "status": status,
        "review": {"decision": "approved"},
        "evidence": {"pending_reviews": [], "unsupported_claims": []},
    }


def _blocker_package(status: str) -> dict:
    return {
        "validation_status": "valid",
        "validation_errors": [],
        "status": status,
        "review": {"decision": "approved"},
    }


def _retry_reason_package(status: str) -> dict:
    return {
        "validation_status": "valid",
        "status": status,
        "evidence": {"failed_checks": [], "unsupported_claims": []},
    }


def _retry_package(pkg_dir: Path, status: str) -> dict:
    # ``_retry_payloads`` reads ``evidence.json`` from disk (via ``_backend_results``) for the
    # backend results, so ``path`` must point at a real built package; the in-memory ``evidence``
    # drives the ``should_retry`` branch under test here.
    return {
        "path": str(pkg_dir),
        "validation_status": "valid",
        "status": status,
        "evidence": {"failed_checks": [], "unsupported_claims": []},
    }


# --- site 1: adoption._index_summary ---


def test_index_summary_does_not_count_machine_pinned_as_accepted() -> None:
    summary = _index_summary([_index_package(status=_MACHINE)])

    assert summary["total"] == 1
    assert summary["accepted"] == 0

    # Contrast: a human-accepted package IS counted.
    accepted_summary = _index_summary([_index_package(status=_ACCEPTED)])
    assert accepted_summary["accepted"] == 1


# --- site 2: adoption._soft_gate_findings ---


def test_soft_gate_findings_flags_machine_pinned_status_as_a_blocker() -> None:
    findings = _soft_gate_findings(["REQ-1"], {"REQ-1": _soft_gate_package(status=_MACHINE)})

    categories = [finding["category"] for finding in findings]
    assert "status" in categories
    status_finding = next(finding for finding in findings if finding["category"] == "status")
    assert "MACHINE_PINNED_PENDING_REVIEW" in str(status_finding["message"])

    # Contrast: a human-accepted, valid, approved package produces no status blocker.
    accepted_findings = _soft_gate_findings(
        ["REQ-1"], {"REQ-1": _soft_gate_package(status=_ACCEPTED)}
    )
    assert "status" not in [finding["category"] for finding in accepted_findings]


# --- site 3: continuous._accepted ---


def test_continuous_accepted_treats_machine_pinned_as_not_accepted() -> None:
    assert _accepted(_MACHINE) is False
    assert _accepted(FinalStatus.MACHINE_PINNED_PENDING_REVIEW) is False
    assert _accepted(_ACCEPTED) is True
    assert _accepted(FinalStatus.ACCEPTED_WITH_EVIDENCE) is True


# --- site 4: agent_workflow._implementation_task_blockers ---


def test_implementation_task_blockers_flags_machine_pinned_status() -> None:
    blockers = _implementation_task_blockers(["REQ-1"], {"REQ-1": _blocker_package(status=_MACHINE)})

    categories = [blocker["category"] for blocker in blockers]
    assert "status" in categories
    status_blocker = next(blocker for blocker in blockers if blocker["category"] == "status")
    assert "MACHINE_PINNED_PENDING_REVIEW" in str(status_blocker["message"])

    # Contrast: a human-accepted package produces no status blocker.
    accepted_blockers = _implementation_task_blockers(
        ["REQ-1"], {"REQ-1": _blocker_package(status=_ACCEPTED)}
    )
    assert "status" not in [blocker["category"] for blocker in accepted_blockers]


# --- site 5: agent_workflow._retry_payloads (the should_retry branch) ---


def test_retry_payloads_retries_machine_pinned_package(tmp_path: Path) -> None:
    # Build a real valid package so ``evidence.json`` exists on disk for ``_backend_results``.
    package_root = tmp_path / "requirements"
    build_package(
        controlled_text=(_FIXTURES / "authorization_precondition.nlreq").read_text(),
        output_dir=package_root / "REQ-AUTH-001",
        requirement_id="REQ-AUTH-001",
        title="Unauthorized operation is rejected before state changes",
        claim_kind="authorization_precondition",
    )
    pkg_dir = package_root / "REQ-AUTH-001"

    machine_payloads = _retry_payloads(
        requirement_ids=["REQ-AUTH-001"],
        packages_by_id={"REQ-AUTH-001": _retry_package(pkg_dir, status=_MACHINE)},
        packages_dir=package_root,
        findings=[],
    )
    # A machine-pinned package is not human-accepted, so it is retried (not treated as done).
    assert len(machine_payloads) == 1
    assert machine_payloads[0]["requirement_id"] == "REQ-AUTH-001"

    # Contrast: a human-accepted package with clean evidence is NOT retried.
    accepted_payloads = _retry_payloads(
        requirement_ids=["REQ-AUTH-001"],
        packages_by_id={"REQ-AUTH-001": _retry_package(pkg_dir, status=_ACCEPTED)},
        packages_dir=package_root,
        findings=[],
    )
    assert accepted_payloads == []


# --- site 6: agent_workflow._retry_reason ---


def test_retry_reason_reports_machine_pinned_status() -> None:
    reason = _retry_reason(_retry_reason_package(status=_MACHINE), [])

    assert "MACHINE_PINNED_PENDING_REVIEW" in reason

    # Contrast: a clean human-accepted package falls through to the final reason, which does not
    # mention the machine-pinned status.
    accepted_reason = _retry_reason(_retry_reason_package(status=_ACCEPTED), [])
    assert "MACHINE_PINNED" not in accepted_reason
