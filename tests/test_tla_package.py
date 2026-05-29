import sys
from pathlib import Path

import pytest

from nlreq.adoption import build_package_index
from nlreq.cli import main
from nlreq.jsonutil import read_json, write_json
from nlreq.models import EvidenceLevel, FinalStatus
from nlreq.tla_adapter import TlaAdapter, TlaModelConfigArtifact
from nlreq.tla_package import build_tla_package, run_tla_checks, validate_tla_package


REQUIREMENT_TEXT = (
    "For every operation request:\n"
    "if actor is not authorized\n"
    "then operation must be rejected before state_change.\n"
)


def test_build_tla_package_records_bounded_checked_evidence(tmp_path: Path) -> None:
    project = _project(tmp_path)
    adapter = _adapter(project)
    out = tmp_path / "requirements" / "REQ-TLA-001"

    build_tla_package(
        controlled_text=REQUIREMENT_TEXT,
        output_dir=out,
        requirement_id="REQ-TLA-001",
        title="Unauthorized operation is rejected before state changes",
        claim_kind="authorization_precondition",
        adapter=adapter,
    )

    ir, evidence, status = validate_tla_package(out, adapter)

    assert ir.bindings["operation"].adapter == "tla"
    assert status.status == FinalStatus.ACCEPTED_WITH_EVIDENCE
    assert evidence.claims[-1].id == "authorization-state-machine"
    assert evidence.claims[-1].required_evidence == EvidenceLevel.BOUNDED_CHECKED
    assert evidence.claims[-1].achieved_evidence == EvidenceLevel.BOUNDED_CHECKED
    assert read_json(out / "counterexamples.json") == []


def test_tla_package_records_counterexample_when_checker_reports_violation(tmp_path: Path) -> None:
    project = _project(tmp_path)
    adapter = _adapter(
        project,
        command=[sys.executable, "-c", "print('Invariant is violated.')"],
    )
    out = tmp_path / "requirements" / "REQ-TLA-FAIL-001"

    build_tla_package(
        controlled_text=REQUIREMENT_TEXT,
        output_dir=out,
        requirement_id="REQ-TLA-001",
        title="Unauthorized operation is rejected before state changes",
        claim_kind="authorization_precondition",
        adapter=adapter,
    )

    _ir, evidence, status = validate_tla_package(out, adapter)

    assert status.status == FinalStatus.REFUSED_FAILED_CHECK
    assert evidence.failed_checks == ["authorization-state-machine"]
    assert read_json(out / "counterexamples.json")[0]["backend"] == "tla"


def test_validate_tla_package_rejects_stale_model_hash(tmp_path: Path) -> None:
    project = _project(tmp_path)
    adapter = _adapter(project)
    out = tmp_path / "requirements" / "REQ-TLA-STALE-001"
    build_tla_package(
        controlled_text=REQUIREMENT_TEXT,
        output_dir=out,
        requirement_id="REQ-TLA-001",
        title="Unauthorized operation is rejected before state changes",
        claim_kind="authorization_precondition",
        adapter=adapter,
    )
    (project / "Authorization.tla").write_text("---- MODULE Authorization ----\n====\n")

    with pytest.raises(ValueError, match="TLA model/config hashes"):
        validate_tla_package(out, adapter)


def test_tla_package_index_validates_when_adapter_is_configured(tmp_path: Path) -> None:
    project = _project(tmp_path)
    adapter = _adapter(project)
    package_root = tmp_path / "requirements"
    build_tla_package(
        controlled_text=REQUIREMENT_TEXT,
        output_dir=package_root / "REQ-TLA-001",
        requirement_id="REQ-TLA-001",
        title="Unauthorized operation is rejected before state changes",
        claim_kind="authorization_precondition",
        adapter=adapter,
    )

    skipped = build_package_index(package_root)
    valid = build_package_index(package_root, tla_adapter=adapter)

    assert skipped["packages"][0]["validation_kind"] == "tla"
    assert skipped["packages"][0]["validation_status"] == "skipped"
    assert valid["packages"][0]["adapter"] == "tla"
    assert valid["packages"][0]["validation_status"] == "valid"


def test_run_tla_checks_returns_result_artifact(tmp_path: Path) -> None:
    project = _project(tmp_path)
    adapter = _adapter(project)
    package_root = tmp_path / "requirements"
    build_tla_package(
        controlled_text=REQUIREMENT_TEXT,
        output_dir=package_root / "REQ-TLA-001",
        requirement_id="REQ-TLA-001",
        title="Unauthorized operation is rejected before state changes",
        claim_kind="authorization_precondition",
        adapter=adapter,
    )

    results = run_tla_checks(
        package_root,
        adapter=adapter,
        requirement_ids=["REQ-TLA-001"],
    )

    assert results.adapter == "tla"
    assert results.results[0].status == "valid"
    assert results.results[0].evidence_level == EvidenceLevel.BOUNDED_CHECKED


def test_tla_cli_builds_validates_and_runs_checks(tmp_path: Path, capsys) -> None:
    project = _project(tmp_path)
    config = tmp_path / "tla-models.json"
    write_json(config, _config())
    requirement = tmp_path / "authorization.nlreq"
    requirement.write_text(REQUIREMENT_TEXT)
    package_root = tmp_path / "requirements"
    out = package_root / "REQ-TLA-001"
    results_out = tmp_path / "tla-results.json"

    build_exit = main(
        [
            "tla-package",
            str(requirement),
            "--out",
            str(out),
            "--requirement-id",
            "REQ-TLA-001",
            "--title",
            "Unauthorized operation is rejected before state changes",
            "--claim-kind",
            "authorization_precondition",
            "--model-config",
            str(config),
            "--project-root",
            str(project),
        ]
    )
    validate_exit = main(
        [
            "tla-validate",
            str(out),
            "--model-config",
            str(config),
            "--project-root",
            str(project),
        ]
    )
    check_exit = main(
        [
            "tla-check",
            str(package_root),
            "--model-config",
            str(config),
            "--requirement-id",
            "REQ-TLA-001",
            "--project-root",
            str(project),
            "--out",
            str(results_out),
        ]
    )

    output = capsys.readouterr().out

    assert build_exit == 0
    assert validate_exit == 0
    assert check_exit == 0
    assert "Package:" in output
    assert "TLA model-checking results:" in output
    assert read_json(results_out)["results"][0]["status"] == "valid"


def _project(tmp_path: Path) -> Path:
    project = tmp_path / "tla"
    project.mkdir()
    (project / "Authorization.tla").write_text(
        "---- MODULE Authorization ----\n"
        "VARIABLE stateChanged\n"
        "Init == stateChanged = FALSE\n"
        "Next == UNCHANGED stateChanged\n"
        "UnauthorizedRejectedBeforeStateChange == stateChanged = FALSE\n"
        "====\n"
    )
    (project / "Authorization.cfg").write_text(
        "INIT Init\nNEXT Next\nINVARIANT UnauthorizedRejectedBeforeStateChange\n"
    )
    return project


def _adapter(project: Path, *, command: list[str] | None = None) -> TlaAdapter:
    return TlaAdapter(_config(command=command), project_root=project)


def _config(command: list[str] | None = None) -> TlaModelConfigArtifact:
    return TlaModelConfigArtifact.model_validate(
        {
            "schema_version": "0.1",
            "adapter": "tla",
            "models": [
                {
                    "model_id": "authorization-state-machine",
                    "requirement_ids": ["REQ-TLA-001"],
                    "module": "Authorization.tla",
                    "config": "Authorization.cfg",
                    "checker": "custom",
                    "command": command
                    or [
                        sys.executable,
                        "-c",
                        "print('Model checking completed. No error has been found.')",
                    ],
                    "properties": ["UnauthorizedRejectedBeforeStateChange"],
                    "bounds": {"actors": 3, "resources": 3, "steps": 10},
                    "requested_evidence": "BOUNDED_CHECKED",
                    "timeout_seconds": 30,
                }
            ],
        }
    )
