from pathlib import Path

from nlreq.bindings import bind_ir_with_diagnostics
from nlreq.jsonschema_adapter import JsonSchemaAdapter
from nlreq.models import EvidenceLevel, SymbolBinding, SymbolRef
from nlreq.parser import RequirementParser


SCHEMA = Path(__file__).parent / "fixtures" / "adapters" / "jsonschema" / "sample-schema.json"


def test_json_schema_adapter_resolves_actions_properties_and_principals() -> None:
    adapter = JsonSchemaAdapter(SCHEMA, schema_name="sample-json-schema")

    results = adapter.resolve_symbols(
        [
            SymbolRef(name="operation", expected_type="action"),
            SymbolRef(name="actor"),
            SymbolRef(name="operation_status"),
            SymbolRef(name="counter"),
        ]
    )

    assert [result.status for result in results] == ["resolved", "resolved", "resolved", "resolved"]
    assert results[0].symbols[0].metadata["sets"] == {"operation_status": "accepted"}
    assert results[1].symbols[0].symbol_type == "principal"
    assert results[2].symbols[0].symbol_type == "state"
    assert results[3].symbols[0].symbol_type == "quantity"


def test_json_schema_adapter_reports_ambiguous_actions() -> None:
    adapter = JsonSchemaAdapter(SCHEMA)

    result = adapter.resolve_symbols([SymbolRef(name="duplicate_operation", expected_type="action")])[0]

    assert result.status == "ambiguous"
    assert len(result.symbols) == 2


def test_json_schema_adapter_validates_bindings_and_capabilities() -> None:
    adapter = JsonSchemaAdapter(SCHEMA)
    binding = SymbolBinding(
        adapter="json_schema",
        symbol="operation",
        symbol_type="action",
        confidence="adapter_resolved",
    )

    assert adapter.validate_binding(binding).valid is True
    assert {
        capability.evidence_level for capability in adapter.available_evidence(adapter.symbols())
    } >= {EvidenceLevel.STATICALLY_RESOLVED, EvidenceLevel.TYPE_CHECKED}


def test_json_schema_adapter_generates_and_runs_state_value_task() -> None:
    adapter = JsonSchemaAdapter(SCHEMA, schema_name="sample-json-schema")
    ir = RequirementParser().parse_ir(
        "For every operation request:\n"
        "if actor is approved\n"
        'then operation must set operation_status to "accepted".\n',
        requirement_id="REQ-JSON-SCHEMA-STATE-001",
        title="Approved operation sets accepted status",
        claim_kind="state_postcondition",
    )
    diagnostics = bind_ir_with_diagnostics(ir, adapter)

    tasks = adapter.generate_tasks(diagnostics.bound_ir)
    result = adapter.run_task(tasks[1])

    assert diagnostics.missing_symbols == []
    assert diagnostics.ambiguous_symbols == []
    assert [task.id for task in tasks] == ["JSON-SCHEMA-SYMBOLS", "JSON-SCHEMA-STATE-VALUE"]
    assert result.status == "valid"
    assert result.evidence_level == EvidenceLevel.TYPE_CHECKED
    assert result.details["property_declares_value"] is True


def test_json_schema_adapter_generates_and_runs_numeric_delta_task() -> None:
    adapter = JsonSchemaAdapter(SCHEMA, schema_name="sample-json-schema")
    ir = RequirementParser().parse_ir(
        "For every operation request:\n"
        "if counter is at most limit\n"
        "then operation must increase counter by 1.\n",
        requirement_id="REQ-JSON-SCHEMA-NUM-001",
        title="Operation increases counter within limit",
        claim_kind="numeric_invariant",
    )
    diagnostics = bind_ir_with_diagnostics(ir, adapter)

    tasks = adapter.generate_tasks(diagnostics.bound_ir)
    result = adapter.run_task(tasks[1])

    assert diagnostics.missing_symbols == []
    assert diagnostics.ambiguous_symbols == []
    assert [task.id for task in tasks] == ["JSON-SCHEMA-SYMBOLS", "JSON-SCHEMA-NUMERIC-DELTA"]
    assert result.status == "valid"
    assert result.details["delta_kind"] == "increase"
