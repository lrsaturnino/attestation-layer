from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from .models import NormalizedTraceArtifact
from .source_adapter import SourceLanguageAdapter, SourceManifest


IMPACT_V2_SCHEMA_VERSION = "0.1"


class SemanticImpactSuggestion(BaseModel):
    model_config = ConfigDict(extra="forbid")

    module_id: str
    reason: str
    source: Literal["llm", "manual", "heuristic"] = "heuristic"


class ImpactDisagreement(BaseModel):
    model_config = ConfigDict(extra="forbid")

    module_id: str
    deterministic: bool
    semantic_suggestion: bool
    trace_touched: bool
    reason: str


class ImpactAnalysisV2Artifact(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["0.1"] = IMPACT_V2_SCHEMA_VERSION
    adapter_id: str
    language: str
    input_symbols: list[str]
    affected_modules: list[str]
    deterministic_modules: list[str]
    trace_touched_modules: list[str] = Field(default_factory=list)
    semantic_suggestions: list[SemanticImpactSuggestion] = Field(default_factory=list)
    disagreements: list[ImpactDisagreement] = Field(default_factory=list)
    call_graph_edges: list[dict[str, str]] = Field(default_factory=list)
    metadata: dict[str, str] = Field(default_factory=dict)


def analyze_source_impact_v2(
    adapter: SourceLanguageAdapter,
    manifest: SourceManifest,
    *,
    symbols: list[str],
    traces: NormalizedTraceArtifact | None = None,
    semantic_suggestions: list[SemanticImpactSuggestion] | None = None,
) -> ImpactAnalysisV2Artifact:
    graph = adapter.call_graph(manifest)
    direct_modules = {
        module.module_id
        for module in manifest.modules
        if any(symbol in module.symbols for symbol in symbols)
    }
    deterministic = _expand_call_graph(direct_modules, graph.edges)
    trace_modules = _trace_touched_modules(traces)
    suggestions = semantic_suggestions or []
    suggested_modules = {suggestion.module_id for suggestion in suggestions}
    affected = deterministic | trace_modules
    disagreements = _disagreements(deterministic, trace_modules, suggested_modules)
    return ImpactAnalysisV2Artifact(
        adapter_id=adapter.adapter_id,
        language=adapter.language,
        input_symbols=sorted(symbols),
        affected_modules=sorted(affected),
        deterministic_modules=sorted(deterministic),
        trace_touched_modules=sorted(trace_modules),
        semantic_suggestions=suggestions,
        disagreements=disagreements,
        call_graph_edges=[
            {"caller": edge.caller, "callee": edge.callee} for edge in graph.edges
        ],
        metadata={"mode": "deterministic_call_graph_with_trace_touchpoints"},
    )


def _expand_call_graph(direct_modules: set[str], edges) -> set[str]:
    affected = set(direct_modules)
    changed = True
    while changed:
        changed = False
        for edge in edges:
            caller_module = edge.caller.split(":", 1)[0]
            callee_module = edge.callee.split(":", 1)[0]
            if caller_module in affected and callee_module not in affected:
                affected.add(callee_module)
                changed = True
            if callee_module in affected and caller_module not in affected:
                affected.add(caller_module)
                changed = True
    return affected


def _trace_touched_modules(traces: NormalizedTraceArtifact | None) -> set[str]:
    if traces is None:
        return set()
    modules: set[str] = set()
    for trace in traces.root:
        module_id = trace.metadata.get("module_id")
        if isinstance(module_id, str):
            modules.add(module_id)
        for event in trace.events:
            event_module = event.metadata.get("module_id")
            if isinstance(event_module, str):
                modules.add(event_module)
    return modules


def _disagreements(
    deterministic: set[str],
    trace_modules: set[str],
    suggested_modules: set[str],
) -> list[ImpactDisagreement]:
    disagreements: list[ImpactDisagreement] = []
    for module_id in sorted(suggested_modules - deterministic):
        disagreements.append(
            ImpactDisagreement(
                module_id=module_id,
                deterministic=False,
                semantic_suggestion=True,
                trace_touched=module_id in trace_modules,
                reason="semantic suggestion is outside deterministic impact",
            )
        )
    for module_id in sorted(trace_modules - deterministic):
        disagreements.append(
            ImpactDisagreement(
                module_id=module_id,
                deterministic=False,
                semantic_suggestion=module_id in suggested_modules,
                trace_touched=True,
                reason="runtime trace touched module outside deterministic impact",
            )
        )
    return disagreements
