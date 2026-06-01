import json
from pathlib import Path

import pytest

from nlreq.cli import main
from nlreq.compositional_ir import migrate_requirement_ir_v1_to_v2
from nlreq.formal_backend import (
    TlaBoundaryBackend,
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
        "core_smt",
        "tla",
        "tla-boundary",
    }


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


def _migrated_auth_ir() -> RequirementIRV2:
    source = RequirementIR.model_validate_json(
        (GOLDENS / "REQ-AUTH-001" / "requirement.ir.json").read_text()
    )
    migrated, _record = migrate_requirement_ir_v1_to_v2(source)
    return migrated
