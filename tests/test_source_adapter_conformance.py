import hashlib
from pathlib import Path

import pytest

from nlreq.adapter_certification import certify_adapter
from nlreq.javascript_source_adapter import JavaScriptSourceLanguageAdapter
from nlreq.models import (
    EvidenceLevel,
    NormalizedTraceArtifact,
    NormalizedTraceProducer,
    SymbolRef,
)
from nlreq.production_source_adapters import SoliditySourceAdapter
from nlreq.python_source_adapter import PythonSourceLanguageAdapter
from nlreq.source_adapter import AdapterCapabilityContract, SourceManifest
from nlreq.source_conformance import (
    SourceAdapterConformanceError,
    SourceAdapterConformanceFixture,
    assert_source_adapter_conforms,
)


def test_python_and_javascript_source_adapters_share_conformance_suite(
    tmp_path: Path,
) -> None:
    python_root = tmp_path / "python"
    javascript_root = tmp_path / "javascript"
    python_manifest = _python_project(python_root)
    javascript_manifest = _javascript_project(javascript_root)

    python_report = assert_source_adapter_conforms(
        PythonSourceLanguageAdapter(project_root=python_root),
        _fixture(python_manifest, ambiguous_ref="duplicate_symbol"),
    )
    javascript_report = assert_source_adapter_conforms(
        JavaScriptSourceLanguageAdapter(project_root=javascript_root),
        _fixture(javascript_manifest, ambiguous_ref="duplicateSymbol"),
    )

    assert python_report.checks == javascript_report.checks
    assert python_report.adapter_id == "python-source"
    assert javascript_report.adapter_id == "javascript-source"


def _fixture(
    manifest: SourceManifest, *, ambiguous_ref: str
) -> SourceAdapterConformanceFixture:
    return SourceAdapterConformanceFixture(
        manifest=manifest,
        resolved_ref=SymbolRef(name="operation"),
        unresolved_ref=SymbolRef(name="missingOperation"),
        ambiguous_ref=SymbolRef(name=ambiguous_ref),
    )


def _python_project(root: Path) -> SourceManifest:
    src = root / "src"
    src.mkdir(parents=True)
    (src / "auth.py").write_text(
        "from state import state_change\n\n"
        "def operation(actor):\n"
        "    return state_change(actor)\n\n"
        "def duplicate_symbol():\n"
        "    return 'auth'\n"
    )
    (src / "state.py").write_text(
        "def state_change(actor):\n"
        "    return actor\n\n"
        "def duplicate_symbol():\n"
        "    return 'state'\n"
    )
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
                    "symbols": ["operation", "duplicate_symbol"],
                },
                {
                    "module_id": "state",
                    "path": "src/state.py",
                    "symbols": ["state_change", "duplicate_symbol"],
                },
            ],
        }
    )


def _javascript_project(root: Path) -> SourceManifest:
    src = root / "src"
    src.mkdir(parents=True)
    (src / "auth.js").write_text(
        "import { stateChange } from './state.js';\n\n"
        "export function operation(actor) {\n"
        "  return stateChange(actor);\n"
        "}\n\n"
        "export function duplicateSymbol() {\n"
        "  return 'auth';\n"
        "}\n"
    )
    (src / "state.js").write_text(
        "export function stateChange(actor) {\n"
        "  return actor;\n"
        "}\n\n"
        "export function duplicateSymbol() {\n"
        "  return 'state';\n"
        "}\n"
    )
    return SourceManifest.model_validate(
        {
            "schema_version": "0.1",
            "adapter": "javascript-source",
            "language": "javascript",
            "runtime": "node",
            "modules": [
                {
                    "module_id": "auth",
                    "path": "src/auth.js",
                    "symbols": ["operation", "duplicateSymbol"],
                },
                {
                    "module_id": "state",
                    "path": "src/state.js",
                    "symbols": ["stateChange", "duplicateSymbol"],
                },
            ],
        }
    )


def _solidity_manifest(root: Path) -> SourceManifest:
    (root / "Bridge.sol").write_text(
        "// SPDX-License-Identifier: MIT\n"
        "pragma solidity ^0.8.13;\n"
        "contract Bridge {\n"
        "  function requestRedemption() public {}\n"
        "}\n"
    )
    return SourceManifest.model_validate(
        {
            "schema_version": "0.1",
            "adapter": "solidity-source",
            "language": "solidity",
            "runtime": "evm",
            "modules": [
                {
                    "module_id": "bridge",
                    "path": "Bridge.sol",
                    "symbols": ["requestRedemption"],
                }
            ],
        }
    )


class _OverclaimingSolidityAdapter(SoliditySourceAdapter):
    """A lexical adapter that dishonestly bumps a trace capability to trace_capable.

    It still ingests (does not produce) traces, so it has no real-tool provenance to back the
    claim — exactly the over-claim PC-1's certification gate must reject.
    """

    def capability_contract(self) -> AdapterCapabilityContract:
        contract = super().capability_contract()
        bumped = [
            claim.model_copy(update={"level": "trace_capable"})
            if claim.capability_id == "runtime_trace_extraction"
            else claim
            for claim in contract.capabilities
        ]
        return contract.model_copy(update={"capabilities": bumped})


class _ToolBackedSolidityAdapter(SoliditySourceAdapter):
    """A Solidity adapter that simulates a real trace producer.

    It stamps producer provenance onto each extracted trace and declares the matching
    trace_capable claim — the shape PC-4's Foundry-backed extraction takes, exercised here without
    requiring Foundry so the gate's positive branch is always covered.
    """

    def extract_traces(self, manifest: SourceManifest) -> NormalizedTraceArtifact:
        ingested = super().extract_traces(manifest)
        stamped = []
        for trace in ingested.root:
            # Mirror a real tool's artifact hash: a genuine sha256 of the produced output, not a
            # placeholder, so the tightened provenance gate accepts it as real-tool evidence.
            digest = hashlib.sha256(trace.model_dump_json().encode("utf-8")).hexdigest()
            stamped.append(
                trace.model_copy(
                    update={
                        "producer": NormalizedTraceProducer(
                            tool="forge", tool_version="forge 1.5.0-stable"
                        ),
                        "source_hash": f"sha256:{digest}",
                    }
                )
            )
        return NormalizedTraceArtifact.model_validate(stamped)

    def capability_contract(self) -> AdapterCapabilityContract:
        contract = super().capability_contract()
        bumped = [
            claim.model_copy(
                update={
                    "level": "trace_capable",
                    "evidence_labels": [EvidenceLevel.TRACE_VALIDATED],
                }
            )
            if claim.capability_id == "runtime_trace_extraction"
            else claim
            for claim in contract.capabilities
        ]
        return contract.model_copy(
            update={
                "capabilities": bumped,
                "supported_evidence": [
                    EvidenceLevel.STATICALLY_RESOLVED,
                    EvidenceLevel.TRACE_VALIDATED,
                    EvidenceLevel.REVIEWED,
                ],
            }
        )


class _PlaceholderHashSolidityAdapter(_OverclaimingSolidityAdapter):
    """Stamps producer metadata over a placeholder (non-sha256) artifact hash.

    This is the precise "stamp arbitrary producer metadata onto ingested JSON" attack the hardened
    gate must reject: a producer is present and the tool version is non-empty, but the artifact hash
    is not a real sha256 digest, so it is not real-tool evidence and the trace_capable claim stays
    unevidenced.
    """

    def extract_traces(self, manifest: SourceManifest) -> NormalizedTraceArtifact:
        ingested = super().extract_traces(manifest)
        stamped = [
            trace.model_copy(
                update={
                    "producer": NormalizedTraceProducer(
                        tool="forge", tool_version="forge 1.5.0-stable"
                    ),
                    "source_hash": "sha256:placeholder-not-a-real-digest",
                }
            )
            for trace in ingested.root
        ]
        return NormalizedTraceArtifact.model_validate(stamped)


def _write_ingested_trace(root: Path) -> str:
    path = root / "trace.json"
    path.write_text(
        NormalizedTraceArtifact.model_validate(
            [
                {
                    "trace_id": "trace-pc1",
                    "adapter_id": "external-producer",
                    "source_hash": "sha256:ingested",
                    "language": "solidity",
                    "runtime": "evm",
                    "events": [
                        {
                            "event_id": "e1",
                            "timestamp": "2026-06-08T00:00:00Z",
                            "action": "requestRedemption",
                        }
                    ],
                }
            ]
        ).model_dump_json()
    )
    return path.name


def test_regex_adapter_does_not_claim_a_trace_level_it_cannot_evidence(tmp_path: Path) -> None:
    """The honest default: a lexical Solidity adapter certifies at static_resolution.

    It declares no trace_capable capability and never advertises TRACE_VALIDATED evidence, so it
    cannot over-claim a runtime trace capability it does not have.
    """
    manifest = _solidity_manifest(tmp_path)
    adapter = SoliditySourceAdapter(project_root=tmp_path)

    contract = adapter.capability_contract()
    report = certify_adapter(
        adapter,
        manifest,
        symbol_refs=[SymbolRef(name="requestRedemption")],
        required_capabilities=["static_symbol_resolution", "runtime_trace_extraction"],
    )

    assert contract.capability_level == "static_resolution"
    assert EvidenceLevel.TRACE_VALIDATED not in contract.supported_evidence
    assert all(claim.level != "trace_capable" for claim in contract.capabilities)
    assert all(claim.level != "production_candidate" for claim in contract.capabilities)
    assert report.result == "certified"
    assert report.level == "static_resolution"


def test_trace_capable_claim_without_real_tool_evidence_fails_certification(
    tmp_path: Path,
) -> None:
    """PC-1 gate: a regex adapter that claims trace_capable without producing provenanced traces
    fails certification. Ingested JSON traces do not count as real-tool evidence."""
    manifest = _solidity_manifest(tmp_path)
    trace_source = _write_ingested_trace(tmp_path)
    manifest = manifest.model_copy(
        update={
            "modules": [
                manifest.modules[0].model_copy(update={"trace_sources": [trace_source]})
            ]
        }
    )
    adapter = _OverclaimingSolidityAdapter(project_root=tmp_path)

    report = certify_adapter(
        adapter,
        manifest,
        symbol_refs=[SymbolRef(name="requestRedemption")],
    )

    assert report.result == "blocked"
    assert report.trace_count == 1  # it ingested a trace, but the trace carries no producer
    blocking = [
        finding
        for finding in report.findings
        if finding.severity == "blocking"
        and finding.category == "capability_contract"
        and finding.subject == "runtime_trace_extraction"
    ]
    assert blocking, report.findings
    assert "without a recorded trace producer" in blocking[0].message


def test_trace_capable_claim_with_recorded_producer_evidence_certifies(tmp_path: Path) -> None:
    """PC-1 gate, positive branch: when extraction yields traces carrying recorded producer
    provenance over a real artifact hash, the trace_capable claim is evidenced and certifies."""
    manifest = _solidity_manifest(tmp_path)
    trace_source = _write_ingested_trace(tmp_path)
    manifest = manifest.model_copy(
        update={
            "modules": [
                manifest.modules[0].model_copy(update={"trace_sources": [trace_source]})
            ]
        }
    )
    adapter = _ToolBackedSolidityAdapter(project_root=tmp_path)

    report = certify_adapter(
        adapter,
        manifest,
        symbol_refs=[SymbolRef(name="requestRedemption")],
        required_capabilities=["runtime_trace_extraction"],
    )

    assert report.result == "certified"
    assert report.trace_count == 1
    assert report.level in {"trace_capable", "production_candidate"}


def test_trace_capable_claim_with_placeholder_artifact_hash_fails_certification(
    tmp_path: Path,
) -> None:
    """PC-1 hardening: a producer stamped over a placeholder hash is not real-tool evidence.

    The gate requires a genuine sha256 digest (``sha256:`` + 64 hex), so producer metadata over a
    non-digest hash cannot fake the trace_capable claim — it is blocked exactly like a producerless
    ingested trace."""
    manifest = _solidity_manifest(tmp_path)
    trace_source = _write_ingested_trace(tmp_path)
    manifest = manifest.model_copy(
        update={
            "modules": [
                manifest.modules[0].model_copy(update={"trace_sources": [trace_source]})
            ]
        }
    )
    adapter = _PlaceholderHashSolidityAdapter(project_root=tmp_path)

    report = certify_adapter(
        adapter,
        manifest,
        symbol_refs=[SymbolRef(name="requestRedemption")],
    )

    assert report.result == "blocked"
    assert report.trace_count == 1  # a producer-stamped trace was produced, but the hash is fake
    assert report.level == "static_resolution"
    blocking = [
        finding
        for finding in report.findings
        if finding.severity == "blocking"
        and finding.category == "capability_contract"
        and finding.subject == "runtime_trace_extraction"
    ]
    assert blocking, report.findings


def _solidity_conformance_project(root: Path) -> SourceManifest:
    """A two-contract Solidity project whose resolved/unresolved/ambiguous refs hold under both the
    Slither-backed and the lexical-fallback resolution paths (a same-named function in two unrelated
    contracts is ambiguous either way)."""
    src = root / "src"
    src.mkdir(parents=True)
    (src / "Auth.sol").write_text(
        "// SPDX-License-Identifier: MIT\n"
        "pragma solidity ^0.8.13;\n"
        "contract Auth {\n"
        "  function operation() public {}\n"
        "  function duplicateSymbol() public {}\n"
        "}\n"
    )
    (src / "State.sol").write_text(
        "// SPDX-License-Identifier: MIT\n"
        "pragma solidity ^0.8.13;\n"
        "contract State {\n"
        "  function stateChange() public {}\n"
        "  function duplicateSymbol() public {}\n"
        "}\n"
    )
    return SourceManifest.model_validate(
        {
            "schema_version": "0.1",
            "adapter": "solidity-source",
            "language": "solidity",
            "runtime": "evm",
            "modules": [
                {
                    "module_id": "auth",
                    "path": "src/Auth.sol",
                    "symbols": ["operation", "duplicateSymbol"],
                },
                {
                    "module_id": "state",
                    "path": "src/State.sol",
                    "symbols": ["stateChange", "duplicateSymbol"],
                },
            ],
        }
    )


def _solidity_conformance_fixture(manifest: SourceManifest) -> SourceAdapterConformanceFixture:
    return SourceAdapterConformanceFixture(
        manifest=manifest,
        resolved_ref=SymbolRef(name="operation"),
        unresolved_ref=SymbolRef(name="missingOperation"),
        ambiguous_ref=SymbolRef(name="duplicateSymbol"),
    )


def test_honest_solidity_adapter_passes_conformance(tmp_path: Path) -> None:
    """The honest adapter declares no trace level it cannot evidence, so it conforms — proving the
    over-claim rejection below is about the trace honesty gate, not a broken fixture."""
    manifest = _solidity_conformance_project(tmp_path)
    report = assert_source_adapter_conforms(
        SoliditySourceAdapter(project_root=tmp_path),
        _solidity_conformance_fixture(manifest),
    )
    assert "trace_capability_honesty" in report.checks


def test_conformance_rejects_static_adapter_claiming_trace_capable(tmp_path: Path) -> None:
    """PC-1 Action 1: the conformance suite — not only certification — rejects a static adapter that
    advertises trace_capable without producing traces carrying real-tool provenance."""
    manifest = _solidity_conformance_project(tmp_path)
    adapter = _OverclaimingSolidityAdapter(project_root=tmp_path)

    with pytest.raises(SourceAdapterConformanceError, match="trace capability over-claimed"):
        assert_source_adapter_conforms(adapter, _solidity_conformance_fixture(manifest))
