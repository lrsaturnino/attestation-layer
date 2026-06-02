from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from .jsonutil import sha256_json, sha256_text
from .models import NormalizedTrace, NormalizedTraceArtifact, TraceEvent


TRACE_NORMALIZATION_V2_SCHEMA_VERSION = "0.1"
TRACE_NORMALIZATION_V2_TOOL_VERSION = "0.1"


class RawTraceEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    event_id: str
    timestamp: str | int
    action: str
    actor: str | None = None
    pre_state: dict[str, Any] | None = None
    post_state: dict[str, Any] | None = None
    causal_predecessor: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class RawTrace(BaseModel):
    model_config = ConfigDict(extra="forbid")

    trace_id: str
    adapter_id: str
    language: str | None = None
    runtime: str | None = None
    events: list[RawTraceEvent] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class RawTraceArtifact(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["0.1"] = TRACE_NORMALIZATION_V2_SCHEMA_VERSION
    traces: list[RawTrace] = Field(default_factory=list)


class TraceNormalizationLossRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    trace_id: str
    event_id: str | None = None
    field: str
    reason: str


class TraceNormalizationV2Report(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["0.1"] = TRACE_NORMALIZATION_V2_SCHEMA_VERSION
    result: Literal["normalized", "lossy_normalized"]
    normalized: NormalizedTraceArtifact
    loss_records: list[TraceNormalizationLossRecord] = Field(default_factory=list)
    input_hashes: dict[str, str] = Field(default_factory=dict)
    tool: str = "nlreq.trace_normalization_v2"
    tool_version: str = TRACE_NORMALIZATION_V2_TOOL_VERSION


def normalize_raw_traces_v2(raw: RawTraceArtifact) -> TraceNormalizationV2Report:
    loss_records: list[TraceNormalizationLossRecord] = []
    normalized_traces: list[NormalizedTrace] = []
    for trace in raw.traces:
        events: list[TraceEvent] = []
        for event in trace.events:
            event_metadata = dict(event.metadata)
            for key in sorted(list(event_metadata)):
                if key.startswith("raw_"):
                    loss_records.append(
                        TraceNormalizationLossRecord(
                            trace_id=trace.trace_id,
                            event_id=event.event_id,
                            field=key,
                            reason="raw adapter-specific field retained only in metadata",
                        )
                    )
            events.append(
                TraceEvent(
                    event_id=event.event_id,
                    timestamp=event.timestamp,
                    actor=event.actor,
                    action=event.action,
                    pre_state=event.pre_state,
                    post_state=event.post_state,
                    causal_predecessor=event.causal_predecessor,
                    language=trace.language,
                    runtime=trace.runtime,
                    metadata=event_metadata,
                )
            )
        normalized_traces.append(
            NormalizedTrace(
                trace_id=trace.trace_id,
                adapter_id=trace.adapter_id,
                source_hash=sha256_text(trace.model_dump_json()),
                language=trace.language,
                runtime=trace.runtime,
                events=events,
                metadata=trace.metadata,
            )
        )
    normalized = NormalizedTraceArtifact.model_validate(normalized_traces)
    return TraceNormalizationV2Report(
        result="lossy_normalized" if loss_records else "normalized",
        normalized=normalized,
        loss_records=loss_records,
        input_hashes={"raw_trace_artifact": sha256_json(raw)},
    )
