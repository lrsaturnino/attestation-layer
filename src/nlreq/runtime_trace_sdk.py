from __future__ import annotations

from pathlib import Path, PurePosixPath
from typing import Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .jsonutil import sha256_json
from .models import NormalizedTraceArtifact


TRACE_SDK_SCHEMA_VERSION = "0.1"
TRACE_SDK_TOOL_VERSION = "0.1"


class TraceProducerRegistration(BaseModel):
    model_config = ConfigDict(extra="forbid")

    producer_id: str
    adapter_id: str
    language: str
    runtime: str | None = None
    produces_normalized_schema: Literal["0.1"]
    command: list[str] = Field(default_factory=list)
    real_producer: bool = True
    metadata: dict[str, str] = Field(default_factory=dict)


class TraceProducerRegistry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["0.1"] = TRACE_SDK_SCHEMA_VERSION
    producers: list[TraceProducerRegistration] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_unique_producers(self) -> TraceProducerRegistry:
        producer_ids = [producer.producer_id for producer in self.producers]
        if len(producer_ids) != len(set(producer_ids)):
            raise ValueError("trace producer ids must be unique")
        return self


class TraceExtractionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    producer_id: str
    trace_source: str
    requirement_ids: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_trace_source(self) -> TraceExtractionRequest:
        parsed = PurePosixPath(self.trace_source)
        if parsed.is_absolute() or ".." in parsed.parts:
            raise ValueError("trace_source must be project-root-relative")
        return self


class TraceExtractionResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["0.1"] = TRACE_SDK_SCHEMA_VERSION
    producer_id: str
    status: Literal["extracted", "unsupported", "invalid"]
    traces: NormalizedTraceArtifact | None = None
    trace_hash: str | None = None
    reasons: list[str] = Field(default_factory=list)
    metadata: dict[str, str] = Field(default_factory=dict)
    tool: str = "nlreq.runtime_trace_sdk"
    tool_version: str = TRACE_SDK_TOOL_VERSION


class RuntimeTraceProducer(Protocol):
    producer_id: str

    def extract(self, request: TraceExtractionRequest, *, project_root: Path) -> TraceExtractionResult:
        ...


class LocalJsonTraceProducer:
    def __init__(self, registration: TraceProducerRegistration) -> None:
        self.registration = registration
        self.producer_id = registration.producer_id

    def extract(self, request: TraceExtractionRequest, *, project_root: Path) -> TraceExtractionResult:
        if request.producer_id != self.producer_id:
            return TraceExtractionResult(
                producer_id=request.producer_id,
                status="invalid",
                reasons=[f"request producer_id does not match {self.producer_id}"],
            )
        path = (project_root / request.trace_source).resolve(strict=False)
        try:
            path.relative_to(project_root.resolve(strict=False))
        except ValueError:
            return TraceExtractionResult(
                producer_id=self.producer_id,
                status="invalid",
                reasons=["trace_source escapes project root"],
            )
        if not path.is_file():
            return TraceExtractionResult(
                producer_id=self.producer_id,
                status="unsupported",
                reasons=["trace_source does not exist"],
            )
        try:
            traces = NormalizedTraceArtifact.model_validate_json(path.read_text())
        except ValueError as exc:
            return TraceExtractionResult(
                producer_id=self.producer_id,
                status="invalid",
                reasons=[str(exc)],
            )
        normalized = NormalizedTraceArtifact.model_validate(
            [
                trace.model_copy(
                    update={
                        "adapter_id": self.registration.adapter_id,
                        "language": trace.language or self.registration.language,
                        "runtime": trace.runtime or self.registration.runtime,
                    }
                )
                for trace in traces.root
            ]
        )
        return TraceExtractionResult(
            producer_id=self.producer_id,
            status="extracted",
            traces=normalized,
            trace_hash=sha256_json(normalized),
            metadata={
                "trace_source": request.trace_source,
                "adapter_id": self.registration.adapter_id,
            },
        )


def producer_from_registry(
    registry: TraceProducerRegistry,
    producer_id: str,
) -> LocalJsonTraceProducer:
    for registration in registry.producers:
        if registration.producer_id == producer_id:
            return LocalJsonTraceProducer(registration)
    raise ValueError(f"unknown trace producer: {producer_id}")
