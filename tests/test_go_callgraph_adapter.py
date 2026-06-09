"""PC-6 — GoSourceAdapter symbol resolution + call graph backed by the real gopls/callgraph tools.

The tool-present tests skip with a recorded reason when the Go toolchain is absent (like the
Apalache/Slither/Foundry real-run tests), so the suite degrades honestly. The fallback tests force
the tools absent and assert the adapter drops to lexical static resolution with a recorded skip
reason — it never claims a tool-backed answer it did not produce.
"""

from pathlib import Path

import pytest

from nlreq import go_client
from nlreq.models import SymbolRef
from nlreq.production_source_adapters import GoSourceAdapter
from nlreq.source_adapter import SourceManifest
from nlreq.source_impact import analyze_production_source_impact


FIXTURE_ROOT = Path(__file__).parent / "fixtures" / "go"

requires_go_tools = pytest.mark.skipif(
    not go_client.go_symbol_tools_available(),
    reason="go/gopls/callgraph are not installed; run with the Go toolchain on PATH",
)


def _manifest() -> SourceManifest:
    return SourceManifest.model_validate(
        {
            "schema_version": "0.1",
            "adapter": "go-source",
            "language": "go",
            "runtime": "go",
            "modules": [
                {
                    "module_id": "coordinator",
                    "path": "coordinator/coordinator.go",
                    "symbols": ["Coordinate", "Run", "Total"],
                }
            ],
        }
    )


@requires_go_tools
def test_unique_function_resolves_via_gopls() -> None:
    adapter = GoSourceAdapter(project_root=FIXTURE_ROOT)

    resolution = adapter.resolve_symbol(SymbolRef(name="Coordinate"), _manifest())

    assert resolution.status == "resolved"
    assert len(resolution.symbols) == 1
    symbol = resolution.symbols[0]
    assert symbol.metadata["analysis"] == "gopls"
    assert symbol.symbol_type == "function"
    assert symbol.source_span is not None and "Coordinate" in symbol.source_span.text


@requires_go_tools
def test_method_shared_across_types_resolves_ambiguous() -> None:
    """Go has no overloads, so its only symbol-resolution ambiguity is a method name declared on more
    than one type. Run is declared on Validator and Recorder (and the Stage interface), so it
    resolves ambiguous with the distinct receivers present — a type-aware result a lexical pass that
    sees only the bare name cannot produce."""
    adapter = GoSourceAdapter(project_root=FIXTURE_ROOT)

    resolution = adapter.resolve_symbol(SymbolRef(name="Run"), _manifest())

    assert resolution.status == "ambiguous"
    containers = {symbol.metadata.get("container") for symbol in resolution.symbols}
    assert {"Validator", "Recorder"} <= containers


@requires_go_tools
def test_unique_method_resolves_to_its_receiver() -> None:
    adapter = GoSourceAdapter(project_root=FIXTURE_ROOT)

    resolution = adapter.resolve_symbol(SymbolRef(name="Total"), _manifest())

    assert resolution.status == "resolved"
    assert resolution.symbols[0].symbol_type == "method"
    assert resolution.symbols[0].metadata["container"] == "Recorder"


@requires_go_tools
def test_ambiguous_method_blocks_source_impact() -> None:
    """An ambiguous resolution is the source-side signal that drives REFUSED_UNBOUND_SYMBOLS: the
    impact analysis blocks and names the ambiguous symbol."""
    adapter = GoSourceAdapter(project_root=FIXTURE_ROOT)

    report = analyze_production_source_impact(adapter, _manifest(), symbols=["Run"])

    assert report.closure_effect == "block"
    assert any(
        finding.category == "ambiguous_symbol" and finding.symbol == "Run"
        for finding in report.findings
    )


@requires_go_tools
def test_call_graph_is_a_real_cha_graph_with_interface_dispatch() -> None:
    adapter = GoSourceAdapter(project_root=FIXTURE_ROOT)

    graph = adapter.call_graph(_manifest())

    assert graph.metadata["analysis"] == "callgraph"
    assert graph.metadata["callgraph_status"] == "analyzed"
    assert graph.metadata.get("go_version")
    # The callgraph binary's OWN version is recorded (read from `go version -m`), not just the Go
    # toolchain — this is the signal the certifier keys on to prove a callgraph binary built the graph.
    assert graph.metadata.get("callgraph_version")
    assert "golang.org/x/tools" in graph.metadata["callgraph_version"]
    edge_pairs = {(edge.caller, edge.callee) for edge in graph.edges}
    # Coordinate dispatches through the Stage interface; CHA resolves the call to EVERY implementation
    # of Stage. Those edges (to the concrete receivers Validator and *Recorder) are ones a lexical
    # pass — which sees only `s.Run(out)` — cannot attribute to a concrete type.
    assert ("coordinator:Coordinate", "coordinator:(Validator).Run") in edge_pairs
    assert ("coordinator:Coordinate", "coordinator:(*Recorder).Run") in edge_pairs


def test_go_tools_absent_falls_back_to_static_resolution_with_recorded_reason(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(go_client, "gopls_binary", lambda: None)
    adapter = GoSourceAdapter(project_root=FIXTURE_ROOT)

    graph = adapter.call_graph(_manifest())
    assert graph.metadata["analysis"] != "callgraph"
    assert graph.metadata["callgraph_status"] == "unavailable"
    assert graph.metadata["callgraph_skip_reason"]

    # Resolution still works lexically, honestly labelled as the regex fallback — with the Go skip
    # reason recorded on the resolved symbol itself, not only on call_graph().
    resolution = adapter.resolve_symbol(SymbolRef(name="Coordinate"), _manifest())
    assert resolution.status == "resolved"
    assert resolution.symbols[0].metadata["analysis"] == "regex-static"
    assert resolution.symbols[0].metadata["go_status"] == "unavailable"
    assert resolution.symbols[0].metadata["go_skip_reason"]


def test_go_tools_absent_unresolved_symbol_surfaces_skip_reason_on_reason(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When the Go tools are absent and nothing resolves, there is no symbol metadata to carry the
    skip reason — so it must surface on the resolution ``reason`` instead of being silently lost."""
    monkeypatch.setattr(go_client, "gopls_binary", lambda: None)
    adapter = GoSourceAdapter(project_root=FIXTURE_ROOT)

    resolution = adapter.resolve_symbol(SymbolRef(name="doesNotExist"), _manifest())

    assert resolution.status == "unresolved"
    assert resolution.symbols == []
    assert "go toolchain" in (resolution.reason or "")
    assert "unavailable" in (resolution.reason or "")


def test_parse_go_node_splits_package_and_method_label() -> None:
    """The callgraph node parser is deterministic and tool-independent, so it is pinned directly: a
    plain function and a pointer-receiver method both split into (package import path, label)."""
    assert go_client._parse_go_node("example.com/m/coordinator.Coordinate", "example.com/m") == (
        "example.com/m/coordinator",
        "Coordinate",
    )
    assert go_client._parse_go_node(
        "(*example.com/m/coordinator.Recorder).Run", "example.com/m"
    ) == ("example.com/m/coordinator", "(*Recorder).Run")
