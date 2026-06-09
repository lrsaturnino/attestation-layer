import json
from pathlib import Path

from nlreq.cli import main
from nlreq.source_impact import SemanticImpactSuggestion, analyze_source_impact_with_context
from nlreq.models import NormalizedTraceArtifact
from nlreq.python_source_adapter import PythonSourceLanguageAdapter
from nlreq.source_adapter import SourceManifest


def test_source_impact_context_combines_call_graph_trace_touchpoints_and_suggestions(
    tmp_path: Path,
) -> None:
    manifest = _project(tmp_path)
    adapter = PythonSourceLanguageAdapter(project_root=tmp_path)
    traces = _traces()

    report = analyze_source_impact_with_context(
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
    # The estimate named "billing" (outside the call graph) AND omitted the deterministic modules
    # "auth"/"state"; both disagreement directions are surfaced, never silently reconciled.
    by_module = {item.module_id: item for item in report.disagreements}
    assert set(by_module) == {"audit", "billing", "auth", "state"}
    # "billing": semantic-only — named by the estimate, outside the deterministic call graph.
    assert by_module["billing"].semantic_suggestion is True
    assert by_module["billing"].deterministic is False
    # "auth"/"state": call-graph-only — deterministic modules the estimate omitted.
    assert by_module["auth"].deterministic is True and by_module["auth"].semantic_suggestion is False
    assert by_module["state"].deterministic is True and by_module["state"].semantic_suggestion is False


def test_source_impact_context_bidirectional_call_graph_expansion(tmp_path: Path) -> None:
    manifest = _project(tmp_path)
    adapter = PythonSourceLanguageAdapter(project_root=tmp_path)

    report = analyze_source_impact_with_context(adapter, manifest, symbols=["state_change"])

    assert report.deterministic_modules == ["auth", "state"]


def test_python_source_impact_context_cli(tmp_path: Path, capsys) -> None:
    manifest = _project(tmp_path)
    manifest_path = tmp_path / "source-manifest.json"
    trace_path = tmp_path / "traces.json"
    out = tmp_path / "source-impact-context.json"
    manifest_path.write_text(json.dumps(manifest.model_dump(mode="json"), indent=2))
    trace_path.write_text(_traces().model_dump_json())

    exit_code = main(
        [
            "python-source-impact-context",
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
    assert "Python contextual source impact:" in output
    data = json.loads(out.read_text())
    assert data["affected_modules"] == ["audit", "auth", "state"]
    # Both directions surface through the CLI: "billing" (semantic-only) and the deterministic
    # modules "auth"/"state" the estimate omitted (call-graph-only).
    assert {item["module_id"] for item in data["disagreements"]} == {"audit", "billing", "auth", "state"}


def test_semantic_suggestions_from_args_absent_flag_means_no_estimate() -> None:
    """The CLI flag IS the estimate, so the argparse default [] (no --semantic-suggestion) parses to
    None — no estimate provided — not an empty estimate. An empty estimate would (correctly) flag
    every deterministic call-graph module as an omission; absence must not, or every estimate-free
    CLI run would spuriously flip closure to review."""
    from nlreq.cli import _semantic_suggestions_from_args

    assert _semantic_suggestions_from_args([]) is None
    parsed = _semantic_suggestions_from_args(["billing:hint:llm"])
    assert parsed is not None
    assert [s.module_id for s in parsed] == ["billing"]


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
