from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from .models import BackendResult, EvidenceLevel
from .proof_closure import EvidenceProducerMapping, bounded_backing_problems


EVIDENCE_PRODUCER_VALIDATION_SCHEMA_VERSION = "0.1"
HIGH_ASSURANCE_LEVELS = {EvidenceLevel.BOUNDED_CHECKED, EvidenceLevel.PROVEN_INDUCTIVE}


class EvidenceProducerValidationStatus(BaseModel):
    model_config = ConfigDict(extra="forbid")

    backend: str
    evidence_level: EvidenceLevel | None = None
    status: Literal["valid", "blocked", "not_applicable"]
    reasons: list[str] = Field(default_factory=list)


class EvidenceProducerValidationReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["0.1"] = EVIDENCE_PRODUCER_VALIDATION_SCHEMA_VERSION
    result: Literal["valid", "blocked"]
    statuses: list[EvidenceProducerValidationStatus] = Field(default_factory=list)


def validate_real_evidence_producers(
    backend_results: list[BackendResult],
    mapping: EvidenceProducerMapping,
) -> EvidenceProducerValidationReport:
    producers = {producer.producer_id: producer for producer in mapping.producers}
    statuses: list[EvidenceProducerValidationStatus] = []
    for result in backend_results:
        if result.evidence_level not in HIGH_ASSURANCE_LEVELS:
            statuses.append(
                EvidenceProducerValidationStatus(
                    backend=result.backend,
                    evidence_level=result.evidence_level,
                    status="not_applicable",
                )
            )
            continue
        reasons: list[str] = []
        producer = producers.get(result.backend)
        if producer is None:
            reasons.append("producer is not registered")
        else:
            if result.evidence_level not in producer.allowed_evidence_levels:
                reasons.append("producer is not allowed to emit this evidence level")
            if not producer.real_producer:
                reasons.append("high-assurance evidence requires a real producer")
        # BOUNDED_CHECKED backing — recorded bounds, command, and a version recorded from the
        # run (not the producer's static catalog version) — uses the single definition the
        # closure gate enforces. PROVEN_INDUCTIVE's proof-artifact backing is gated by the
        # evidence-boundary report; here it still must carry reproducibility hashes.
        reasons.extend(bounded_backing_problems(result))
        if not _has_reproducibility_hashes(result):
            reasons.append("input/output or artifact hashes are missing")
        statuses.append(
            EvidenceProducerValidationStatus(
                backend=result.backend,
                evidence_level=result.evidence_level,
                status="blocked" if reasons else "valid",
                reasons=reasons,
            )
        )
    blocked = any(status.status == "blocked" for status in statuses)
    return EvidenceProducerValidationReport(
        result="blocked" if blocked else "valid",
        statuses=statuses,
    )


def _has_reproducibility_hashes(result: BackendResult) -> bool:
    if isinstance(result.details.get("input_hashes"), dict):
        return True
    if isinstance(result.details.get("output_hashes"), dict):
        return True
    return any(key.endswith("_hash") or key.endswith("_hashes") for key in result.details)
