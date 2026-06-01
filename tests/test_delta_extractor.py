from pathlib import Path

from nlreq.cli import main
from nlreq.coverage_alignment import ModuleCoverageStatus, SpecCoverageReport
from nlreq.delta_extractor import build_delta_report, delta_report_markdown
from nlreq.jsonutil import read_json
from nlreq.models import BackendResult
from nlreq.requirement_self_consistency import RequirementSelfConsistencyResult
from nlreq.spec_drift import SpecDriftReport, SpecDriftStatus
from nlreq.system_checker import SystemConsistencyResult
from nlreq.trace_replay import TraceReplayObservation, TraceReplayReport


def test_delta_extractor_collects_blocking_actions() -> None:
    report = build_delta_report(
        self_consistency=_self_consistency("contradiction"),
        system_consistency=_system_consistency("counterexample"),
        spec_coverage=_coverage(),
        trace_replay=_trace_replay("violating"),
        spec_drift=_drift(),
    )

    assert report.result == "changes_required"
    assert {delta.category for delta in report.deltas} == {"requirement", "spec", "code"}
    assert report.deltas[0].source == "requirement_self_consistency"
    assert any(delta.source == "spec_drift" for delta in report.deltas)


def test_delta_extractor_returns_no_changes_for_green_reports() -> None:
    report = build_delta_report(
        self_consistency=_self_consistency("valid"),
        system_consistency=_system_consistency("valid"),
        spec_coverage=_coverage(covered=True),
        trace_replay=_trace_replay("satisfied"),
        spec_drift=SpecDriftReport(result="passed", statuses=[]),
    )

    assert report.result == "no_changes"
    assert report.deltas == []


def test_delta_report_markdown_lists_required_actions() -> None:
    report = build_delta_report(spec_coverage=_coverage())

    markdown = delta_report_markdown(report)

    assert "# Delta Report" in markdown
    assert "`delta:spec:auth`" in markdown
    assert "add, review, or refresh" in markdown


def test_delta_extract_cli_writes_json_and_markdown(tmp_path: Path, capsys) -> None:
    coverage_path = tmp_path / "coverage.json"
    out = tmp_path / "delta.json"
    markdown_out = tmp_path / "delta.md"
    coverage_path.write_text(_coverage().model_dump_json())

    exit_code = main(
        [
            "delta-extract",
            "--spec-coverage",
            str(coverage_path),
            "--out",
            str(out),
            "--markdown-out",
            str(markdown_out),
        ]
    )

    output = capsys.readouterr().out

    assert exit_code == 0
    assert "Delta report:" in output
    assert read_json(out)["result"] == "changes_required"
    assert "# Delta Report" in markdown_out.read_text()


def _self_consistency(status: str) -> RequirementSelfConsistencyResult:
    return RequirementSelfConsistencyResult(
        requirement_id="REQ-DELTA-001",
        status=status,
        result=BackendResult(
            backend="requirement_self_consistency",
            status="valid" if status == "valid" else "invalid",
        ),
    )


def _system_consistency(status: str) -> SystemConsistencyResult:
    return SystemConsistencyResult(
        requirement_id="REQ-DELTA-001",
        result=BackendResult(
            backend="solver_system_checker",
            status=status,
        ),
        spec_ids=["spec:auth"],
    )


def _coverage(*, covered: bool = False) -> SpecCoverageReport:
    return SpecCoverageReport(
        result="passed" if covered else "blocked",
        threshold=1.0,
        covered_modules=1 if covered else 0,
        total_modules=1,
        coverage_ratio=1.0 if covered else 0.0,
        modules=[
            ModuleCoverageStatus(
                module_id="auth",
                status="covered" if covered else "missing",
            )
        ],
    )


def _trace_replay(status: str) -> TraceReplayReport:
    return TraceReplayReport(
        requirement_id="REQ-DELTA-001",
        result="passed" if status == "satisfied" else "blocked",
        observations=[
            TraceReplayObservation(
                trace_id="TRACE-1",
                requirement_id="REQ-DELTA-001",
                status=status,
            )
        ],
    )


def _drift() -> SpecDriftReport:
    return SpecDriftReport(
        result="blocked",
        statuses=[
            SpecDriftStatus(
                module_id="auth",
                status="stale",
                spec_ids=["spec:auth"],
                required_refresh_actions=["refresh specs spec:auth for changed source"],
            )
        ],
    )
