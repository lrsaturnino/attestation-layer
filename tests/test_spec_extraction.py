from pathlib import Path

import pytest

from nlreq.cli import main
from nlreq.coverage_alignment import build_spec_coverage_report
from nlreq.dsl_v2 import DslV2Parser
from nlreq.impact import ImpactAnalysisArtifact
from nlreq.jsonutil import read_json
from nlreq.models import RequirementIRV2
from nlreq.source_adapter import CodePresentation
from nlreq.spec_extraction import (
    build_spec_extraction_workbench_report,
    candidate_to_draft_spec_entry,
    promote_candidate_spec,
)
from nlreq.system_spec import SystemSpecRegistry
from nlreq.trace_replay import TraceReplayReport


FIXTURES = Path(__file__).parent / "fixtures" / "requirements"


def test_spec_extraction_generates_draft_candidate_with_provenance() -> None:
    report = build_spec_extraction_workbench_report(
        requirement=_ir(),
        impact=_impact(),
        registry=_registry([]),
        project_root=Path("."),
        code_presentation=_code_presentation(),
        trace_replay=_trace_replay(),
    )

    candidate = report.candidates[0]

    assert report.result == "candidates"
    assert candidate.review_status == "draft"
    assert candidate.freshness == "unknown"
    assert candidate.trace_grounding_status == "passed"
    assert candidate.content_hash.startswith("sha256:")
    assert candidate.provenance.code_presentation_hash is not None
    assert candidate.provenance.trace_replay_hash is not None
    assert "candidate spec is draft and cannot satisfy coverage" in candidate.gaps


def test_spec_extraction_skips_fresh_reviewed_modules(tmp_path: Path) -> None:
    specs = tmp_path / "specs"
    specs.mkdir()
    (specs / "Redemption.tla").write_text("---- MODULE Redemption ----\n====\n")
    registry = _registry(
        [
            {
                "spec_id": "spec:redemption",
                "module_ids": ["redemption"],
                "formalism": "tla",
                "path": "specs/Redemption.tla",
                "version": "1",
                "review_status": "reviewed",
                "freshness": "fresh",
            }
        ]
    )

    report = build_spec_extraction_workbench_report(
        requirement=_ir(),
        impact=_impact(),
        registry=registry,
        project_root=tmp_path,
    )

    assert report.result == "none"
    assert report.candidates == []


def test_draft_candidate_cannot_satisfy_spec_coverage(tmp_path: Path) -> None:
    report = build_spec_extraction_workbench_report(
        requirement=_ir(),
        impact=_impact(),
        registry=_registry([]),
        project_root=tmp_path,
    )
    candidate = report.candidates[0]
    spec_path = tmp_path / candidate.path
    spec_path.parent.mkdir(parents=True)
    spec_path.write_text(candidate.content)
    registry = _registry([candidate_to_draft_spec_entry(candidate).model_dump(mode="json")])

    coverage = build_spec_coverage_report(
        impact=_impact(),
        registry=registry,
        project_root=tmp_path,
    )

    assert coverage.result == "blocked"
    assert coverage.modules[0].status == "unreviewed"


def test_candidate_promotion_is_explicit_and_hash_checked() -> None:
    candidate = build_spec_extraction_workbench_report(
        requirement=_ir(),
        impact=_impact(),
        registry=_registry([]),
        project_root=Path("."),
    ).candidates[0]

    with pytest.raises(ValueError, match="approved candidate hash"):
        promote_candidate_spec(candidate, approved_hash="sha256:wrong", version="1")

    entry = promote_candidate_spec(
        candidate,
        approved_hash=candidate.content_hash,
        version="1",
    )

    assert entry.review_status == "reviewed"
    assert entry.freshness == "fresh"
    assert entry.recorded_hash == candidate.content_hash


def test_spec_extraction_cli_writes_report(tmp_path: Path, capsys) -> None:
    ir_path = tmp_path / "requirement.ir.json"
    impact_path = tmp_path / "impact.json"
    registry_path = tmp_path / "registry.json"
    trace_path = tmp_path / "trace-replay.json"
    out = tmp_path / "spec-extraction.json"
    ir_path.write_text(_ir().model_dump_json())
    impact_path.write_text(_impact().model_dump_json())
    registry_path.write_text(_registry([]).model_dump_json())
    trace_path.write_text(_trace_replay().model_dump_json())

    exit_code = main(
        [
            "spec-extract",
            "--requirement-ir",
            str(ir_path),
            "--impact",
            str(impact_path),
            "--registry",
            str(registry_path),
            "--trace-replay",
            str(trace_path),
            "--out",
            str(out),
        ]
    )

    output = capsys.readouterr().out

    assert exit_code == 0
    assert "Spec extraction workbench report:" in output
    assert read_json(out)["result"] == "candidates"


def _ir() -> RequirementIRV2:
    return DslV2Parser().parse_ir(
        (FIXTURES / "dsl_v2_redemption.nlreq2").read_text(),
        requirement_id="REQ-EXTRACT-001",
        title="Spec extraction",
    )


def _impact() -> ImpactAnalysisArtifact:
    return ImpactAnalysisArtifact(
        adapter_id="python-source",
        language="python",
        input_symbols=["finalize_redemption"],
        affected_modules=["redemption"],
    )


def _registry(specs: list[dict]) -> SystemSpecRegistry:
    return SystemSpecRegistry.model_validate({"schema_version": "0.1", "specs": specs})


def _code_presentation() -> CodePresentation:
    return CodePresentation(
        adapter_id="python-source",
        language="python",
        snippets=[{"path": "redemption.py", "content": "def finalize_redemption(): ..."}],
    )


def _trace_replay() -> TraceReplayReport:
    return TraceReplayReport(
        requirement_id="REQ-EXTRACT-001",
        result="passed",
        observations=[],
    )
