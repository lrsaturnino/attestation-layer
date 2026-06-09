from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from .llm_client import LlmClient, parse_impact_estimate
from .models import NormalizedTraceArtifact, SymbolRef
from .source_adapter import SourceLanguageAdapter, SourceManifest, SourceSymbolResolution


SOURCE_IMPACT_SCHEMA_VERSION = "0.1"
PRODUCTION_SOURCE_IMPACT_SCHEMA_VERSION = "0.3"


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


class SourceImpactAnalysisArtifact(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["0.1"] = SOURCE_IMPACT_SCHEMA_VERSION
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


class ImpactConfidencePolicy(BaseModel):
    model_config = ConfigDict(extra="forbid")

    require_resolved_symbols: bool = True
    minimum_gateable_confidence: float = 0.75
    semantic_suggestions_gateable: bool = False
    trace_only_impact_requires_review: bool = True


class SourceImpactFinding(BaseModel):
    model_config = ConfigDict(extra="forbid")

    severity: Literal["blocking", "review", "info"]
    category: Literal[
        "unresolved_symbol",
        "ambiguous_symbol",
        "semantic_suggestion",
        "semantic_omission",
        "trace_disagreement",
        "low_confidence",
    ]
    message: str
    symbol: str | None = None
    module_id: str | None = None


class ProductionImpactedModule(BaseModel):
    model_config = ConfigDict(extra="forbid")

    module_id: str
    roles: list[Literal["deterministic", "dependency", "trace_touched", "semantic_suggestion"]]
    confidence: float
    gateable: bool
    reasons: list[str] = Field(default_factory=list)


class ProductionSourceImpactReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["0.3"] = PRODUCTION_SOURCE_IMPACT_SCHEMA_VERSION
    adapter_id: str
    language: str
    input_symbols: list[str]
    symbol_resolutions: list[SourceSymbolResolution] = Field(default_factory=list)
    affected_modules: list[str]
    deterministic_modules: list[str]
    dependency_modules: list[str] = Field(default_factory=list)
    trace_touched_modules: list[str] = Field(default_factory=list)
    modules: list[ProductionImpactedModule] = Field(default_factory=list)
    semantic_suggestions: list[SemanticImpactSuggestion] = Field(default_factory=list)
    disagreements: list[ImpactDisagreement] = Field(default_factory=list)
    findings: list[SourceImpactFinding] = Field(default_factory=list)
    confidence_policy: ImpactConfidencePolicy = Field(default_factory=ImpactConfidencePolicy)
    closure_effect: Literal["allow", "review", "block"]
    call_graph_edges: list[dict[str, str]] = Field(default_factory=list)
    metadata: dict[str, str] = Field(default_factory=dict)


def llm_semantic_suggestions(
    client: LlmClient,
    *,
    prose: str,
    symbols: list[str],
    candidate_modules: list[str],
) -> list[SemanticImpactSuggestion]:
    """Produce semantic impact suggestions from an (untrusted) LLM estimate (PC-9).

    Calls the LLM client for a semantic impact estimate over ``candidate_modules``, parses it
    defensively with :func:`parse_impact_estimate`, and wraps each named module as a
    ``SemanticImpactSuggestion`` with ``source="llm"``. These feed the existing production-impact
    cross-validation (:func:`analyze_production_source_impact`), which surfaces any module outside
    the deterministic call-graph set as a non-gateable review disagreement — the LLM estimate never
    becomes gateable on its own. Use a ``RecordedLlmClient`` for offline/deterministic runs.
    """
    raw_estimate = client.estimate_impacted_modules(
        prose=prose, symbols=symbols, candidate_modules=candidate_modules
    )
    return [
        SemanticImpactSuggestion(
            module_id=module_id,
            reason="LLM semantic impact estimate (cross-validation only, non-gateable)",
            source="llm",
        )
        for module_id in parse_impact_estimate(raw_estimate)
    ]


def analyze_source_impact_with_context(
    adapter: SourceLanguageAdapter,
    manifest: SourceManifest,
    *,
    symbols: list[str],
    traces: NormalizedTraceArtifact | None = None,
    semantic_suggestions: list[SemanticImpactSuggestion] | None = None,
) -> SourceImpactAnalysisArtifact:
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
    disagreements = _disagreements(
        deterministic,
        trace_modules,
        suggested_modules,
        semantic_estimate_provided=semantic_suggestions is not None,
    )
    return SourceImpactAnalysisArtifact(
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


def analyze_production_source_impact(
    adapter: SourceLanguageAdapter,
    manifest: SourceManifest,
    *,
    symbols: list[str],
    traces: NormalizedTraceArtifact | None = None,
    semantic_suggestions: list[SemanticImpactSuggestion] | None = None,
    confidence_policy: ImpactConfidencePolicy | None = None,
) -> ProductionSourceImpactReport:
    policy = confidence_policy or ImpactConfidencePolicy()
    graph = adapter.call_graph(manifest)
    resolutions = [adapter.resolve_symbol(SymbolRef(name=symbol), manifest) for symbol in symbols]
    findings = _resolution_findings(resolutions, policy)
    direct_modules = {
        symbol.module_id
        for resolution in resolutions
        if resolution.status == "resolved"
        for symbol in resolution.symbols
    }
    deterministic = _expand_call_graph(direct_modules, graph.edges)
    dependency_modules = deterministic - direct_modules
    trace_modules = _trace_touched_modules(traces)
    suggestions = semantic_suggestions or []
    suggested_modules = {suggestion.module_id for suggestion in suggestions}
    affected = deterministic | trace_modules
    disagreements = _disagreements(
        deterministic,
        trace_modules,
        suggested_modules,
        semantic_estimate_provided=semantic_suggestions is not None,
    )
    findings.extend(_disagreement_findings(disagreements, policy))
    modules = _production_modules(
        deterministic=deterministic,
        direct_modules=direct_modules,
        dependency_modules=dependency_modules,
        trace_modules=trace_modules,
        suggested_modules=suggested_modules,
        suggestions=suggestions,
        policy=policy,
    )
    findings.extend(_low_confidence_findings(modules, policy))
    return ProductionSourceImpactReport(
        adapter_id=adapter.adapter_id,
        language=adapter.language,
        input_symbols=sorted(symbols),
        symbol_resolutions=resolutions,
        affected_modules=sorted(affected),
        deterministic_modules=sorted(deterministic),
        dependency_modules=sorted(dependency_modules),
        trace_touched_modules=sorted(trace_modules),
        modules=modules,
        semantic_suggestions=suggestions,
        disagreements=disagreements,
        findings=findings,
        confidence_policy=policy,
        closure_effect=_closure_effect(findings),
        call_graph_edges=[
            {"caller": edge.caller, "callee": edge.callee} for edge in graph.edges
        ],
        metadata={"mode": "production_source_impact_v2"},
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
    *,
    semantic_estimate_provided: bool,
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
    # call_graph_only: the (untrusted) semantic estimate OMITTED a deterministic call-graph module.
    # The call graph is authoritative, so the module stays in the gateable affected set; the omission
    # is surfaced as a review disagreement (mirroring impact.cross_validate_impact's call_graph_only
    # direction) so the estimate's disagreement is reconciled by a human, never silently dropped.
    # Only emitted when an estimate was actually provided — an estimate-free analysis has nothing to
    # disagree with, so every deterministic module would otherwise be spuriously flagged.
    if semantic_estimate_provided:
        for module_id in sorted(deterministic - suggested_modules):
            disagreements.append(
                ImpactDisagreement(
                    module_id=module_id,
                    deterministic=True,
                    semantic_suggestion=False,
                    trace_touched=module_id in trace_modules,
                    reason="deterministic call-graph module omitted by the semantic estimate",
                )
            )
    return disagreements


def _resolution_findings(
    resolutions: list[SourceSymbolResolution],
    policy: ImpactConfidencePolicy,
) -> list[SourceImpactFinding]:
    if not policy.require_resolved_symbols:
        return []
    findings: list[SourceImpactFinding] = []
    for resolution in resolutions:
        if resolution.status == "unresolved":
            findings.append(
                SourceImpactFinding(
                    severity="blocking",
                    category="unresolved_symbol",
                    symbol=resolution.ref.name,
                    message=resolution.reason or "input symbol did not resolve",
                )
            )
        elif resolution.status == "ambiguous":
            findings.append(
                SourceImpactFinding(
                    severity="blocking",
                    category="ambiguous_symbol",
                    symbol=resolution.ref.name,
                    message=resolution.reason or "input symbol resolved ambiguously",
                )
            )
    return findings


def _disagreement_findings(
    disagreements: list[ImpactDisagreement],
    policy: ImpactConfidencePolicy,
) -> list[SourceImpactFinding]:
    findings: list[SourceImpactFinding] = []
    for disagreement in disagreements:
        # call_graph_only: a deterministic module the semantic estimate omitted. The authoritative
        # set still includes it, so the review finding asks a human to reconcile the estimate's view
        # rather than gate the module out — parity with the semantic_only/trace directions, which
        # also flip closure to review. (Uniquely identified: only call_graph_only disagreements are
        # deterministic with no semantic suggestion.)
        if disagreement.deterministic and not disagreement.semantic_suggestion:
            findings.append(
                SourceImpactFinding(
                    severity="review",
                    category="semantic_omission",
                    module_id=disagreement.module_id,
                    message=disagreement.reason,
                )
            )
            continue
        if disagreement.trace_touched and policy.trace_only_impact_requires_review:
            findings.append(
                SourceImpactFinding(
                    severity="review",
                    category="trace_disagreement",
                    module_id=disagreement.module_id,
                    message=disagreement.reason,
                )
            )
        if disagreement.semantic_suggestion:
            findings.append(
                SourceImpactFinding(
                    severity="review",
                    category="semantic_suggestion",
                    module_id=disagreement.module_id,
                    message="semantic suggestion is non-gateable until reviewed",
                )
            )
    return findings


def _production_modules(
    *,
    deterministic: set[str],
    direct_modules: set[str],
    dependency_modules: set[str],
    trace_modules: set[str],
    suggested_modules: set[str],
    suggestions: list[SemanticImpactSuggestion],
    policy: ImpactConfidencePolicy,
) -> list[ProductionImpactedModule]:
    suggestion_reasons = {suggestion.module_id: suggestion.reason for suggestion in suggestions}
    modules: list[ProductionImpactedModule] = []
    for module_id in sorted(deterministic | trace_modules | suggested_modules):
        roles: list[Literal["deterministic", "dependency", "trace_touched", "semantic_suggestion"]] = []
        reasons: list[str] = []
        if module_id in deterministic:
            roles.append("deterministic")
            reasons.append("adapter symbol resolution and call graph")
        if module_id in dependency_modules:
            roles.append("dependency")
            reasons.append("call graph dependency")
        if module_id in trace_modules:
            roles.append("trace_touched")
            reasons.append("runtime trace touched module")
        if module_id in suggested_modules:
            roles.append("semantic_suggestion")
            reasons.append(suggestion_reasons.get(module_id, "semantic suggestion"))
        confidence = _module_confidence(
            module_id,
            direct_modules=direct_modules,
            deterministic=deterministic,
            trace_modules=trace_modules,
            suggested_modules=suggested_modules,
        )
        gateable = module_id in deterministic or (
            module_id in trace_modules and confidence >= policy.minimum_gateable_confidence
        )
        if module_id in suggested_modules and not policy.semantic_suggestions_gateable:
            gateable = module_id in deterministic
        modules.append(
            ProductionImpactedModule(
                module_id=module_id,
                roles=roles,
                confidence=confidence,
                gateable=gateable,
                reasons=reasons,
            )
        )
    return modules


def _module_confidence(
    module_id: str,
    *,
    direct_modules: set[str],
    deterministic: set[str],
    trace_modules: set[str],
    suggested_modules: set[str],
) -> float:
    if module_id in direct_modules:
        return 1.0
    if module_id in deterministic and module_id in trace_modules:
        return 0.95
    if module_id in deterministic:
        return 0.9
    if module_id in trace_modules:
        return 0.7
    if module_id in suggested_modules:
        return 0.25
    return 0.0


def _low_confidence_findings(
    modules: list[ProductionImpactedModule],
    policy: ImpactConfidencePolicy,
) -> list[SourceImpactFinding]:
    findings: list[SourceImpactFinding] = []
    for module in modules:
        if not module.gateable or module.confidence < policy.minimum_gateable_confidence:
            findings.append(
                SourceImpactFinding(
                    severity="review",
                    category="low_confidence",
                    module_id=module.module_id,
                    message=(
                        f"impact confidence {module.confidence:.2f} is below "
                        f"gateable threshold {policy.minimum_gateable_confidence:.2f}"
                    ),
                )
            )
    return findings


def _closure_effect(findings: list[SourceImpactFinding]) -> Literal["allow", "review", "block"]:
    if any(finding.severity == "blocking" for finding in findings):
        return "block"
    if any(finding.severity == "review" for finding in findings):
        return "review"
    return "allow"
