from pathlib import Path

from nlreq.graphql_adapter import GraphQlAdapter
from nlreq.models import EvidenceLevel, SymbolBinding, SymbolRef


SCHEMA = Path(__file__).parent / "fixtures" / "adapters" / "graphql" / "sample-schema.graphql"


def test_graphql_adapter_resolves_symbols_from_schema() -> None:
    adapter = GraphQlAdapter(SCHEMA, schema_name="sample-graphql")

    results = adapter.resolve_symbols(
        [
            SymbolRef(name="operation", expected_type="action"),
            SymbolRef(name="actor"),
            SymbolRef(name="state_change"),
        ]
    )

    assert [result.status for result in results] == ["resolved", "resolved", "resolved"]
    assert results[0].symbols[0].metadata["operation_type"] == "Mutation"
    assert results[1].symbols[0].symbol_type == "principal"
    assert results[2].symbols[0].symbol_type == "state_transition"


def test_graphql_adapter_reports_ambiguous_operations() -> None:
    adapter = GraphQlAdapter(SCHEMA)

    result = adapter.resolve_symbols([SymbolRef(name="duplicate_operation", expected_type="action")])[0]

    assert result.status == "ambiguous"
    assert len(result.symbols) == 2


def test_graphql_adapter_validates_bindings_and_capabilities() -> None:
    adapter = GraphQlAdapter(SCHEMA)
    binding = SymbolBinding(
        adapter="graphql",
        symbol="operation",
        symbol_type="action",
        confidence="adapter_resolved",
    )

    assert adapter.validate_binding(binding).valid is True
    assert {
        capability.evidence_level for capability in adapter.available_evidence(adapter.symbols())
    } >= {EvidenceLevel.STATICALLY_RESOLVED, EvidenceLevel.TYPE_CHECKED}
