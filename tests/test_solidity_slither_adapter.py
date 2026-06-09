"""PC-3 — SoliditySourceAdapter symbol resolution + call graph backed by the real Slither analyzer.

The Slither-present tests skip with a recorded reason when Slither is not installed (like the
Apalache/cvc5 real-run tests), so the suite degrades honestly. The fallback test forces Slither
absent and asserts the adapter drops to lexical static resolution with a recorded skip reason — it
never claims a Slither-backed answer it did not produce.
"""

import json
import types
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

    # Resolution still works lexically, and is honestly labelled as the regex fallback — with the
    # Slither skip reason recorded on the resolved symbol itself, not only on call_graph().
    resolution = adapter.resolve_symbol(SymbolRef(name="_audit"), _manifest())
    assert resolution.status == "resolved"
    assert resolution.symbols[0].metadata["analysis"] == "regex-static"
    assert resolution.symbols[0].metadata["slither_status"] == "unavailable"
    assert resolution.symbols[0].metadata["slither_skip_reason"]


def test_slither_absent_unresolved_symbol_surfaces_skip_reason_on_reason(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When Slither is absent and nothing resolves, there is no symbol metadata to carry the skip
    reason — so it must surface on the resolution ``reason`` instead of being silently lost."""
    monkeypatch.setattr(slither_client, "slither_interpreter", lambda: None)
    adapter = SoliditySourceAdapter(project_root=FIXTURE_ROOT)

    resolution = adapter.resolve_symbol(SymbolRef(name="doesNotExist"), _manifest())

    assert resolution.status == "unresolved"
    assert resolution.symbols == []
    assert "slither" in (resolution.reason or "")
    assert "unavailable" in (resolution.reason or "")


def test_slither_cli_success_field_drives_verdict_not_exit_code() -> None:
    """The CLI gate reads only the JSON ``success`` field. ``slither --json -`` exits non-zero when
    detectors fire, so a ``success: true`` payload must be ``ok`` regardless of the exit code; a
    ``success: false`` payload is ``failed``; non-JSON is ``unparseable``."""
    ok = slither_client.interpret_slither_cli(
        '{"success": true, "error": null, "results": {"detectors": [{"check": "pragma"}]}}'
    )
    assert ok.outcome == "ok"

    failed = slither_client.interpret_slither_cli('{"success": false, "error": "compile boom"}')
    assert failed.outcome == "failed"
    assert failed.error == "compile boom"

    assert slither_client.interpret_slither_cli("not json at all").outcome == "unparseable"
    assert slither_client.interpret_slither_cli("").outcome == "unparseable"


def _stub_slither_subprocess(
    monkeypatch: pytest.MonkeyPatch, *, cli_stdout: str, cli_returncode: int
) -> None:
    """Stub Slither's CLI + driver subprocesses so the client path is exercised without the tool."""
    monkeypatch.setattr(slither_client, "slither_interpreter", lambda: "/fake/python")
    monkeypatch.setattr(slither_client, "slither_console", lambda: "/fake/slither")

    def fake_run(cmd, **kwargs):
        if "--version" in cmd:
            return types.SimpleNamespace(returncode=0, stdout="0.9.6-test\n", stderr="")
        if "--json" in cmd:  # the `slither <target> --json -` success gate
            return types.SimpleNamespace(returncode=cli_returncode, stdout=cli_stdout, stderr="")
        # the driver invocation: a minimal but valid analysis payload between the sentinels
        payload = {
            "slither_version": "0.9.6-test",
            "files": ["src/Base.sol"],
            "symbols": [
                {"name": "Base", "kind": "contract", "signature": "Base", "declarer": "Base"}
            ],
            "edges": [],
        }
        out = f"{slither_client.JSON_BEGIN}\n{json.dumps(payload)}\n{slither_client.JSON_END}\n"
        return types.SimpleNamespace(returncode=0, stdout=out, stderr="")

    monkeypatch.setattr(slither_client.subprocess, "run", fake_run)


def test_analyze_with_slither_treats_nonzero_exit_with_success_true_as_analyzed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Regression: the documented non-zero-exit-with-``success:true`` behavior. Slither exits 255 on
    detector findings; the client must still analyze because the JSON ``success`` field is true.
    Stubbed subprocesses make this deterministic and tool-independent."""
    _stub_slither_subprocess(
        monkeypatch,
        cli_stdout='{"success": true, "error": null, "results": {"detectors": [{"x": 1}]}}',
        cli_returncode=255,
    )

    result = slither_client.analyze_with_slither(
        [FIXTURE_ROOT / "src" / "Base.sol"], project_root=FIXTURE_ROOT
    )

    assert result.status == "analyzed"
    assert result.slither_version == "0.9.6-test"
    assert result.analysis is not None
    assert any(symbol.name == "Base" for symbol in result.analysis.symbols)


def test_analyze_with_slither_rejects_cli_success_false(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The success gate fails closed: a ``success: false`` CLI verdict (a real compile/analysis
    failure) yields a tool_error and never reaches the driver, so no Slither-backed answer is
    fabricated from a failed compile."""
    _stub_slither_subprocess(
        monkeypatch,
        cli_stdout='{"success": false, "error": "compilation failed"}',
        cli_returncode=255,
    )

    result = slither_client.analyze_with_slither(
        [FIXTURE_ROOT / "src" / "Base.sol"], project_root=FIXTURE_ROOT
    )

    assert result.status == "tool_error"
    assert result.analysis is None
    assert "compilation failed" in (result.reason or "")
