import json
from pathlib import Path

from nlreq.agnostic_wedge import build_agnostic_wedge_report
from nlreq.cli import main
from nlreq.coverage_alignment import SpecCoverageReport, TraceAlignmentReport
from nlreq.dsl_v2 import DslV2Parser
from nlreq.formal_backend import FormalBackendResponse
from nlreq.models import BackendResult, EvidenceLevel, RequirementIRV2
from nlreq.proof_closure import build_proof_dispatch_plan, build_proof_object
from nlreq.source_adapter import SourceManifest


DSL = (
    "For every redemption:\n"
    "when wallet is authorized\n"
    "then finalize_redemption must emit redemption_finalized within 6 hours.\n"
)


def test_agnostic_wedge_passes_for_closed_cross_language_proof() -> None:
    ir = _ir()
    proof = _closed_proof(ir)

    report = build_agnostic_wedge_report(
        proof=proof,
        source_manifests=[_manifest("python", "python-source"), _manifest("solidity", "solidity-source")],
        requirement=ir,
    )

    assert report.result == "passed"
    assert report.wedge_type == "cross_language"
    assert "cross-formalism backend diversity is not demonstrated" in report.limitations


def test_agnostic_wedge_passes_for_closed_cross_formalism_proof() -> None:
    ir = _ir()
    formal_responses = [
        FormalBackendResponse(
            backend_id="core_smt",
            target="smt",
            result=BackendResult(
                backend="core_smt",
                status="valid",
                evidence_level=EvidenceLevel.SMT_CHECKED,
            ),
        ),
        FormalBackendResponse(
            backend_id="tla",
            target="tla",
            result=BackendResult(
                backend="tla",
                status="valid",
                evidence_level=EvidenceLevel.BOUNDED_CHECKED,
                # A real bounded check carries its backing: recorded bounds, the checker
                # command, and a version recorded from the run. Without it the closure gate
                # rejects the BOUNDED_CHECKED claim as unbacked (PB-9).
                details={
                    "bounds": {"max_depth": 10},
                    "command": ["apalache-mc", "check", "Model.tla"],
                    "tool_version": "0.44.0",
                },
            ),
        ),
    ]
    proof = _closed_proof(ir, extra_backend_results=[response.result for response in formal_responses])

    report = build_agnostic_wedge_report(
        proof=proof,
        formal_responses=formal_responses,
        requirement=ir,
    )

    assert report.result == "passed"
    assert report.wedge_type == "cross_formalism"


def test_agnostic_wedge_blocks_single_axis_or_open_proof() -> None:
    ir = _ir()
    proof = _closed_proof(ir)

    single_axis = build_agnostic_wedge_report(
        proof=proof,
        source_manifests=[_manifest("python", "python-source")],
        requirement=ir,
    )
    open_proof = build_agnostic_wedge_report(
        proof=proof.model_copy(update={"status": "open"}),
        source_manifests=[_manifest("python", "python-source"), _manifest("solidity", "solidity-source")],
        requirement=ir,
    )

    assert single_axis.result == "blocked"
    assert single_axis.blockers[0].category == "insufficient_diversity"
    assert open_proof.result == "blocked"
    assert any(blocker.category == "proof_not_closed" for blocker in open_proof.blockers)


def test_agnostic_wedge_blocks_adapter_specific_semantic_ir_metadata() -> None:
    ir = _ir()
    data = ir.model_dump(mode="json", exclude_none=True)
    data["semantic_ir"]["metadata"] = {"language": "python"}
    contaminated = RequirementIRV2.model_validate(data)

    report = build_agnostic_wedge_report(
        proof=_closed_proof(ir),
        source_manifests=[_manifest("python", "python-source"), _manifest("solidity", "solidity-source")],
        requirement=contaminated,
    )

    assert report.result == "blocked"
    assert any(blocker.category == "ir_boundary" for blocker in report.blockers)


def test_agnostic_wedge_cli(tmp_path: Path, capsys) -> None:
    ir = _ir()
    proof = _closed_proof(ir)
    proof_path = tmp_path / "proof.json"
    ir_path = tmp_path / "requirement.ir.json"
    python_manifest = tmp_path / "python-manifest.json"
    solidity_manifest = tmp_path / "solidity-manifest.json"
    out = tmp_path / "wedge.json"
    proof_path.write_text(json.dumps(proof.model_dump(mode="json"), indent=2))
    ir_path.write_text(json.dumps(ir.model_dump(mode="json"), indent=2))
    python_manifest.write_text(json.dumps(_manifest("python", "python-source").model_dump(mode="json"), indent=2))
    solidity_manifest.write_text(
        json.dumps(_manifest("solidity", "solidity-source").model_dump(mode="json"), indent=2)
    )

    exit_code = main(
        [
            "agnostic-wedge",
            "--proof-object",
            str(proof_path),
            "--source-manifest",
            str(python_manifest),
            "--source-manifest",
            str(solidity_manifest),
            "--requirement-ir",
            str(ir_path),
            "--out",
            str(out),
        ]
    )

    output = capsys.readouterr().out

    assert exit_code == 0
    assert "Agnostic wedge report:" in output
    assert json.loads(out.read_text())["result"] == "passed"


def _ir() -> RequirementIRV2:
    return DslV2Parser().parse_ir(DSL, requirement_id="REQ-WEDGE-001", title="Agnostic wedge")


def _closed_proof(
    ir: RequirementIRV2,
    *,
    extra_backend_results: list[BackendResult] | None = None,
):
    # This wedge test isolates cross-language / cross-formalism closure, not premise routing, so
    # it requests the legacy single-backend dispatch explicitly to close on one system_checker
    # verdict. The closure default now routes by kind, where a lone verdict would not close.
    return build_proof_object(
        requirement=ir,
        backend_results=[
            BackendResult(
                backend="system_checker",
                status="valid",
                evidence_level=EvidenceLevel.CONSISTENCY_CHECKED,
            )
        ]
        + (extra_backend_results or []),
        coverage=SpecCoverageReport(
            result="passed",
            threshold=1.0,
            covered_modules=1,
            total_modules=1,
            coverage_ratio=1.0,
        ),
        trace_alignment=TraceAlignmentReport(result="passed"),
        dispatch=build_proof_dispatch_plan(ir, backend_id="system_checker"),
    )


def _manifest(language: str, adapter: str) -> SourceManifest:
    return SourceManifest.model_validate(
        {
            "schema_version": "0.1",
            "adapter": adapter,
            "language": language,
            "runtime": f"{language}-runtime",
            "modules": [
                {
                    "module_id": f"{language}:redemption",
                    "path": f"src/{language}/redemption",
                    "symbols": ["finalize_redemption"],
                }
            ],
        }
    )
