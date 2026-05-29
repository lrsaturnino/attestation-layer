from pathlib import Path

import pytest

from nlreq.adoption import build_package_index
from nlreq.cli import main
from nlreq.models import EvidenceLevel, FinalStatus
from nlreq.protobuf_adapter import ProtobufAdapter
from nlreq.protobuf_package import build_protobuf_package, validate_protobuf_package


FIXTURES = Path(__file__).parent / "fixtures" / "requirements"
SCHEMA = Path(__file__).parent / "fixtures" / "adapters" / "protobuf" / "sample.proto"


def test_build_protobuf_package_records_static_schema_evidence(tmp_path: Path) -> None:
    out = tmp_path / "REQ-PROTOBUF-001"
    adapter = ProtobufAdapter(SCHEMA, schema_name="sample-protobuf")

    build_protobuf_package(
        controlled_text=(FIXTURES / "authorization_precondition.nlreq").read_text(),
        output_dir=out,
        requirement_id="REQ-PROTOBUF-001",
        title="Unauthorized gRPC operation is rejected before state changes",
        claim_kind="authorization_precondition",
        adapter=adapter,
    )

    ir, evidence, status = validate_protobuf_package(out, adapter)

    assert ir.bindings["operation"].adapter == "protobuf"
    assert status.status == FinalStatus.ACCEPTED_WITH_EVIDENCE
    assert [claim.id for claim in evidence.claims] == [
        "C-static",
        "C-consistency",
        "C-smt",
        "PROTOBUF-SYMBOLS",
        "PROTOBUF-AUTH-REJECTION",
    ]
    assert evidence.claims[-1].achieved_evidence == EvidenceLevel.STATICALLY_RESOLVED


def test_validate_protobuf_package_rejects_stale_schema_hash(tmp_path: Path) -> None:
    schema = tmp_path / "sample.proto"
    schema.write_text(SCHEMA.read_text())
    adapter = ProtobufAdapter(schema, schema_name="sample-protobuf")
    out = tmp_path / "REQ-PROTOBUF-STALE-001"
    build_protobuf_package(
        controlled_text=(FIXTURES / "authorization_precondition.nlreq").read_text(),
        output_dir=out,
        requirement_id="REQ-PROTOBUF-STALE-001",
        title="Unauthorized gRPC operation is rejected before state changes",
        claim_kind="authorization_precondition",
        adapter=adapter,
    )
    schema.write_text(schema.read_text() + "\nmessage Extra { string id = 1; }\n")

    with pytest.raises(ValueError, match="Protobuf schema hash"):
        validate_protobuf_package(out, ProtobufAdapter(schema, schema_name="sample-protobuf"))


def test_package_index_validates_protobuf_packages_with_configured_adapter(tmp_path: Path) -> None:
    package_root = tmp_path / "requirements"
    adapter = ProtobufAdapter(SCHEMA, schema_name="sample-protobuf")
    build_protobuf_package(
        controlled_text=(FIXTURES / "authorization_precondition.nlreq").read_text(),
        output_dir=package_root / "REQ-PROTOBUF-001",
        requirement_id="REQ-PROTOBUF-001",
        title="Unauthorized gRPC operation is rejected before state changes",
        claim_kind="authorization_precondition",
        adapter=adapter,
    )

    skipped = build_package_index(package_root)
    valid = build_package_index(package_root, protobuf_adapter=adapter)

    assert skipped["packages"][0]["validation_kind"] == "protobuf"
    assert skipped["packages"][0]["validation_status"] == "skipped"
    assert valid["packages"][0]["validation_status"] == "valid"
    assert valid["packages"][0]["adapter"] == "protobuf"


def test_protobuf_cli_package_validate_conformance_and_index(tmp_path: Path, capsys) -> None:
    package_root = tmp_path / "requirements"
    out = package_root / "REQ-PROTOBUF-CLI-001"

    conformance_exit = main(
        [
            "protobuf-conformance",
            str(SCHEMA),
            "--protobuf-name",
            "sample-protobuf",
        ]
    )
    build_exit = main(
        [
            "protobuf-package",
            str(FIXTURES / "authorization_precondition.nlreq"),
            "--out",
            str(out),
            "--requirement-id",
            "REQ-PROTOBUF-CLI-001",
            "--title",
            "Unauthorized gRPC operation is rejected before state changes",
            "--claim-kind",
            "authorization_precondition",
            "--schema",
            str(SCHEMA),
            "--protobuf-name",
            "sample-protobuf",
        ]
    )
    validate_exit = main(
        [
            "protobuf-validate",
            str(out),
            "--schema",
            str(SCHEMA),
            "--protobuf-name",
            "sample-protobuf",
        ]
    )
    index_exit = main(
        [
            "package-index",
            str(package_root),
            "--protobuf-schema",
            str(SCHEMA),
            "--protobuf-name",
            "sample-protobuf",
        ]
    )

    output = capsys.readouterr().out

    assert conformance_exit == 0
    assert build_exit == 0
    assert validate_exit == 0
    assert index_exit == 0
    assert "Adapter: protobuf" in output
    assert "Package:" in output
    assert "Status: ACCEPTED_WITH_EVIDENCE" in output
    assert '"validation_status": "valid"' in output
