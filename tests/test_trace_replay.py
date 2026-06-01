from pathlib import Path

from nlreq.cli import main
from nlreq.coverage_alignment import SpecCoverageReport
from nlreq.dsl_v2 import DslV2Parser
from nlreq.jsonutil import read_json
from nlreq.models import NormalizedTraceArtifact, RequirementIRV2
from nlreq.trace_replay import build_trace_replay_report


FIXTURES = Path(__file__).parent / "fixtures" / "requirements"


def test_trace_replay_accepts_satisfied_requirement() -> None:
    report = build_trace_replay_report(
        requirement=_ir(),
        traces=_traces(),
        coverage=_coverage(),
    )

    assert report.result == "passed"
    assert report.observations[0].status == "satisfied"
    assert report.observations[0].event_ids[:2] == ["evt-action", "evt-finalized"]
    assert report.counterexamples == []


def test_trace_replay_reports_missing_required_event() -> None:
    report = build_trace_replay_report(
        requirement=_ir(),
        traces=_traces(actions=["finalize_redemption"]),
        coverage=_coverage(),
    )

    assert report.result == "blocked"
    assert report.observations[0].status == "violating"
    assert report.observations[0].expected["event_after_action"] == "redemption_finalized"
    assert report.counterexamples[0].metadata["event_ids"] == ["evt-action"]


def test_trace_replay_reports_state_mismatch() -> None:
    report = build_trace_replay_report(
        requirement=_ir(),
        traces=_traces(collateral=90, reserve_floor=100),
        coverage=_coverage(),
    )

    assert report.result == "blocked"
    assert report.observations[0].status == "violating"
    assert report.observations[0].actual == {"collateral": 90, "reserve_floor": 100}
    assert report.counterexamples[0].backend == "trace_replay"


def test_trace_replay_marks_uncovered_when_action_is_absent() -> None:
    report = build_trace_replay_report(
        requirement=_ir(),
        traces=_traces(actions=["redemption_requested"]),
        coverage=_coverage(),
    )

    assert report.result == "blocked"
    assert report.observations[0].status == "uncovered"
    assert report.observations[0].reason == "requirement action was not observed"


def test_trace_replay_blocks_when_coverage_failed() -> None:
    report = build_trace_replay_report(
        requirement=_ir(),
        traces=_traces(),
        coverage=_coverage(result="blocked"),
    )

    assert report.result == "blocked"
    assert report.observations[0].status == "unsupported"
    assert report.observations[0].actual == {"coverage": "blocked"}


def test_trace_replay_preserves_lossy_normalization_warnings() -> None:
    report = build_trace_replay_report(
        requirement=_ir(),
        traces=_traces(lossy=True),
        coverage=_coverage(),
    )

    assert report.observations[0].warnings == [
        "trace metadata declares lossy_normalization",
        "event evt-finalized declares lossy_normalization",
    ]


def test_trace_replay_cli_writes_report(tmp_path: Path, capsys) -> None:
    ir_path = tmp_path / "requirement.ir.json"
    trace_path = tmp_path / "traces.json"
    coverage_path = tmp_path / "coverage.json"
    out = tmp_path / "trace-replay.json"
    ir_path.write_text(_ir().model_dump_json())
    trace_path.write_text(_traces().model_dump_json())
    coverage_path.write_text(_coverage().model_dump_json())

    exit_code = main(
        [
            "trace-replay",
            "--requirement-ir",
            str(ir_path),
            "--trace-artifact",
            str(trace_path),
            "--coverage",
            str(coverage_path),
            "--out",
            str(out),
        ]
    )

    output = capsys.readouterr().out

    assert exit_code == 0
    assert "Trace replay report:" in output
    assert read_json(out)["result"] == "passed"


def _ir() -> RequirementIRV2:
    return DslV2Parser().parse_ir(
        (FIXTURES / "dsl_v2_redemption.nlreq2").read_text(),
        requirement_id="REQ-REPLAY-001",
        title="Trace replay",
    )


def _coverage(*, result: str = "passed") -> SpecCoverageReport:
    return SpecCoverageReport(
        result=result,
        threshold=1.0,
        covered_modules=1 if result == "passed" else 0,
        total_modules=1,
        coverage_ratio=1.0 if result == "passed" else 0.0,
    )


def _traces(
    *,
    actions: list[str] | None = None,
    collateral: int = 150,
    reserve_floor: int = 100,
    lossy: bool = False,
) -> NormalizedTraceArtifact:
    actions = actions or ["finalize_redemption", "redemption_finalized"]
    events = []
    for index, action in enumerate(actions):
        event_id = "evt-action" if index == 0 else "evt-finalized"
        events.append(
            {
                "event_id": event_id,
                "timestamp": f"2026-06-01T00:00:0{index}Z",
                "action": action,
                "post_state": (
                    {"collateral": collateral, "reserve_floor": reserve_floor}
                    if action == "redemption_finalized"
                    else {}
                ),
                "metadata": {"lossy_normalization": True}
                if lossy and action == "redemption_finalized"
                else {},
            }
        )
    return NormalizedTraceArtifact.model_validate(
        [
            {
                "trace_id": "TRACE-REPLAY-001",
                "adapter_id": "python-source",
                "source_hash": "sha256:trace-source",
                "events": events,
                "metadata": {"lossy_normalization": lossy},
            }
        ]
    )
