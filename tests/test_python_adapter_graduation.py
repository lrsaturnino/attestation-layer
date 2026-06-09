"""PC-14 — graduate the Python source adapter to a certified, ast-backed static_resolution adapter,
substantiate domain agnosticism on a non-DeFi vehicle, and keep TS/Rust/Java honest.

The Python adapter drives CPython's built-in ``ast`` (a real parser, not regex): it resolves symbols
and a call graph from the AST and records ``analysis: "ast"`` plus the interpreter version as the
producer. ``ast`` runs no program, so the only level it can HONESTLY evidence is static_resolution —
the certification gate certifies it there, never trace_capable. Agnosticism is shown by running the
SAME adapter over a non-DeFi procurement-approval codebase. The TypeScript / Rust / Java adapters stay
honestly at static_resolution with a recorded external-trace-producer reason — their real tooling is
not wired, so they must not claim a trace level.
"""

from pathlib import Path

from nlreq.adapter_certification import (
    capability_overclaim_violations,
    certify_adapter,
    trace_evidence_violations,
)
from nlreq.models import SymbolRef
from nlreq.production_source_adapters import (
    JavaSourceAdapter,
    RustSourceAdapter,
    TypeScriptSourceAdapter,
)
from nlreq.python_source_adapter import PythonSourceLanguageAdapter
from nlreq.source_adapter import SourceManifest


_TRACE_LEVELS = {"trace_capable", "production_candidate"}


def _python_project(tmp_path: Path, files: dict[str, str]) -> Path:
    for name, content in files.items():
        (tmp_path / name).write_text(content)
    return tmp_path


def _manifest(modules: list[dict[str, object]]) -> SourceManifest:
    return SourceManifest.model_validate(
        {
            "schema_version": "0.1",
            "adapter": "python-source",
            "language": "python",
            "runtime": "cpython",
            "modules": modules,
        }
    )


def test_python_adapter_certifies_at_static_resolution_with_ast_producer(tmp_path: Path) -> None:
    """The DoD: the Python adapter passes conformance at a real tool-backed level (static_resolution,
    the honest ceiling for a parser with no trace producer) with a REAL producer — the ast analysis and
    interpreter version recorded on every symbol and the call graph, not the regex floor."""
    _python_project(
        tmp_path,
        {
            "auth.py": "def operation():\n    return state_change()\n",
            "state.py": "def state_change():\n    return True\n",
        },
    )
    manifest = _manifest(
        [
            {"module_id": "auth", "path": "auth.py", "symbols": ["operation"]},
            {"module_id": "state", "path": "state.py", "symbols": ["state_change"]},
        ]
    )
    adapter = PythonSourceLanguageAdapter(project_root=tmp_path)

    report = certify_adapter(
        adapter,
        manifest,
        symbol_refs=[SymbolRef(name="operation")],
        required_capabilities=["static_symbol_resolution", "call_graph", "code_presentation"],
    )

    assert report.result == "certified"
    assert report.level == "static_resolution"
    # No runtime trace producer, so it stays static_resolution — never a fabricated trace level.
    assert report.trace_count == 0
    assert report.call_graph_edges >= 1

    # The producer is REAL and recorded: a regex adapter would not carry an ast analysis stamp.
    call_graph = adapter.call_graph(manifest)
    assert call_graph.metadata["analysis"] == "ast"
    assert call_graph.metadata["python_version"]
    resolved = adapter.resolve_symbol(SymbolRef(name="operation"), manifest)
    assert resolved.status == "resolved"
    assert resolved.symbols[0].metadata["analysis"] == "ast"


def test_python_capability_contract_is_honest_no_trace_overclaim(tmp_path: Path) -> None:
    """The contract declares static_resolution and NO claim is a trace level; with zero provenanced
    traces and an achieved static_resolution level the shared honesty rules report no over-claim."""
    adapter = PythonSourceLanguageAdapter(project_root=tmp_path)
    contract = adapter.capability_contract()

    assert contract.capability_level == "static_resolution"
    assert all(claim.level not in _TRACE_LEVELS for claim in contract.capabilities)
    # An ast adapter must declare a runtime-trace limitation (it produces no traces of its own).
    assert any(limitation.category == "runtime_trace" for limitation in contract.limitations)
    # The shared honesty gates (the same ones certification/conformance use) see no over-claim.
    assert trace_evidence_violations(contract, provenanced_trace_count=0) == []
    assert capability_overclaim_violations(contract, achieved_level="static_resolution") == []


def test_python_adapter_is_agnostic_over_a_non_defi_procurement_domain(tmp_path: Path) -> None:
    """Agnosticism on a non-DeFi domain: the SAME graduated adapter resolves real symbols and a real
    call graph over a procurement-approval codebase (purchase orders + approver routing — no tokens, no
    chain, no DeFi), substantiating that the adapter and the agnostic core are domain-independent."""
    _python_project(
        tmp_path,
        {
            "procurement.py": (
                "def submit_purchase_order(order):\n"
                "    return route_for_approval(order)\n\n"
                "def route_for_approval(order):\n"
                "    return assign_approver(order)\n"
            ),
            "approvers.py": (
                "def assign_approver(order):\n"
                "    return 'department_manager'\n"
            ),
        },
    )
    manifest = _manifest(
        [
            {
                "module_id": "procurement",
                "path": "procurement.py",
                "symbols": ["submit_purchase_order", "route_for_approval"],
            },
            {"module_id": "approvers", "path": "approvers.py", "symbols": ["assign_approver"]},
        ]
    )
    adapter = PythonSourceLanguageAdapter(project_root=tmp_path)

    resolved = adapter.resolve_symbol(SymbolRef(name="submit_purchase_order"), manifest)
    assert resolved.status == "resolved"
    assert resolved.symbols[0].symbol_type == "function"
    assert resolved.symbols[0].metadata["analysis"] == "ast"

    call_graph = adapter.call_graph(manifest)
    edges = {(edge.caller, edge.callee) for edge in call_graph.edges}
    # The real ast call graph follows the approval routing across modules.
    assert ("procurement:submit_purchase_order", "procurement:route_for_approval") in edges
    assert ("procurement:route_for_approval", "approvers:assign_approver") in edges
    assert call_graph.metadata["analysis"] == "ast"

    # The same adapter certifies on this non-DeFi domain, at the honest static_resolution level.
    report = certify_adapter(
        adapter,
        manifest,
        symbol_refs=[SymbolRef(name="submit_purchase_order")],
        required_capabilities=["static_symbol_resolution", "call_graph"],
    )
    assert report.result == "certified"
    assert report.level == "static_resolution"


def test_typescript_rust_java_stay_honest_at_static_resolution(tmp_path: Path) -> None:
    """PC-14(c): the TypeScript / Rust / Java adapters are NOT wired to their real tooling, so each
    declares static_resolution, claims no trace level, and records an external-trace-producer reason —
    they must never masquerade as trace_capable."""
    adapters = [
        TypeScriptSourceAdapter(project_root=tmp_path),
        RustSourceAdapter(project_root=tmp_path),
        JavaSourceAdapter(project_root=tmp_path),
    ]
    for adapter in adapters:
        contract = adapter.capability_contract()
        assert contract.capability_level == "static_resolution", adapter.adapter_id
        assert all(
            claim.level not in _TRACE_LEVELS for claim in contract.capabilities
        ), adapter.adapter_id
        # A recorded reason their real tooling is not wired: an external-trace-producer limitation.
        assert any(
            limitation.category == "runtime_trace" for limitation in contract.limitations
        ), adapter.adapter_id
        # No over-claim under the shared honesty rule (no provenanced traces, static achieved level).
        assert trace_evidence_violations(contract, provenanced_trace_count=0) == [], adapter.adapter_id
        assert (
            capability_overclaim_violations(contract, achieved_level="static_resolution") == []
        ), adapter.adapter_id
