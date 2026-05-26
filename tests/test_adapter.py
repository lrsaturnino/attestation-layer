from nlreq.adapter import default_generic_adapter
from nlreq.bindings import bind_ir
from nlreq.models import EvidenceLevel, SymbolRef
from nlreq.parser import RequirementParser


def test_generic_adapter_resolves_stable_symbols() -> None:
    adapter = default_generic_adapter()
    refs = [SymbolRef(name="operation", expected_type="action"), SymbolRef(name="actor")]

    first = adapter.resolve_symbols(refs)
    second = adapter.resolve_symbols(refs)

    assert first == second
    assert [resolution.status for resolution in first] == ["resolved", "resolved"]
    assert first[0].symbols[0].symbol_type == "action"


def test_generic_adapter_reports_unresolved_symbol() -> None:
    adapter = default_generic_adapter()

    result = adapter.resolve_symbols([SymbolRef(name="missing")])[0]

    assert result.status == "unresolved"
    assert result.reason == "symbol not found"


def test_generic_adapter_only_reports_static_resolution_capability() -> None:
    adapter = default_generic_adapter()
    symbol = adapter.resolve_symbols([SymbolRef(name="operation")])[0].symbols[0]

    capabilities = adapter.available_evidence([symbol])

    assert [cap.evidence_level for cap in capabilities] == [EvidenceLevel.STATICALLY_RESOLVED]


def test_bind_ir_adds_bindings() -> None:
    ir = RequirementParser().parse_ir(
        "For every operation request:\nif actor is not authorized\nthen operation must be rejected before state_change.\n",
        requirement_id="REQ-AUTH-001",
        title="Auth",
        claim_kind="authorization_precondition",
    )

    bound, missing = bind_ir(ir, default_generic_adapter())

    assert missing == []
    assert sorted(bound.bindings) == ["actor", "operation", "state_change"]
