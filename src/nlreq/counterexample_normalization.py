from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from .formal_backend import FormalBackendResponse
from .jsonutil import sha256_json
from .models import Counterexample
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
