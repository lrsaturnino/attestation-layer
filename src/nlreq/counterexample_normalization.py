from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from .formal_backend import FormalBackendResponse
from .formal_claim import FormalClaim
from .jsonutil import sha256_json
from .models import Counterexample, SourceSpan
from .system_checker import SystemConsistencyResult


COUNTEREXAMPLE_NORMALIZATION_SCHEMA_VERSION = "0.1"
COUNTEREXAMPLE_NORMALIZATION_TOOL_VERSION = "0.1"


class CounterexampleStep(BaseModel):
    model_config = ConfigDict(extra="forbid")

    step_index: int = Field(ge=0)
    source: str
    marker: str | None = None
    excerpt: str | None = None
    state: dict[str, Any] = Field(default_factory=dict)
    event: dict[str, Any] = Field(default_factory=dict)


class NormalizedCounterexample(BaseModel):
    model_config = ConfigDict(extra="forbid")

    counterexample_id: str
    backend: str
    requirement_id: str | None = None
    source_result_hash: str
    status: Literal["counterexample"]
    steps: list[CounterexampleStep] = Field(default_factory=list)
    summary: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class CounterexampleNormalizationReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["0.1"] = COUNTEREXAMPLE_NORMALIZATION_SCHEMA_VERSION
    result: Literal["counterexamples", "none"]
    counterexamples: list[NormalizedCounterexample] = Field(default_factory=list)
    input_hashes: dict[str, str] = Field(default_factory=dict)
    tool: str = "nlreq.counterexample_normalization"
    tool_version: str = COUNTEREXAMPLE_NORMALIZATION_TOOL_VERSION


class CounterexampleSourceMapping(BaseModel):
    model_config = ConfigDict(extra="forbid")

    claim_fragment_id: str
    source_node_id: str
    canonical: str
    source_spans: list[SourceSpan] = Field(default_factory=list)


class CounterexampleExplanation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    explanation_id: str
    counterexample_id: str
    backend: str
    requirement_id: str | None = None
    violated_property: str
    backend_bound: dict[str, Any] = Field(default_factory=dict)
    shortest_known_trace: list[CounterexampleStep] = Field(default_factory=list)
    source_mappings: list[CounterexampleSourceMapping] = Field(default_factory=list)
    summary: str
    next_actions: list[str] = Field(default_factory=list)
    markdown: str


class CounterexampleExplanationReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["0.1"] = COUNTEREXAMPLE_NORMALIZATION_SCHEMA_VERSION
    result: Literal["explained", "none"]
    explanations: list[CounterexampleExplanation] = Field(default_factory=list)
    input_hashes: dict[str, str] = Field(default_factory=dict)
    tool: str = "nlreq.counterexample_normalization"
    tool_version: str = COUNTEREXAMPLE_NORMALIZATION_TOOL_VERSION


def normalize_backend_counterexamples(
    responses: list[FormalBackendResponse],
) -> CounterexampleNormalizationReport:
    normalized: list[NormalizedCounterexample] = []
    input_hashes: dict[str, str] = {}
    for response in responses:
        response_hash = sha256_json(response)
        input_hashes[response.backend_id] = response_hash
        if response.result.status != "counterexample":
            continue
        raw_items = response.result.details.get("counterexamples", [])
        if not isinstance(raw_items, list) or not raw_items:
            raw_items = [{"source": "backend", "marker": None, "excerpt": None}]
        for index, item in enumerate(raw_items, start=1):
            normalized.append(
                NormalizedCounterexample(
                    counterexample_id=f"{response.backend_id}:cex:{index}",
                    backend=response.backend_id,
                    requirement_id=response.result.details.get("requirement_id"),
                    source_result_hash=response_hash,
                    status="counterexample",
                    steps=[_step_from_raw(0, item)],
                    summary=(
                        f"{response.backend_id} produced a counterexample"
                        if index == 1
                        else f"{response.backend_id} produced counterexample {index}"
                    ),
                    metadata={
                        "target": response.target,
                        "backend_status": response.result.status,
                    },
                )
            )
    return CounterexampleNormalizationReport(
        result="counterexamples" if normalized else "none",
        counterexamples=normalized,
        input_hashes=input_hashes,
    )


def explain_counterexamples(
    normalization: CounterexampleNormalizationReport,
    *,
    formal_claim: FormalClaim | None = None,
    backend_responses: list[FormalBackendResponse] | None = None,
) -> CounterexampleExplanationReport:
    backend_by_id = {
        response.backend_id: response for response in (backend_responses or [])
    }
    source_mappings = _source_mappings(formal_claim)
    explanations = [
        _explain_counterexample(
            counterexample,
            backend_response=backend_by_id.get(counterexample.backend),
            source_mappings=source_mappings,
        )
        for counterexample in normalization.counterexamples
    ]
    input_hashes = {"normalization": sha256_json(normalization)}
    if formal_claim is not None:
        input_hashes["formal_claim"] = sha256_json(formal_claim)
    if backend_responses:
        input_hashes["backend_responses"] = sha256_json(backend_responses)
    return CounterexampleExplanationReport(
        result="explained" if explanations else "none",
        explanations=explanations,
        input_hashes=input_hashes,
    )


def normalize_system_counterexamples(
    results: list[SystemConsistencyResult],
) -> CounterexampleNormalizationReport:
    normalized: list[NormalizedCounterexample] = []
    input_hashes: dict[str, str] = {}
    for result in results:
        result_hash = sha256_json(result)
        input_hashes[result.requirement_id] = result_hash
        for counterexample in result.counterexamples:
            normalized.append(_from_counterexample(counterexample, result_hash))
    return CounterexampleNormalizationReport(
        result="counterexamples" if normalized else "none",
        counterexamples=normalized,
        input_hashes=input_hashes,
    )


def _source_mappings(formal_claim: FormalClaim | None) -> list[CounterexampleSourceMapping]:
    if formal_claim is None:
        return []
    fragments = [
        *formal_claim.scope,
        *formal_claim.premises,
        formal_claim.action,
        *formal_claim.obligations,
    ]
    return [
        CounterexampleSourceMapping(
            claim_fragment_id=fragment.fragment_id,
            source_node_id=fragment.source_node_id,
            canonical=fragment.canonical,
            source_spans=fragment.source_spans,
        )
        for fragment in fragments
    ]


def _explain_counterexample(
    counterexample: NormalizedCounterexample,
    *,
    backend_response: FormalBackendResponse | None,
    source_mappings: list[CounterexampleSourceMapping],
) -> CounterexampleExplanation:
    bounds = {}
    violated = "backend-reported requirement property"
    if backend_response is not None:
        raw_bounds = backend_response.result.details.get("bounds")
        if isinstance(raw_bounds, dict):
            bounds = raw_bounds
        module = backend_response.result.details.get("module")
        if isinstance(module, str):
            violated = module
    if source_mappings:
        violated = source_mappings[-1].canonical
    summary = (
        f"{counterexample.backend} found a counterexample for {violated}; "
        f"{len(counterexample.steps)} trace step(s) were retained."
    )
    next_actions = [
        "Inspect the mapped controlled-text spans and backend trace excerpt.",
        "Decide whether to fix the requirement, update the reviewed system spec, or fix implementation behavior.",
    ]
    markdown = _counterexample_markdown(
        counterexample=counterexample,
        violated_property=violated,
        bounds=bounds,
        next_actions=next_actions,
    )
    return CounterexampleExplanation(
        explanation_id=f"explain:{counterexample.counterexample_id}",
        counterexample_id=counterexample.counterexample_id,
        backend=counterexample.backend,
        requirement_id=counterexample.requirement_id,
        violated_property=violated,
        backend_bound=bounds,
        shortest_known_trace=counterexample.steps,
        source_mappings=source_mappings,
        summary=summary,
        next_actions=next_actions,
        markdown=markdown,
    )


def _counterexample_markdown(
    *,
    counterexample: NormalizedCounterexample,
    violated_property: str,
    bounds: dict[str, Any],
    next_actions: list[str],
) -> str:
    lines = [
        f"### Counterexample `{counterexample.counterexample_id}`",
        "",
        f"- Backend: `{counterexample.backend}`",
        f"- Violated property: `{violated_property}`",
    ]
    if bounds:
        lines.append(f"- Bounds: `{bounds}`")
    lines.append(f"- Trace steps retained: `{len(counterexample.steps)}`")
    lines.append("")
    lines.append("Next actions:")
    lines.extend(f"- {action}" for action in next_actions)
    return "\n".join(lines)


def _from_counterexample(
    counterexample: Counterexample,
    source_hash: str,
) -> NormalizedCounterexample:
    return NormalizedCounterexample(
        counterexample_id=counterexample.counterexample_id,
        backend=counterexample.backend,
        requirement_id=counterexample.claim_id,
        source_result_hash=source_hash,
        status="counterexample",
        steps=[
            CounterexampleStep(
                step_index=0,
                source="normalized-counterexample",
                state={
                    "inputs": counterexample.inputs,
                    "expected": counterexample.expected,
                    "actual": counterexample.actual,
                },
            )
        ],
        summary=counterexample.description,
        metadata=counterexample.metadata,
    )


def _step_from_raw(index: int, item: Any) -> CounterexampleStep:
    if isinstance(item, dict):
        return CounterexampleStep(
            step_index=index,
            source=str(item.get("source") or "combined"),
            marker=item.get("marker"),
            excerpt=item.get("excerpt"),
            event={
                key: value
                for key, value in item.items()
                if key not in {"source", "marker", "excerpt"}
            },
        )
    return CounterexampleStep(
        step_index=index,
        source="combined",
        excerpt=str(item),
    )
