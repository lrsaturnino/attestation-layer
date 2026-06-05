import typing
from pathlib import Path

import pytest

from nlreq.adapter import (
    GenericAdapter,
    _EXPECTED_KIND_NODE_KIND,
    _PREDICATE_OP_NODE_KIND,
    _node_kind_for_expected_kind,
    _node_kind_for_predicate_op,
    default_generic_adapter,
)
from nlreq.bindings import bind_ir, bind_ir_with_diagnostics
from nlreq.compositional_ir import migrate_requirement_ir_v1_to_v2
from nlreq.conformance import AdapterConformanceFixture, assert_adapter_conforms
from nlreq.models import (
    Claim,
    EvidenceLevel,
    ExpectedResult,
    Predicate,
    RequirementIR,
    RequirementSource,
    SourceSpan,
    SymbolRef,
    ValueRef,
    VerificationTask,
)
from nlreq.parser import RequirementParser
from nlreq.proof_closure import backend_for_proof_node


FIXTURES = Path(__file__).parent / "fixtures" / "requirements"

# Every backend the generic adapter may stamp onto a VerificationTask, taken from the model's own
# Literal so this test set tracks the schema rather than a hand-copied list.
_VERIFICATION_TASK_BACKENDS = set(typing.get_args(VerificationTask.model_fields["backend"].annotation))


def _span(text: str) -> SourceSpan:
    return SourceSpan(document="controlled_requirement", start_char=0, end_char=len(text), text=text)


def _generic_tasks(fixture_name: str, *, requirement_id: str, claim_kind: str) -> list[VerificationTask]:
    adapter = default_generic_adapter()
    ir = RequirementParser().parse_ir(
        (FIXTURES / fixture_name).read_text(),
        requirement_id=requirement_id,
        title=requirement_id,
        claim_kind=claim_kind,
    )
    bound = bind_ir_with_diagnostics(ir, adapter).bound_ir
    return adapter.generate_tasks(bound)


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


def test_generate_tasks_emits_consistency_task_plus_one_per_premise_and_obligation() -> None:
    tasks = _generic_tasks(
        "authorization_precondition.nlreq",
        requirement_id="REQ-AUTH-001",
        claim_kind="authorization_precondition",
    )

    # C1 (whole-requirement consistency) + one task per condition premise + one obligation task.
    assert [task.id for task in tasks] == ["C1", "P1", "O1"]
    assert tasks[0].backend == "core_smt"
    assert tasks[-1].payload["role"] == "obligation"


def test_generate_tasks_routes_mixed_requirement_across_multiple_backends() -> None:
    # The per-premise regression on the package surface: a requirement whose premise and obligation need
    # different backends produces a verification plan with more than one backend, never a single
    # blanket core_smt task. state_postcondition: approved premise -> core_smt, set obligation ->
    # apalache (S ∧ R model check).
    tasks = _generic_tasks(
        "state_postcondition.nlreq",
        requirement_id="REQ-STATE-001",
        claim_kind="state_postcondition",
    )

    backends = {task.backend for task in tasks}
    assert backends == {"core_smt", "apalache"}
    assert backends != {"core_smt"}


def test_generate_tasks_routes_comparison_premise_to_smt_theories() -> None:
    tasks = _generic_tasks(
        "numeric_invariant.nlreq",
        requirement_id="REQ-NUM-001",
        claim_kind="numeric_invariant",
    )

    premise = next(task for task in tasks if task.payload.get("role") == "premise")
    assert premise.payload["op"] == "lte"
    assert premise.backend == "smt-theories"


def test_generate_tasks_routes_set_membership_premise_to_cvc5() -> None:
    adapter = default_generic_adapter()
    ir = RequirementParser().parse_ir(
        "For every operation request:\n"
        "if operation_status is in allowed_states\n"
        "then operation must be rejected before state_change.\n",
        requirement_id="REQ-MEMBER-001",
        title="Membership routing",
        claim_kind="authorization_precondition",
    )
    bound = bind_ir_with_diagnostics(ir, adapter).bound_ir

    tasks = adapter.generate_tasks(bound)

    premise = next(task for task in tasks if task.payload.get("role") == "premise")
    assert premise.payload["op"] == "in"
    # Set-literal membership routes to cvc5's native finite-set theory, never the linear-arithmetic
    # smt-theories backend that cannot encode a set literal.
    assert premise.backend == "cvc5"


def test_generate_tasks_only_emits_backends_the_proof_router_can_route() -> None:
    # Every backend the generic adapter stamps on a task must be a real output of the per-premise
    # router, so a task's named backend is always a producer that could discharge it. Exercised over
    # every v1 predicate op and expected-result kind, not just the committed fixtures.
    router_backends = {
        backend_for_proof_node(role, node_kind)
        for role in ("premise", "obligation")
        for node_kind in (*_PREDICATE_OP_NODE_KIND.values(), *_EXPECTED_KIND_NODE_KIND.values())
    }
    assert router_backends <= _VERIFICATION_TASK_BACKENDS


def test_predicate_op_map_covers_every_op_and_routes_theories_and_membership() -> None:
    op_literals = set(typing.get_args(Predicate.model_fields["op"].annotation))
    assert set(_PREDICATE_OP_NODE_KIND) == op_literals

    routed = {op: backend_for_proof_node("premise", _node_kind_for_predicate_op(op)) for op in op_literals}
    assert routed["lte"] == "smt-theories"
    assert routed["in"] == "cvc5"
    assert routed["not_authorized"] == "core_smt"


def test_obligation_node_kind_map_matches_v1_to_v2_migration() -> None:
    # The obligation map is pinned to the authoritative migration (compositional_ir._expected_node):
    # each expected kind must lower to the same proof-node kind a migrated requirement's
    # obligation.must would, so package routing and proof dispatch cannot silently diverge.
    kind_literals = set(typing.get_args(ExpectedResult.model_fields["kind"].annotation))
    assert set(_EXPECTED_KIND_NODE_KIND) == kind_literals

    targets = {
        "rejected": None,
        "succeed": None,
        "rejected_before": "state_change",
        "emit": "event_symbol",
        "not_change": "operation_status",
        "set": "operation_status",
        "increase": "counter",
        "decrease": "counter",
    }
    for kind in kind_literals:
        migrated, _record = migrate_requirement_ir_v1_to_v2(_ir_with_expected(kind, targets[kind]))
        assert _EXPECTED_KIND_NODE_KIND[kind] == migrated.semantic_ir.obligation.must.kind


def test_node_kind_maps_raise_on_unmapped_op_and_kind() -> None:
    with pytest.raises(ValueError, match="no proof-node routing for premise predicate op"):
        _node_kind_for_predicate_op("not_a_real_op")
    with pytest.raises(ValueError, match="no proof-node routing for obligation expected kind"):
        _node_kind_for_expected_kind("not_a_real_kind")


def _ir_with_expected(kind: str, target: str | None) -> RequirementIR:
    return RequirementIR(
        requirement_id="REQ-DRIFT-001",
        title="Drift",
        source=RequirementSource(controlled_text="controlled requirement"),
        claim=Claim(
            kind="state_postcondition",
            action="operation",
            forall=[],
            condition=[
                Predicate(
                    op="approved",
                    args=[ValueRef(kind="identifier", value="actor")],
                    source_span=_span("approved"),
                )
            ],
            expected=ExpectedResult(kind=kind, target=target, source_span=_span(kind)),
        ),
    )
