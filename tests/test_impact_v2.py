import json
from pathlib import Path

from nlreq.cli import main
from nlreq.impact_v2 import SemanticImpactSuggestion, analyze_source_impact_v2
from nlreq.models import NormalizedTraceArtifact
from nlreq.python_source_adapter import PythonSourceLanguageAdapter
from nlreq.source_adapter import SourceManifest


def test_impact_v2_combines_call_graph_trace_touchpoints_and_suggestions(
    tmp_path: Path,
) -> None:
    manifest = _project(tmp_path)
    adapter = PythonSourceLanguageAdapter(project_root=tmp_path)
    traces = _traces()

    report = analyze_source_impact_v2(
        adapter,
        manifest,
        symbols=["operation"],
        traces=traces,
        semantic_suggestions=[
            SemanticImpactSuggestion(module_id="billing", reason="semantic hint", source="llm")
        ],
    )

    assert report.deterministic_modules == ["auth", "state"]
    assert report.trace_touched_modules == ["audit"]
    assert report.affected_modules == ["audit", "auth", "state"]
    assert report.semantic_suggestions[0].module_id == "billing"
    assert {item.module_id for item in report.disagreements} == {"audit", "billing"}
    assert report.disagreements[0].deterministic is False


def test_impact_v2_bidirectional_call_graph_expansion(tmp_path: Path) -> None:
    manifest = _project(tmp_path)
    adapter = PythonSourceLanguageAdapter(project_root=tmp_path)

    report = analyze_source_impact_v2(adapter, manifest, symbols=["state_change"])

    assert report.deterministic_modules == ["auth", "state"]


def test_python_source_impact_v2_cli(tmp_path: Path, capsys) -> None:
    manifest = _project(tmp_path)
    manifest_path = tmp_path / "source-manifest.json"
    trace_path = tmp_path / "traces.json"
    out = tmp_path / "impact-v2.json"
    manifest_path.write_text(json.dumps(manifest.model_dump(mode="json"), indent=2))
    trace_path.write_text(_traces().model_dump_json())

    exit_code = main(
        [
            "python-source-impact-v2",
            "--manifest",
            str(manifest_path),
            "--symbol",
            "operation",
            "--trace-artifact",
            str(trace_path),
            "--semantic-suggestion",
            "billing:semantic hint:llm",
            "--project-root",
            str(tmp_path),
            "--out",
            str(out),
        ]
    )

    output = capsys.readouterr().out

    assert exit_code == 0
    assert "Python source impact v2:" in output
    data = json.loads(out.read_text())
    assert data["affected_modules"] == ["audit", "auth", "state"]
    assert {item["module_id"] for item in data["disagreements"]} == {"audit", "billing"}


def _project(tmp_path: Path) -> SourceManifest:
    src = tmp_path / "src"
    src.mkdir()
    (src / "auth.py").write_text(
        "from state import state_change\n\n"
        "def operation(actor):\n"
        "    return state_change()\n"
    )
    (src / "state.py").write_text("def state_change():\n    return 'changed'\n")
    return SourceManifest.model_validate(
        {
            "schema_version": "0.1",
            "adapter": "python-source",
            "language": "python",
            "runtime": "cpython",
            "modules": [
                {
                    "module_id": "auth",
                    "path": "src/auth.py",
                    "symbols": ["operation"],
                },
                {
                    "module_id": "state",
                    "path": "src/state.py",
                    "symbols": ["state_change"],
                },
            ],
        }
    )


def _traces() -> NormalizedTraceArtifact:
    return NormalizedTraceArtifact.model_validate(
        [
            {
                "trace_id": "TRACE-IMPACT-001",
                "adapter_id": "python-source",
                "source_hash": "sha256:trace",
                "events": [
                    {
                        "event_id": "evt-1",
                        "timestamp": "2026-06-01T00:00:00Z",
                        "action": "audit_log",
                        "metadata": {"module_id": "audit"},
                    }
                ],
            }
        ]
    )
