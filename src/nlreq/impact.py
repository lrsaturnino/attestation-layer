from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from .source_adapter import SourceLanguageAdapter, SourceManifest


IMPACT_SCHEMA_VERSION = "0.1"


class ImpactAnalysisArtifact(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["0.1"] = IMPACT_SCHEMA_VERSION
    adapter_id: str
    language: str
    input_symbols: list[str]
    affected_modules: list[str]
    call_graph_edges: list[dict[str, str]] = Field(default_factory=list)
    metadata: dict[str, str] = Field(default_factory=dict)


def analyze_source_impact(
    adapter: SourceLanguageAdapter,
    manifest: SourceManifest,
    *,
    symbols: list[str],
) -> ImpactAnalysisArtifact:
    direct_modules = {
        module.module_id
        for module in manifest.modules
        if any(symbol in module.symbols for symbol in symbols)
    }
    graph = adapter.call_graph(manifest)
    affected = set(direct_modules)
    changed = True
    while changed:
        changed = False
        for edge in graph.edges:
            caller_module = edge.caller.split(":", 1)[0]
            callee_module = edge.callee.split(":", 1)[0]
            if caller_module in affected and callee_module not in affected:
                affected.add(callee_module)
                changed = True
    return ImpactAnalysisArtifact(
        adapter_id=adapter.adapter_id,
        language=adapter.language,
        input_symbols=sorted(symbols),
        affected_modules=sorted(affected),
        call_graph_edges=[
            {"caller": edge.caller, "callee": edge.callee} for edge in graph.edges
        ],
        metadata={"mode": "deterministic_call_graph"},
    )
