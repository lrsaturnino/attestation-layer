from pathlib import Path

import pytest

from nlreq.adoption import build_package_index
from nlreq.cli import main
from nlreq.jsonschema_adapter import JsonSchemaAdapter
from nlreq.jsonschema_package import build_json_schema_package, validate_json_schema_package
from nlreq.models import EvidenceLevel, FinalStatus


FIXTURES = Path(__file__).parent / "fixtures" / "requirements"
SCHEMA = Path(__file__).parent / "fixtures" / "adapters" / "jsonschema" / "sample-schema.json"


def test_build_json_schema_package_records_state_value_evidence(tmp_path: Path) -> None:
    out = tmp_path / "REQ-JSON-SCHEMA-001"
    adapter = JsonSchemaAdapter(SCHEMA, schema_name="sample-json-schema")

    build_json_schema_package(
        controlled_text=(FIXTURES / "state_postcondition.nlreq").read_text(),
        output_dir=out,
        requirement_id="REQ-JSON-SCHEMA-001",
        title="Approved operation sets accepted status",
        claim_kind="state_postcondition",
        adapter=adapter,
    )

    ir, evidence, status = validate_json_schema_package(out, adapter)

    assert ir.bindings["operation"].adapter == "json_schema"
    assert status.status == FinalStatus.ACCEPTED_WITH_EVIDENCE
    assert [claim.id for claim in evidence.claims] == [
        "C-static",
        "C-consistency",
        "C-smt",
        "JSON-SCHEMA-SYMBOLS",
        "JSON-SCHEMA-STATE-VALUE",
    ]
    assert evidence.claims[-1].achieved_evidence == EvidenceLevel.TYPE_CHECKED


def test_build_json_schema_package_records_numeric_delta_evidence(tmp_path: Path) -> None:
    out = tmp_path / "REQ-JSON-SCHEMA-NUM-001"
    adapter = JsonSchemaAdapter(SCHEMA, schema_name="sample-json-schema")

    build_json_schema_package(
        controlled_text=(FIXTURES / "numeric_invariant.nlreq").read_text(),
        output_dir=out,
        requirement_id="REQ-JSON-SCHEMA-NUM-001",
        title="Operation increases counter within limit",
        claim_kind="numeric_invariant",
        adapter=adapter,
    )

    _ir, evidence, status = validate_json_schema_package(out, adapter)

    assert status.status == FinalStatus.ACCEPTED_WITH_EVIDENCE
    assert evidence.claims[-1].id == "JSON-SCHEMA-NUMERIC-DELTA"
    assert evidence.claims[-1].achieved_evidence == EvidenceLevel.TYPE_CHECKED


def test_validate_json_schema_package_rejects_stale_schema_hash(tmp_path: Path) -> None:
    schema = tmp_path / "schema.json"
    schema.write_text(SCHEMA.read_text())
    adapter = JsonSchemaAdapter(schema, schema_name="sample-json-schema")
    out = tmp_path / "REQ-JSON-SCHEMA-STALE-001"
    build_json_schema_package(
        controlled_text=(FIXTURES / "state_postcondition.nlreq").read_text(),
        output_dir=out,
        requirement_id="REQ-JSON-SCHEMA-STALE-001",
        title="Approved operation sets accepted status",
        claim_kind="state_postcondition",
        adapter=adapter,
    )
    schema.write_text(schema.read_text().replace('"accepted"', '"accepted"', 1) + "\n")

    with pytest.raises(ValueError, match="JSON Schema hash"):
        validate_json_schema_package(out, JsonSchemaAdapter(schema, schema_name="sample-json-schema"))


def test_package_index_validates_json_schema_packages_with_configured_adapter(tmp_path: Path) -> None:
    package_root = tmp_path / "requirements"
    adapter = JsonSchemaAdapter(SCHEMA, schema_name="sample-json-schema")
    build_json_schema_package(
        controlled_text=(FIXTURES / "state_postcondition.nlreq").read_text(),
        output_dir=package_root / "REQ-JSON-SCHEMA-001",
        requirement_id="REQ-JSON-SCHEMA-001",
        title="Approved operation sets accepted status",
        claim_kind="state_postcondition",
        adapter=adapter,
    )

    skipped = build_package_index(package_root)
    valid = build_package_index(package_root, json_schema_adapter=adapter)

    assert skipped["packages"][0]["validation_kind"] == "json_schema"
    assert skipped["packages"][0]["validation_status"] == "skipped"
    assert valid["packages"][0]["validation_status"] == "valid"
    assert valid["packages"][0]["adapter"] == "json_schema"


def test_json_schema_cli_package_validate_and_conformance(tmp_path: Path, capsys) -> None:
    out = tmp_path / "REQ-JSON-SCHEMA-CLI-001"

    conformance_exit = main(
        [
            "json-schema-conformance",
            str(SCHEMA),
            "--json-schema-name",
            "sample-json-schema",
        ]
    )
    build_exit = main(
        [
            "json-schema-package",
            str(FIXTURES / "state_postcondition.nlreq"),
            "--out",
            str(out),
            "--requirement-id",
            "REQ-JSON-SCHEMA-CLI-001",
            "--title",
            "Approved operation sets accepted status",
            "--claim-kind",
            "state_postcondition",
            "--schema",
            str(SCHEMA),
            "--json-schema-name",
            "sample-json-schema",
        ]
    )
    validate_exit = main(
        [
            "json-schema-validate",
            str(out),
            "--schema",
            str(SCHEMA),
            "--json-schema-name",
            "sample-json-schema",
        ]
    )

    output = capsys.readouterr().out

    assert conformance_exit == 0
    assert build_exit == 0
    assert validate_exit == 0
    assert "Adapter: json_schema" in output
    assert "Package:" in output
    assert "Status: ACCEPTED_WITH_EVIDENCE" in output
