import json
from pathlib import Path

from nlreq.cli import main
from nlreq.impact import analyze_source_impact
from nlreq.models import SymbolRef
from nlreq.python_source_adapter import PythonSourceLanguageAdapter
from nlreq.source_adapter import SourceBinding, SourceManifest


def test_python_source_adapter_resolves_symbols_and_presents_code(tmp_path: Path) -> None:
    manifest = _project(tmp_path)
    adapter = PythonSourceLanguageAdapter(project_root=tmp_path)

    result = adapter.resolve_symbol(SymbolRef(name="operation"), manifest)
    presentation = adapter.present_to_llm([SymbolRef(name="operation")], manifest)

    assert result.status == "resolved"
    assert result.symbols[0].symbol_type == "function"
    assert "def operation" in presentation.snippets[0]["content"]


def test_python_source_adapter_extracts_call_graph(tmp_path: Path) -> None:
    manifest = _project(tmp_path)
    adapter = PythonSourceLanguageAdapter(project_root=tmp_path)

    graph = adapter.call_graph(manifest)

    assert ("auth:operation", "state:state_change") in {
        (edge.caller, edge.callee) for edge in graph.edges
    }


def test_python_source_adapter_validates_bindings_and_extracts_traces(tmp_path: Path) -> None:
    manifest = _project(tmp_path, with_trace=True)
    adapter = PythonSourceLanguageAdapter(project_root=tmp_path)
    result = adapter.resolve_symbol(SymbolRef(name="operation"), manifest)
    binding = SourceBinding(adapter_id="python-source", symbol=result.symbols[0])

    validation = adapter.validate_binding(binding)
    traces = adapter.extract_traces(manifest)

    assert validation.valid is True
    assert traces.root[0].adapter_id == "python-source"
    assert traces.root[0].language == "python"
    assert traces.root[0].runtime == "cpython"


def test_python_source_impact_returns_deterministic_affected_modules(tmp_path: Path) -> None:
    manifest = _project(tmp_path)
    adapter = PythonSourceLanguageAdapter(project_root=tmp_path)

    report = analyze_source_impact(adapter, manifest, symbols=["operation"])

    assert report.affected_modules == ["auth", "state"]
    assert report.metadata["mode"] == "deterministic_call_graph"


def test_python_source_impact_cli(tmp_path: Path, capsys) -> None:
    manifest = _project(tmp_path)
    manifest_path = tmp_path / "source-manifest.json"
    out = tmp_path / "impact.json"
    manifest_path.write_text(json.dumps(manifest.model_dump(mode="json"), indent=2))

    exit_code = main(
        [
            "python-source-impact",
            "--manifest",
            str(manifest_path),
            "--symbol",
            "operation",
            "--project-root",
            str(tmp_path),
            "--out",
            str(out),
        ]
    )

    output = capsys.readouterr().out

    assert exit_code == 0
    assert "Python source impact:" in output
    assert json.loads(out.read_text())["affected_modules"] == ["auth", "state"]


def _project(tmp_path: Path, *, with_trace: bool = False) -> SourceManifest:
    src = tmp_path / "src"
    src.mkdir()
    (src / "auth.py").write_text(
        "from state import state_change\n\n"
        "def operation(actor):\n"
        "    if actor:\n"
        "        return state_change()\n"
        "    return 'rejected'\n"
    )
    (src / "state.py").write_text(
        "def state_change():\n"
        "    return 'changed'\n"
    )
    trace_sources: list[str] = []
    if with_trace:
        trace_path = tmp_path / "traces.json"
        trace_path.write_text(
            json.dumps(
                [
                    {
                        "trace_id": "TRACE-PY-001",
                        "adapter_id": "raw-python",
                        "source_hash": "sha256:source",
                        "events": [
                            {
                                "event_id": "evt-1",
                                "timestamp": "2026-06-01T00:00:00Z",
                                "action": "operation",
                            }
                        ],
                    }
                ]
            )
        )
        trace_sources.append("traces.json")
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
                    "trace_sources": trace_sources,
                },
                {
                    "module_id": "state",
                    "path": "src/state.py",
                    "symbols": ["state_change"],
                },
            ],
        }
    )
