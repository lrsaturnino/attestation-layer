from pathlib import Path

from nlreq.adapter_certification import (
    AdapterCertificationFixture,
    build_adapter_plugin_manifest,
    certify_adapter,
    validate_adapter_plugin_manifest,
)
from nlreq.cli import main
from nlreq.jsonutil import read_json
from nlreq.models import NormalizedTraceArtifact, SymbolRef
from nlreq.production_source_adapters import production_adapter_for_language
from nlreq.source_adapter import SourceManifest


def test_phase138_adapter_interface_v2_capability_contract_blocks_missing_claims(
    tmp_path: Path,
) -> None:
    (tmp_path / "Bridge.sol").write_text(
        "contract Bridge { function requestRedemption() public {} }\n"
    )
    manifest = _manifest(
        adapter="solidity-source",
        language="solidity",
        runtime="evm",
        path="Bridge.sol",
        module_id="bridge",
        symbols=["requestRedemption"],
    )
    adapter = production_adapter_for_language("solidity", project_root=tmp_path)

    contract = adapter.capability_contract()
    certified = certify_adapter(
        adapter,
        manifest,
        symbol_refs=[SymbolRef(name="requestRedemption")],
        required_capabilities=["static_symbol_resolution", "code_presentation"],
    )
    blocked = certify_adapter(
        adapter,
        manifest,
        symbol_refs=[SymbolRef(name="requestRedemption")],
        required_capabilities=["specula_candidate_extraction"],
    )

    assert contract.schema_version == "0.2"
    assert contract.interface_version == "2.0"
    assert contract.ecosystem == "transaction_event"
    assert {"static_symbol_resolution", "normalized_trace"} <= {
        claim.capability_id for claim in contract.capabilities
    }
    assert certified.result == "certified"
    assert certified.source_presentation_snippets == 1
    assert blocked.result == "blocked"
    assert blocked.missing_capabilities == ["specula_candidate_extraction"]


def test_phase139_solidity_graduation_blocks_overloads_and_normalizes_traces(
    tmp_path: Path,
) -> None:
    (tmp_path / "Ambiguous.sol").write_text(
        "contract Bridge {\n"
        "  function requestRedemption(uint256 amount) public {}\n"
        "  function requestRedemption(address wallet) public {}\n"
        "}\n"
    )
    ambiguous_manifest = _manifest(
        adapter="solidity-source",
        language="solidity",
        runtime="evm",
        path="Ambiguous.sol",
        module_id="bridge",
        symbols=["requestRedemption"],
    )
    adapter = production_adapter_for_language("solidity", project_root=tmp_path)

    ambiguous = certify_adapter(
        adapter,
        ambiguous_manifest,
        symbol_refs=[SymbolRef(name="requestRedemption")],
    )

    assert ambiguous.result == "blocked"
    assert ambiguous.findings[0].category == "symbol_resolution"
    assert "ambiguous" in ambiguous.findings[0].message

    (tmp_path / "Bridge.sol").write_text(
        "contract Bridge {\n"
        "  event Redeemed(address user);\n"
        "  function requestRedemption() public { emit Redeemed(msg.sender); }\n"
        "}\n"
    )
    trace_path = _write_traces(tmp_path, adapter_id="external-solidity", language="solidity", runtime=None)
    manifest = _manifest(
        adapter="solidity-source",
        language="solidity",
        runtime="evm",
        path="Bridge.sol",
        module_id="bridge",
        symbols=["requestRedemption", "Redeemed"],
        trace_sources=[trace_path.name],
    )
    event_resolution = adapter.resolve_symbol(SymbolRef(name="Redeemed"), manifest)
    certified = certify_adapter(
        adapter,
        manifest,
        symbol_refs=[SymbolRef(name="requestRedemption")],
        required_capabilities=["normalized_trace", "runtime_trace_extraction"],
    )

    assert event_resolution.status == "resolved"
    assert event_resolution.symbols[0].metadata["binding_role"] == "event"
    assert certified.result == "certified"
    assert certified.level == "production_candidate"
    assert certified.trace_count == 1


def test_phase140_go_graduation_certifies_package_graph_and_runtime_trace(
    tmp_path: Path,
) -> None:
    (tmp_path / "service.go").write_text(
        "package redemption\n\n"
        "func Redeem() { Audit() }\n"
        "func Audit() {}\n"
        "type Wallet struct {}\n"
    )
    trace_path = _write_traces(tmp_path, adapter_id="go-source", language=None, runtime=None)
    manifest = _manifest(
        adapter="go-source",
        language="go",
        runtime="go",
        path="service.go",
        module_id="redemption",
        symbols=["Redeem", "Audit", "Wallet"],
        trace_sources=[trace_path.name],
    )
    adapter = production_adapter_for_language("go", project_root=tmp_path)

    graph = adapter.call_graph(manifest)
    report = certify_adapter(
        adapter,
        manifest,
        symbol_refs=[SymbolRef(name="Redeem")],
        required_capabilities=["call_graph", "normalized_trace"],
    )

    assert ("redemption:Redeem", "redemption:Audit") in {
        (edge.caller, edge.callee) for edge in graph.edges
    }
    assert graph.metadata["package_count"] == "1"
    assert report.result == "certified"
    assert report.level == "production_candidate"
    assert report.trace_count == 1


def test_phase141_typescript_and_javascript_graduation_exposes_dynamic_limits(
    tmp_path: Path,
) -> None:
    (tmp_path / "handler.ts").write_text(
        "export interface Request { id: string }\n"
        "export async function handleRequest() { return renderState(); }\n"
        "export const renderState = () => true;\n"
    )
    ts_manifest = _manifest(
        adapter="typescript-source",
        language="typescript",
        runtime="node",
        path="handler.ts",
        module_id="frontend",
        symbols=["Request", "handleRequest", "renderState"],
    )
    ts_adapter = production_adapter_for_language("typescript", project_root=tmp_path)
    ts_report = certify_adapter(
        ts_adapter,
        ts_manifest,
        symbol_refs=[SymbolRef(name="handleRequest")],
        required_capabilities=["static_symbol_resolution"],
    )

    (tmp_path / "handler.js").write_text(
        "export function handleClick() { return renderState(); }\n"
        "export const renderState = () => true;\n"
    )
    js_manifest = _manifest(
        adapter="javascript-source",
        language="javascript",
        runtime="node",
        path="handler.js",
        module_id="frontend-js",
        symbols=["handleClick", "renderState"],
    )
    js_adapter = production_adapter_for_language("javascript", project_root=tmp_path)
    js_report = certify_adapter(
        js_adapter,
        js_manifest,
        symbol_refs=[SymbolRef(name="handleClick")],
        required_capabilities=["static_symbol_resolution"],
    )

    assert ts_report.result == "certified"
    assert ts_report.capability_contract.ecosystem == "frontend_service"
    assert js_report.result == "certified"
    assert any(
        limitation.limitation_id == "javascript-dynamic-properties"
        and limitation.closure_effect == "unsupported"
        for limitation in js_report.capability_contract.limitations
    )


def test_phase142_rust_and_java_pressure_test_compiled_ecosystems(tmp_path: Path) -> None:
    (tmp_path / "lib.rs").write_text(
        "pub fn redeem() { audit(); }\n"
        "pub fn audit() {}\n"
        "pub struct Wallet {}\n"
    )
    rust_manifest = _manifest(
        adapter="rust-source",
        language="rust",
        runtime="rust",
        path="lib.rs",
        module_id="redemption-rs",
        symbols=["redeem", "audit", "Wallet"],
    )
    rust_adapter = production_adapter_for_language("rust", project_root=tmp_path)
    rust_report = certify_adapter(
        rust_adapter,
        rust_manifest,
        symbol_refs=[SymbolRef(name="redeem")],
        required_capabilities=["call_graph"],
    )

    (tmp_path / "Service.java").write_text(
        "public class Service {\n"
        "  public void redeem(int amount) {}\n"
        "  public void redeem(String wallet) {}\n"
        "}\n"
    )
    java_manifest = _manifest(
        adapter="java-source",
        language="java",
        runtime="jvm",
        path="Service.java",
        module_id="redemption-java",
        symbols=["Service", "redeem"],
    )
    java_adapter = production_adapter_for_language("java", project_root=tmp_path)
    java_report = certify_adapter(
        java_adapter,
        java_manifest,
        symbol_refs=[SymbolRef(name="redeem")],
    )

    assert rust_report.result == "certified"
    assert rust_report.capability_contract.ecosystem == "compiled_system"
    assert java_report.result == "blocked"
    assert java_report.missing_capabilities == []
    assert "ambiguous" in java_report.findings[0].message


def test_phase143_plugin_sdk_manifest_validates_against_certification(
    tmp_path: Path,
    capsys,
) -> None:
    (tmp_path / "service.go").write_text("package redemption\nfunc Redeem() {}\n")
    manifest = _manifest(
        adapter="go-source",
        language="go",
        runtime="go",
        path="service.go",
        module_id="redemption",
        symbols=["Redeem"],
    )
    adapter = production_adapter_for_language("go", project_root=tmp_path)
    certification = certify_adapter(
        adapter,
        manifest,
        symbol_refs=[SymbolRef(name="Redeem")],
        required_capabilities=["static_symbol_resolution"],
    )
    fixture = AdapterCertificationFixture(
        fixture_id="go-redemption",
        manifest=manifest,
        required_symbols=[SymbolRef(name="Redeem")],
        required_capabilities=["static_symbol_resolution"],
    )
    plugin = build_adapter_plugin_manifest(
        plugin_id="go-plugin",
        package="example_go_adapter",
        entry_point="example_go_adapter:adapter",
        adapter=adapter,
        fixtures=[fixture],
    )
    accepted = validate_adapter_plugin_manifest(plugin, certification)
    blocked = validate_adapter_plugin_manifest(
        plugin.model_copy(update={"fixtures": []}),
        certification,
    )

    assert accepted.result == "accepted"
    assert blocked.result == "blocked"
    assert "certification fixture" in blocked.findings[0].message

    capabilities_out = tmp_path / "go-capabilities.json"
    exit_code = main(
        [
            "adapter-capabilities",
            "--language",
            "go",
            "--project-root",
            str(tmp_path),
            "--out",
            str(capabilities_out),
        ]
    )

    assert exit_code == 0
    assert "Adapter capability contract:" in capsys.readouterr().out
    assert read_json(capabilities_out)["interface_version"] == "2.0"


def _manifest(
    *,
    adapter: str,
    language: str,
    runtime: str,
    path: str,
    module_id: str,
    symbols: list[str],
    trace_sources: list[str] | None = None,
) -> SourceManifest:
    return SourceManifest.model_validate(
        {
            "schema_version": "0.1",
            "adapter": adapter,
            "language": language,
            "runtime": runtime,
            "modules": [
                {
                    "module_id": module_id,
                    "path": path,
                    "symbols": symbols,
                    "spec_refs": [f"spec:{module_id}"],
                    "trace_sources": trace_sources or [],
                }
            ],
        }
    )


def _write_traces(
    tmp_path: Path,
    *,
    adapter_id: str,
    language: str | None,
    runtime: str | None,
) -> Path:
    path = tmp_path / "traces.json"
    path.write_text(
        NormalizedTraceArtifact.model_validate(
            [
                {
                    "trace_id": "trace-13",
                    "adapter_id": adapter_id,
                    "source_hash": "sha256:trace-source",
                    "language": language,
                    "runtime": runtime,
                    "events": [
                        {
                            "event_id": "event-1",
                            "timestamp": "2026-06-03T00:00:00Z",
                            "action": "Redeem",
                        }
                    ],
                }
            ]
        ).model_dump_json()
    )
    return path
