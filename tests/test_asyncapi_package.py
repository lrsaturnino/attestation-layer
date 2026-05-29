from pathlib import Path

import pytest

from nlreq.adoption import build_package_index
from nlreq.asyncapi_adapter import AsyncApiAdapter
from nlreq.asyncapi_package import build_asyncapi_package, validate_asyncapi_package
from nlreq.cli import main
from nlreq.models import EvidenceLevel, FinalStatus


FIXTURES = Path(__file__).parent / "fixtures" / "requirements"
DOCUMENT = Path(__file__).parent / "fixtures" / "adapters" / "asyncapi" / "sample-asyncapi.json"


def test_build_asyncapi_package_records_event_emission_evidence(tmp_path: Path) -> None:
    out = tmp_path / "REQ-ASYNCAPI-001"
    adapter = AsyncApiAdapter(DOCUMENT, document_name="sample-event-api")

    build_asyncapi_package(
        controlled_text=(FIXTURES / "event_emit.nlreq").read_text(),
        output_dir=out,
        requirement_id="REQ-ASYNCAPI-001",
        title="Approved operation emits accepted event",
        claim_kind="event_state_correspondence",
        adapter=adapter,
    )

    ir, evidence, status = validate_asyncapi_package(out, adapter)

    assert ir.bindings["operation"].adapter == "asyncapi"
    assert status.status == FinalStatus.ACCEPTED_WITH_EVIDENCE
    assert [claim.id for claim in evidence.claims] == [
        "C-static",
        "C-consistency",
        "C-smt",
        "ASYNCAPI-SYMBOLS",
        "ASYNCAPI-EVENT-EMISSION",
    ]
    assert evidence.claims[-1].achieved_evidence == EvidenceLevel.TYPE_CHECKED


def test_validate_asyncapi_package_rejects_stale_document_hash(tmp_path: Path) -> None:
    document = tmp_path / "asyncapi.json"
    document.write_text(DOCUMENT.read_text())
    adapter = AsyncApiAdapter(document, document_name="sample-event-api")
    out = tmp_path / "REQ-ASYNCAPI-STALE-001"
    build_asyncapi_package(
        controlled_text=(FIXTURES / "event_emit.nlreq").read_text(),
        output_dir=out,
        requirement_id="REQ-ASYNCAPI-STALE-001",
        title="Approved operation emits accepted event",
        claim_kind="event_state_correspondence",
        adapter=adapter,
    )
    document.write_text(document.read_text() + "\n")

    with pytest.raises(ValueError, match="AsyncAPI document hash"):
        validate_asyncapi_package(out, AsyncApiAdapter(document, document_name="sample-event-api"))


def test_package_index_validates_asyncapi_packages_with_configured_adapter(tmp_path: Path) -> None:
    package_root = tmp_path / "requirements"
    adapter = AsyncApiAdapter(DOCUMENT, document_name="sample-event-api")
    build_asyncapi_package(
        controlled_text=(FIXTURES / "event_emit.nlreq").read_text(),
        output_dir=package_root / "REQ-ASYNCAPI-001",
        requirement_id="REQ-ASYNCAPI-001",
        title="Approved operation emits accepted event",
        claim_kind="event_state_correspondence",
        adapter=adapter,
    )

    skipped = build_package_index(package_root)
    valid = build_package_index(package_root, asyncapi_adapter=adapter)

    assert skipped["packages"][0]["validation_kind"] == "asyncapi"
    assert skipped["packages"][0]["validation_status"] == "skipped"
    assert valid["packages"][0]["validation_status"] == "valid"
    assert valid["packages"][0]["adapter"] == "asyncapi"


def test_asyncapi_cli_package_validate_and_conformance(tmp_path: Path, capsys) -> None:
    out = tmp_path / "REQ-ASYNCAPI-CLI-001"

    conformance_exit = main(
        [
            "asyncapi-conformance",
            str(DOCUMENT),
            "--asyncapi-name",
            "sample-event-api",
        ]
    )
    build_exit = main(
        [
            "asyncapi-package",
            str(FIXTURES / "event_emit.nlreq"),
            "--out",
            str(out),
            "--requirement-id",
            "REQ-ASYNCAPI-CLI-001",
            "--title",
            "Approved operation emits accepted event",
            "--claim-kind",
            "event_state_correspondence",
            "--document",
            str(DOCUMENT),
            "--asyncapi-name",
            "sample-event-api",
        ]
    )
    validate_exit = main(
        [
            "asyncapi-validate",
            str(out),
            "--document",
            str(DOCUMENT),
            "--asyncapi-name",
            "sample-event-api",
        ]
    )

    output = capsys.readouterr().out

    assert conformance_exit == 0
    assert build_exit == 0
    assert validate_exit == 0
    assert "Adapter: asyncapi" in output
    assert "Package:" in output
    assert "Status: ACCEPTED_WITH_EVIDENCE" in output
