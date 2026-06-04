import json
from pathlib import Path

import json
from pathlib import Path

from nlreq.cli import main
from nlreq.coverage_alignment import build_spec_coverage_report, build_trace_alignment_report
from nlreq.dsl_v2 import DslV2Parser
from nlreq.impact import ImpactAnalysisArtifact
from nlreq.models import BackendResult, EvidenceLevel, NormalizedTraceArtifact
from nlreq.proof_closure import (
    EvidenceProducer,
    EvidenceProducerMapping,
    ProofDispatchPlan,
    ProofPremiseRoute,
    backend_results_from_system_consistency,
    build_proof_dispatch_plan,
    build_proof_object,
    default_evidence_producer_mapping,
    evaluate_closure_gate,
)
from nlreq.system_checker import check_system_consistency_fixture
from nlreq.system_spec import SystemSpecRegistry
from nlreq.translator import lower_ir_v2_to_tla


DSL = (
    "For every redemption:\n"
    "when wallet is authorized\n"
    "and requested_amount <= spendable_balance\n"
    "then finalize_redemption must emit redemption_finalized within 6 hours.\n"
)


def test_proof_object_closes_when_all_context_and_premises_are_discharged(
    tmp_path: Path,
) -> None:
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

    proof = build_proof_object(
        requirement=ir,
        backend_results=backend_results_from_system_consistency(consistency),
        coverage=coverage,
        trace_alignment=alignment,
    )
    gate = evaluate_closure_gate(proof, downstream_action="merge")

    assert proof.status == "closed"
    assert {premise.status for premise in proof.premises} == {"discharged"}
    assert proof.coverage_result == "passed"
    assert proof.trace_alignment_result == "passed"
    assert gate.result == "passed"


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
            BackendResult(
                backend="drafting-tool",
                status="valid",
                evidence_level=EvidenceLevel.PROVEN_INDUCTIVE,
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
    assert json.loads(proof_path.read_text())["status"] == "closed"
    assert json.loads(gate_path.read_text())["result"] == "passed"


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
