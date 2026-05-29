import json
from pathlib import Path

import pytest

from nlreq.jsonutil import read_json, write_json
from nlreq.models import EvidenceLevel, FinalStatus
from nlreq.openapi_adapter import OpenApiAdapter
from nlreq.openapi_package import build_openapi_package, validate_openapi_package


FIXTURE_DOCUMENT = Path(__file__).parent / "fixtures" / "adapters" / "openapi" / "sample-openapi.json"


def test_build_openapi_package_records_adapter_evidence(tmp_path: Path) -> None:
    out = tmp_path / "REQ-OPENAPI-001"
    adapter = _adapter()

    build_openapi_package(
        controlled_text=(
            "For every operation request:\n"
            "if actor is not authorized\n"
            "then operation must be rejected before state_change.\n"
        ),
        output_dir=out,
        requirement_id="REQ-OPENAPI-001",
        title="Unauthorized OpenAPI operation is rejected before state changes",
        claim_kind="authorization_precondition",
        adapter=adapter,
    )

    expected = {
        "requirement.md",
        "source-diff.md",
        "requirement.ir.json",
        "bindings.json",
        "assumptions.json",
        "review.json",
        "verification-tasks.json",
        "adapter-results.json",
        "generated-tests.json",
        "counterexamples.json",
        "normalized-traces.json",
        "evidence.json",
        "status.json",
        "implementation-spec.md",
        "smt",
    }
    assert expected.issubset({path.name for path in out.iterdir()})

    ir, evidence, status = validate_openapi_package(out, adapter)
    assert ir.bindings["operation"].adapter == "openapi"
    assert ir.bindings["actor"].symbol == "bearerAuth"
    assert status.status == FinalStatus.ACCEPTED_WITH_EVIDENCE
    assert [claim.id for claim in evidence.claims] == [
        "C-static",
        "C-consistency",
        "C-smt",
        "OPENAPI-SYMBOLS",
        "OPENAPI-AUTH-REJECTION",
    ]
    assert evidence.claims[-1].required_evidence == EvidenceLevel.STATICALLY_RESOLVED
    assert evidence.claims[-1].achieved_evidence == EvidenceLevel.STATICALLY_RESOLVED
    assert read_json(out / "generated-tests.json") == []
    assert read_json(out / "counterexamples.json") == []
    assert read_json(out / "normalized-traces.json") == []


def test_build_openapi_package_records_success_response_evidence(tmp_path: Path) -> None:
    out = tmp_path / "REQ-OPENAPI-SUCCESS-001"
    adapter = _adapter()

    build_openapi_package(
        controlled_text=(
            "For every operation request:\n"
            "if actor is approved\n"
            "then operation must succeed.\n"
        ),
        output_dir=out,
        requirement_id="REQ-OPENAPI-SUCCESS-001",
        title="Approved OpenAPI operation succeeds",
        claim_kind="state_precondition",
        adapter=adapter,
    )

    _ir, evidence, status = validate_openapi_package(out, adapter)

    assert status.status == FinalStatus.ACCEPTED_WITH_EVIDENCE
    assert [claim.id for claim in evidence.claims] == [
        "C-static",
        "C-consistency",
        "C-smt",
        "OPENAPI-SYMBOLS",
        "OPENAPI-SUCCESS-RESPONSE",
    ]
    success_claim = next(claim for claim in evidence.claims if claim.id == "OPENAPI-SUCCESS-RESPONSE")
    assert success_claim.achieved_evidence == EvidenceLevel.STATICALLY_RESOLVED
    assert success_claim.backend_results[0].details["success_responses"] == ["200"]


def test_validate_openapi_package_rejects_stale_adapter_result(tmp_path: Path) -> None:
    out = tmp_path / "REQ-OPENAPI-STALE-001"
    adapter = _adapter()
    build_openapi_package(
        controlled_text=(
            "For every operation request:\n"
            "if actor is not authorized\n"
            "then operation must be rejected before state_change.\n"
        ),
        output_dir=out,
        requirement_id="REQ-OPENAPI-STALE-001",
        title="Unauthorized OpenAPI operation is rejected",
        claim_kind="authorization_precondition",
        adapter=adapter,
    )
    results = read_json(out / "adapter-results.json")
    results[1]["details"]["task_input_hash"] = "sha256:stale"
    write_json(out / "adapter-results.json", results)

    with pytest.raises(ValueError, match="evidence.json does not match adapter-results.json"):
        validate_openapi_package(out, adapter)


def test_build_openapi_package_refuses_missing_rejection_response(tmp_path: Path) -> None:
    document = _write_openapi_without_auth_rejection(tmp_path)
    adapter = OpenApiAdapter(document, document_name="missing-rejection-api")
    out = tmp_path / "REQ-OPENAPI-FAIL-001"

    build_openapi_package(
        controlled_text=(
            "For every operation request:\n"
            "if actor is not authorized\n"
            "then operation must be rejected before state_change.\n"
        ),
        output_dir=out,
        requirement_id="REQ-OPENAPI-FAIL-001",
        title="Unauthorized OpenAPI operation is rejected",
        claim_kind="authorization_precondition",
        adapter=adapter,
    )

    _ir, evidence, status = validate_openapi_package(out, adapter)

    assert status.status == FinalStatus.REFUSED_FAILED_CHECK
    auth_claim = next(claim for claim in evidence.claims if claim.id == "OPENAPI-AUTH-REJECTION")
    assert auth_claim.achieved_evidence is None
    assert "operation does not declare a 401 or 403 response" in auth_claim.backend_results[0].details[
        "problems"
    ]


def test_validate_openapi_package_rejects_stale_document_hash(tmp_path: Path) -> None:
    document = tmp_path / "sample-openapi.json"
    document.write_text(FIXTURE_DOCUMENT.read_text())
    adapter = OpenApiAdapter(document, document_name="sample-api")
    out = tmp_path / "REQ-OPENAPI-SOURCE-STALE-001"
    build_openapi_package(
        controlled_text=(
            "For every operation request:\n"
            "if actor is approved\n"
            "then operation must succeed.\n"
        ),
        output_dir=out,
        requirement_id="REQ-OPENAPI-SOURCE-STALE-001",
        title="Approved OpenAPI operation succeeds",
        claim_kind="state_precondition",
        adapter=adapter,
    )
    raw = json.loads(document.read_text())
    raw["paths"]["/operation"]["post"]["responses"].pop("200")
    document.write_text(json.dumps(raw, indent=2, sort_keys=True) + "\n")
    changed_adapter = OpenApiAdapter(document, document_name="sample-api")

    with pytest.raises(ValueError, match="OpenAPI document hashes"):
        validate_openapi_package(out, changed_adapter)


def _adapter() -> OpenApiAdapter:
    return OpenApiAdapter(FIXTURE_DOCUMENT, document_name="sample-api")


def _write_openapi_without_auth_rejection(tmp_path: Path) -> Path:
    raw = json.loads(FIXTURE_DOCUMENT.read_text())
    operation = raw["paths"]["/operation"]["post"]
    operation["responses"].pop("401")
    operation["responses"].pop("403")
    document = tmp_path / "missing-rejection-openapi.json"
    document.write_text(json.dumps(raw, indent=2, sort_keys=True) + "\n")
    return document
