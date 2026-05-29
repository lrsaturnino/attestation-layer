from pathlib import Path

from nlreq.bindings import bind_ir_with_diagnostics
from nlreq.models import EvidenceLevel, SymbolBinding, SymbolRef
from nlreq.parser import RequirementParser
from nlreq.protobuf_adapter import ProtobufAdapter


SCHEMA = Path(__file__).parent / "fixtures" / "adapters" / "protobuf" / "sample.proto"


def test_protobuf_adapter_resolves_rpcs_messages_fields_and_principals() -> None:
    adapter = ProtobufAdapter(SCHEMA, schema_name="sample-protobuf")

    results = adapter.resolve_symbols(
        [
            SymbolRef(name="operation", expected_type="action"),
            SymbolRef(name="actor"),
            SymbolRef(name="state_change"),
            SymbolRef(name="OperationRequest", expected_type="message"),
            SymbolRef(name="OperationResponse", expected_type="message"),
            SymbolRef(name="OperationResponse.operation_status"),
        ]
    )

    assert [result.status for result in results] == [
        "resolved",
        "resolved",
        "resolved",
        "resolved",
        "resolved",
        "resolved",
    ]
    assert results[0].symbols[0].metadata["request_type"] == "OperationRequest"
    assert results[1].symbols[0].symbol_type == "principal"
    assert results[2].symbols[0].symbol_type == "state_transition"
    assert results[5].symbols[0].symbol_type == "state"


def test_protobuf_adapter_reports_ambiguous_actions() -> None:
    adapter = ProtobufAdapter(SCHEMA)

    result = adapter.resolve_symbols([SymbolRef(name="duplicate_operation", expected_type="action")])[0]

    assert result.status == "ambiguous"
    assert len(result.symbols) == 2


def test_protobuf_adapter_validates_bindings_and_capabilities() -> None:
    adapter = ProtobufAdapter(SCHEMA)
    binding = SymbolBinding(
        adapter="protobuf",
        symbol="operation",
        symbol_type="action",
        confidence="adapter_resolved",
    )

    assert adapter.validate_binding(binding).valid is True
    assert {
        capability.evidence_level for capability in adapter.available_evidence(adapter.symbols())
    } >= {EvidenceLevel.STATICALLY_RESOLVED, EvidenceLevel.TYPE_CHECKED}


def test_protobuf_adapter_generates_and_runs_auth_rejection_task() -> None:
    adapter = ProtobufAdapter(SCHEMA, schema_name="sample-protobuf")
    ir = RequirementParser().parse_ir(
        "For every operation request:\n"
        "if actor is not authorized\n"
        "then operation must be rejected before state_change.\n",
        requirement_id="REQ-PROTOBUF-001",
        title="Unauthorized gRPC operation is rejected before state changes",
        claim_kind="authorization_precondition",
    )
    diagnostics = bind_ir_with_diagnostics(ir, adapter)

    tasks = adapter.generate_tasks(diagnostics.bound_ir)
    result = adapter.run_task(tasks[1])

    assert diagnostics.missing_symbols == []
    assert diagnostics.ambiguous_symbols == []
    assert [task.id for task in tasks] == ["PROTOBUF-SYMBOLS", "PROTOBUF-AUTH-REJECTION"]
    assert result.status == "valid"
    assert result.evidence_level == EvidenceLevel.STATICALLY_RESOLVED
    assert result.details["auth_options"] == ["nlreq.auth_required"]
    assert result.details["state_transition_symbol"] == "state_change"


def test_protobuf_adapter_requires_rpc_level_reviewed_auth_options(tmp_path: Path) -> None:
    schema = tmp_path / "service-option-only.proto"
    schema.write_text(
        'syntax = "proto3";\n'
        'option (nlreq.actor) = "actor";\n'
        "message OperationRequest { string actor_id = 1; }\n"
        "message OperationResponse { string operation_status = 1; }\n"
        "service OperationService {\n"
        "  option (nlreq.auth_required) = true;\n"
        '  option (nlreq.rejects_unauthorized_before) = "state_change";\n'
        "  rpc operation (OperationRequest) returns (OperationResponse);\n"
        "}\n"
    )
    adapter = ProtobufAdapter(schema, schema_name="service-option-only")
    ir = RequirementParser().parse_ir(
        "For every operation request:\n"
        "if actor is not authorized\n"
        "then operation must be rejected before state_change.\n",
        requirement_id="REQ-PROTOBUF-SERVICE-001",
        title="Service-level options are not RPC auth proof",
        claim_kind="authorization_precondition",
    )
    diagnostics = bind_ir_with_diagnostics(ir, adapter)

    tasks = adapter.generate_tasks(diagnostics.bound_ir)
    result = adapter.run_task(tasks[1])

    assert diagnostics.missing_symbols == ["state_change"]
    assert result.status == "invalid"
    assert "RPC does not declare a reviewed auth option" in result.details["problems"]


def test_protobuf_adapter_generates_and_runs_success_response_task() -> None:
    adapter = ProtobufAdapter(SCHEMA, schema_name="sample-protobuf")
    ir = RequirementParser().parse_ir(
        "For every operation request:\n"
        "if actor is approved\n"
        "then operation must succeed.\n",
        requirement_id="REQ-PROTOBUF-002",
        title="Approved gRPC operation succeeds",
        claim_kind="state_precondition",
    )
    diagnostics = bind_ir_with_diagnostics(ir, adapter)

    tasks = adapter.generate_tasks(diagnostics.bound_ir)
    result = adapter.run_task(tasks[1])

    assert diagnostics.missing_symbols == []
    assert diagnostics.ambiguous_symbols == []
    assert [task.id for task in tasks] == ["PROTOBUF-SYMBOLS", "PROTOBUF-SUCCESS-RESPONSE"]
    assert result.status == "valid"
    assert result.evidence_level == EvidenceLevel.STATICALLY_RESOLVED
    assert result.details["response_type"] == "OperationResponse"
