import json
from pathlib import Path

from nlreq.cli import main
from nlreq.adoption import build_package_index
from nlreq.jsonutil import write_json
from nlreq.package import build_package


FIXTURES = Path(__file__).parent / "fixtures" / "requirements"
PY_FIXTURE_ROOT = Path(__file__).parent / "fixtures" / "adapters" / "pythonpkg"
PY_FIXTURE_PACKAGE = PY_FIXTURE_ROOT / "samplepkg"


def test_validate_all_reports_all_packages(capsys) -> None:
    exit_code = main(["validate-all", "requirements"])

    output = capsys.readouterr().out

    assert exit_code == 0
    assert "Packages: 4 valid" in output
    assert "REQ-AUTH-001: ACCEPTED_WITH_EVIDENCE" in output
    assert "REQ-REFUSED-UNBOUND-001: REFUSED_UNBOUND_SYMBOLS" in output


def test_validate_all_rejects_empty_package_root(tmp_path: Path, capsys) -> None:
    exit_code = main(["validate-all", str(tmp_path)])

    stderr = capsys.readouterr().err

    assert exit_code == 1
    assert "no package directories found" in stderr


def test_validate_reports_ambiguous_bindings(tmp_path: Path, capsys) -> None:
    out = tmp_path / "REQ-AMBIGUOUS-001"
    build_package(
        controlled_text=(
            "For every operation request:\n"
            "if ambiguous_actor is not authorized\n"
            "then operation must be rejected before state_change.\n"
        ),
        output_dir=out,
        requirement_id="REQ-AMBIGUOUS-001",
        title="Ambiguous actor",
        claim_kind="authorization_precondition",
    )

    exit_code = main(["validate", str(out)])
    output = capsys.readouterr().out

    assert exit_code == 0
    assert "Bindings: ambiguous" in output
    assert "Status: REFUSED_AMBIGUOUS" in output


def test_conformance_reports_generic_adapter(capsys) -> None:
    exit_code = main(["conformance"])

    output = capsys.readouterr().out

    assert exit_code == 0
    assert "Adapter: generic" in output
    assert "Conformance: passed" in output


def test_python_package_and_validate_commands(tmp_path: Path, capsys) -> None:
    requirement = tmp_path / "python_requirement.nlreq"
    requirement.write_text(
        "For every operation request:\n"
        "if actor is approved\n"
        "then operation must succeed.\n"
    )
    out = tmp_path / "REQ-PY-CLI-001"

    build_exit = main(
        [
            "python-package",
            str(requirement),
            "--out",
            str(out),
            "--requirement-id",
            "REQ-PY-CLI-001",
            "--title",
            "Python operation succeeds for approved actor",
            "--claim-kind",
            "state_precondition",
            "--package-root",
            str(PY_FIXTURE_PACKAGE),
            "--package-name",
            "samplepkg",
            "--project-root",
            str(Path(__file__).parents[1]),
            "--test-path",
            str(PY_FIXTURE_ROOT),
            "--property-checks",
        ]
    )
    validate_exit = main(
        [
            "python-validate",
            str(out),
            "--package-root",
            str(PY_FIXTURE_PACKAGE),
            "--package-name",
            "samplepkg",
            "--project-root",
            str(Path(__file__).parents[1]),
            "--test-path",
            str(PY_FIXTURE_ROOT),
            "--property-checks",
        ]
    )

    output = capsys.readouterr().out

    assert build_exit == 0
    assert validate_exit == 0
    assert "Package:" in output
    assert "Requirement: REQ-PY-CLI-001" in output
    assert "Status: ACCEPTED_WITH_EVIDENCE" in output


def test_package_index_reports_package_statuses(tmp_path: Path, capsys) -> None:
    package_root = tmp_path / "requirements"
    build_package(
        controlled_text=(FIXTURES / "authorization_precondition.nlreq").read_text(),
        output_dir=package_root / "REQ-AUTH-001",
        requirement_id="REQ-AUTH-001",
        title="Unauthorized operation is rejected before state changes",
        claim_kind="authorization_precondition",
    )
    build_package(
        controlled_text=(FIXTURES / "unbound_symbol.nlreq").read_text(),
        output_dir=package_root / "REQ-REFUSED-UNBOUND-001",
        requirement_id="REQ-REFUSED-UNBOUND-001",
        title="Unbound operator example",
        claim_kind="authorization_precondition",
    )

    exit_code = main(["package-index", str(package_root)])
    output = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert output["summary"]["total"] == 2
    assert output["summary"]["valid"] == 2
    assert output["summary"]["accepted"] == 1
    assert output["summary"]["refused"] == 1
    assert output["summary"]["unresolved_bindings"] == 1


def test_ci_report_is_shadow_mode_and_reports_findings(tmp_path: Path, capsys) -> None:
    package_root = tmp_path / "requirements"
    build_package(
        controlled_text=(FIXTURES / "unbound_symbol.nlreq").read_text(),
        output_dir=package_root / "REQ-REFUSED-UNBOUND-001",
        requirement_id="REQ-REFUSED-UNBOUND-001",
        title="Unbound operator example",
        claim_kind="authorization_precondition",
    )

    exit_code = main(["ci-report", str(package_root)])
    output = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert output["mode"] == "shadow"
    assert output["result"] == "report_only"
    assert output["summary"]["findings"] >= 1
    assert any(finding["category"] == "unresolved_bindings" for finding in output["findings"])


def test_review_template_outputs_required_checklist(capsys) -> None:
    exit_code = main(["review-template", "REQ-AUTH-001"])
    output = capsys.readouterr().out

    assert exit_code == 0
    assert "Requirement: `REQ-AUTH-001`" in output
    assert "Controlled form matches original intent." in output
    assert "- [ ] approved" in output


def test_soft_gate_passes_for_accepted_requirement(tmp_path: Path, capsys) -> None:
    package_root = tmp_path / "requirements"
    build_package(
        controlled_text=(FIXTURES / "authorization_precondition.nlreq").read_text(),
        output_dir=package_root / "REQ-AUTH-001",
        requirement_id="REQ-AUTH-001",
        title="Unauthorized operation is rejected before state changes",
        claim_kind="authorization_precondition",
    )

    exit_code = main(["soft-gate", str(package_root), "--requirement-id", "REQ-AUTH-001"])
    output = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert output["mode"] == "soft_gate"
    assert output["result"] == "pass"
    assert output["references"] == ["REQ-AUTH-001"]
    assert output["summary"]["blocking_findings"] == 0


def test_soft_gate_reports_missing_reference_without_failing_by_default(capsys) -> None:
    exit_code = main(["soft-gate", "requirements"])
    output = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert output["result"] == "blocked"
    assert output["summary"]["missing_references"] == 1
    assert output["findings"][0]["category"] == "missing_requirement_reference"


def test_soft_gate_can_fail_on_blocking(capsys) -> None:
    exit_code = main(["soft-gate", "requirements", "--fail-on-blocking"])
    output = json.loads(capsys.readouterr().out)

    assert exit_code == 1
    assert output["result"] == "blocked"


def test_soft_gate_extracts_references_from_file(tmp_path: Path, capsys) -> None:
    package_root = tmp_path / "requirements"
    references = tmp_path / "pr-body.md"
    references.write_text("Implements REQ-AUTH-001 and mentions REQ-AUTH-001 again.\n")
    build_package(
        controlled_text=(FIXTURES / "authorization_precondition.nlreq").read_text(),
        output_dir=package_root / "REQ-AUTH-001",
        requirement_id="REQ-AUTH-001",
        title="Unauthorized operation is rejected before state changes",
        claim_kind="authorization_precondition",
    )

    exit_code = main(["soft-gate", str(package_root), "--references-file", str(references)])
    output = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert output["result"] == "pass"
    assert output["references"] == ["REQ-AUTH-001"]


def test_soft_gate_blocks_unknown_requirement(capsys) -> None:
    exit_code = main(["soft-gate", "requirements", "--requirement-id", "REQ-UNKNOWN-999"])
    output = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert output["result"] == "blocked"
    assert output["summary"]["unknown_references"] == 1
    assert output["findings"][0]["category"] == "unknown_requirement_reference"


def test_soft_gate_blocks_refused_requirement(capsys) -> None:
    exit_code = main(
        [
            "soft-gate",
            "requirements",
            "--requirement-id",
            "REQ-REFUSED-UNBOUND-001",
        ]
    )
    output = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert output["result"] == "blocked"
    assert any(finding["category"] == "status" for finding in output["findings"])


def test_hard_gate_passes_for_in_scope_accepted_requirement(tmp_path: Path, capsys) -> None:
    package_root = tmp_path / "requirements"
    policy = _write_hard_gate_policy(tmp_path, package_root)
    report_json = tmp_path / "hard-gate.json"
    report_md = tmp_path / "hard-gate.md"
    build_package(
        controlled_text=(FIXTURES / "authorization_precondition.nlreq").read_text(),
        output_dir=package_root / "REQ-AUTH-001",
        requirement_id="REQ-AUTH-001",
        title="Unauthorized operation is rejected before state changes",
        claim_kind="authorization_precondition",
    )

    exit_code = main(
        [
            "hard-gate",
            str(package_root),
            "--policy",
            str(policy),
            "--requirement-id",
            "REQ-AUTH-001",
            "--changed-path",
            "src/auth.py",
            "--out",
            str(report_json),
            "--markdown-out",
            str(report_md),
        ]
    )
    capsys.readouterr()
    output = json.loads(report_json.read_text())

    assert exit_code == 0
    assert output["mode"] == "hard_gate"
    assert output["result"] == "pass"
    assert output["summary"]["hard_blocking_findings"] == 0
    assert "# NLReq Hard Gate Report" in report_md.read_text()


def test_hard_gate_blocks_in_scope_refused_requirement(tmp_path: Path, capsys) -> None:
    package_root = tmp_path / "requirements"
    policy = _write_hard_gate_policy(tmp_path, package_root)
    build_package(
        controlled_text=(FIXTURES / "unbound_symbol.nlreq").read_text(),
        output_dir=package_root / "REQ-REFUSED-UNBOUND-001",
        requirement_id="REQ-REFUSED-UNBOUND-001",
        title="Unbound operator example",
        claim_kind="authorization_precondition",
    )

    exit_code = main(
        [
            "hard-gate",
            str(package_root),
            "--policy",
            str(policy),
            "--requirement-id",
            "REQ-REFUSED-UNBOUND-001",
            "--changed-path",
            "src/auth.py",
        ]
    )
    output = json.loads(capsys.readouterr().out)

    assert exit_code == 1
    assert output["result"] == "blocked"
    assert output["summary"]["hard_blocking_findings"] >= 1
    assert any(finding["category"] == "status" for finding in output["findings"])


def test_hard_gate_applies_valid_waiver(tmp_path: Path, capsys) -> None:
    package_root = tmp_path / "requirements"
    policy = _write_hard_gate_policy(tmp_path, package_root)
    build_package(
        controlled_text=(FIXTURES / "unbound_symbol.nlreq").read_text(),
        output_dir=package_root / "REQ-REFUSED-UNBOUND-001",
        requirement_id="REQ-REFUSED-UNBOUND-001",
        title="Unbound operator example",
        claim_kind="authorization_precondition",
    )
    waiver = _write_waiver(
        tmp_path,
        package_root,
        requirement_id="REQ-REFUSED-UNBOUND-001",
        stale=False,
    )

    exit_code = main(
        [
            "hard-gate",
            str(package_root),
            "--policy",
            str(policy),
            "--waiver",
            str(waiver),
            "--requirement-id",
            "REQ-REFUSED-UNBOUND-001",
            "--changed-path",
            "src/auth.py",
        ]
    )
    output = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert output["result"] == "pass"
    assert output["summary"]["hard_blocking_findings"] == 0
    assert output["summary"]["waived_findings"] >= 1
    assert {decision["decision"] for decision in output["waiver_decisions"]} == {"applied"}


def test_hard_gate_ignores_stale_waiver(tmp_path: Path, capsys) -> None:
    package_root = tmp_path / "requirements"
    policy = _write_hard_gate_policy(tmp_path, package_root)
    build_package(
        controlled_text=(FIXTURES / "unbound_symbol.nlreq").read_text(),
        output_dir=package_root / "REQ-REFUSED-UNBOUND-001",
        requirement_id="REQ-REFUSED-UNBOUND-001",
        title="Unbound operator example",
        claim_kind="authorization_precondition",
    )
    waiver = _write_waiver(
        tmp_path,
        package_root,
        requirement_id="REQ-REFUSED-UNBOUND-001",
        stale=True,
    )

    exit_code = main(
        [
            "hard-gate",
            str(package_root),
            "--policy",
            str(policy),
            "--waiver",
            str(waiver),
            "--requirement-id",
            "REQ-REFUSED-UNBOUND-001",
            "--changed-path",
            "src/auth.py",
        ]
    )
    output = json.loads(capsys.readouterr().out)

    assert exit_code == 1
    assert output["result"] == "blocked"
    assert output["summary"]["hard_blocking_findings"] >= 1
    assert "stale" in {decision["decision"] for decision in output["waiver_decisions"]}


def test_hard_gate_ignores_expired_waiver(tmp_path: Path, capsys) -> None:
    package_root = tmp_path / "requirements"
    policy = _write_hard_gate_policy(tmp_path, package_root)
    build_package(
        controlled_text=(FIXTURES / "unbound_symbol.nlreq").read_text(),
        output_dir=package_root / "REQ-REFUSED-UNBOUND-001",
        requirement_id="REQ-REFUSED-UNBOUND-001",
        title="Unbound operator example",
        claim_kind="authorization_precondition",
    )
    waiver = _write_waiver(
        tmp_path,
        package_root,
        requirement_id="REQ-REFUSED-UNBOUND-001",
        stale=False,
        expires_at="2000-01-01T00:00:00Z",
    )

    exit_code = main(
        [
            "hard-gate",
            str(package_root),
            "--policy",
            str(policy),
            "--waiver",
            str(waiver),
            "--requirement-id",
            "REQ-REFUSED-UNBOUND-001",
            "--changed-path",
            "src/auth.py",
        ]
    )
    output = json.loads(capsys.readouterr().out)

    assert exit_code == 1
    assert output["result"] == "blocked"
    assert output["summary"]["hard_blocking_findings"] >= 1
    assert "expired" in {decision["decision"] for decision in output["waiver_decisions"]}


def test_hard_gate_reports_refused_requirement_out_of_scope_by_changed_path(
    tmp_path: Path, capsys
) -> None:
    package_root = tmp_path / "requirements"
    policy = _write_hard_gate_policy(tmp_path, package_root)
    build_package(
        controlled_text=(FIXTURES / "unbound_symbol.nlreq").read_text(),
        output_dir=package_root / "REQ-REFUSED-UNBOUND-001",
        requirement_id="REQ-REFUSED-UNBOUND-001",
        title="Unbound operator example",
        claim_kind="authorization_precondition",
    )

    exit_code = main(
        [
            "hard-gate",
            str(package_root),
            "--policy",
            str(policy),
            "--requirement-id",
            "REQ-REFUSED-UNBOUND-001",
            "--changed-path",
            "docs/readme.md",
        ]
    )
    output = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert output["result"] == "pass"
    assert output["summary"]["hard_blocking_findings"] == 0
    assert output["summary"]["out_of_scope_findings"] >= 1


def _write_hard_gate_policy(tmp_path: Path, package_root: Path) -> Path:
    policy = tmp_path / "gate-policy.json"
    write_json(
        policy,
        {
            "policy_id": "GATE-POLICY-TEST",
            "schema_version": "0.1",
            "mode": "hard_gate",
            "scope": {
                "adapters": ["generic"],
                "changed_path_patterns": ["src/**"],
                "package_roots": [package_root.as_posix()],
                "requirement_id_patterns": ["REQ-*"],
            },
            "rules": {
                "allowed_statuses": ["ACCEPTED_WITH_EVIDENCE"],
                "block_findings": [
                    "missing_requirement_reference",
                    "unknown_requirement_reference",
                    "package_validity",
                    "stale_evidence",
                    "status",
                    "pending_reviews",
                ],
                "minimum_evidence": [
                    "STATICALLY_RESOLVED",
                    "CONSISTENCY_CHECKED",
                    "SMT_CHECKED",
                ],
                "require_approved_review": True,
                "report_only_findings": ["unsupported_claims"],
            },
            "waivers": {
                "allow_waivers": True,
                "max_duration_days": 500000,
                "require_reviewed_hashes": True,
            },
        },
    )
    return policy


def _write_waiver(
    tmp_path: Path,
    package_root: Path,
    *,
    requirement_id: str,
    stale: bool,
    expires_at: str = "2999-01-01T00:00:00Z",
) -> Path:
    package_index = build_package_index(package_root)
    package = next(
        package
        for package in package_index["packages"]
        if package["requirement_id"] == requirement_id
    )
    waiver = tmp_path / "waiver.json"
    write_json(
        waiver,
        {
            "waiver_id": "WAIVER-REQ-REFUSED-001",
            "schema_version": "0.1",
            "requirement_ids": [requirement_id],
            "package_paths": [package["path"]],
            "reviewer": "reviewer@example.invalid",
            "reason": "Temporary exception for a known negative fixture.",
            "expires_at": expires_at,
            "reviewed_hashes": {
                "requirement_ir": "sha256:stale"
                if stale
                else package["artifacts"]["requirement.ir.json"],
                "status": package["artifacts"]["status.json"],
            },
            "linked_issue": "https://github.com/example/repo/issues/1",
            "may_satisfy_hard_gate": True,
        },
    )
    return waiver
