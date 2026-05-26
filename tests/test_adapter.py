from nlreq.adapter import GenericAdapter, default_generic_adapter
from nlreq.bindings import bind_ir, bind_ir_with_diagnostics
from nlreq.conformance import AdapterConformanceFixture, assert_adapter_conforms
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


def test_generic_adapter_reports_ambiguous_symbol() -> None:
    adapter = default_generic_adapter()

    result = adapter.resolve_symbols([SymbolRef(name="ambiguous_operation", expected_type="action")])[0]

    assert result.status == "ambiguous"
    assert [symbol.name for symbol in result.symbols] == [
        "ambiguous_operation_v1",
        "ambiguous_operation_v2",
    ]


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


def test_bind_ir_reports_ambiguous_symbols_separately() -> None:
    ir = RequirementParser().parse_ir(
        "For every operation request:\nif ambiguous_actor is not authorized\nthen operation must be rejected before state_change.\n",
        requirement_id="REQ-AMBIGUOUS-001",
        title="Ambiguous actor",
        claim_kind="authorization_precondition",
    )

    diagnostics = bind_ir_with_diagnostics(ir, default_generic_adapter())

    assert diagnostics.missing_symbols == []
    assert diagnostics.ambiguous_symbols == ["ambiguous_actor"]
    assert sorted(diagnostics.bound_ir.bindings) == ["operation", "state_change"]


def test_generic_adapter_passes_conformance_suite() -> None:
    adapter = default_generic_adapter()
    ir = RequirementParser().parse_ir(
        "For every operation request:\nif actor is not authorized\nthen operation must be rejected before state_change.\n",
        requirement_id="REQ-CONFORMANCE-001",
        title="Conformance",
        claim_kind="authorization_precondition",
    )

    report = assert_adapter_conforms(
        adapter,
        AdapterConformanceFixture(
            resolved_ref=SymbolRef(name="operation", expected_type="action"),
            unresolved_ref=SymbolRef(name="definitely_missing_symbol"),
            ambiguous_ref=SymbolRef(name="ambiguous_operation", expected_type="action"),
            sample_ir=ir,
        ),
    )

    assert report.adapter_id == "generic"
    assert "stable_resolution" in report.checks


def test_conformance_suite_rejects_adapter_without_ambiguity() -> None:
    adapter = GenericAdapter({"operation": {"type": "action"}})
    ir = RequirementParser().parse_ir(
        "For every operation request:\nif actor is not authorized\nthen operation must be rejected before state_change.\n",
        requirement_id="REQ-CONFORMANCE-FAIL-001",
        title="Conformance failure",
        claim_kind="authorization_precondition",
    )

    try:
        assert_adapter_conforms(
            adapter,
            AdapterConformanceFixture(
                resolved_ref=SymbolRef(name="operation", expected_type="action"),
                unresolved_ref=SymbolRef(name="definitely_missing_symbol"),
                ambiguous_ref=SymbolRef(name="ambiguous_operation", expected_type="action"),
                sample_ir=ir,
            ),
        )
    except AssertionError as exc:
        assert "ambiguous_operation must be reported as ambiguous" in str(exc)
    else:
        raise AssertionError("adapter without ambiguity support unexpectedly passed conformance")
