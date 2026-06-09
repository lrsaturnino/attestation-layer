from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from .llm_client import LlmClient, parse_impact_estimate
from .source_adapter import SourceLanguageAdapter, SourceManifest


IMPACT_SCHEMA_VERSION = "0.1"
IMPACT_CROSS_VALIDATION_SCHEMA_VERSION = "0.1"


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


class ImpactCrossValidationFlag(BaseModel):
    model_config = ConfigDict(extra="forbid")

    severity: Literal["review", "info"]
    category: Literal["call_graph_only", "semantic_only"]
    module_id: str
    message: str


class ImpactCrossValidationReport(BaseModel):
    """The call-graph-derived affected set cross-validated against a semantic (LLM) estimate (PC-9).

    The AUTHORITATIVE affected set is ``affected_modules`` — it is the call-graph-reachable set from
    :func:`analyze_source_impact`, never the LLM estimate. The semantic estimate is UNTRUSTED and is
    used only to surface agreement/disagreement: a module the call graph reaches but the estimate
    omits, or a module the estimate names but the call graph never reaches, is recorded as a review
    ``flag`` rather than silently reconciled. A semantic-only module is deliberately NOT folded into
    the gateable affected set — the call graph stays the source of truth, mirroring the
    non-gateable-semantic-suggestion discipline in ``source_impact.py``.
    """

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["0.1"] = IMPACT_CROSS_VALIDATION_SCHEMA_VERSION
    adapter_id: str
    language: str
    input_symbols: list[str]
    affected_modules: list[str]
    call_graph_modules: list[str]
    semantic_modules: list[str]
    agreed_modules: list[str]
    call_graph_only_modules: list[str]
    semantic_only_modules: list[str]
    flags: list[ImpactCrossValidationFlag] = Field(default_factory=list)
    semantic_estimate_source: Literal["llm", "manual", "none"] = "none"
    disagreement: bool = False
    metadata: dict[str, str] = Field(default_factory=dict)


def cross_validate_impact(
    artifact: ImpactAnalysisArtifact,
    *,
    semantic_modules: list[str],
    semantic_estimate_source: Literal["llm", "manual"] = "llm",
) -> ImpactCrossValidationReport:
    """Cross-validate the call-graph-derived affected set against a semantic module estimate.

    ``artifact.affected_modules`` is the authoritative, call-graph-reachable set; ``semantic_modules``
    is the (untrusted) estimate. Disagreement is surfaced in BOTH directions as review flags — a
    call-graph module the estimate missed (``call_graph_only``) and an estimate module the call graph
    never reached (``semantic_only``) — and never silently resolved. The returned ``affected_modules``
    is the call-graph set unchanged, so the estimate cannot widen or narrow the gateable impact.
    """
    call_graph = set(artifact.affected_modules)
    semantic = set(semantic_modules)
    agreed = call_graph & semantic
    call_graph_only = call_graph - semantic
    semantic_only = semantic - call_graph
    flags: list[ImpactCrossValidationFlag] = []
    for module_id in sorted(call_graph_only):
        flags.append(
            ImpactCrossValidationFlag(
                severity="review",
                category="call_graph_only",
                module_id=module_id,
                message=(
                    "call-graph reachability flagged this module but the semantic estimate omitted "
                    "it; review whether the requirement truly impacts it"
                ),
            )
        )
    for module_id in sorted(semantic_only):
        flags.append(
            ImpactCrossValidationFlag(
                severity="review",
                category="semantic_only",
                module_id=module_id,
                message=(
                    "the semantic estimate named this module but call-graph reachability did not "
                    "reach it; it is NOT in the gateable affected set until evidenced"
                ),
            )
        )
    return ImpactCrossValidationReport(
        adapter_id=artifact.adapter_id,
        language=artifact.language,
        input_symbols=list(artifact.input_symbols),
        affected_modules=sorted(call_graph),
        call_graph_modules=sorted(call_graph),
        semantic_modules=sorted(semantic),
        agreed_modules=sorted(agreed),
        call_graph_only_modules=sorted(call_graph_only),
        semantic_only_modules=sorted(semantic_only),
        flags=flags,
        semantic_estimate_source=semantic_estimate_source,
        disagreement=bool(call_graph_only or semantic_only),
        metadata={"mode": "call_graph_vs_semantic_cross_validation"},
    )


def cross_validate_impact_with_llm(
    artifact: ImpactAnalysisArtifact,
    *,
    client: LlmClient,
    prose: str,
    symbols: list[str],
    candidate_modules: list[str],
) -> ImpactCrossValidationReport:
    """Cross-validate the call-graph affected set against a fresh LLM impact estimate (PC-9).

    Calls the (untrusted) LLM client for a semantic estimate over ``candidate_modules``, parses it
    defensively with :func:`parse_impact_estimate`, and hands it to :func:`cross_validate_impact`.
    Use a ``RecordedLlmClient`` for offline/deterministic runs — no live model is required.
    """
    raw_estimate = client.estimate_impacted_modules(
        prose=prose, symbols=symbols, candidate_modules=candidate_modules
    )
    semantic_modules = parse_impact_estimate(raw_estimate)
    return cross_validate_impact(
        artifact, semantic_modules=semantic_modules, semantic_estimate_source="llm"
    )
