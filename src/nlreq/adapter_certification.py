from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from .jsonutil import sha256_json
from .models import EvidenceLevel, SymbolRef
from .source_adapter import (
    AdapterCapabilityClaim,
    AdapterCapabilityContract,
    AdapterCapabilityKind,
    AdapterLimitation,
    SourceBinding,
    SourceLanguageAdapter,
    SourceManifest,
)


ADAPTER_CERTIFICATION_SCHEMA_VERSION = "0.2"
ADAPTER_CERTIFICATION_TOOL_VERSION = "0.2"
ADAPTER_PLUGIN_MANIFEST_SCHEMA_VERSION = "0.1"


AdapterCertificationLevel = Literal[
    "manifest_only",
    "static_resolution",
    "trace_capable",
    "production_candidate",
]


class AdapterCertificationFinding(BaseModel):
    model_config = ConfigDict(extra="forbid")

    category: Literal[
        "manifest",
        "capability_contract",
        "symbol_resolution",
        "binding_validation",
        "call_graph",
        "code_presentation",
        "trace_extraction",
        "plugin_sdk",
    ]
    severity: Literal["info", "blocking"]
    message: str
    subject: str | None = None


class AdapterCertificationFixture(BaseModel):
    model_config = ConfigDict(extra="forbid")

    fixture_id: str
    manifest: SourceManifest
    required_symbols: list[SymbolRef] = Field(default_factory=list)
    required_capabilities: list[AdapterCapabilityKind] = Field(default_factory=list)
    expected_minimum_level: AdapterCertificationLevel = "static_resolution"


class AdapterPluginManifest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["0.1"] = ADAPTER_PLUGIN_MANIFEST_SCHEMA_VERSION
    plugin_id: str
    package: str
    entry_point: str
    adapter_id: str
    language: str
    runtime: str | None = None
    capability_contract: AdapterCapabilityContract
    fixtures: list[AdapterCertificationFixture] = Field(default_factory=list)


class AdapterPluginValidationReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["0.1"] = ADAPTER_PLUGIN_MANIFEST_SCHEMA_VERSION
    plugin_id: str
    adapter_id: str
    result: Literal["accepted", "blocked"]
    findings: list[AdapterCertificationFinding] = Field(default_factory=list)
    input_hashes: dict[str, str] = Field(default_factory=dict)


class AdapterCertificationReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["0.2"] = ADAPTER_CERTIFICATION_SCHEMA_VERSION
    interface_version: Literal["2.0"] = "2.0"
    adapter_id: str
    language: str
    result: Literal["certified", "blocked"]
    level: AdapterCertificationLevel
    capability_contract: AdapterCapabilityContract
    required_capabilities: list[str] = Field(default_factory=list)
    missing_capabilities: list[str] = Field(default_factory=list)
    supported_evidence: list[EvidenceLevel] = Field(default_factory=list)
    limitation_ids: list[str] = Field(default_factory=list)
    findings: list[AdapterCertificationFinding] = Field(default_factory=list)
    resolved_symbols: int = 0
    unresolved_symbols: int = 0
    call_graph_edges: int = 0
    source_presentation_snippets: int = 0
    trace_count: int = 0
    plugin_sdk_compatible: bool = False
    input_hashes: dict[str, str] = Field(default_factory=dict)
    tool: str = "nlreq.adapter_certification"
    tool_version: str = ADAPTER_CERTIFICATION_TOOL_VERSION


def certify_adapter(
    adapter: SourceLanguageAdapter,
    manifest: SourceManifest,
    *,
    symbol_refs: list[SymbolRef],
    required_capabilities: list[AdapterCapabilityKind] | None = None,
) -> AdapterCertificationReport:
    findings: list[AdapterCertificationFinding] = []
    required_capabilities = list(required_capabilities or [])
    contract = _capability_contract(adapter, findings)
    if manifest.adapter != adapter.adapter_id:
        findings.append(
            AdapterCertificationFinding(
                category="manifest",
                severity="blocking",
                message=(
                    f"manifest adapter mismatch: expected {adapter.adapter_id}, "
                    f"found {manifest.adapter}"
                ),
            )
        )
    if manifest.language != adapter.language:
        findings.append(
            AdapterCertificationFinding(
                category="manifest",
                severity="blocking",
                message=(
                    f"manifest language mismatch: expected {adapter.language}, "
                    f"found {manifest.language}"
                ),
            )
        )
    if contract.adapter_id != adapter.adapter_id:
        findings.append(
            AdapterCertificationFinding(
                category="capability_contract",
                severity="blocking",
                message=(
                    f"capability contract adapter mismatch: expected {adapter.adapter_id}, "
                    f"found {contract.adapter_id}"
                ),
            )
        )
    if contract.language != adapter.language:
        findings.append(
            AdapterCertificationFinding(
                category="capability_contract",
                severity="blocking",
                message=(
                    f"capability contract language mismatch: expected {adapter.language}, "
                    f"found {contract.language}"
                ),
            )
        )
    missing_capabilities = _missing_capabilities(contract, required_capabilities)
    for capability in missing_capabilities:
        findings.append(
            AdapterCertificationFinding(
                category="capability_contract",
                severity="blocking",
                subject=capability,
                message=f"required adapter capability is not declared: {capability}",
            )
        )
    findings.extend(_method_findings(adapter, contract))
    if not manifest.modules:
        findings.append(
            AdapterCertificationFinding(
                category="manifest",
                severity="blocking",
                message="manifest has no modules",
            )
        )
    resolved = 0
    unresolved = 0
    resolved_bindings = []
    for ref in symbol_refs:
        resolution = adapter.resolve_symbol(ref, manifest)
        if resolution.status == "resolved":
            resolved += 1
            resolved_bindings.extend(
                SourceBinding(adapter_id=adapter.adapter_id, symbol=symbol)
                for symbol in resolution.symbols
            )
        else:
            unresolved += 1
            findings.append(
                AdapterCertificationFinding(
                    category="symbol_resolution",
                    severity="blocking",
                    subject=ref.name,
                    message=f"symbol resolution status is {resolution.status}",
                )
            )
    for binding in resolved_bindings:
        validation = adapter.validate_binding(binding)
        if not validation.valid:
            findings.append(
                AdapterCertificationFinding(
                    category="binding_validation",
                    severity="blocking",
                    subject=binding.symbol.name,
                    message=validation.reason or "binding validation failed",
                )
            )
    try:
        call_graph = adapter.call_graph(manifest)
        call_graph_edges = len(call_graph.edges)
    except Exception as exc:  # pragma: no cover - defensive certification boundary
        call_graph_edges = 0
        findings.append(
            AdapterCertificationFinding(
                category="call_graph",
                severity="blocking",
                message=f"call graph extraction raised {type(exc).__name__}: {exc}",
            )
        )
    try:
        presentation = adapter.present_to_llm(symbol_refs, manifest)
        source_presentation_snippets = len(presentation.snippets)
    except Exception as exc:  # pragma: no cover - defensive certification boundary
        source_presentation_snippets = 0
        findings.append(
            AdapterCertificationFinding(
                category="code_presentation",
                severity="blocking",
                message=f"source presentation raised {type(exc).__name__}: {exc}",
            )
        )
    if resolved and "code_presentation" in required_capabilities and source_presentation_snippets == 0:
        findings.append(
            AdapterCertificationFinding(
                category="code_presentation",
                severity="blocking",
                message="required code presentation capability emitted no source snippets",
            )
        )
    trace_count = 0
    provenanced_trace_count = 0
    try:
        traces = adapter.extract_traces(manifest)
        trace_count = len(traces.root)
        # A trace counts as real-tool evidence only when it carries recorded producer provenance
        # (a captured tool + tool version) over a real artifact hash (source_hash). Traces ingested
        # from manifest-declared JSON have no producer, so they never lift the adapter above
        # static_resolution — the honesty gate the regex adapters must observe (PC-1).
        provenanced_trace_count = sum(
            1
            for trace in traces.root
            if trace.producer is not None
            and trace.producer.tool_version.strip()
            and trace.source_hash.strip()
        )
    except Exception as exc:  # pragma: no cover - defensive certification boundary
        findings.append(
            AdapterCertificationFinding(
                category="trace_extraction",
                severity="blocking",
                message=f"trace extraction raised {type(exc).__name__}: {exc}",
            )
        )
    trace_sources = [
        trace_source
        for module in manifest.modules
        for trace_source in module.trace_sources
    ]
    if trace_sources and not trace_count:
        findings.append(
            AdapterCertificationFinding(
                category="trace_extraction",
                severity="blocking",
                message="manifest declares trace sources but adapter emitted no traces",
            )
        )
    findings.extend(_trace_evidence_findings(contract, provenanced_trace_count))
    level = _level(
        resolved=resolved,
        unresolved=unresolved,
        edges=call_graph_edges,
        provenanced_traces=provenanced_trace_count,
    )
    blocked = any(finding.severity == "blocking" for finding in findings)
    return AdapterCertificationReport(
        adapter_id=adapter.adapter_id,
        language=adapter.language,
        result="blocked" if blocked else "certified",
        level=level,
        capability_contract=contract,
        required_capabilities=[str(capability) for capability in required_capabilities],
        missing_capabilities=missing_capabilities,
        supported_evidence=contract.supported_evidence,
        limitation_ids=[limitation.limitation_id for limitation in contract.limitations],
        findings=findings,
        resolved_symbols=resolved,
        unresolved_symbols=unresolved,
        call_graph_edges=call_graph_edges,
        source_presentation_snippets=source_presentation_snippets,
        trace_count=trace_count,
        plugin_sdk_compatible=not blocked and not missing_capabilities,
        input_hashes={
            "manifest": sha256_json(manifest),
            "symbol_refs": sha256_json(symbol_refs),
            "capability_contract": sha256_json(contract),
        },
    )


def build_adapter_plugin_manifest(
    *,
    plugin_id: str,
    package: str,
    entry_point: str,
    adapter: SourceLanguageAdapter,
    fixtures: list[AdapterCertificationFixture] | None = None,
) -> AdapterPluginManifest:
    contract = adapter.capability_contract()
    return AdapterPluginManifest(
        plugin_id=plugin_id,
        package=package,
        entry_point=entry_point,
        adapter_id=adapter.adapter_id,
        language=adapter.language,
        runtime=adapter.runtime,
        capability_contract=contract,
        fixtures=list(fixtures or []),
    )


def validate_adapter_plugin_manifest(
    manifest: AdapterPluginManifest,
    certification: AdapterCertificationReport,
) -> AdapterPluginValidationReport:
    findings: list[AdapterCertificationFinding] = []
    if manifest.adapter_id != certification.adapter_id:
        findings.append(
            AdapterCertificationFinding(
                category="plugin_sdk",
                severity="blocking",
                message=(
                    f"plugin adapter id {manifest.adapter_id} does not match "
                    f"certification adapter id {certification.adapter_id}"
                ),
            )
        )
    if manifest.language != certification.language:
        findings.append(
            AdapterCertificationFinding(
                category="plugin_sdk",
                severity="blocking",
                message=(
                    f"plugin language {manifest.language} does not match "
                    f"certification language {certification.language}"
                ),
            )
        )
    if manifest.capability_contract != certification.capability_contract:
        findings.append(
            AdapterCertificationFinding(
                category="plugin_sdk",
                severity="blocking",
                message="plugin capability contract does not match the certified contract",
            )
        )
    if certification.result != "certified":
        findings.append(
            AdapterCertificationFinding(
                category="plugin_sdk",
                severity="blocking",
                message="adapter certification did not pass",
            )
        )
    if not manifest.fixtures:
        findings.append(
            AdapterCertificationFinding(
                category="plugin_sdk",
                severity="blocking",
                message="plugin manifest must include at least one certification fixture",
            )
        )
    result = "blocked" if any(finding.severity == "blocking" for finding in findings) else "accepted"
    return AdapterPluginValidationReport(
        plugin_id=manifest.plugin_id,
        adapter_id=manifest.adapter_id,
        result=result,
        findings=findings,
        input_hashes={
            "plugin_manifest": sha256_json(manifest),
            "certification": sha256_json(certification),
        },
    )


def _capability_contract(
    adapter: SourceLanguageAdapter,
    findings: list[AdapterCertificationFinding],
) -> AdapterCapabilityContract:
    try:
        return adapter.capability_contract()
    except Exception as exc:  # pragma: no cover - defensive certification boundary
        findings.append(
            AdapterCertificationFinding(
                category="capability_contract",
                severity="blocking",
                message=f"capability contract raised {type(exc).__name__}: {exc}",
            )
        )
        return AdapterCapabilityContract(
            adapter_id=getattr(adapter, "adapter_id", "unknown"),
            language=getattr(adapter, "language", "unknown"),
            runtime=getattr(adapter, "runtime", None),
            capabilities=[
                AdapterCapabilityClaim(capability_id="manifest", level="manifest_only"),
            ],
            limitations=[
                AdapterLimitation(
                    limitation_id="missing-capability-contract",
                    category="tooling",
                    description="Adapter did not expose a valid v2 capability contract.",
                    closure_effect="block",
                )
            ],
        )


def _missing_capabilities(
    contract: AdapterCapabilityContract,
    required_capabilities: list[AdapterCapabilityKind],
) -> list[str]:
    declared = {claim.capability_id for claim in contract.capabilities}
    return sorted(str(capability) for capability in required_capabilities if capability not in declared)


def _method_findings(
    adapter: SourceLanguageAdapter,
    contract: AdapterCapabilityContract,
) -> list[AdapterCertificationFinding]:
    findings: list[AdapterCertificationFinding] = []
    for method in contract.required_methods:
        if not callable(getattr(adapter, method, None)):
            findings.append(
                AdapterCertificationFinding(
                    category="capability_contract",
                    severity="blocking",
                    subject=method,
                    message=f"required source adapter method is not callable: {method}",
                )
            )
    return findings


_TRACE_LEVELS: frozenset[AdapterCapabilityLevel] = frozenset(
    {"trace_capable", "production_candidate"}
)


def _trace_evidence_findings(
    contract: AdapterCapabilityContract,
    provenanced_trace_count: int,
) -> list[AdapterCertificationFinding]:
    """Block a contract that claims a trace level it did not evidence with real-tool provenance.

    PC-1.T2: a ``trace_capable``/``production_candidate`` capability requires a recorded trace
    producer plus tool-version evidence. We honour that empirically — the claim is only evidenced
    when ``extract_traces`` actually yields traces carrying producer provenance over a real artifact
    hash. A purely lexical adapter that declares such a level (whether on the contract as a whole or
    on a single capability claim) but produces no provenanced traces is over-claiming, so it fails
    certification.
    """
    if provenanced_trace_count > 0:
        return []
    findings: list[AdapterCertificationFinding] = []
    if contract.capability_level in _TRACE_LEVELS:
        findings.append(
            AdapterCertificationFinding(
                category="capability_contract",
                severity="blocking",
                subject=contract.capability_level,
                message=(
                    f"capability contract declares level {contract.capability_level} but trace "
                    "extraction produced no traces with recorded real-tool provenance (a captured "
                    "tool version and a real artifact hash)"
                ),
            )
        )
    for claim in contract.capabilities:
        if claim.level in _TRACE_LEVELS:
            findings.append(
                AdapterCertificationFinding(
                    category="capability_contract",
                    severity="blocking",
                    subject=str(claim.capability_id),
                    message=(
                        f"capability {claim.capability_id} claims {claim.level} without a recorded "
                        "trace producer + tool-version evidence; trace extraction produced no "
                        "provenanced traces"
                    ),
                )
            )
    return findings


def _level(
    *,
    resolved: int,
    unresolved: int,
    edges: int,
    provenanced_traces: int,
) -> AdapterCertificationLevel:
    """The capability level the adapter empirically *achieved* on this run.

    A trace level is reachable only with real-tool provenance: ingested JSON (``provenanced_traces``
    == 0) never lifts the adapter past static_resolution. production_candidate is the complete,
    tool-backed vertical — symbol resolution, a call graph, and provenanced traces all present.
    """
    if resolved == 0 or unresolved > 0:
        return "manifest_only"
    if provenanced_traces > 0 and edges > 0:
        return "production_candidate"
    if provenanced_traces > 0:
        return "trace_capable"
    if edges > 0 or resolved > 0:
        return "static_resolution"
    return "manifest_only"
