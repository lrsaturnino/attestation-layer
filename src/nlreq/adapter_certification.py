from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from .jsonutil import sha256_json
from .models import SymbolRef
from .source_adapter import SourceLanguageAdapter, SourceManifest


ADAPTER_CERTIFICATION_SCHEMA_VERSION = "0.1"
ADAPTER_CERTIFICATION_TOOL_VERSION = "0.1"


AdapterCertificationLevel = Literal[
    "manifest_only",
    "static_resolution",
    "trace_capable",
    "production_candidate",
]


class AdapterCertificationFinding(BaseModel):
    model_config = ConfigDict(extra="forbid")

    category: Literal["manifest", "symbol_resolution", "call_graph", "trace_extraction"]
    severity: Literal["info", "blocking"]
    message: str
    subject: str | None = None


class AdapterCertificationReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["0.1"] = ADAPTER_CERTIFICATION_SCHEMA_VERSION
    adapter_id: str
    language: str
    result: Literal["certified", "blocked"]
    level: AdapterCertificationLevel
    findings: list[AdapterCertificationFinding] = Field(default_factory=list)
    resolved_symbols: int = 0
    unresolved_symbols: int = 0
    call_graph_edges: int = 0
    trace_count: int = 0
    input_hashes: dict[str, str] = Field(default_factory=dict)
    tool: str = "nlreq.adapter_certification"
    tool_version: str = ADAPTER_CERTIFICATION_TOOL_VERSION


def certify_adapter_v2(
    adapter: SourceLanguageAdapter,
    manifest: SourceManifest,
    *,
    symbol_refs: list[SymbolRef],
) -> AdapterCertificationReport:
    findings: list[AdapterCertificationFinding] = []
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
    for ref in symbol_refs:
        resolution = adapter.resolve_symbol(ref, manifest)
        if resolution.status == "resolved":
            resolved += 1
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
    call_graph = adapter.call_graph(manifest)
    traces = adapter.extract_traces(manifest)
    trace_sources = [
        trace_source
        for module in manifest.modules
        for trace_source in module.trace_sources
    ]
    if trace_sources and not traces.root:
        findings.append(
            AdapterCertificationFinding(
                category="trace_extraction",
                severity="blocking",
                message="manifest declares trace sources but adapter emitted no traces",
            )
        )
    level = _level(
        resolved=resolved,
        unresolved=unresolved,
        edges=len(call_graph.edges),
        traces=len(traces.root),
        trace_sources=len(trace_sources),
    )
    blocked = any(finding.severity == "blocking" for finding in findings)
    return AdapterCertificationReport(
        adapter_id=adapter.adapter_id,
        language=adapter.language,
        result="blocked" if blocked else "certified",
        level=level,
        findings=findings,
        resolved_symbols=resolved,
        unresolved_symbols=unresolved,
        call_graph_edges=len(call_graph.edges),
        trace_count=len(traces.root),
        input_hashes={
            "manifest": sha256_json(manifest),
            "symbol_refs": sha256_json(symbol_refs),
        },
    )


def _level(
    *,
    resolved: int,
    unresolved: int,
    edges: int,
    traces: int,
    trace_sources: int,
) -> AdapterCertificationLevel:
    if resolved == 0 or unresolved > 0:
        return "manifest_only"
    if trace_sources and traces > 0:
        return "production_candidate"
    if traces > 0:
        return "trace_capable"
    if edges > 0 or resolved > 0:
        return "static_resolution"
    return "manifest_only"
