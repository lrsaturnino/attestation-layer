from pathlib import Path

import pytest

from nlreq.adoption import build_package_index
from nlreq.cli import main
from nlreq.graphql_adapter import GraphQlAdapter
from nlreq.graphql_package import build_graphql_package, validate_graphql_package
from nlreq.jsonutil import read_json
from nlreq.models import EvidenceLevel, FinalStatus


FIXTURES = Path(__file__).parent / "fixtures" / "requirements"
SCHEMA = Path(__file__).parent / "fixtures" / "adapters" / "graphql" / "sample-schema.graphql"


def test_build_graphql_package_records_static_schema_evidence(tmp_path: Path) -> None:
    out = tmp_path / "REQ-GRAPHQL-001"
    adapter = GraphQlAdapter(SCHEMA, schema_name="sample-graphql")

    build_graphql_package(
        controlled_text=(FIXTURES / "authorization_precondition.nlreq").read_text(),
        output_dir=out,
        requirement_id="REQ-GRAPHQL-001",
        title="Unauthorized GraphQL operation is rejected before state changes",
        claim_kind="authorization_precondition",
        adapter=adapter,
    )

    ir, evidence, status = validate_graphql_package(out, adapter)

    assert ir.bindings["operation"].adapter == "graphql"
    assert status.status == FinalStatus.ACCEPTED_WITH_EVIDENCE
    assert [claim.id for claim in evidence.claims] == [
        "C-static",
        "C-consistency",
        "C-smt",
        "GRAPHQL-SYMBOLS",
        "GRAPHQL-AUTH-REJECTION",
    ]
    assert evidence.claims[-1].achieved_evidence == EvidenceLevel.STATICALLY_RESOLVED


def test_validate_graphql_package_rejects_stale_schema_hash(tmp_path: Path) -> None:
    schema = tmp_path / "schema.graphql"
    schema.write_text(SCHEMA.read_text())
    adapter = GraphQlAdapter(schema, schema_name="sample-graphql")
    out = tmp_path / "REQ-GRAPHQL-STALE-001"
    build_graphql_package(
        controlled_text=(FIXTURES / "authorization_precondition.nlreq").read_text(),
        output_dir=out,
        requirement_id="REQ-GRAPHQL-STALE-001",
        title="Unauthorized GraphQL operation is rejected before state changes",
        claim_kind="authorization_precondition",
        adapter=adapter,
    )
    schema.write_text(schema.read_text() + "\ntype Extra { id: ID! }\n")

    with pytest.raises(ValueError, match="GraphQL schema hash"):
        validate_graphql_package(out, GraphQlAdapter(schema, schema_name="sample-graphql"))


def test_package_index_validates_graphql_packages_with_configured_adapter(tmp_path: Path) -> None:
    package_root = tmp_path / "requirements"
    adapter = GraphQlAdapter(SCHEMA, schema_name="sample-graphql")
    build_graphql_package(
        controlled_text=(FIXTURES / "authorization_precondition.nlreq").read_text(),
        output_dir=package_root / "REQ-GRAPHQL-001",
        requirement_id="REQ-GRAPHQL-001",
        title="Unauthorized GraphQL operation is rejected before state changes",
        claim_kind="authorization_precondition",
        adapter=adapter,
    )

    skipped = build_package_index(package_root)
    valid = build_package_index(package_root, graphql_adapter=adapter)

    assert skipped["packages"][0]["validation_kind"] == "graphql"
    assert skipped["packages"][0]["validation_status"] == "skipped"
    assert valid["packages"][0]["validation_status"] == "valid"
    assert valid["packages"][0]["adapter"] == "graphql"


def test_graphql_cli_package_validate_and_conformance(tmp_path: Path, capsys) -> None:
    out = tmp_path / "REQ-GRAPHQL-CLI-001"

    conformance_exit = main(
        [
            "graphql-conformance",
            str(SCHEMA),
            "--graphql-name",
            "sample-graphql",
        ]
    )
    build_exit = main(
        [
            "graphql-package",
            str(FIXTURES / "authorization_precondition.nlreq"),
            "--out",
            str(out),
            "--requirement-id",
            "REQ-GRAPHQL-CLI-001",
            "--title",
            "Unauthorized GraphQL operation is rejected before state changes",
            "--claim-kind",
            "authorization_precondition",
            "--schema",
            str(SCHEMA),
            "--graphql-name",
            "sample-graphql",
        ]
    )
    validate_exit = main(
        [
            "graphql-validate",
            str(out),
            "--schema",
            str(SCHEMA),
            "--graphql-name",
            "sample-graphql",
        ]
    )

    output = capsys.readouterr().out

    assert conformance_exit == 0
    assert build_exit == 0
    assert validate_exit == 0
    assert "Adapter: graphql" in output
    assert "Package:" in output
    assert "Status: ACCEPTED_WITH_EVIDENCE" in output
