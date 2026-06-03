from __future__ import annotations

import hashlib
from pathlib import Path, PurePosixPath
from typing import Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .jsonutil import sha256_json
from .models import NormalizedTraceArtifact


TRACE_SDK_SCHEMA_VERSION = "0.1"
TRACE_SDK_TOOL_VERSION = "0.1"
TRACE_SDK_V2_SCHEMA_VERSION = "0.2"


class TraceLossRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    trace_id: str
    event_id: str | None = None
    field: str
    reason: str
    severity: Literal["info", "blocking"] = "blocking"


class TraceProducerRegistration(BaseModel):
    model_config = ConfigDict(extra="forbid")

    producer_id: str
    adapter_id: str
    language: str
    runtime: str | None = None
    produces_normalized_schema: Literal["0.1"]
    command: list[str] = Field(default_factory=list)
    real_producer: bool = True
    producer_kind: Literal["runtime", "test_harness", "log_importer", "manual"] = "runtime"
    signing_key_id: str | None = None
    runtime_metadata: dict[str, str] = Field(default_factory=dict)
    retains_replay_inputs: bool = True
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
    run_id: str | None = None
    runtime_metadata: dict[str, str] = Field(default_factory=dict)
    high_assurance: bool = False

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
    loss_records: list[TraceLossRecord] = Field(default_factory=list)
    replay_input_hashes: dict[str, str] = Field(default_factory=dict)
    runtime_metadata: dict[str, str] = Field(default_factory=dict)
    signing_key_id: str | None = None
    reasons: list[str] = Field(default_factory=list)
    metadata: dict[str, str] = Field(default_factory=dict)
    tool: str = "nlreq.runtime_trace_sdk"
    tool_version: str = TRACE_SDK_TOOL_VERSION


class TraceProducerEvidenceReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["0.2"] = TRACE_SDK_V2_SCHEMA_VERSION
    producer_id: str
    result: Literal["accepted", "blocked", "needs_review"]
    closure_effect: Literal["allow", "block", "review"]
    high_assurance: bool
    trace_hash: str | None = None
    real_producer: bool
    replayable: bool
    signature_required: bool
    signing_key_id: str | None = None
    loss_records: list[TraceLossRecord] = Field(default_factory=list)
    blockers: list[str] = Field(default_factory=list)
    metadata: dict[str, str] = Field(default_factory=dict)


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
            loss_records=_loss_records(normalized),
            replay_input_hashes={request.trace_source: _sha256_path(path)},
            runtime_metadata={
                **self.registration.runtime_metadata,
                **request.runtime_metadata,
                "runtime": self.registration.runtime or "",
            },
            signing_key_id=self.registration.signing_key_id,
            metadata={
                "trace_source": request.trace_source,
                "adapter_id": self.registration.adapter_id,
                "run_id": request.run_id or "",
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


def build_trace_producer_evidence_report(
    *,
    registration: TraceProducerRegistration,
    result: TraceExtractionResult,
    high_assurance: bool = False,
    require_signature: bool = False,
    require_replay: bool = True,
) -> TraceProducerEvidenceReport:
    blockers: list[str] = []
    if not registration.real_producer:
        blockers.append("trace producer is not registered as real")
    if result.status != "extracted" or result.traces is None:
        blockers.append("trace extraction did not produce normalized traces")
    if result.producer_id != registration.producer_id:
        blockers.append("trace extraction producer_id does not match registration")
    if high_assurance and result.loss_records:
        blockers.append("lossy traces cannot satisfy high-assurance closure")
    if require_signature and not registration.signing_key_id:
        blockers.append("trace producer signature is required but no signing key is registered")
    if require_replay and not result.replay_input_hashes:
        blockers.append("trace replay inputs were not retained")
    if blockers:
        closure_effect: Literal["allow", "block", "review"] = "block"
    elif result.loss_records:
        closure_effect = "review"
    else:
        closure_effect = "allow"
    return TraceProducerEvidenceReport(
        producer_id=registration.producer_id,
        result="accepted" if closure_effect == "allow" else ("blocked" if closure_effect == "block" else "needs_review"),
        closure_effect=closure_effect,
        high_assurance=high_assurance,
        trace_hash=result.trace_hash,
        real_producer=registration.real_producer,
        replayable=bool(result.replay_input_hashes),
        signature_required=require_signature,
        signing_key_id=registration.signing_key_id,
        loss_records=result.loss_records,
        blockers=blockers,
        metadata={
            "producer_kind": registration.producer_kind,
            "adapter_id": registration.adapter_id,
            "language": registration.language,
        },
    )


def _loss_records(traces: NormalizedTraceArtifact) -> list[TraceLossRecord]:
    records: list[TraceLossRecord] = []
    for trace in traces.root:
        if trace.metadata.get("lossy_normalization") is True:
            records.append(
                TraceLossRecord(
                    trace_id=trace.trace_id,
                    field="trace.metadata.lossy_normalization",
                    reason="trace metadata declares lossy normalization",
                )
            )
        for event in trace.events:
            if event.metadata.get("lossy_normalization") is True:
                records.append(
                    TraceLossRecord(
                        trace_id=trace.trace_id,
                        event_id=event.event_id,
                        field="event.metadata.lossy_normalization",
                        reason="event metadata declares lossy normalization",
                    )
                )
    return records


def _sha256_path(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()
