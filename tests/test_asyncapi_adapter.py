from pathlib import Path

from nlreq.asyncapi_adapter import AsyncApiAdapter
from nlreq.bindings import bind_ir_with_diagnostics
from nlreq.models import EvidenceLevel, SymbolBinding, SymbolRef
from nlreq.parser import RequirementParser


DOCUMENT = Path(__file__).parent / "fixtures" / "adapters" / "asyncapi" / "sample-asyncapi.json"


def test_asyncapi_adapter_resolves_operations_messages_channels_and_principals() -> None:
    adapter = AsyncApiAdapter(DOCUMENT, document_name="sample-event-api")

    results = adapter.resolve_symbols(
        [
            SymbolRef(name="operation", expected_type="action"),
            SymbolRef(name="actor"),
            SymbolRef(name="operation_accepted"),
            SymbolRef(name="operation-events"),
        ]
    )

    assert [result.status for result in results] == ["resolved", "resolved", "resolved", "resolved"]
    assert results[0].symbols[0].metadata["emits"] == ["operation_accepted"]
    assert results[1].symbols[0].symbol_type == "principal"
    assert results[2].symbols[0].symbol_type == "event"
    assert results[3].symbols[0].symbol_type == "channel"


def test_asyncapi_adapter_reports_ambiguous_actions() -> None:
    adapter = AsyncApiAdapter(DOCUMENT)

    result = adapter.resolve_symbols([SymbolRef(name="duplicate_operation", expected_type="action")])[0]

    assert result.status == "ambiguous"
    assert len(result.symbols) == 2


def test_asyncapi_adapter_validates_bindings_and_capabilities() -> None:
    adapter = AsyncApiAdapter(DOCUMENT)
    binding = SymbolBinding(
        adapter="asyncapi",
        symbol="operation",
        symbol_type="action",
        confidence="adapter_resolved",
    )

    assert adapter.validate_binding(binding).valid is True
    assert {
        capability.evidence_level for capability in adapter.available_evidence(adapter.symbols())
    } >= {EvidenceLevel.STATICALLY_RESOLVED, EvidenceLevel.TYPE_CHECKED}


def test_asyncapi_adapter_generates_and_runs_event_emission_task() -> None:
    adapter = AsyncApiAdapter(DOCUMENT, document_name="sample-event-api")
    ir = RequirementParser().parse_ir(
        "For every operation request:\n"
        "if actor is approved\n"
        "then operation must emit operation_accepted.\n",
        requirement_id="REQ-ASYNCAPI-001",
        title="Approved operation emits accepted event",
        claim_kind="event_state_correspondence",
    )
    diagnostics = bind_ir_with_diagnostics(ir, adapter)

    tasks = adapter.generate_tasks(diagnostics.bound_ir)
    result = adapter.run_task(tasks[1])

    assert diagnostics.missing_symbols == []
    assert diagnostics.ambiguous_symbols == []
    assert [task.id for task in tasks] == ["ASYNCAPI-SYMBOLS", "ASYNCAPI-EVENT-EMISSION"]
    assert result.status == "valid"
    assert result.evidence_level == EvidenceLevel.TYPE_CHECKED
    assert result.details["emitted_events"] == ["operation_accepted"]
