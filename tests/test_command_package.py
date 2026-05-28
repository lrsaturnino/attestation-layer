import sys
from pathlib import Path

import pytest

from nlreq.adoption import build_package_index
from nlreq.cli import main
from nlreq.command_adapter import CommandAdapter, CommandChecksArtifact
from nlreq.command_package import (
    build_command_package,
    run_command_evidence,
    validate_command_package,
)
from nlreq.conformance import assert_adapter_conforms
from nlreq.jsonutil import read_json, write_json
from nlreq.models import EvidenceLevel, FinalStatus, SymbolRef
from nlreq.parser import RequirementParser
from nlreq.conformance import AdapterConformanceFixture


REQUIREMENT_TEXT = (
    "For every operation request:\n"
    "if actor is not authorized\n"
    "then operation must be rejected before state_change.\n"
)


def test_build_command_package_records_test_validated_evidence(tmp_path: Path) -> None:
    project = _project(tmp_path)
    adapter = _adapter(project)
    out = tmp_path / "requirements" / "REQ-CMD-001"

    build_command_package(
        controlled_text=REQUIREMENT_TEXT,
        output_dir=out,
        requirement_id="REQ-CMD-001",
        title="Unauthorized operation is rejected by an existing command check",
        claim_kind="authorization_precondition",
        adapter=adapter,
    )

    expected = {
        "command-checks.json",
        "command-results.json",
        "adapter-results.json",
        "counterexamples.json",
        "evidence.json",
        "status.json",
    }
    assert expected.issubset({path.name for path in out.iterdir()})

    ir, evidence, status = validate_command_package(out, adapter)

    assert ir.bindings["operation"].adapter == "command"
    assert status.status == FinalStatus.ACCEPTED_WITH_EVIDENCE
    assert evidence.claims[-1].id == "CHK-AUTH-UNAUTHORIZED"
    assert evidence.claims[-1].required_evidence == EvidenceLevel.TEST_VALIDATED
    assert evidence.claims[-1].achieved_evidence == EvidenceLevel.TEST_VALIDATED
    assert read_json(out / "counterexamples.json") == []


def test_command_package_records_failed_command_counterexample(tmp_path: Path) -> None:
    project = _project(tmp_path)
    adapter = _adapter(
        project,
        command=[sys.executable, "-c", "raise SystemExit(2)"],
    )
    out = tmp_path / "requirements" / "REQ-CMD-FAIL-001"

    build_command_package(
        controlled_text=REQUIREMENT_TEXT,
        output_dir=out,
        requirement_id="REQ-CMD-001",
        title="Unauthorized operation is rejected by an existing command check",
        claim_kind="authorization_precondition",
        adapter=adapter,
    )

    _ir, evidence, status = validate_command_package(out, adapter)

    assert status.status == FinalStatus.REFUSED_FAILED_CHECK
    assert evidence.failed_checks == ["CHK-AUTH-UNAUTHORIZED"]
    counterexamples = read_json(out / "counterexamples.json")
    assert counterexamples[0]["backend"] == "command"
    assert counterexamples[0]["actual"]["exit_code"] == 2


def test_validate_command_package_rejects_stale_target_hash(tmp_path: Path) -> None:
    project = _project(tmp_path)
    adapter = _adapter(project)
    out = tmp_path / "requirements" / "REQ-CMD-STALE-001"
    build_command_package(
        controlled_text=REQUIREMENT_TEXT,
        output_dir=out,
        requirement_id="REQ-CMD-001",
        title="Unauthorized operation is rejected by an existing command check",
        claim_kind="authorization_precondition",
        adapter=adapter,
    )
    (project / "src" / "auth.py").write_text("def changed():\n    return True\n")

    with pytest.raises(ValueError, match="command source/test hashes"):
        validate_command_package(out, adapter)


def test_command_package_index_validates_when_adapter_is_configured(tmp_path: Path) -> None:
    project = _project(tmp_path)
    adapter = _adapter(project)
    package_root = tmp_path / "requirements"
    build_command_package(
        controlled_text=REQUIREMENT_TEXT,
        output_dir=package_root / "REQ-CMD-001",
        requirement_id="REQ-CMD-001",
        title="Unauthorized operation is rejected by an existing command check",
        claim_kind="authorization_precondition",
        adapter=adapter,
    )

    skipped = build_package_index(package_root)
    valid = build_package_index(package_root, command_adapter=adapter)

    assert skipped["packages"][0]["validation_status"] == "skipped"
    assert skipped["packages"][0]["validation_kind"] == "command"
    assert valid["packages"][0]["validation_status"] == "valid"
    assert valid["packages"][0]["adapter"] == "command"


def test_run_command_evidence_returns_result_artifact(tmp_path: Path) -> None:
    project = _project(tmp_path)
    adapter = _adapter(project)
    package_root = tmp_path / "requirements"
    build_command_package(
        controlled_text=REQUIREMENT_TEXT,
        output_dir=package_root / "REQ-CMD-001",
        requirement_id="REQ-CMD-001",
        title="Unauthorized operation is rejected by an existing command check",
        claim_kind="authorization_precondition",
        adapter=adapter,
    )

    results = run_command_evidence(
        package_root,
        adapter=adapter,
        requirement_ids=["REQ-CMD-001"],
    )

    assert results.adapter == "command"
    assert results.results[0].status == "valid"
    assert results.results[0].details["check_id"] == "CHK-AUTH-UNAUTHORIZED"


def test_command_cli_builds_validates_and_runs_evidence(tmp_path: Path, capsys) -> None:
    project = _project(tmp_path)
    checks = tmp_path / "command-checks.json"
    write_json(checks, _checks())
    requirement = tmp_path / "authorization.nlreq"
    requirement.write_text(REQUIREMENT_TEXT)
    package_root = tmp_path / "requirements"
    out = package_root / "REQ-CMD-001"
    evidence_out = tmp_path / "command-results.json"

    build_exit = main(
        [
            "command-package",
            str(requirement),
            "--out",
            str(out),
            "--requirement-id",
            "REQ-CMD-001",
            "--title",
            "Unauthorized operation is rejected by an existing command check",
            "--claim-kind",
            "authorization_precondition",
            "--checks",
            str(checks),
            "--project-root",
            str(project),
        ]
    )
    validate_exit = main(
        [
            "command-validate",
            str(out),
            "--checks",
            str(checks),
            "--project-root",
            str(project),
        ]
    )
    evidence_exit = main(
        [
            "command-evidence",
            str(package_root),
            "--checks",
            str(checks),
            "--requirement-id",
            "REQ-CMD-001",
            "--project-root",
            str(project),
            "--out",
            str(evidence_out),
        ]
    )

    output = capsys.readouterr().out

    assert build_exit == 0
    assert validate_exit == 0
    assert evidence_exit == 0
    assert "Package:" in output
    assert "Requirement: REQ-CMD-001" in output
    assert "Command evidence:" in output
    assert read_json(evidence_out)["results"][0]["status"] == "valid"


def test_command_adapter_conforms(tmp_path: Path) -> None:
    project = _project(tmp_path)
    adapter = _adapter(project, requirement_ids=["REQ-COMMAND-CONFORMANCE-001"])
    ir = RequirementParser().parse_ir(
        REQUIREMENT_TEXT,
        requirement_id="REQ-COMMAND-CONFORMANCE-001",
        title="Command adapter conformance fixture",
        claim_kind="authorization_precondition",
    )

    report = assert_adapter_conforms(
        adapter,
        AdapterConformanceFixture(
            resolved_ref=SymbolRef(name="operation", expected_type="action"),
            unresolved_ref=SymbolRef(name="definitely_missing_symbol"),
            ambiguous_ref=SymbolRef(name="ambiguous_operation", expected_type="action"),
            sample_ir=ir,
        ),
    )

    assert report.adapter_id == "command"


def _project(tmp_path: Path) -> Path:
    project = tmp_path / "project"
    (project / "src").mkdir(parents=True)
    (project / "tests").mkdir()
    (project / "src" / "auth.py").write_text("def rejects_unauthorized():\n    return True\n")
    (project / "tests" / "test_auth.py").write_text("def test_rejects_unauthorized():\n    assert True\n")
    return project


def _adapter(
    project: Path,
    *,
    command: list[str] | None = None,
    requirement_ids: list[str] | None = None,
) -> CommandAdapter:
    return CommandAdapter(_checks(command=command, requirement_ids=requirement_ids), project_root=project)


def _checks(
    *,
    command: list[str] | None = None,
    requirement_ids: list[str] | None = None,
) -> CommandChecksArtifact:
    return CommandChecksArtifact.model_validate(
        {
            "schema_version": "0.1",
            "adapter": "command",
            "checks": [
                {
                    "check_id": "CHK-AUTH-UNAUTHORIZED",
                    "name": "Unauthorized request is rejected",
                    "requirement_ids": requirement_ids or ["REQ-CMD-001"],
                    "command": command
                    or [
                        sys.executable,
                        "-c",
                        (
                            "import pathlib; "
                            "assert pathlib.Path('src/auth.py').is_file(); "
                            "assert pathlib.Path('tests/test_auth.py').is_file()"
                        ),
                    ],
                    "cwd": ".",
                    "timeout_seconds": 10,
                    "expected_exit_code": 0,
                    "target_paths": ["src/auth.py"],
                    "test_paths": ["tests/test_auth.py"],
                    "requested_evidence": "TEST_VALIDATED",
                }
            ],
        }
    )
