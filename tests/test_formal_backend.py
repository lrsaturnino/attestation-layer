import json
import sys
from pathlib import Path

import pytest

from nlreq.cli import main
from nlreq.compositional_ir import migrate_requirement_ir_v1_to_v2
from nlreq.dsl_v2 import DslV2Parser
from nlreq.formal_backend import (
    FormalBackendBudget,
    FormalBackendExecution,
    TlaBoundaryBackend,
    TlaRunnerBackend,
    build_formal_backend_request,
    check_formal_backend,
    existing_formal_boundaries,
)
from nlreq.models import RequirementIR, RequirementIRV2


FIXTURES = Path(__file__).parent / "fixtures" / "requirements"
GOLDENS = Path(__file__).parents[1] / "requirements"


def test_tla_boundary_accepts_supported_migrated_flat_ir_shape() -> None:
    ir = _migrated_auth_ir()
    request = build_formal_backend_request(ir, backend_id="tla-boundary")

    response = check_formal_backend(request)

    assert response.backend_id == "tla-boundary"
    assert response.target == "tla"
    assert response.result.status == "needs_review"
    assert response.result.evidence_level is None
    assert response.unsupported_constructs == []
    assert response.result.details["execution"] == "not_run"


def test_tla_boundary_reports_unsupported_constructs_for_richer_ir() -> None:
    ir = RequirementIRV2.model_validate_json(
        (FIXTURES / "compositional_ir_v02_multi_premise.json").read_text()
    )
    request = build_formal_backend_request(ir, backend_id="tla-boundary")

    response = check_formal_backend(request)

    assert response.result.status == "unsupported"
    unsupported = {(item.node_id, item.kind) for item in response.unsupported_constructs}
    assert ("obligation.must.within", "within") in unsupported
    assert response.result.details["unsupported_constructs"]


def test_tla_boundary_records_versioned_annotations_it_consumes() -> None:
    ir = _migrated_auth_ir()
    data = ir.model_dump(mode="json", exclude_none=True)
    data["semantic_ir"]["annotations"] = {
        "tla": {"schema_version": "0.1", "operator_hint": "Operation"}
    }
    annotated = RequirementIRV2.model_validate(data)
    request = build_formal_backend_request(annotated, backend_id="tla-boundary")

    response = check_formal_backend(request)

    assert response.result.status == "needs_review"
    assert response.consumed_annotations[0].node_id == "rule.root"
    assert response.consumed_annotations[0].namespace == "tla"
    assert response.consumed_annotations[0].schema_version == "0.1"
    assert response.consumed_annotations[0].keys == ["operator_hint", "schema_version"]


def test_tla_boundary_requires_schema_version_for_consumed_annotations() -> None:
    ir = _migrated_auth_ir()
    data = ir.model_dump(mode="json", exclude_none=True)
    data["semantic_ir"]["annotations"] = {"tla": {"operator_hint": "Operation"}}
    annotated = RequirementIRV2.model_validate(data)
    request = build_formal_backend_request(annotated, backend_id="tla-boundary")

    response = check_formal_backend(request)

    assert response.result.status == "unsupported"
    assert response.unsupported_constructs[0].reason == "tla annotation requires schema_version"


def test_unknown_formal_backend_refuses() -> None:
    with pytest.raises(ValueError, match="unknown formal backend"):
        build_formal_backend_request(_migrated_auth_ir(), backend_id="unknown")


def test_existing_formal_boundaries_document_core_smt_and_tla() -> None:
    boundaries = existing_formal_boundaries()

    assert {boundary["backend_id"] for boundary in boundaries} == {
        "apalache",
        "core_smt",
        "tlc",
        "tla",
        "tla-boundary",
        "tla-runner",
    }


def test_tla_runner_lowers_writes_artifacts_and_maps_valid_result(tmp_path: Path) -> None:
    ir = _dsl_v2_ir()
    request = build_formal_backend_request(
        ir,
        backend_id=TlaRunnerBackend.backend_id,
        budget=FormalBackendBudget(timeout_seconds=5, max_depth=10),
        execution=FormalBackendExecution(
            checker_id="custom",
            command=[
                sys.executable,
                "-c",
                "print('Model checking completed. No error has been found.')",
            ],
            artifact_dir=tmp_path.as_posix(),
            tool_version="custom-checker 1.0",
        ),
    )

    response = check_formal_backend(request)

    assert response.backend_id == "tla-runner"
    assert response.result.status == "valid"
    assert response.result.evidence_level.value == "BOUNDED_CHECKED"
    assert response.result.details["runner_outcome"] == "valid"
    assert response.result.details["bounds"]["max_depth"] == 10
    assert (tmp_path / "Req_REQ_DSL_V2_001.tla").is_file()
    assert (tmp_path / "Req_REQ_DSL_V2_001.cfg").read_text() == (
        "INIT Init\nNEXT Next\nPROPERTY RequirementHolds\n"
    )


def test_tla_runner_preserves_counterexample_artifacts(tmp_path: Path) -> None:
    request = build_formal_backend_request(
        _dsl_v2_ir(),
        backend_id=TlaRunnerBackend.backend_id,
        execution=FormalBackendExecution(
            checker_id="custom",
            command=[sys.executable, "-c", "print('Invariant is violated.')"],
            artifact_dir=tmp_path.as_posix(),
        ),
    )

    response = check_formal_backend(request)

    assert response.result.status == "counterexample"
    assert response.result.details["counterexamples"][0]["marker"] == "invariant is violated"


def test_tla_runner_refuses_unsupported_lowering_before_execution(tmp_path: Path) -> None:
    ir = RequirementIRV2.model_validate_json(
        (FIXTURES / "compositional_ir_v02_multi_premise.json").read_text()
    )
    request = build_formal_backend_request(
        ir,
        backend_id=TlaRunnerBackend.backend_id,
        execution=FormalBackendExecution(
            checker_id="custom",
            command=[sys.executable, "-c", "raise SystemExit(99)"],
            artifact_dir=tmp_path.as_posix(),
        ),
    )

    response = check_formal_backend(request)

    assert response.result.status == "unsupported"
    assert not list(tmp_path.iterdir())
    assert response.unsupported_constructs[0].kind == "invariant"


def test_formal_backend_check_cli_outputs_response_json(capsys) -> None:
    exit_code = main(
        [
            "formal-backend-check",
            str(FIXTURES / "compositional_ir_v02_multi_premise.json"),
            "--backend",
            TlaBoundaryBackend.backend_id,
        ]
    )

    output = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert output["backend_id"] == "tla-boundary"
    assert output["result"]["status"] == "unsupported"


def test_tla_runner_cli_executes_checker_and_writes_artifacts(tmp_path: Path, capsys) -> None:
    ir_path = tmp_path / "requirement.ir.json"
    artifact_dir = tmp_path / "artifacts"
    ir_path.write_text(_dsl_v2_ir().model_dump_json())

    exit_code = main(
        [
            "formal-backend-check",
            str(ir_path),
            "--backend",
            TlaRunnerBackend.backend_id,
            "--artifact-dir",
            str(artifact_dir),
            "--checker-id",
            "custom",
            "--timeout-seconds",
            "5",
            "--checker-command",
            sys.executable,
            "-c",
            "print('verification successful')",
        ]
    )

    output = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert output["backend_id"] == "tla-runner"
    assert output["result"]["status"] == "valid"
    assert (artifact_dir / "Req_REQ_DSL_V2_001.tla").is_file()


def _migrated_auth_ir() -> RequirementIRV2:
    source = RequirementIR.model_validate_json(
        (GOLDENS / "REQ-AUTH-001" / "requirement.ir.json").read_text()
    )
    migrated, _record = migrate_requirement_ir_v1_to_v2(source)
    return migrated


def _dsl_v2_ir() -> RequirementIRV2:
    return DslV2Parser().parse_ir(
        (FIXTURES / "dsl_v2_redemption.nlreq2").read_text(),
        requirement_id="REQ-DSL-V2-001",
        title="Redemption finalization is timely and reserve-safe",
    )
