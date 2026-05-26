import json
from pathlib import Path

from nlreq.cli import main
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
