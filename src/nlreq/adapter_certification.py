from __future__ import annotations

import hashlib
import json
import re
from typing import Iterable, Literal

from pydantic import BaseModel, ConfigDict, Field

from .jsonutil import sha256_json
from .models import EvidenceLevel, NormalizedTrace, SymbolRef
from .source_adapter import (
    AdapterCapabilityClaim,
    AdapterCapabilityContract,
    AdapterCapabilityKind,
    AdapterCapabilityLevel,
    AdapterLimitation,
    SourceBinding,
    SourceCallGraph,
    SourceLanguageAdapter,
    SourceManifest,
)


# A real artifact hash is a genuine sha256 digest: the literal prefix plus 64 lowercase hex chars,
# as ``hashlib.sha256(...).hexdigest()`` produces. The trace-evidence gate requires this exact shape
# so a placeholder like ``sha256:ingested`` cannot masquerade as a real tool artifact hash.
_REAL_ARTIFACT_HASH = re.compile(r"^sha256:[0-9a-f]{64}$")

_TRACE_LEVELS: frozenset[AdapterCapabilityLevel] = frozenset(
    {"trace_capable", "production_candidate"}
)


def _recomputed_artifact_hash(raw_output: str) -> str:
    """The sha256 digest of a captured raw tool artifact, in the ``sha256:<hex>`` form the tool
    clients record (byte-for-byte identical to ``foundry_client``'s ``raw_output_hash``)."""
    return "sha256:" + hashlib.sha256(raw_output.encode("utf-8")).hexdigest()


def _forge_report_is_well_formed(raw_output: str, trace: NormalizedTrace) -> bool:
    """Whether ``raw_output`` is a genuine ``forge test --json`` report (not normalized-trace JSON).

    A real forge report is a JSON *object* keyed by suite id, each suite carrying a ``test_results``
    object whose per-test values carry a ``traces`` field — the nesting forge emits. A normalized
    trace artifact serializes as a JSON *array* and a single ``NormalizedTrace`` as an object with
    ``events``/``producer`` (no ``test_results``), so neither passes. When the trace records its own
    ``suite``/``test`` in metadata (the Foundry path does), those names must appear in the report,
    binding this specific trace to the forge run.
    """
    try:
        report = json.loads(raw_output)
    except (json.JSONDecodeError, ValueError):
        return False
    if not isinstance(report, dict) or not report:
        return False
    # Require AT LEAST ONE forge-shaped suite (suite -> test_results -> test -> traces) rather than
    # demanding every top-level value be a suite: forge's --json may carry non-suite top-level keys
    # (warnings/metadata), and rejecting on those would false-negative a REAL forge trace and cap
    # certification at static_resolution. A normalized-trace blob still has no forge-shaped suite (its
    # producer/metadata sub-objects carry no ``test_results``), so it is still rejected.
    forge_shaped = False
    for suite in report.values():
        if not isinstance(suite, dict):
            continue
        test_results = suite.get("test_results")
        if not isinstance(test_results, dict):
            continue
        for test in test_results.values():
            if isinstance(test, dict) and "traces" in test:
                forge_shaped = True
                break
        if forge_shaped:
            break
    if not forge_shaped:
        return False
    suite_name = trace.metadata.get("suite")
    if isinstance(suite_name, str) and suite_name and suite_name not in report:
        return False
    test_name = trace.metadata.get("test")
    if isinstance(test_name, str) and test_name and not any(
        isinstance(suite, dict) and test_name in suite.get("test_results", {})
        for suite in report.values()
    ):
        return False
    return True


# Per-tool validators that confirm a producer's carried ``raw_output`` is a genuine artifact of that
# tool (not ingested JSON dressed up as provenance). Extended per vertical — Go/OTel producers (PC-7)
# register their own. A producer whose ``tool`` has no registered validator is not accepted as
# source-bound evidence, so the gate never over-trusts a tool it cannot verify.
_RAW_OUTPUT_VALIDATORS = {
    "forge": _forge_report_is_well_formed,
}


def trace_has_real_tool_provenance(trace: NormalizedTrace) -> bool:
    """Whether a trace carries SOURCE-BOUND real-tool provenance the capability gate accepts.

    Real-tool evidence is a recorded producer (the tool that ran plus its captured version string)
    over a *real artifact hash* — a genuine sha256 digest (``sha256:`` + 64 lowercase hex) of the
    tool's actual output. The gate is source-bound, not merely shape-bound: the producer must carry
    the captured ``raw_output`` it was projected from, ``sha256(raw_output)`` must equal the trace's
    ``source_hash``, AND ``raw_output`` must be a genuine artifact of ``producer.tool`` (a per-tool
    shape check). Stamping a producer + a self-consistent hash over ingested JSON cannot satisfy this
    — ingested JSON is not a forge report — which is the loophole PC-1 closes.

    Residual in-process ceiling (documented, not closeable here): an adapter that hand-builds a
    minimal forge-shaped artifact, or runs forge once and reuses its real output over unrelated
    traces, would also pass — there is no data-only way to distinguish that from a genuine run
    without re-executing the tool inside certification. The gate defeats the realistic, flagged
    attack (the lazy stamp-over-ingested-JSON path); the honest production path goes through the
    tool client, which is the trust anchor.
    """
    producer = trace.producer
    if producer is None:
        return False
    if not producer.tool.strip() or not producer.tool_version.strip():
        return False
    source_hash = trace.source_hash.strip()
    if not _REAL_ARTIFACT_HASH.match(source_hash):
        return False
    raw_output = producer.raw_output
    if raw_output is None:
        return False
    if _recomputed_artifact_hash(raw_output) != source_hash:
        return False
    validator = _RAW_OUTPUT_VALIDATORS.get(producer.tool.strip().lower())
    if validator is None:
        return False
    return validator(raw_output, trace)


def count_provenanced_traces(traces: Iterable[NormalizedTrace]) -> int:
    """How many traces carry real-tool provenance — the evidence count the gate scores against."""
    return sum(1 for trace in traces if trace_has_real_tool_provenance(trace))


def trace_evidence_violations(
    contract: AdapterCapabilityContract,
    provenanced_trace_count: int,
) -> list[tuple[str, str]]:
    """The shared trace-evidence honesty rule, as ``(subject, message)`` over-claim pairs.

    A ``trace_capable``/``production_candidate`` claim requires a recorded trace producer plus a
    captured tool version over a real artifact hash. When extraction yields no provenanced traces,
    every trace-level declaration — the whole-contract ``capability_level`` and each individual
    capability claim — is an over-claim. Both the certification suite and the conformance suite call
    this, so a regex/static adapter cannot pass *either* by declaring a trace level it cannot
    evidence (PC-1.T2).
    """
    if provenanced_trace_count > 0:
        return []
    violations: list[tuple[str, str]] = []
    if contract.capability_level in _TRACE_LEVELS:
        violations.append(
            (
                contract.capability_level,
                (
                    f"capability contract declares level {contract.capability_level} but trace "
                    "extraction produced no traces with recorded real-tool provenance (a captured "
                    "tool version and a real artifact hash)"
                ),
            )
        )
    for claim in contract.capabilities:
        if claim.level in _TRACE_LEVELS:
            violations.append(
                (
                    str(claim.capability_id),
                    (
                        f"capability {claim.capability_id} claims {claim.level} without a recorded "
                        "trace producer + tool-version evidence; trace extraction produced no "
                        "provenanced traces"
                    ),
                )
            )
    return violations


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
    # Whether the call graph came from a real static-analysis tool (Slither) with a recorded version,
    # rather than the regex fallback. production_candidate requires this: a regex/static call graph
    # caps the achieved level below production_candidate even when provenanced traces are present.
    call_graph_tool_backed: bool = False
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
        call_graph_tool_backed = _call_graph_is_tool_backed(call_graph)
    except Exception as exc:  # pragma: no cover - defensive certification boundary
        call_graph_edges = 0
        call_graph_tool_backed = False
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
        # (a captured tool + tool version) over a *real* artifact hash — a genuine sha256 digest, not
        # a placeholder. Traces ingested from manifest-declared JSON have no producer (and any stamped
        # placeholder hash fails the digest-shape check), so they never lift the adapter above
        # static_resolution — the honesty gate the regex adapters must observe (PC-1).
        provenanced_trace_count = count_provenanced_traces(traces.root)
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
        tool_backed_call_graph=call_graph_tool_backed,
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
        call_graph_tool_backed=call_graph_tool_backed,
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


def _trace_evidence_findings(
    contract: AdapterCapabilityContract,
    provenanced_trace_count: int,
) -> list[AdapterCertificationFinding]:
    """Block a contract that claims a trace level it did not evidence with real-tool provenance.

    PC-1.T2: a ``trace_capable``/``production_candidate`` capability requires a recorded trace
    producer plus tool-version evidence over a real artifact hash. The empirical check lives in the
    shared :func:`trace_evidence_violations` so the conformance suite enforces the same honesty rule;
    here we wrap each over-claim as a blocking certification finding.
    """
    return [
        AdapterCertificationFinding(
            category="capability_contract",
            severity="blocking",
            subject=subject,
            message=message,
        )
        for subject, message in trace_evidence_violations(contract, provenanced_trace_count)
    ]


def _call_graph_is_tool_backed(call_graph: SourceCallGraph) -> bool:
    """Whether the call graph came from a real static-analysis tool with a recorded version.

    production_candidate requires a tool-backed call graph (Slither for Solidity), not the regex
    fallback. The signal is the metadata the Slither-backed path records: an ``analyzed`` status AND
    a captured tool version (the regex fallback records neither). Unlike trace evidence — which is
    preimage-bound above — this call-graph signal is adapter-asserted: a malicious adapter could
    stamp ``slither_status=analyzed`` with a fabricated version. That asymmetry is deliberate and
    documented; tying the call-graph evidence to the tool client's captured output is a future
    tightening. What this gate guarantees now is that a *regex* fallback cannot reach
    production_candidate, which is the honesty boundary the HELPER flagged.
    """
    metadata = call_graph.metadata or {}
    return metadata.get("slither_status") == "analyzed" and bool(metadata.get("slither_version"))


def _level(
    *,
    resolved: int,
    unresolved: int,
    edges: int,
    provenanced_traces: int,
    tool_backed_call_graph: bool,
) -> AdapterCertificationLevel:
    """The capability level the adapter empirically *achieved* on this run.

    A trace level is reachable only with real-tool provenance: ingested JSON (``provenanced_traces``
    == 0) never lifts the adapter past static_resolution. production_candidate is the complete,
    tool-backed vertical — symbol resolution, a *tool-backed* call graph, and provenanced traces all
    present. A regex/static call graph (``tool_backed_call_graph`` False) caps the run at
    trace_capable even with provenanced traces: regex edges do not evidence production_candidate.
    """
    if resolved == 0 or unresolved > 0:
        return "manifest_only"
    if provenanced_traces > 0 and edges > 0 and tool_backed_call_graph:
        return "production_candidate"
    if provenanced_traces > 0:
        return "trace_capable"
    if edges > 0 or resolved > 0:
        return "static_resolution"
    return "manifest_only"
