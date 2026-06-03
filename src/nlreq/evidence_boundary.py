from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from .jsonutil import sha256_json
from .models import BackendResult, EvidenceLevel
from .proof_closure import EvidenceProducerMapping, ProofObject


EVIDENCE_BOUNDARY_SCHEMA_VERSION = "0.1"
EVIDENCE_BOUNDARY_TOOL_VERSION = "0.1"


class EvidenceBoundaryFinding(BaseModel):
    model_config = ConfigDict(extra="forbid")

    backend: str
    evidence_level: EvidenceLevel | None = None
    severity: Literal["info", "blocking"]
    message: str


class ProofEvidenceBoundaryReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["0.1"] = EVIDENCE_BOUNDARY_SCHEMA_VERSION
    proof_id: str
    requirement_id: str
    result: Literal["passed", "blocked"]
    highest_claim: Literal["none", "reviewed", "bounded", "inductive"]
    findings: list[EvidenceBoundaryFinding] = Field(default_factory=list)
    tool: str = "nlreq.evidence_boundary"
    tool_version: str = EVIDENCE_BOUNDARY_TOOL_VERSION


class ProofArtifactRef(BaseModel):
    model_config = ConfigDict(extra="forbid")

    artifact_id: str
    kind: Literal["theorem_statement", "proof_script", "checked_proof", "checker_log"]
    sha256: str
    path: str | None = None
    checker: str | None = None


class ProofProducingBackendBoundaryReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["0.1"] = EVIDENCE_BOUNDARY_SCHEMA_VERSION
    backend: str
    result: Literal["accepted", "blocked"]
    claimed_evidence_level: EvidenceLevel | None = None
    producer_kind: str | None = None
    proof_artifacts: list[ProofArtifactRef] = Field(default_factory=list)
    checker_command: list[str] = Field(default_factory=list)
    findings: list[EvidenceBoundaryFinding] = Field(default_factory=list)
    input_hashes: dict[str, str] = Field(default_factory=dict)
    tool: str = "nlreq.evidence_boundary"
    tool_version: str = EVIDENCE_BOUNDARY_TOOL_VERSION


def build_proof_evidence_boundary_report(proof: ProofObject) -> ProofEvidenceBoundaryReport:
    producers = {producer.producer_id: producer for producer in proof.producer_mapping.producers}
    findings: list[EvidenceBoundaryFinding] = []
    highest = "none"
    for result in proof.backend_results:
        level = result.evidence_level
        if level is None:
            findings.append(
                EvidenceBoundaryFinding(
                    backend=result.backend,
                    evidence_level=None,
                    severity="info",
                    message="backend emitted no assurance level",
                )
            )
            continue
        highest = _max_claim(highest, _claim_for_level(level))
        producer = producers.get(result.backend)
        if level == EvidenceLevel.PROVEN_INDUCTIVE:
            if producer is None or producer.producer_kind != "proof_assistant":
                findings.append(
                    EvidenceBoundaryFinding(
                        backend=result.backend,
                        evidence_level=level,
                        severity="blocking",
                        message="PROVEN_INDUCTIVE requires a registered proof_assistant producer",
                    )
                )
        if level == EvidenceLevel.BOUNDED_CHECKED and result.status == "valid":
            findings.append(
                EvidenceBoundaryFinding(
                    backend=result.backend,
                    evidence_level=level,
                    severity="info",
                    message="bounded check may support closure but is not an inductive proof",
                )
            )
    return ProofEvidenceBoundaryReport(
        proof_id=proof.proof_id,
        requirement_id=proof.requirement_id,
        result="blocked" if any(item.severity == "blocking" for item in findings) else "passed",
        highest_claim=highest,
        findings=findings,
    )


def build_proof_producing_backend_boundary_report(
    *,
    backend_result: BackendResult,
    producer_mapping: EvidenceProducerMapping,
    proof_artifacts: list[ProofArtifactRef] | None = None,
    checker_command: list[str] | None = None,
) -> ProofProducingBackendBoundaryReport:
    artifacts = proof_artifacts or []
    command = checker_command or []
    producer = {
        item.producer_id: item for item in producer_mapping.producers
    }.get(backend_result.backend)
    findings: list[EvidenceBoundaryFinding] = []
    if backend_result.evidence_level == EvidenceLevel.PROVEN_INDUCTIVE:
        if backend_result.status != "valid":
            findings.append(
                EvidenceBoundaryFinding(
                    backend=backend_result.backend,
                    evidence_level=backend_result.evidence_level,
                    severity="blocking",
                    message="PROVEN_INDUCTIVE requires a valid checked backend result",
                )
            )
        if producer is None or producer.producer_kind != "proof_assistant":
            findings.append(
                EvidenceBoundaryFinding(
                    backend=backend_result.backend,
                    evidence_level=backend_result.evidence_level,
                    severity="blocking",
                    message="PROVEN_INDUCTIVE requires a registered proof_assistant producer",
                )
            )
        if not any(artifact.kind == "checked_proof" for artifact in artifacts):
            findings.append(
                EvidenceBoundaryFinding(
                    backend=backend_result.backend,
                    evidence_level=backend_result.evidence_level,
                    severity="blocking",
                    message="PROVEN_INDUCTIVE requires a retained checked_proof artifact",
                )
            )
        if not command:
            findings.append(
                EvidenceBoundaryFinding(
                    backend=backend_result.backend,
                    evidence_level=backend_result.evidence_level,
                    severity="blocking",
                    message="PROVEN_INDUCTIVE requires proof checker command metadata",
                )
            )
    elif backend_result.evidence_level == EvidenceLevel.BOUNDED_CHECKED:
        findings.append(
            EvidenceBoundaryFinding(
                backend=backend_result.backend,
                evidence_level=backend_result.evidence_level,
                severity="info",
                message="bounded model-checker evidence cannot claim PROVEN_INDUCTIVE",
            )
        )
    elif backend_result.evidence_level is None:
        findings.append(
            EvidenceBoundaryFinding(
                backend=backend_result.backend,
                evidence_level=None,
                severity="info",
                message="backend emitted no evidence level",
            )
        )
    return ProofProducingBackendBoundaryReport(
        backend=backend_result.backend,
        result="blocked" if any(item.severity == "blocking" for item in findings) else "accepted",
        claimed_evidence_level=backend_result.evidence_level,
        producer_kind=producer.producer_kind if producer is not None else None,
        proof_artifacts=artifacts,
        checker_command=command,
        findings=findings,
        input_hashes={
            "backend_result": sha256_json(backend_result),
            "producer_mapping": sha256_json(producer_mapping),
            "proof_artifacts": sha256_json(artifacts),
        },
    )


def _claim_for_level(level: EvidenceLevel) -> Literal["none", "reviewed", "bounded", "inductive"]:
    if level == EvidenceLevel.PROVEN_INDUCTIVE:
        return "inductive"
    if level in {EvidenceLevel.BOUNDED_CHECKED, EvidenceLevel.SMT_CHECKED}:
        return "bounded"
    if level == EvidenceLevel.REVIEWED:
        return "reviewed"
    return "none"


def _max_claim(current: str, candidate: str):
    order = {"none": 0, "reviewed": 1, "bounded": 2, "inductive": 3}
    return candidate if order[candidate] > order[current] else current
