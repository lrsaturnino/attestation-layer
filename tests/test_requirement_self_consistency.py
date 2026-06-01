import json
import sys
from pathlib import Path

from nlreq.cli import main
from nlreq.dsl_v2 import DslV2Parser
from nlreq.formal_backend import FormalBackendBudget, FormalBackendExecution
from nlreq.models import RequirementIRV2
from nlreq.requirement_self_consistency import check_requirement_self_consistency


FIXTURES = Path(__file__).parent / "fixtures" / "requirements"


def test_requirement_self_consistency_accepts_valid_backend_run(tmp_path: Path) -> None:
    report = check_requirement_self_consistency(
        _ir(),
        budget=FormalBackendBudget(timeout_seconds=5, max_depth=8),
        execution=FormalBackendExecution(
            checker_id="custom",
            command=[sys.executable, "-c", "print('verification successful')"],
            artifact_dir=tmp_path.as_posix(),
        ),
    )

    assert report.status == "valid"
    assert report.result.status == "valid"
    assert report.result.evidence_level.value == "BOUNDED_CHECKED"
    assert report.formal_backend_response is not None
    assert report.formal_backend_response.result.details["bounds"]["max_depth"] == 8


def test_requirement_self_consistency_rejects_impossible_precondition_before_backend(
    tmp_path: Path,
) -> None:
    report = check_requirement_self_consistency(
        _impossible_precondition_ir(),
        execution=FormalBackendExecution(
            checker_id="custom",
            command=[sys.executable, "-c", "raise SystemExit(99)"],
            artifact_dir=tmp_path.as_posix(),
        ),
    )

    assert report.status == "contradiction"
    assert report.result.status == "invalid"
    assert report.contradictions[0].contradiction_type == "impossible_comparison"
    assert report.formal_backend_response is None
    assert not list(tmp_path.iterdir())


def test_requirement_self_consistency_maps_backend_counterexample(tmp_path: Path) -> None:
    report = check_requirement_self_consistency(
        _ir(),
        execution=FormalBackendExecution(
            checker_id="custom",
            command=[sys.executable, "-c", "print('Invariant is violated.')"],
            artifact_dir=tmp_path.as_posix(),
        ),
    )

    assert report.status == "contradiction"
    assert report.result.status == "invalid"
    assert report.contradictions[0].contradiction_type == "backend_counterexample"


def test_requirement_self_consistency_reports_unsupported_node() -> None:
    ir = RequirementIRV2.model_validate_json(
        (FIXTURES / "compositional_ir_v02_multi_premise.json").read_text()
    )

    report = check_requirement_self_consistency(ir)

    assert report.status == "unsupported"
    unsupported = {(item.node_id, item.kind) for item in report.unsupported_constructs}
    assert ("obligation.must.reserve_floor", "invariant") in unsupported


def test_requirement_self_consistency_timeouts_never_approve(tmp_path: Path) -> None:
    report = check_requirement_self_consistency(
        _ir(),
        budget=FormalBackendBudget(timeout_seconds=1),
        execution=FormalBackendExecution(
            checker_id="custom",
            command=[sys.executable, "-c", "import time; time.sleep(2)"],
            artifact_dir=tmp_path.as_posix(),
        ),
    )

    assert report.status == "timeout"
    assert report.result.status == "timeout"
    assert report.result.evidence_level is None


def test_requirement_self_consistency_tool_errors_never_approve(tmp_path: Path) -> None:
    report = check_requirement_self_consistency(
        _ir(),
        execution=FormalBackendExecution(
            checker_id="custom",
            command=[sys.executable, "-c", "raise SystemExit(3)"],
            artifact_dir=tmp_path.as_posix(),
        ),
    )

    assert report.status == "tool_error"
    assert report.result.status == "invalid"
    assert report.result.evidence_level is None


def test_requirement_self_consistency_cli_writes_report(tmp_path: Path, capsys) -> None:
    ir_path = tmp_path / "requirement.ir.json"
    out = tmp_path / "self-consistency.json"
    artifacts = tmp_path / "artifacts"
    ir_path.write_text(_ir().model_dump_json())

    exit_code = main(
        [
            "requirement-self-consistency",
            "--requirement-ir",
            str(ir_path),
            "--artifact-dir",
            str(artifacts),
            "--checker-id",
            "custom",
            "--out",
            str(out),
            "--checker-command",
            sys.executable,
            "-c",
            "print('verification successful')",
        ]
    )

    output = capsys.readouterr().out

    assert exit_code == 0
    assert "Requirement self-consistency:" in output
    assert json.loads(out.read_text())["status"] == "valid"


def _ir() -> RequirementIRV2:
    return DslV2Parser().parse_ir(
        (FIXTURES / "dsl_v2_redemption.nlreq2").read_text(),
        requirement_id="REQ-SELF-001",
        title="Self consistency",
    )


def _impossible_precondition_ir() -> RequirementIRV2:
    data = _ir().model_dump(mode="json")
    comparison = data["semantic_ir"]["premise"]["children"][2]
    comparison["args"] = [
        {"kind": "number", "value": 5},
        {"kind": "number", "value": 3},
    ]
    return RequirementIRV2.model_validate(data)
