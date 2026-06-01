import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from nlreq.models import NormalizedTraceArtifact, SymbolRef
from nlreq.source_adapter import (
    NullSourceLanguageAdapter,
    SourceBinding,
    SourceManifest,
)


def test_null_source_adapter_resolves_symbols_from_manifest() -> None:
    adapter = NullSourceLanguageAdapter()
    manifest = _manifest()

    result = adapter.resolve_symbol(
        SymbolRef(name="operation", expected_type="function"),
        manifest,
    )

    assert result.status == "resolved"
    assert result.symbols[0].module_id == "auth"
    assert result.symbols[0].symbol_type == "function"


def test_null_source_adapter_reports_ambiguous_and_unresolved_symbols() -> None:
    adapter = NullSourceLanguageAdapter()
    manifest = _manifest(
        modules=[
            {"module_id": "a", "path": "src/a.null", "symbols": ["operation"]},
            {"module_id": "b", "path": "src/b.null", "symbols": ["operation"]},
        ]
    )

    ambiguous = adapter.resolve_symbol(SymbolRef(name="operation"), manifest)
    unresolved = adapter.resolve_symbol(SymbolRef(name="missing"), manifest)

    assert ambiguous.status == "ambiguous"
    assert unresolved.status == "unresolved"


def test_null_source_adapter_exercises_call_graph_binding_presentation_and_traces() -> None:
    adapter = NullSourceLanguageAdapter()
    manifest = _manifest()
    resolved = adapter.resolve_symbol(SymbolRef(name="operation"), manifest)
    binding = SourceBinding(adapter_id="null-source", symbol=resolved.symbols[0])

    call_graph = adapter.call_graph(manifest)
    validation = adapter.validate_binding(binding)
    presentation = adapter.present_to_llm([SymbolRef(name="operation")], manifest)
    traces = adapter.extract_traces(manifest)

    assert call_graph.modules == ["auth"]
    assert validation.valid is True
    assert presentation.snippets[0]["symbol"] == "operation"
    assert traces.root == []


def test_source_manifest_rejects_escaping_paths() -> None:
    with pytest.raises(ValidationError):
        SourceManifest.model_validate(
            {
                "schema_version": "0.1",
                "adapter": "null-source",
                "language": "null",
                "modules": [{"module_id": "bad", "path": "../bad.null"}],
            }
        )


def test_source_manifest_round_trips_from_file(tmp_path: Path) -> None:
    path = tmp_path / "source-manifest.json"
    path.write_text(json.dumps(_manifest().model_dump(mode="json"), indent=2))

    parsed = NullSourceLanguageAdapter().parse_manifest(path)

    assert parsed.modules[0].module_id == "auth"


def test_verification_grade_trace_fields_are_optional_and_validated() -> None:
    artifact = NormalizedTraceArtifact.model_validate(
        [
            {
                "trace_id": "TRACE-SOURCE-001",
                "adapter_id": "null-source",
                "source_hash": "sha256:source",
                "language": "go",
                "runtime": "go1.22",
                "events": [
                    {
                        "event_id": "evt-1",
                        "timestamp": "2026-06-01T00:00:00Z",
                        "actor": "actor",
                        "action": "operation",
                        "pre_state": {"status": "pending"},
                        "post_state": {"status": "accepted"},
                        "causal_predecessor": None,
                        "language": "go",
                        "runtime": "go1.22",
                        "metadata": {"lossy_normalization": "none"},
                    },
                    {
                        "event_id": "evt-2",
                        "timestamp": "2026-06-01T00:00:01Z",
                        "action": "state_change",
                        "causal_predecessor": "evt-1",
                    },
                ],
                "metadata": {
                    "requirement_ids": ["REQ-AUTH-001"],
                    "normalization": {"omitted_fields": []},
                },
            }
        ]
    )

    assert artifact.root[0].language == "go"
    assert artifact.root[0].events[1].causal_predecessor == "evt-1"


def _manifest(modules: list[dict[str, object]] | None = None) -> SourceManifest:
    return SourceManifest.model_validate(
        {
            "schema_version": "0.1",
            "adapter": "null-source",
            "language": "null",
            "modules": modules
            or [
                {
                    "module_id": "auth",
                    "path": "src/auth.null",
                    "symbols": ["operation"],
                    "spec_refs": ["spec:auth"],
                    "trace_sources": [],
                }
            ],
        }
    )
