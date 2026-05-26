from pathlib import Path

from nlreq.bindings import bind_ir_with_diagnostics
from nlreq.cli import main
from nlreq.conformance import AdapterConformanceFixture, assert_adapter_conforms
from nlreq.models import BackendResult, EvidenceLevel, SymbolBinding, SymbolRef
from nlreq.openapi_adapter import OpenApiAdapter
from nlreq.parser import RequirementParser


FIXTURE_DOCUMENT = Path(__file__).parent / "fixtures" / "adapters" / "openapi" / "sample-openapi.json"
FIXTURE_YAML = Path(__file__).parent / "fixtures" / "adapters" / "openapi" / "sample-openapi.yaml"


def test_openapi_adapter_indexes_paths_operations_parameters_schemas_and_security() -> None:
    adapter = OpenApiAdapter(FIXTURE_DOCUMENT, document_name="sample-api")

    symbols = {(symbol.name, symbol.symbol_type): symbol for symbol in adapter.symbols()}

    assert symbols[("/operation", "path")].metadata["kind"] == "path"
    assert symbols[("operation", "action")].metadata["method"] == "POST"
    assert symbols[("request_id", "parameter")].metadata["in"] == "header"
    assert symbols[("OperationRequest", "schema")].metadata["kind"] == "component_schema"
    assert symbols[("operation.request", "request_schema")].metadata["schema_refs"] == [
        "OperationRequest"
    ]
    assert symbols[("operation.response.200", "response_schema")].metadata["schema_refs"] == [
        "OperationResponse"
    ]
    assert symbols[("bearerAuth", "principal")].metadata["scheme"] == "bearer"
    assert symbols[("state_change", "state_transition")].metadata["operation"] == "operation"


def test_openapi_adapter_loads_simple_yaml_documents() -> None:
    adapter = OpenApiAdapter(FIXTURE_YAML, document_name="sample-yaml-api")

    operation = adapter.resolve_symbols([SymbolRef(name="operation", expected_type="action")])[0]
    actor = adapter.resolve_symbols([SymbolRef(name="actor")])[0]

    assert operation.status == "resolved"
    assert operation.symbols[0].metadata["path"] == "/operation"
    assert actor.status == "resolved"
    assert actor.symbols[0].name == "bearerAuth"


def test_openapi_adapter_resolves_actor_and_state_transition_symbols() -> None:
    adapter = OpenApiAdapter(FIXTURE_DOCUMENT, document_name="sample-api")

    results = adapter.resolve_symbols(
        [
            SymbolRef(name="operation", expected_type="action"),
            SymbolRef(name="actor"),
            SymbolRef(name="state_change"),
        ]
    )

    assert [result.status for result in results] == ["resolved", "resolved", "resolved"]
    assert results[0].symbols[0].symbol_type == "action"
    assert results[1].symbols[0].name == "bearerAuth"
    assert results[1].symbols[0].symbol_type == "principal"
    assert results[2].symbols[0].symbol_type == "state_transition"


def test_openapi_adapter_reports_ambiguous_operation_ids() -> None:
    adapter = OpenApiAdapter(FIXTURE_DOCUMENT, document_name="sample-api")

    result = adapter.resolve_symbols([SymbolRef(name="duplicate_operation", expected_type="action")])[0]

    assert result.status == "ambiguous"
    assert [symbol.metadata["path"] for symbol in result.symbols] == [
        "/duplicates/a",
        "/duplicates/b",
    ]


def test_openapi_adapter_validates_binding_against_document() -> None:
    adapter = OpenApiAdapter(FIXTURE_DOCUMENT, document_name="sample-api")

    valid = adapter.validate_binding(
        SymbolBinding(
            adapter="openapi",
            symbol="operation",
            symbol_type="action",
            confidence="adapter_resolved",
        )
    )
    wrong_type = adapter.validate_binding(
        SymbolBinding(
            adapter="openapi",
            symbol="operation",
            symbol_type="schema",
            confidence="adapter_resolved",
        )
    )

    assert valid.valid is True
    assert wrong_type.valid is False
    assert wrong_type.reason == "binding type mismatch: expected schema, found action"


def test_openapi_adapter_reports_conservative_evidence_capabilities() -> None:
    adapter = OpenApiAdapter(FIXTURE_DOCUMENT, document_name="sample-api")
    symbol = adapter.resolve_symbols([SymbolRef(name="operation", expected_type="action")])[0].symbols[0]

    capabilities = adapter.available_evidence([symbol])

    assert [cap.evidence_level for cap in capabilities] == [
        EvidenceLevel.STATICALLY_RESOLVED,
        EvidenceLevel.TYPE_CHECKED,
    ]


def test_openapi_adapter_generates_auth_rejection_task_for_bound_ir() -> None:
    adapter = OpenApiAdapter(FIXTURE_DOCUMENT, document_name="sample-api")
    ir = RequirementParser().parse_ir(
        "For every operation request:\n"
        "if actor is not authorized\n"
        "then operation must be rejected before state_change.\n",
        requirement_id="REQ-OPENAPI-001",
        title="Unauthorized OpenAPI operation is rejected",
        claim_kind="authorization_precondition",
    )
    diagnostics = bind_ir_with_diagnostics(ir, adapter)

    tasks = adapter.generate_tasks(diagnostics.bound_ir)

    assert diagnostics.missing_symbols == []
    assert diagnostics.ambiguous_symbols == []
    assert sorted(diagnostics.bound_ir.bindings) == ["actor", "operation", "state_change"]
    assert [task.id for task in tasks] == ["OPENAPI-SYMBOLS", "OPENAPI-AUTH-REJECTION"]
    assert tasks[0].payload["bindings"] == [
        {
            "requirement_ref": "actor",
            "symbol": "bearerAuth",
            "symbol_type": "principal",
        },
        {
            "requirement_ref": "operation",
            "symbol": "operation",
            "symbol_type": "action",
        },
        {
            "requirement_ref": "state_change",
            "symbol": "state_change",
            "symbol_type": "state_transition",
        },
    ]
    assert tasks[1].payload["task"] == "auth_rejection"
    assert tasks[1].payload["document_hash"].startswith("sha256:")


def test_openapi_adapter_runs_auth_rejection_task() -> None:
    adapter = OpenApiAdapter(FIXTURE_DOCUMENT, document_name="sample-api")
    ir = RequirementParser().parse_ir(
        "For every operation request:\n"
        "if actor is not authorized\n"
        "then operation must be rejected before state_change.\n",
        requirement_id="REQ-OPENAPI-001",
        title="Unauthorized OpenAPI operation is rejected",
        claim_kind="authorization_precondition",
    )
    diagnostics = bind_ir_with_diagnostics(ir, adapter)

    result = adapter.run_task(adapter.generate_tasks(diagnostics.bound_ir)[1])

    assert result.backend == "openapi"
    assert result.status == "valid"
    assert result.evidence_level == EvidenceLevel.STATICALLY_RESOLVED
    assert result.details["rejection_responses"] == ["401", "403"]
    assert result.details["security_schemes"] == ["bearerAuth"]


def test_openapi_adapter_generates_and_runs_success_response_task() -> None:
    adapter = OpenApiAdapter(FIXTURE_DOCUMENT, document_name="sample-api")
    ir = RequirementParser().parse_ir(
        "For every operation request:\n"
        "if actor is approved\n"
        "then operation must succeed.\n",
        requirement_id="REQ-OPENAPI-SUCCESS-001",
        title="Approved OpenAPI operation succeeds",
        claim_kind="state_precondition",
    )
    diagnostics = bind_ir_with_diagnostics(ir, adapter)

    tasks = adapter.generate_tasks(diagnostics.bound_ir)
    result = adapter.run_task(tasks[1])

    assert [task.id for task in tasks] == ["OPENAPI-SYMBOLS", "OPENAPI-SUCCESS-RESPONSE"]
    assert result.status == "valid"
    assert result.evidence_level == EvidenceLevel.STATICALLY_RESOLVED
    assert result.details["success_responses"] == ["200"]


def test_openapi_adapter_collects_backend_results() -> None:
    adapter = OpenApiAdapter(FIXTURE_DOCUMENT, document_name="sample-api")

    results = adapter.collect_evidence(
        [
            {
                "backend": "openapi",
                "status": "valid",
                "evidence_level": "STATICALLY_RESOLVED",
                "details": {"task_id": "OPENAPI-AUTH-REJECTION"},
            }
        ]
    )

    assert results == [
        BackendResult(
            backend="openapi",
            status="valid",
            evidence_level=EvidenceLevel.STATICALLY_RESOLVED,
            details={"task_id": "OPENAPI-AUTH-REJECTION"},
        )
    ]


def test_openapi_adapter_passes_conformance_suite() -> None:
    adapter = OpenApiAdapter(FIXTURE_DOCUMENT, document_name="sample-api")
    ir = RequirementParser().parse_ir(
        "For every operation request:\n"
        "if actor is not authorized\n"
        "then operation must be rejected before state_change.\n",
        requirement_id="REQ-OPENAPI-CONFORMANCE-001",
        title="OpenAPI adapter conformance",
        claim_kind="authorization_precondition",
    )

    report = assert_adapter_conforms(
        adapter,
        AdapterConformanceFixture(
            resolved_ref=SymbolRef(name="operation", expected_type="action"),
            unresolved_ref=SymbolRef(name="definitely_missing_symbol"),
            ambiguous_ref=SymbolRef(name="duplicate_operation", expected_type="action"),
            sample_ir=ir,
        ),
    )

    assert report.adapter_id == "openapi"
    assert report.target_kind == "openapi_document"


def test_openapi_conformance_cli(capsys) -> None:
    exit_code = main(
        [
            "openapi-conformance",
            str(FIXTURE_DOCUMENT),
            "--openapi-name",
            "sample-api",
        ]
    )

    output = capsys.readouterr().out

    assert exit_code == 0
    assert "Adapter: openapi" in output
    assert "Document: sample-api" in output
    assert "Conformance: passed" in output
