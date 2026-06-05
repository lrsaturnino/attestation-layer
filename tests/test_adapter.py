import typing
from pathlib import Path

import pytest

from nlreq.adapter import (
    GenericAdapter,
    _EXPECTED_KIND_NODE_KIND,
    _PREDICATE_OP_NODE_KIND,
    _UNSUPPORTED_PREMISE_BACKEND,
    _generic_premise_backend,
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


def test_generate_tasks_routes_opaque_v1_membership_to_unsupported() -> None:
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
    # The node kind IS membership, but the v1 grammar admits only the opaque ``value is in value`` form,
    # so ``allowed_states`` is an OPAQUE named set, not a concrete set literal. cvc5 discharges only a
    # concrete set-literal membership (``x is in {A, B}``, v3-only), so no wired backend can discharge
    # this premise: the plan emits it OPEN with the ``unsupported`` sentinel rather than naming a cvc5
    # route that would decline every time. (A concrete set-literal membership reaching cvc5 is covered
    # at the cvc5 surface by ``test_cvc5_discharges_concrete_set_literal_membership``.)
    assert premise.payload["node_kind"] == "membership"
    assert premise.backend == _UNSUPPORTED_PREMISE_BACKEND


def _comparison_ir(args: list[ValueRef]) -> RequirementIR:
    # A numeric_invariant requirement whose single premise compares ``args``. The op and source span are
    # held fixed so the only thing that can move the premise task's hash is the operands themselves.
    return RequirementIR(
        requirement_id="REQ-OPERAND-HASH-001",
        title="Operand hashing",
        source=RequirementSource(controlled_text="controlled requirement"),
        claim=Claim(
            kind="numeric_invariant",
            action="operation",
            forall=[],
            condition=[Predicate(op="lte", args=args, source_span=_span("counter is at most limit"))],
            expected=ExpectedResult(
                kind="increase",
                target="counter",
                value=ValueRef(kind="number", value=1),
                source_span=_span("increase counter by 1"),
            ),
        ),
    )


def _set_obligation_ir(*, target: str, value: ValueRef) -> RequirementIR:
    # A state_postcondition whose obligation is ``set <target> to <value>``. The expected kind and source
    # span are held fixed so the only thing that can move the obligation task's hash is target/value.
    return RequirementIR(
        requirement_id="REQ-OBLIGATION-HASH-001",
        title="Obligation hashing",
        source=RequirementSource(controlled_text="controlled requirement"),
        claim=Claim(
            kind="state_postcondition",
            action="operation",
            forall=[],
            condition=[],
            expected=ExpectedResult(kind="set", target=target, value=value, source_span=_span("set status")),
        ),
    )


def test_per_premise_task_input_hash_binds_operands() -> None:
    adapter = default_generic_adapter()
    base_args = [ValueRef(kind="identifier", value="counter"), ValueRef(kind="identifier", value="limit")]
    changed_args = [ValueRef(kind="identifier", value="counter"), ValueRef(kind="identifier", value="other")]

    base = next(t for t in adapter.generate_tasks(_comparison_ir(base_args)) if t.id == "P1")
    changed = next(t for t in adapter.generate_tasks(_comparison_ir(changed_args)) if t.id == "P1")
    repeat = next(t for t in adapter.generate_tasks(_comparison_ir(base_args)) if t.id == "P1")

    # The payload carries the operands themselves, so the task is a self-contained backend input — not a
    # route that forces the backend to re-read requirement.ir.json to recover the operands.
    assert base.payload["args"] == [
        {"kind": "identifier", "value": "counter"},
        {"kind": "identifier", "value": "limit"},
    ]
    # Only the second operand changed (limit -> other); op and source span are byte-identical, so a
    # differing input_hash can only come from the operands being bound into the task identity.
    assert base.payload["op"] == changed.payload["op"]
    assert base.payload["source_span"] == changed.payload["source_span"]
    assert base.input_hash != changed.input_hash
    # Identical content hashes identically — the task identity is deterministic, not incidental.
    assert base.input_hash == repeat.input_hash


def test_obligation_task_input_hash_binds_target_and_value() -> None:
    adapter = default_generic_adapter()
    accepted = ValueRef(kind="string", value="accepted")
    rejected = ValueRef(kind="string", value="rejected")

    base = next(t for t in adapter.generate_tasks(_set_obligation_ir(target="operation_status", value=accepted)) if t.id == "O1")
    other_target = next(t for t in adapter.generate_tasks(_set_obligation_ir(target="other_status", value=accepted)) if t.id == "O1")
    other_value = next(t for t in adapter.generate_tasks(_set_obligation_ir(target="operation_status", value=rejected)) if t.id == "O1")
    repeat = next(t for t in adapter.generate_tasks(_set_obligation_ir(target="operation_status", value=accepted)) if t.id == "O1")

    # The obligation's effect lives in the payload (action it constrains, the target it writes, the value
    # it writes), so a backend has the whole obligation without re-parsing the requirement.
    assert base.payload["action"] == "operation"
    assert base.payload["target"] == "operation_status"
    assert base.payload["value"] == {"kind": "string", "value": "accepted"}
    # Expected kind and source span are identical across all four; only target or value varies, so a
    # differing input_hash proves both are bound into the obligation task's identity.
    assert base.payload["expected_kind"] == other_target.payload["expected_kind"] == other_value.payload["expected_kind"]
    assert base.payload["source_span"] == other_target.payload["source_span"] == other_value.payload["source_span"]
    assert base.input_hash != other_target.input_hash
    assert base.input_hash != other_value.input_hash
    assert base.input_hash == repeat.input_hash


def test_obligation_payload_omits_absent_target_and_value() -> None:
    # ``succeed`` defines neither target nor value; the payload mirrors the source model's optional
    # fields and omits them rather than emitting nulls, so the stored task round-trips byte-for-byte.
    adapter = default_generic_adapter()
    ir = RequirementIR(
        requirement_id="REQ-OBLIGATION-OMIT-001",
        title="Obligation omits absent fields",
        source=RequirementSource(controlled_text="controlled requirement"),
        claim=Claim(
            kind="authorization_precondition",
            action="operation",
            forall=[],
            condition=[],
            expected=ExpectedResult(kind="succeed", source_span=_span("succeed")),
        ),
    )

    o1 = next(t for t in adapter.generate_tasks(ir) if t.id == "O1")

    assert "target" not in o1.payload
    assert "value" not in o1.payload
    # Action and source span are always present — they are defined for every obligation kind.
    assert o1.payload["action"] == "operation"
    assert "source_span" in o1.payload


def test_generate_tasks_only_emits_dischargeable_backends_or_the_open_sentinel() -> None:
    # Every backend the generic adapter stamps is either a real output of the per-premise router (a
    # producer that could discharge it) OR the explicit ``unsupported`` open sentinel for a premise no
    # wired backend discharges as the v1 grammar produces it (an opaque membership). Exercised over
    # every v1 predicate op and expected-result kind, not just the committed fixtures.
    router_backends = {
        backend_for_proof_node(role, node_kind)
        for role in ("premise", "obligation")
        for node_kind in (*_PREDICATE_OP_NODE_KIND.values(), *_EXPECTED_KIND_NODE_KIND.values())
    }
    assert router_backends <= _VERIFICATION_TASK_BACKENDS

    emitted_premise_backends = {
        _generic_premise_backend(node_kind) for node_kind in _PREDICATE_OP_NODE_KIND.values()
    }
    assert emitted_premise_backends <= _VERIFICATION_TASK_BACKENDS
    # The only backend the adapter emits that the router does NOT is the open sentinel — every other
    # emitted backend is a discharging router output. This pins the override to exactly the open kinds.
    assert _UNSUPPORTED_PREMISE_BACKEND in _VERIFICATION_TASK_BACKENDS
    assert emitted_premise_backends - router_backends == {_UNSUPPORTED_PREMISE_BACKEND}


def test_predicate_op_map_covers_every_op_and_routes_theories_and_membership() -> None:
    op_literals = set(typing.get_args(Predicate.model_fields["op"].annotation))
    assert set(_PREDICATE_OP_NODE_KIND) == op_literals

    # ``routed`` is the KIND-ONLY router's decision per op — the shared ``backend_for_proof_node``
    # policy, which maps ``membership`` -> cvc5 for the v2 dispatch path. The generic v1 adapter then
    # OVERRIDES the membership case (see the emitted-task assertions below and
    # ``test_generate_tasks_routes_opaque_v1_membership_to_unsupported``), so ``routed["in"] == "cvc5"``
    # describes the router, NOT the task the generic adapter emits.
    routed = {op: backend_for_proof_node("premise", _node_kind_for_predicate_op(op)) for op in op_literals}
    assert routed["lte"] == "smt-theories"
    assert routed["in"] == "cvc5"
    assert routed["not_authorized"] == "core_smt"

    # The override the generic adapter applies on top of that router: an opaque v1 membership is
    # emitted OPEN (never a cvc5 task), while a comparison still routes to its theory backend.
    assert _generic_premise_backend(_node_kind_for_predicate_op("in")) == _UNSUPPORTED_PREMISE_BACKEND
    assert _generic_premise_backend(_node_kind_for_predicate_op("lte")) == "smt-theories"


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
