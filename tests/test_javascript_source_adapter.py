import json
from pathlib import Path

from nlreq.agnostic_wedge import build_agnostic_wedge_report
from nlreq.cli import main
from nlreq.coverage_alignment import SpecCoverageReport, TraceAlignmentReport
from nlreq.dsl_v2 import DslV2Parser
from nlreq.impact import analyze_source_impact
from nlreq.javascript_source_adapter import JavaScriptSourceLanguageAdapter
from nlreq.jsonutil import read_json
from nlreq.models import BackendResult, EvidenceLevel, NormalizedTraceArtifact, SymbolRef
from nlreq.proof_closure import build_proof_dispatch_plan, build_proof_object
from nlreq.source_adapter import SourceBinding, SourceManifest
from nlreq.trace_replay import build_trace_replay_report


DSL = (
    "For every redemption:\n"
    "when wallet is authorized\n"
    "then finalizeRedemption must emit redemption_finalized within 6 hours.\n"
)


def test_javascript_source_adapter_resolves_symbols_and_presents_code(
    tmp_path: Path,
) -> None:
    manifest = _project(tmp_path)
    adapter = JavaScriptSourceLanguageAdapter(project_root=tmp_path)

    result = adapter.resolve_symbol(SymbolRef(name="finalizeRedemption"), manifest)
    presentation = adapter.present_to_llm([SymbolRef(name="finalizeRedemption")], manifest)

    assert result.status == "resolved"
    assert result.symbols[0].symbol_type == "function"
    assert "function finalizeRedemption" in presentation.snippets[0]["content"]


def test_javascript_source_adapter_extracts_call_graph(tmp_path: Path) -> None:
    manifest = _project(tmp_path)
    adapter = JavaScriptSourceLanguageAdapter(project_root=tmp_path)

    graph = adapter.call_graph(manifest)

    assert ("redemption:finalizeRedemption", "events:emitFinalized") in {
        (edge.caller, edge.callee) for edge in graph.edges
    }


def test_javascript_source_adapter_validates_bindings_and_extracts_traces(
    tmp_path: Path,
) -> None:
    manifest = _project(tmp_path, with_trace=True)
    adapter = JavaScriptSourceLanguageAdapter(project_root=tmp_path)
    result = adapter.resolve_symbol(SymbolRef(name="finalizeRedemption"), manifest)
    binding = SourceBinding(adapter_id="javascript-source", symbol=result.symbols[0])

    validation = adapter.validate_binding(binding)
    traces = adapter.extract_traces(manifest)

    assert validation.valid is True
    assert traces.root[0].adapter_id == "javascript-source"
    assert traces.root[0].language == "javascript"
    assert traces.root[0].runtime == "node"


def test_javascript_source_impact_and_cli(tmp_path: Path, capsys) -> None:
    manifest = _project(tmp_path)
    adapter = JavaScriptSourceLanguageAdapter(project_root=tmp_path)
    report = analyze_source_impact(adapter, manifest, symbols=["finalizeRedemption"])
    manifest_path = tmp_path / "source-manifest.json"
    out = tmp_path / "impact.json"
    manifest_path.write_text(json.dumps(manifest.model_dump(mode="json"), indent=2))

    exit_code = main(
        [
            "javascript-source-impact",
            "--manifest",
            str(manifest_path),
            "--symbol",
            "finalizeRedemption",
            "--project-root",
            str(tmp_path),
            "--out",
            str(out),
        ]
    )

    output = capsys.readouterr().out

    assert report.affected_modules == ["events", "redemption"]
    assert exit_code == 0
    assert "JavaScript source impact:" in output
    assert read_json(out)["affected_modules"] == ["events", "redemption"]


def test_javascript_source_adapter_drives_trace_replay_and_cross_language_wedge(
    tmp_path: Path,
) -> None:
    manifest = _project(tmp_path, with_trace=True)
    adapter = JavaScriptSourceLanguageAdapter(project_root=tmp_path)
    ir = DslV2Parser().parse_ir(DSL, requirement_id="REQ-JS-001", title="JS source")
    traces = adapter.extract_traces(manifest)
    coverage = SpecCoverageReport(
        result="passed",
        threshold=1.0,
        covered_modules=1,
        total_modules=1,
        coverage_ratio=1.0,
    )

    replay = build_trace_replay_report(requirement=ir, traces=traces, coverage=coverage)
    # This test isolates the cross-language wedge over a closed proof, not premise routing, so it
    # requests the legacy single-backend dispatch explicitly to close on one system_checker verdict.
    proof = build_proof_object(
        requirement=ir,
        backend_results=[
            BackendResult(
                backend="system_checker",
                status="valid",
                evidence_level=EvidenceLevel.CONSISTENCY_CHECKED,
            )
        ],
        coverage=coverage,
        trace_alignment=TraceAlignmentReport(result="passed"),
        dispatch=build_proof_dispatch_plan(ir, backend_id="system_checker"),
    )
    wedge = build_agnostic_wedge_report(
        proof=proof,
        source_manifests=[_python_manifest(), manifest],
        requirement=ir,
    )

    assert replay.result == "passed"
    assert wedge.result == "passed"
    assert wedge.wedge_type == "cross_language"


def _project(tmp_path: Path, *, with_trace: bool = False) -> SourceManifest:
    src = tmp_path / "src"
    src.mkdir()
    (src / "redemption.js").write_text(
        "import { emitFinalized } from './events.js';\n\n"
        "export function finalizeRedemption(wallet) {\n"
        "  if (wallet.authorized) {\n"
        "    return emitFinalized(wallet.id);\n"
        "  }\n"
        "  return 'rejected';\n"
        "}\n"
    )
    (src / "events.js").write_text(
        "export const emitFinalized = (walletId) => {\n"
        "  return { type: 'redemption_finalized', walletId };\n"
        "};\n"
    )
    trace_sources: list[str] = []
    if with_trace:
        trace_path = tmp_path / "traces.json"
        trace_path.write_text(_traces().model_dump_json())
        trace_sources.append("traces.json")
    return SourceManifest.model_validate(
        {
            "schema_version": "0.1",
            "adapter": "javascript-source",
            "language": "javascript",
            "runtime": "node",
            "modules": [
                {
                    "module_id": "redemption",
                    "path": "src/redemption.js",
                    "symbols": ["finalizeRedemption"],
                    "trace_sources": trace_sources,
                },
                {
                    "module_id": "events",
                    "path": "src/events.js",
                    "symbols": ["emitFinalized"],
                },
            ],
        }
    )


def _traces() -> NormalizedTraceArtifact:
    return NormalizedTraceArtifact.model_validate(
        [
            {
                "trace_id": "TRACE-JS-001",
                "adapter_id": "raw-javascript",
                "source_hash": "sha256:source",
                "events": [
                    {
                        "event_id": "evt-action",
                        "timestamp": "2026-06-01T00:00:00Z",
                        "action": "finalizeRedemption",
                    },
                    {
                        "event_id": "evt-finalized",
                        "timestamp": "2026-06-01T00:00:01Z",
                        "action": "redemption_finalized",
                        "post_state": {"collateral": 150, "reserve_floor": 100},
                    },
                ],
            }
        ]
    )


def _python_manifest() -> SourceManifest:
    return SourceManifest.model_validate(
        {
            "schema_version": "0.1",
            "adapter": "python-source",
            "language": "python",
            "runtime": "cpython",
            "modules": [
                {
                    "module_id": "python:redemption",
                    "path": "src/python/redemption.py",
                    "symbols": ["finalize_redemption"],
                }
            ],
        }
    )
