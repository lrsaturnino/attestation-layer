"""PC-3 — SoliditySourceAdapter symbol resolution + call graph backed by the real Slither analyzer.

The Slither-present tests skip with a recorded reason when Slither is not installed (like the
Apalache/cvc5 real-run tests), so the suite degrades honestly. The fallback test forces Slither
absent and asserts the adapter drops to lexical static resolution with a recorded skip reason — it
never claims a Slither-backed answer it did not produce.
"""

from pathlib import Path

import pytest

from nlreq import slither_client
from nlreq.models import SymbolRef
from nlreq.production_source_adapters import SoliditySourceAdapter
from nlreq.source_adapter import SourceManifest
from nlreq.source_impact import analyze_production_source_impact


FIXTURE_ROOT = Path(__file__).parent / "fixtures" / "solidity"

requires_slither = pytest.mark.skipif(
    not slither_client.slither_available(),
    reason="slither is not installed; run with slither on PATH to exercise the real analyzer",
)


def _manifest() -> SourceManifest:
    return SourceManifest.model_validate(
        {
            "schema_version": "0.1",
            "adapter": "solidity-source",
            "language": "solidity",
            "runtime": "evm",
            "modules": [
                {
                    "module_id": "base",
                    "path": "src/Base.sol",
                    "symbols": ["Base", "Redeemed", "_audit"],
                },
                {
                    "module_id": "vault",
                    "path": "src/Vault.sol",
                    "symbols": ["Vault", "withdraw", "total"],
                },
            ],
        }
    )


@requires_slither
def test_inherited_symbol_resolves_to_its_base_declaration() -> None:
    adapter = SoliditySourceAdapter(project_root=FIXTURE_ROOT)

    resolution = adapter.resolve_symbol(SymbolRef(name="_audit"), _manifest())

    assert resolution.status == "resolved"
    # _audit is declared once in Base and inherited by Vault; inheritance-aware resolution collapses
    # it to a single definition attributed to Base, rather than counting the inherited copy twice.
    assert len(resolution.symbols) == 1
    symbol = resolution.symbols[0]
    assert symbol.metadata["analysis"] == "slither"
    assert symbol.metadata["declarer"] == "Base"
    assert symbol.symbol_type == "function"
    assert symbol.source_span is not None and "_audit" in symbol.source_span.text


@requires_slither
def test_inherited_event_resolves_once_across_the_hierarchy() -> None:
    adapter = SoliditySourceAdapter(project_root=FIXTURE_ROOT)

    resolution = adapter.resolve_symbol(SymbolRef(name="Redeemed"), _manifest())

    assert resolution.status == "resolved"
    assert len(resolution.symbols) == 1
    assert resolution.symbols[0].metadata["binding_role"] == "event"
    assert resolution.symbols[0].symbol_type == "event"


@requires_slither
def test_overloaded_symbol_resolves_ambiguous_with_distinct_signatures() -> None:
    adapter = SoliditySourceAdapter(project_root=FIXTURE_ROOT)

    resolution = adapter.resolve_symbol(SymbolRef(name="withdraw"), _manifest())

    assert resolution.status == "ambiguous"
    assert len(resolution.symbols) == 2
    assert {symbol.metadata["signature"] for symbol in resolution.symbols} == {
        "withdraw(uint256)",
        "withdraw(address)",
    }


@requires_slither
def test_ambiguous_overload_blocks_source_impact() -> None:
    """An ambiguous resolution is the source-side signal that drives REFUSED_UNBOUND_SYMBOLS: the
    impact analysis blocks and names the ambiguous symbol."""
    adapter = SoliditySourceAdapter(project_root=FIXTURE_ROOT)

    report = analyze_production_source_impact(adapter, _manifest(), symbols=["withdraw"])

    assert report.closure_effect == "block"
    assert any(
        finding.category == "ambiguous_symbol" and finding.symbol == "withdraw"
        for finding in report.findings
    )


@requires_slither
def test_call_graph_is_a_real_slither_graph_crossing_inheritance() -> None:
    adapter = SoliditySourceAdapter(project_root=FIXTURE_ROOT)

    graph = adapter.call_graph(_manifest())

    assert graph.metadata["analysis"] == "slither"
    assert graph.metadata.get("slither_version")
    edge_pairs = {(edge.caller, edge.callee) for edge in graph.edges}
    # Both overloads call the inherited _audit: the edges are overload-distinct AND cross the
    # inheritance boundary (callee attributed to Base, the declaring contract) — a real Slither
    # call graph, not the name-collapsed edges a regex pass would emit.
    assert ("vault:withdraw(uint256)", "base:_audit()") in edge_pairs
    assert ("vault:withdraw(address)", "base:_audit()") in edge_pairs


def test_slither_absent_falls_back_to_static_resolution_with_recorded_reason(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(slither_client, "slither_interpreter", lambda: None)
    adapter = SoliditySourceAdapter(project_root=FIXTURE_ROOT)

    graph = adapter.call_graph(_manifest())
    assert graph.metadata["analysis"] != "slither"
    assert graph.metadata["slither_status"] == "unavailable"
    assert graph.metadata["slither_skip_reason"]

    # Resolution still works lexically, and is honestly labelled as the regex fallback.
    resolution = adapter.resolve_symbol(SymbolRef(name="_audit"), _manifest())
    assert resolution.status == "resolved"
    assert resolution.symbols[0].metadata["analysis"] == "regex-static"
