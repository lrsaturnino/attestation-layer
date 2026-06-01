from pathlib import Path

import pytest
from pydantic import ValidationError

from nlreq.cli import main
from nlreq.compositional_ir import (
    legacy_projection_from_v2,
    migrate_requirement_ir_v1_to_v2,
    validate_requirement_ir_data,
    validate_requirement_ir_json,
)
from nlreq.jsonutil import read_json
from nlreq.models import RequirementIR, RequirementIRV2


FIXTURES = Path(__file__).parent / "fixtures" / "requirements"
GOLDENS = Path(__file__).parents[1] / "requirements"


def test_compositional_ir_v2_fixture_validates() -> None:
    ir = validate_requirement_ir_json((FIXTURES / "compositional_ir_v02_multi_premise.json").read_text())

    assert isinstance(ir, RequirementIRV2)
    assert ir.ir_version == "0.2"
    assert ir.semantic_ir.kind == "rule"
    assert ir.semantic_ir.premise is not None
    assert len(ir.semantic_ir.premise.children) == 3
    assert ir.semantic_ir.obligation is not None
    assert ir.semantic_ir.obligation.must is not None
    assert ir.semantic_ir.obligation.must.kind == "and"


def test_dispatch_validation_rejects_unknown_ir_version() -> None:
    with pytest.raises(ValueError, match="unsupported ir_version"):
        validate_requirement_ir_data({"ir_version": "9.9"})


def test_compositional_ir_rejects_unknown_node_kind() -> None:
    data = read_json(FIXTURES / "compositional_ir_v02_multi_premise.json")
    data["semantic_ir"]["kind"] = "backend_specific_magic"

    with pytest.raises(ValidationError):
        RequirementIRV2.model_validate(data)


def test_migrate_flat_ir_to_compositional_ir_records_auditable_diff() -> None:
    source = RequirementIR.model_validate_json(
        (GOLDENS / "REQ-AUTH-001" / "requirement.ir.json").read_text()
    )

    migrated, record = migrate_requirement_ir_v1_to_v2(source)

    assert migrated.ir_version == "0.2"
    assert migrated.requirement_id == source.requirement_id
    assert migrated.semantic_ir.metadata["legacy_claim_kind"] == source.claim.kind
    assert record.source_ir_version == "0.1"
    assert record.target_ir_version == "0.2"
    assert record.source_ir_hash.startswith("sha256:")
    assert record.target_ir_hash.startswith("sha256:")
    assert record.diff


def test_migrated_ir_projects_exactly_to_flat_ir() -> None:
    source = RequirementIR.model_validate_json(
        (GOLDENS / "REQ-AUTH-001" / "requirement.ir.json").read_text()
    )
    migrated, _record = migrate_requirement_ir_v1_to_v2(source)

    projected = legacy_projection_from_v2(migrated)

    assert projected.model_dump(mode="json", exclude_none=True) == source.model_dump(
        mode="json",
        exclude_none=True,
    )


def test_legacy_projection_rejects_compositional_structure_that_cannot_downcast() -> None:
    ir = RequirementIRV2.model_validate_json(
        (FIXTURES / "compositional_ir_v02_multi_premise.json").read_text()
    )

    with pytest.raises(ValueError, match="legacy_claim_kind"):
        legacy_projection_from_v2(ir)


def test_legacy_projection_rejects_unsupported_node_inside_legacy_shaped_ir() -> None:
    source = RequirementIR.model_validate_json(
        (GOLDENS / "REQ-AUTH-001" / "requirement.ir.json").read_text()
    )
    migrated, _record = migrate_requirement_ir_v1_to_v2(source)
    data = migrated.model_dump(mode="json", exclude_none=True)
    must = data["semantic_ir"]["obligation"]["must"]
    must["kind"] = "within"
    must["temporal_bound"] = {"value": 1, "unit": "hour"}
    ir = RequirementIRV2.model_validate(data)

    with pytest.raises(ValueError, match="cannot project within"):
        legacy_projection_from_v2(ir)


def test_cli_validate_ir_accepts_compositional_ir(capsys) -> None:
    exit_code = main(["validate-ir", str(FIXTURES / "compositional_ir_v02_multi_premise.json")])

    output = capsys.readouterr().out

    assert exit_code == 0
    assert output == "IR: valid\n"


def test_cli_migrate_ir_writes_migrated_ir_and_record(tmp_path: Path, capsys) -> None:
    out = tmp_path / "requirement.ir.v02.json"
    record = tmp_path / "requirement.ir.migration.json"

    exit_code = main(
        [
            "migrate-ir",
            str(GOLDENS / "REQ-AUTH-001" / "requirement.ir.json"),
            "--out",
            str(out),
            "--migration-record",
            str(record),
        ]
    )

    output = capsys.readouterr().out

    assert exit_code == 0
    assert "Migrated IR:" in output
    assert RequirementIRV2.model_validate_json(out.read_text()).ir_version == "0.2"
    assert read_json(record)["source_ir_version"] == "0.1"
