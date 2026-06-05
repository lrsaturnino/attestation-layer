import json
from pathlib import Path

from nlreq.backend_agreement import build_backend_agreement_report
from nlreq.cli import main
from nlreq.coverage_alignment import SpecCoverageReport, TraceAlignmentReport
from nlreq.dsl_v2 import DslV2Parser
from nlreq.formal_backend import FormalBackendResponse
from nlreq.jsonutil import read_json
from nlreq.models import BackendResult, EvidenceLevel
from nlreq.proof_closure import build_proof_object


DSL = (
    "For every redemption:\n"
    "when wallet is authorized\n"
    "then finalize_redemption must emit redemption_finalized within 6 hours.\n"
)


def test_backend_agreement_passes_matching_overlapping_results() -> None:
    report = build_backend_agreement_report(
        [
            _bounded_result("tla-runner"),
            _bounded_result("alloy-runner"),
        ]
    )

    assert report.status == "agreed"
    assert report.closure_effect == "allow"
    assert report.comparisons[0].status == "agreed"


def test_backend_agreement_blocks_status_and_bound_disagreement() -> None:
    report = build_backend_agreement_report(
        [
            _bounded_result("tla-runner", max_depth=8),
            _bounded_result("alloy-runner", status="counterexample", max_depth=6),
        ]
    )

    assert report.status == "disagreed"
    assert report.closure_effect == "block"
    assert report.comparisons[0].status == "disagreed"
    assert "status differs" in report.comparisons[0].reasons[0]
    assert "bounds differ" in report.comparisons[0].reasons


def test_backend_agreement_blocks_counterexample_disagreement() -> None:
    report = build_backend_agreement_report(
        [
            _bounded_result(
                "tla-runner",
                status="counterexample",
                counterexample={"state": "wallet_authorized"},
            ),
            _bounded_result(
                "alloy-runner",
                status="counterexample",
                counterexample={"state": "wallet_locked"},
            ),
        ]
    )

    assert report.status == "disagreed"
    assert "counterexamples differ" in report.comparisons[0].reasons


def test_backend_agreement_records_non_overlap_without_comparison() -> None:
    report = build_backend_agreement_report(
        [
            _bounded_result("tla-runner", overlap_key="bounded-safety"),
            _bounded_result("lean-runner", overlap_key="inductive-safety"),
        ],
        policy="report_only",
    )

    assert report.status == "non_overlap"
    assert report.closure_effect == "report_only"
    assert report.comparisons[0].status == "non_overlap"
    assert report.blockers == ["no backend result pair declared overlapping semantics"]


def test_backend_agreement_cli_writes_report_from_formal_responses(
    tmp_path: Path, capsys
) -> None:
    left = FormalBackendResponse(
        backend_id="tla-runner",
        target="tla",
        result=_bounded_result("tla-runner"),
    )
    right = FormalBackendResponse(
        backend_id="alloy-runner",
        target="alloy",
        result=_bounded_result("alloy-runner"),
    )
    left_path = tmp_path / "left.json"
    right_path = tmp_path / "right.json"
    out = tmp_path / "agreement.json"
    left_path.write_text(json.dumps(left.model_dump(mode="json"), indent=2))
    right_path.write_text(json.dumps(right.model_dump(mode="json"), indent=2))

    exit_code = main(
        [
            "backend-agreement",
            "--formal-backend-response",
            str(left_path),
            "--formal-backend-response",
            str(right_path),
            "--overlap-key",
            "bounded-safety",
            "--out",
            str(out),
        ]
    )

    output = capsys.readouterr().out

    assert exit_code == 0
    assert "Backend agreement report:" in output
    assert read_json(out)["status"] == "agreed"


def test_proof_object_blocks_supplied_backend_disagreement() -> None:
    ir = DslV2Parser().parse_ir(DSL, requirement_id="REQ-BACKEND-AGREE", title="Backend agree")
    disagreement = build_backend_agreement_report(
        [
            _bounded_result("tla-runner", status="valid"),
            _bounded_result("alloy-runner", status="counterexample"),
        ]
    )

    proof = build_proof_object(
        requirement=ir,
        backend_results=[
            BackendResult(
                backend="system_checker",
                status="valid",
                evidence_level=EvidenceLevel.CONSISTENCY_CHECKED,
            )
        ],
        coverage=SpecCoverageReport(
            result="passed",
            threshold=1.0,
            covered_modules=1,
            total_modules=1,
            coverage_ratio=1.0,
        ),
        trace_alignment=TraceAlignmentReport(result="passed"),
        backend_agreement=disagreement,
    )

    assert proof.status == "blocked"
    assert proof.backend_agreement is not None
    assert any(blocker.category == "backend_agreement" for blocker in proof.blockers)


def _bounded_result(
    backend: str,
    *,
    status: str = "valid",
    overlap_key: str = "bounded-safety",
    max_depth: int = 8,
    counterexample: dict[str, str] | None = None,
) -> BackendResult:
    details = {
        "overlap_key": overlap_key,
        "bounds": {"max_depth": max_depth},
        # A BOUNDED_CHECKED result carries its full run backing (bounds + command + a
        # run-recorded version); these are real backed results compared for agreement.
        "command": ["apalache-mc", "check", "Model.tla"],
        "tool_version": "apalache 0.58.0",
        "unsupported_constructs": [],
    }
    if counterexample is not None:
        details["counterexample"] = counterexample
    return BackendResult(
        backend=backend,
        status=status,  # type: ignore[arg-type]
        evidence_level=EvidenceLevel.BOUNDED_CHECKED,
        details=details,
    )
