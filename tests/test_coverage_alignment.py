import json
from pathlib import Path

from nlreq.cli import main
from nlreq.coverage_alignment import (
    build_spec_coverage_gate,
    build_spec_coverage_report,
    build_trace_alignment_report,
)
from nlreq.dsl_v2 import DslV2Parser
from nlreq.impact import ImpactAnalysisArtifact
from nlreq.models import NormalizedTraceArtifact
from nlreq.system_spec import SystemSpecRegistry, unspecified_modules


DSL = (
    "For every redemption:\n"
    "when wallet is authorized\n"
    "then finalize_redemption must emit redemption_finalized within 6 hours.\n"
)


def test_spec_coverage_passes_for_fresh_reviewed_specs(tmp_path: Path) -> None:
    report = build_spec_coverage_report(
        impact=_impact(["redemption"]),
        registry=_registry(tmp_path),
        project_root=tmp_path,
    )

    assert report.result == "passed"
    assert report.coverage_ratio == 1.0
    assert report.modules[0].status == "covered"


def test_spec_coverage_blocks_missing_and_stale_modules(tmp_path: Path) -> None:
    registry = _registry(tmp_path, freshness="stale")

    report = build_spec_coverage_report(
        impact=_impact(["redemption", "wallet"]),
        registry=registry,
        project_root=tmp_path,
    )

    assert report.result == "blocked"
    assert [module.status for module in report.modules] == ["stale", "missing"]


def test_spec_coverage_gate_blocks_unspecified_module_and_queues_extraction(tmp_path: Path) -> None:
    """PC-10: an affected module with no registered spec returns NEEDS_SPEC_COVERAGE and queues a
    placeholder Specula extraction for exactly that module."""
    registry = _registry(tmp_path)  # covers "redemption" only
    gate = build_spec_coverage_gate(
        impact=_impact(["redemption", "wallet"]),
        registry=registry,
    )

    assert gate.result == "needs_spec_coverage"
    assert gate.unspecified_modules == ["wallet"]
    assert gate.covered_modules == ["redemption"]
    assert [request.module_id for request in gate.extraction_requests] == ["wallet"]
    assert gate.extraction_requests[0].status == "queued"


def test_spec_coverage_gate_is_covered_when_every_module_has_a_spec(tmp_path: Path) -> None:
    gate = build_spec_coverage_gate(
        impact=_impact(["redemption"]),
        registry=_registry(tmp_path),
    )

    assert gate.result == "covered"
    assert gate.unspecified_modules == []
    assert gate.extraction_requests == []


def test_unspecified_modules_ignores_draft_or_stale_specs(tmp_path: Path) -> None:
    """A module with ANY registry entry (even draft/stale) is not 'unspec'd' — that is a separate
    coverage failure. NEEDS_SPEC_COVERAGE is reserved for modules with no spec at all."""
    registry = _registry(tmp_path, freshness="stale")  # a stale but present spec for "redemption"
    assert unspecified_modules(registry, ["redemption"]) == []
    assert unspecified_modules(registry, ["redemption", "wallet"]) == ["wallet"]


def test_trace_alignment_classifies_aligned_violating_uncovered_and_unsupported(
    tmp_path: Path,
) -> None:
    coverage = build_spec_coverage_report(
        impact=_impact(["redemption"]),
        registry=_registry(tmp_path),
        project_root=tmp_path,
    )
    traces = NormalizedTraceArtifact.model_validate(
        [
            _trace("TRACE-ALIGNED", ["finalize_redemption"]),
            _trace("TRACE-VIOLATING", ["finalize_redemption"], violation=True),
            _trace("TRACE-UNCOVERED", ["other_action"]),
        ]
    )

    report = build_trace_alignment_report(requirement=_ir(), traces=traces, coverage=coverage)

    assert [item.status for item in report.alignments] == [
        "aligned",
        "violating",
        "uncovered",
    ]
    assert report.result == "blocked"

    blocked_coverage = coverage.model_copy(update={"result": "blocked"})
    unsupported = build_trace_alignment_report(
        requirement=_ir(),
        traces=NormalizedTraceArtifact.model_validate([_trace("TRACE-UNSUPPORTED", ["finalize_redemption"])]),
        coverage=blocked_coverage,
    )
    assert unsupported.alignments[0].status == "unsupported"


def test_spec_coverage_and_trace_alignment_cli(tmp_path: Path, capsys) -> None:
    registry = _registry(tmp_path)
    impact = _impact(["redemption"])
    ir = _ir()
    traces = NormalizedTraceArtifact.model_validate([_trace("TRACE-ALIGNED", ["finalize_redemption"])])
    registry_path = tmp_path / "registry.json"
    impact_path = tmp_path / "impact.json"
    ir_path = tmp_path / "requirement.ir.json"
    traces_path = tmp_path / "traces.json"
    coverage_out = tmp_path / "coverage.json"
    alignment_out = tmp_path / "alignment.json"
    registry_path.write_text(json.dumps(registry.model_dump(mode="json"), indent=2))
    impact_path.write_text(json.dumps(impact.model_dump(mode="json"), indent=2))
    ir_path.write_text(json.dumps(ir.model_dump(mode="json"), indent=2))
    traces_path.write_text(json.dumps(traces.model_dump(mode="json"), indent=2))

    coverage_exit = main(
        [
            "spec-coverage",
            "--impact",
            str(impact_path),
            "--registry",
            str(registry_path),
            "--project-root",
            str(tmp_path),
            "--out",
            str(coverage_out),
        ]
    )
    alignment_exit = main(
        [
            "trace-align",
            "--requirement-ir",
            str(ir_path),
            "--trace-artifact",
            str(traces_path),
            "--coverage",
            str(coverage_out),
            "--out",
            str(alignment_out),
        ]
    )

    output = capsys.readouterr().out

    assert coverage_exit == 0
    assert alignment_exit == 0
    assert "Spec coverage report:" in output
    assert "Trace alignment report:" in output
    assert json.loads(alignment_out.read_text())["result"] == "passed"


def _registry(tmp_path: Path, *, freshness: str = "fresh") -> SystemSpecRegistry:
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
                    "freshness": freshness,
                }
            ],
        }
    )


def _impact(modules: list[str]) -> ImpactAnalysisArtifact:
    return ImpactAnalysisArtifact(
        adapter_id="python-source",
        language="python",
        input_symbols=["finalize_redemption"],
        affected_modules=modules,
    )


def _ir():
    return DslV2Parser().parse_ir(DSL, requirement_id="REQ-COVERAGE-001", title="Coverage")


def _trace(trace_id: str, actions: list[str], *, violation: bool = False) -> dict[str, object]:
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
        "metadata": {"alignment_violation": violation} if violation else {},
    }
