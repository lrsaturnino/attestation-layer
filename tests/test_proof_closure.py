import json
from pathlib import Path

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from nlreq.cli import main
from nlreq.coverage_alignment import build_spec_coverage_report, build_trace_alignment_report
from nlreq.dsl_v2 import DslV2Parser
from nlreq.dsl_v3 import DslV3Parser
from nlreq.impact import ImpactAnalysisArtifact
from nlreq.models import BackendResult, EvidenceLevel, NormalizedTraceArtifact
from nlreq.proof_closure import (
    EvidenceProducer,
    EvidenceProducerMapping,
    ProofDispatchPlan,
    ProofPremiseRoute,
    backend_for_proof_node,
    backend_results_from_system_consistency,
    build_proof_dispatch_plan,
    build_proof_object,
    default_evidence_producer_mapping,
    evaluate_closure_gate,
)
from nlreq.system_checker import SystemConsistencyResult, check_system_consistency_fixture
from nlreq.system_spec import SystemSpecRegistry
from nlreq.translator import lower_ir_v2_to_tla


DSL = (
    "For every redemption:\n"
    "when wallet is authorized\n"
    "and requested_amount <= spendable_balance\n"
    "then finalize_redemption must emit redemption_finalized within 6 hours.\n"
)


def test_lone_system_checker_verdict_blocks_by_default_but_closes_under_explicit_single_backend(
    tmp_path: Path,
) -> None:
    """A lone system_checker verdict no longer closes a multi-premise proof by default.

    The closure default routes each premise to the backend its kind needs (route_by_kind), so a
    single system-consistency result — which routes to none of those per-kind backends —
    discharges nothing and the proof blocks with its premises open. The legacy single-backend
    plan, which closes on that one verdict, is still reachable but must be requested explicitly
    (it names backend_id), so a lone verdict can no longer silently over-close.
    """
    ir = _ir()
    coverage = _coverage(tmp_path)
    alignment = _alignment(ir, coverage)
    consistency = check_system_consistency_fixture(
        requirement=ir,
        lowered=lower_ir_v2_to_tla(ir),
        registry=_registry(tmp_path),
        impact=_impact(),
        project_root=tmp_path,
    )
    system_results = backend_results_from_system_consistency(consistency)

    # Default dispatch routes by kind: the lone system_checker verdict discharges none of the
    # per-kind routes, so the proof blocks with open premises and the closure gate blocks.
    blocked = build_proof_object(
        requirement=ir,
        backend_results=system_results,
        coverage=coverage,
        trace_alignment=alignment,
    )
    assert blocked.status == "blocked"
    assert any(premise.status != "discharged" for premise in blocked.premises)
    assert all(premise.routed_backend != "system_checker" for premise in blocked.premises)
    assert evaluate_closure_gate(blocked, downstream_action="merge").result == "blocked"

    # The explicitly-requested legacy single-backend plan still closes on that one verdict — the
    # happy path is preserved, just no longer the silent default.
    closed = build_proof_object(
        requirement=ir,
        backend_results=system_results,
        coverage=coverage,
        trace_alignment=alignment,
        dispatch=build_proof_dispatch_plan(ir, backend_id="system_checker"),
    )
    gate = evaluate_closure_gate(closed, downstream_action="merge")

    assert closed.status == "closed"
    assert {premise.status for premise in closed.premises} == {"discharged"}
    assert closed.coverage_result == "passed"
    assert closed.trace_alignment_result == "passed"
    assert gate.result == "passed"


def _consistency(tmp_path: Path):
    ir = _ir()
    return check_system_consistency_fixture(
        requirement=ir,
        lowered=lower_ir_v2_to_tla(ir),
        registry=_registry(tmp_path),
        impact=_impact(),
        project_root=tmp_path,
    )


def test_unbacked_bounded_evidence_cannot_enter_a_proof(tmp_path: Path) -> None:
    """An unbacked BOUNDED_CHECKED result cannot enter a proof, even built via model_construct.

    PB-9: real bounded backing is bounds *and* the checker command *and* a run-recorded tool
    version. The construction guard now rejects an unbacked bounded claim outright, so a genuine
    producer can never emit one. A result injected via model_construct (bypassing the BackendResult
    guard) with bounds alone -- no command, no version -- is re-validated when it is placed in a
    ProofObject, so build_proof_object raises rather than return a proof that holds unbacked
    bounded evidence. The premises here discharge on the system_checker floor, so the unbacked
    claim is the only thing that could carry the proof, and it cannot.
    """
    ir = _ir()
    coverage = _coverage(tmp_path)
    alignment = _alignment(ir, coverage)
    # Bounds alone is not real bounded backing. The BackendResult guard rejects this, so build it
    # via model_construct to get an unbacked result past construction and into build_proof_object.
    unbacked = BackendResult.model_construct(
        backend="apalache",
        status="valid",
        evidence_level=EvidenceLevel.BOUNDED_CHECKED,
        details={"bounds": {"max_depth": 5}},
    )

    # The construction guard now bars an unbacked bounded result from being held in a proof at
    # all: ProofObject re-validates its backend_results, so build_proof_object raises rather than
    # return a proof that smuggles in unbacked bounded evidence. The closure layer keeps the same
    # backing check as defense in depth (bounded_backing_problems, covered via
    # test_evidence_producers), but the type boundary now rejects the result before closure could.
    with pytest.raises(ValidationError, match="BOUNDED_CHECKED requires the full backing"):
        build_proof_object(
            requirement=ir,
            backend_results=[
                *backend_results_from_system_consistency(_consistency(tmp_path)),
                unbacked,
            ],
            coverage=coverage,
            trace_alignment=alignment,
        )


def test_backed_bounded_evidence_does_not_block_closure(tmp_path: Path) -> None:
    """The same BOUNDED_CHECKED result, carrying recorded bounds + command + a run-recorded
    version, is accepted — the contract gates on real backing, not on the checker's name."""
    ir = _ir()
    coverage = _coverage(tmp_path)
    alignment = _alignment(ir, coverage)
    backed = BackendResult(
        backend="apalache",
        status="valid",
        evidence_level=EvidenceLevel.BOUNDED_CHECKED,
        details={
            "bounds": {"max_depth": 6},
            "command": ["apalache-mc", "check", "Model.tla"],
            "reproducibility": {"tool_version": "0.58.0"},
        },
    )

    # This test isolates the backing check on a BOUNDED_CHECKED result, not premise routing, so it
    # closes on the legacy single-backend plan (requested explicitly) while the backed apalache
    # result coexists in backend_results without tripping a "not backed" blocker.
    proof = build_proof_object(
        requirement=ir,
        backend_results=[*backend_results_from_system_consistency(_consistency(tmp_path)), backed],
        coverage=coverage,
        trace_alignment=alignment,
        dispatch=build_proof_dispatch_plan(ir, backend_id="system_checker"),
    )

    assert proof.status == "closed"
    assert not any("not backed" in blocker.message for blocker in proof.blockers)


def test_proof_object_blocks_when_coverage_or_trace_alignment_blocks(
    tmp_path: Path,
) -> None:
    ir = _ir()
    coverage = build_spec_coverage_report(
        impact=ImpactAnalysisArtifact(
            adapter_id="python-source",
            language="python",
            input_symbols=["finalize_redemption"],
            affected_modules=["redemption", "wallet"],
        ),
        registry=_registry(tmp_path),
        project_root=tmp_path,
    )
    alignment = build_trace_alignment_report(
        requirement=ir,
        traces=NormalizedTraceArtifact.model_validate([_trace("TRACE-UNCOVERED", ["other_action"])]),
        coverage=coverage,
    )
    consistency = check_system_consistency_fixture(
        requirement=ir,
        lowered=lower_ir_v2_to_tla(ir),
        registry=_registry(tmp_path),
        impact=_impact(),
        project_root=tmp_path,
    )

    proof = build_proof_object(
        requirement=ir,
        backend_results=backend_results_from_system_consistency(consistency),
        coverage=coverage,
        trace_alignment=alignment,
    )
    gate = evaluate_closure_gate(proof)

    assert proof.status == "blocked"
    assert {blocker.category for blocker in proof.blockers} >= {"coverage", "trace_alignment"}
    assert gate.result == "blocked"


def test_proof_object_rejects_high_assurance_from_non_real_producer(
    tmp_path: Path,
) -> None:
    ir = _ir()
    mapping = EvidenceProducerMapping(
        producers=[
            EvidenceProducer(
                producer_id="drafting-tool",
                producer_kind="other",
                real_producer=False,
                allowed_evidence_levels=[EvidenceLevel.PROVEN_INDUCTIVE],
                tool="nlreq.drafting.placeholder",
            )
        ]
    )
    dispatch = build_proof_dispatch_plan(
        ir,
        backend_id="drafting-tool",
        required_evidence=EvidenceLevel.PROVEN_INDUCTIVE,
        policy_id="test-high-assurance",
    )

    proof = build_proof_object(
        requirement=ir,
        backend_results=[
            # Carries well-formed checked-proof + proof-assistant + command metadata (passes the
            # construction guard) but the producer is not a real one; the proof-closure producer
            # mapping must still reject the high-assurance claim (defense in depth beyond the
            # type-level construction guard).
            BackendResult(
                backend="drafting-tool",
                status="valid",
                evidence_level=EvidenceLevel.PROVEN_INDUCTIVE,
                details={
                    "proof_artifact_sha256": "sha256:" + "d" * 64,
                    "proof_assistant": "tlaps",
                    "command": ["tlapm", "Draft.tla"],
                },
            )
        ],
        coverage=_coverage(tmp_path),
        trace_alignment=_alignment(ir, _coverage(tmp_path)),
        producer_mapping=mapping,
        dispatch=dispatch,
    )

    assert proof.status == "blocked"
    assert any(
        blocker.category == "producer_mapping"
        and blocker.message == "high-assurance evidence requires a real producer"
        for blocker in proof.blockers
    )


def test_proof_object_and_closure_gate_cli(tmp_path: Path, capsys) -> None:
    ir = _ir()
    coverage = _coverage(tmp_path)
    alignment = _alignment(ir, coverage)
    consistency = check_system_consistency_fixture(
        requirement=ir,
        lowered=lower_ir_v2_to_tla(ir),
        registry=_registry(tmp_path),
        impact=_impact(),
        project_root=tmp_path,
    )
    ir_path = tmp_path / "requirement.ir.json"
    consistency_path = tmp_path / "system-consistency.json"
    coverage_path = tmp_path / "coverage.json"
    alignment_path = tmp_path / "alignment.json"
    proof_path = tmp_path / "proof.json"
    gate_path = tmp_path / "closure-gate.json"
    ir_path.write_text(json.dumps(ir.model_dump(mode="json"), indent=2))
    consistency_path.write_text(json.dumps(consistency.model_dump(mode="json"), indent=2))
    coverage_path.write_text(json.dumps(coverage.model_dump(mode="json"), indent=2))
    alignment_path.write_text(json.dumps(alignment.model_dump(mode="json"), indent=2))

    proof_exit = main(
        [
            "proof-object",
            "--requirement-ir",
            str(ir_path),
            "--system-consistency",
            str(consistency_path),
            "--spec-coverage",
            str(coverage_path),
            "--trace-alignment",
            str(alignment_path),
            "--out",
            str(proof_path),
        ]
    )
    gate_exit = main(
        [
            "closure-gate",
            str(proof_path),
            "--downstream-action",
            "merge",
            "--out",
            str(gate_path),
        ]
    )

    output = capsys.readouterr().out

    assert proof_exit == 0
    assert gate_exit == 0
    assert "Proof object:" in output
    assert "Closure gate report:" in output
    # The public proof-object command routes each premise to the backend that can discharge it
    # rather than collapsing every premise onto system_checker. The single fixture S ∧ R result
    # (backend system_checker) therefore discharges none of the routed premises, so the proof
    # blocks with them open — a lone S ∧ R verdict no longer over-closes a multi-premise
    # requirement whose comparison and predicate premises need their own producers.
    proof = json.loads(proof_path.read_text())
    assert proof["status"] == "blocked"
    open_premises = [premise for premise in proof["premises"] if premise["status"] != "discharged"]
    assert open_premises
    # The comparison premise (requested_amount <= spendable_balance) routes to smt-theories, and no
    # premise is left routed to the single system_checker verdict that previously closed them all.
    assert any(premise["routed_backend"] == "smt-theories" for premise in open_premises)
    assert all(premise["routed_backend"] != "system_checker" for premise in proof["premises"])
    assert json.loads(gate_path.read_text())["result"] == "blocked"


def test_proof_object_cli_routes_lowered_requirement_to_formal_claim_backends(
    tmp_path: Path,
) -> None:
    # A requirement that lowers to a FormalClaim drives the public proof-object command through the
    # authoritative per-fragment routing: its predicate and rejection-order premises route to
    # solver_system_checker (the S ∧ R producer), which the coarse kind-only router never selects.
    # A raw S ∧ R verdict that does not attribute itself to specific fragments (no
    # covered_fragment_ids — the coverage the gate synthesizes, which this low-level command does
    # not) therefore discharges none of them, so the proof blocks with the formal-claim premises
    # left open rather than over-closing on one verdict.
    fixture = (
        Path(__file__).parent
        / "fixtures"
        / "requirements"
        / "authorization_precondition_v3.nlreq"
    )
    ir = DslV3Parser().parse_ir(
        fixture.read_text(),
        requirement_id="AUTH-CLI-001",
        title="Authorization precondition",
    )
    consistency = SystemConsistencyResult(
        requirement_id="AUTH-CLI-001",
        spec_ids=["spec:authorization"],
        result=BackendResult(
            backend="solver_system_checker",
            status="valid",
            evidence_level=EvidenceLevel.BOUNDED_CHECKED,
            details={
                "bounds": {"length": 5},
                "command": "apalache-mc check",
                "tool_version": "0.44.0",
            },
        ),
    )
    ir_path = tmp_path / "req.ir.json"
    consistency_path = tmp_path / "system-consistency.json"
    proof_path = tmp_path / "proof.json"
    ir_path.write_text(json.dumps(ir.model_dump(mode="json"), indent=2))
    consistency_path.write_text(consistency.model_dump_json(indent=2))

    exit_code = main(
        [
            "proof-object",
            "--requirement-ir",
            str(ir_path),
            "--system-consistency",
            str(consistency_path),
            "--out",
            str(proof_path),
        ]
    )

    assert exit_code == 0
    proof = json.loads(proof_path.read_text())
    # The FormalClaim dispatch ran through the CLI: a premise routes to the S ∧ R producer, which
    # the coarse kind-only fallback (predicate -> core_smt) would never select.
    routed_backends = {premise["routed_backend"] for premise in proof["premises"]}
    assert "solver_system_checker" in routed_backends
    assert "system_checker" not in routed_backends
    # A non-attributed verdict discharges none of the routed fragments, so closure is honest.
    assert proof["status"] == "blocked"
    assert all(premise["status"] != "discharged" for premise in proof["premises"])


def test_backend_for_proof_node_routes_each_kind_to_its_discharging_backend() -> None:
    # The per-premise routing decision: each premise kind goes to the backend that can discharge it.
    assert backend_for_proof_node("premise", "predicate") == "core_smt"
    assert backend_for_proof_node("premise", "comparison") == "smt-theories"
    assert backend_for_proof_node("premise", "lte") == "smt-theories"
    # Set-membership routes to cvc5 (its native finite-set theory), matching the authoritative
    # FormalClaim routing — never to the linear-arithmetic smt-theories backend that cannot encode it.
    assert backend_for_proof_node("premise", "membership") == "cvc5"
    assert backend_for_proof_node("obligation", "invariant") == "apalache"
    assert backend_for_proof_node("obligation", "eventually") == "apalache"
    assert backend_for_proof_node("obligation", "trace_ref") == "trace_validation"
    # Unclassified / propositional structure falls back to the core SMT consistency checker.
    assert backend_for_proof_node("premise", "and") == "core_smt"


def test_dispatch_plan_route_by_kind_sends_premises_to_distinct_backends() -> None:
    ir = _ir()
    # The single-backend plan is a legacy, explicitly-requested construction (it requires naming
    # backend_id) that collapses every premise onto one backend. It is not the public proof-object
    # routing: that path routes each premise to the backend its kind needs (route_by_kind / the
    # FormalClaim dispatch), so a lone verdict cannot over-close a multi-backend requirement.
    legacy_single_backend_plan = build_proof_dispatch_plan(ir, backend_id="system_checker")
    routed_plan = build_proof_dispatch_plan(ir, route_by_kind=True)

    assert {route.backend_id for route in legacy_single_backend_plan.routes} == {"system_checker"}
    # Each route goes to the backend its kind needs, and the comparison premise
    # (requested_amount <= spendable_balance) routes somewhere other than the propositional default.
    for route in routed_plan.routes:
        assert route.backend_id == backend_for_proof_node(route.role, route.node_kind)
    assert {route.backend_id for route in routed_plan.routes} != {"system_checker"}


def _ir():
    return DslV2Parser().parse_ir(DSL, requirement_id="REQ-PROOF-001", title="Proof closure")


def _coverage(tmp_path: Path):
    return build_spec_coverage_report(
        impact=_impact(),
        registry=_registry(tmp_path),
        project_root=tmp_path,
    )


def _alignment(ir, coverage):
    return build_trace_alignment_report(
        requirement=ir,
        traces=NormalizedTraceArtifact.model_validate(
            [_trace("TRACE-ALIGNED", ["finalize_redemption"])]
        ),
        coverage=coverage,
    )


def _impact() -> ImpactAnalysisArtifact:
    return ImpactAnalysisArtifact(
        adapter_id="python-source",
        language="python",
        input_symbols=["finalize_redemption"],
        affected_modules=["redemption"],
    )


def _registry(tmp_path: Path) -> SystemSpecRegistry:
    specs = tmp_path / "specs"
    specs.mkdir(exist_ok=True)
    (specs / "Redemption.tla").write_text("---- MODULE Redemption ----\n====\n")
    return SystemSpecRegistry.model_validate(
        {
            "schema_version": "0.1",
            "specs": [
                {
                    "spec_id": "spec:redemption",
                    "module_ids": ["redemption"],
                    "formalism": "tla",
                    "path": "specs/Redemption.tla",
                    "version": "1",
                    "review_status": "reviewed",
                    "freshness": "fresh",
                }
            ],
        }
    )


def test_fragment_binding_result_with_covered_ids_does_not_discharge_other_routes() -> None:
    """A BackendResult that declares covered_fragment_ids must only discharge matching routes.

    Without this guard, a single backend success discharges every route on that backend,
    even if the result only covers one FormalClaim fragment.
    """
    ir = _ir()
    route_a = ProofPremiseRoute(
        premise_id="fragment.A",
        node_id="n1",
        node_kind="predicate",
        role="premise",
        backend_id="core_smt",
        required_evidence=EvidenceLevel.SMT_CHECKED,
        reason="route A",
    )
    route_b = ProofPremiseRoute(
        premise_id="fragment.B",
        node_id="n2",
        node_kind="comparison",
        role="obligation",
        backend_id="core_smt",
        required_evidence=EvidenceLevel.SMT_CHECKED,
        reason="route B",
    )
    dispatch = ProofDispatchPlan(policy_id="test-fragment-binding", routes=[route_a, route_b])

    # Result covers only fragment.A — fragment.B must remain open
    result_covers_a_only = BackendResult(
        backend="core_smt",
        status="valid",
        evidence_level=EvidenceLevel.SMT_CHECKED,
        details={"covered_fragment_ids": ["fragment.A"]},
    )
    proof = build_proof_object(
        requirement=ir,
        backend_results=[result_covers_a_only],
        dispatch=dispatch,
    )

    premise_by_id = {p.premise_id: p for p in proof.premises}
    assert premise_by_id["fragment.A"].status == "discharged"
    assert premise_by_id["fragment.B"].status == "open"


def test_fragment_binding_result_without_covered_ids_discharges_all_backend_routes() -> None:
    """A BackendResult without covered_fragment_ids uses backward-compatible backend-only matching."""
    ir = _ir()
    route_a = ProofPremiseRoute(
        premise_id="fragment.A",
        node_id="n1",
        node_kind="predicate",
        role="premise",
        backend_id="core_smt",
        required_evidence=EvidenceLevel.SMT_CHECKED,
        reason="route A",
    )
    route_b = ProofPremiseRoute(
        premise_id="fragment.B",
        node_id="n2",
        node_kind="comparison",
        role="obligation",
        backend_id="core_smt",
        required_evidence=EvidenceLevel.SMT_CHECKED,
        reason="route B",
    )
    dispatch = ProofDispatchPlan(policy_id="test-no-covered-ids", routes=[route_a, route_b])

    # No covered_fragment_ids — both routes match by backend
    result_no_fragment_ids = BackendResult(
        backend="core_smt",
        status="valid",
        evidence_level=EvidenceLevel.SMT_CHECKED,
        details={},
    )
    proof = build_proof_object(
        requirement=ir,
        backend_results=[result_no_fragment_ids],
        dispatch=dispatch,
    )

    premise_by_id = {p.premise_id: p for p in proof.premises}
    assert premise_by_id["fragment.A"].status == "discharged"
    assert premise_by_id["fragment.B"].status == "discharged"


def test_formal_claim_route_requires_covered_fragment_ids() -> None:
    """formal_claim routes stay open unless the result explicitly names the fragment ID.

    A BackendResult without covered_fragment_ids cannot discharge a formal_claim route —
    only results that carry covered_fragment_ids=[route.premise_id] match. This prevents
    a legacy system-consistency result from accidentally discharging a FormalClaim premise.
    """
    ir = _ir()
    route_fc = ProofPremiseRoute(
        premise_id="FC-fragment.PRED",
        node_id="n1",
        node_kind="predicate",
        role="premise",
        backend_id="core_smt",
        required_evidence=EvidenceLevel.SMT_CHECKED,
        reason="formal claim predicate",
        routing_mode="formal_claim",
    )
    dispatch = ProofDispatchPlan(policy_id="test-formal-claim-routing", routes=[route_fc])

    # Result without covered_fragment_ids — must NOT discharge a formal_claim route
    result_no_ids = BackendResult(
        backend="core_smt",
        status="valid",
        evidence_level=EvidenceLevel.SMT_CHECKED,
        details={},
    )
    proof_no_ids = build_proof_object(
        requirement=ir,
        backend_results=[result_no_ids],
        dispatch=dispatch,
    )
    assert proof_no_ids.premises[0].status == "open"

    # Result with covered_fragment_ids that matches — must discharge the route
    result_with_ids = BackendResult(
        backend="core_smt",
        status="valid",
        evidence_level=EvidenceLevel.SMT_CHECKED,
        details={"covered_fragment_ids": ["FC-fragment.PRED"]},
    )
    proof_with_ids = build_proof_object(
        requirement=ir,
        backend_results=[result_with_ids],
        dispatch=dispatch,
    )
    assert proof_with_ids.premises[0].status == "discharged"


def test_semantic_node_route_still_discharges_without_covered_ids() -> None:
    """semantic_node routes retain backward-compatible matching (no covered_fragment_ids needed)."""
    ir = _ir()
    route_sn = ProofPremiseRoute(
        premise_id="sn-premise",
        node_id="n1",
        node_kind="predicate",
        role="premise",
        backend_id="core_smt",
        required_evidence=EvidenceLevel.SMT_CHECKED,
        reason="semantic node route",
        routing_mode="semantic_node",
    )
    dispatch = ProofDispatchPlan(policy_id="test-semantic-node-routing", routes=[route_sn])

    result_no_ids = BackendResult(
        backend="core_smt",
        status="valid",
        evidence_level=EvidenceLevel.SMT_CHECKED,
        details={},
    )
    proof = build_proof_object(
        requirement=ir,
        backend_results=[result_no_ids],
        dispatch=dispatch,
    )
    assert proof.premises[0].status == "discharged"


def _trace(trace_id: str, actions: list[str]) -> dict[str, object]:
    return {
        "trace_id": trace_id,
        "adapter_id": "python-source",
        "source_hash": "sha256:source",
        "language": "python",
        "runtime": "cpython",
        "events": [
            {
                "event_id": f"{trace_id}-{index}",
                "timestamp": f"2026-06-01T00:00:0{index}Z",
                "action": action,
            }
            for index, action in enumerate(actions, start=1)
        ],
    }
