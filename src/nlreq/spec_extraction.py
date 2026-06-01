from __future__ import annotations

from pathlib import Path, PurePosixPath
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from .impact import ImpactAnalysisArtifact
from .jsonutil import sha256_json, sha256_text
from .models import RequirementIRV2
from .source_adapter import CodePresentation
from .system_spec import (
    SystemSpecEntry,
    SystemSpecRegistry,
    build_system_spec_registry_report,
)
from .trace_replay import TraceReplayReport


SPEC_EXTRACTION_SCHEMA_VERSION = "0.1"


class CandidateSpecProvenance(BaseModel):
    model_config = ConfigDict(extra="forbid")

    extraction_tool: str = "nlreq.spec_extraction"
    extraction_version: str = SPEC_EXTRACTION_SCHEMA_VERSION
    requirement_id: str
    impact_hash: str
    code_presentation_hash: str | None = None
    trace_replay_hash: str | None = None
    llm_draft_used: bool = False
    metadata: dict[str, str] = Field(default_factory=dict)


class CandidateSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    candidate_id: str
    module_id: str
    formalism: Literal["tla", "smt", "ltl", "alloy", "lean", "other"] = "tla"
    path: str
    review_status: Literal["draft"] = "draft"
    freshness: Literal["unknown"] = "unknown"
    content: str
    content_hash: str
    trace_grounding_status: Literal["passed", "blocked", "missing"]
    gaps: list[str] = Field(default_factory=list)
    provenance: CandidateSpecProvenance


class SpecExtractionWorkbenchReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["0.1"] = SPEC_EXTRACTION_SCHEMA_VERSION
    requirement_id: str
    result: Literal["candidates", "none"]
    candidates: list[CandidateSpec] = Field(default_factory=list)


def build_spec_extraction_workbench_report(
    *,
    requirement: RequirementIRV2,
    impact: ImpactAnalysisArtifact,
    registry: SystemSpecRegistry,
    project_root: Path,
    code_presentation: CodePresentation | None = None,
    trace_replay: TraceReplayReport | None = None,
) -> SpecExtractionWorkbenchReport:
    registry_report = build_system_spec_registry_report(
        registry,
        project_root=project_root,
        module_ids=impact.affected_modules,
    )
    fresh_modules = {
        module_id
        for status in registry_report.statuses
        if status.status == "fresh"
        for module_id in status.module_ids
    }
    candidates = [
        _candidate_for_module(
            module_id,
            requirement=requirement,
            impact=impact,
            code_presentation=code_presentation,
            trace_replay=trace_replay,
        )
        for module_id in impact.affected_modules
        if module_id not in fresh_modules
    ]
    return SpecExtractionWorkbenchReport(
        requirement_id=requirement.requirement_id,
        result="candidates" if candidates else "none",
        candidates=candidates,
    )


def candidate_to_draft_spec_entry(candidate: CandidateSpec) -> SystemSpecEntry:
    return SystemSpecEntry(
        spec_id=f"candidate:{candidate.candidate_id}",
        module_ids=[candidate.module_id],
        formalism=candidate.formalism,
        path=candidate.path,
        version="candidate",
        review_status="draft",
        freshness="unknown",
        recorded_hash=candidate.content_hash,
        metadata={"source": "spec_extraction_workbench"},
    )


def promote_candidate_spec(
    candidate: CandidateSpec,
    *,
    approved_hash: str,
    version: str,
) -> SystemSpecEntry:
    if approved_hash != candidate.content_hash:
        raise ValueError("approved candidate hash does not match extracted content")
    return SystemSpecEntry(
        spec_id=f"spec:{candidate.module_id}",
        module_ids=[candidate.module_id],
        formalism=candidate.formalism,
        path=candidate.path,
        version=version,
        review_status="reviewed",
        freshness="fresh",
        recorded_hash=approved_hash,
        metadata={"source": "spec_extraction_workbench", "candidate_id": candidate.candidate_id},
    )


def _candidate_for_module(
    module_id: str,
    *,
    requirement: RequirementIRV2,
    impact: ImpactAnalysisArtifact,
    code_presentation: CodePresentation | None,
    trace_replay: TraceReplayReport | None,
) -> CandidateSpec:
    path = f"specs/candidates/{_safe_path_part(module_id)}.tla"
    content = _candidate_tla_content(module_id, requirement)
    gaps = [
        "candidate spec is draft and cannot satisfy coverage",
        "semantic obligations require human review",
    ]
    if code_presentation is None:
        gaps.append("code presentation was not supplied")
    if trace_replay is None:
        gaps.append("trace grounding was not supplied")
    trace_status = trace_replay.result if trace_replay is not None else "missing"
    return CandidateSpec(
        candidate_id=f"{requirement.requirement_id}:{module_id}",
        module_id=module_id,
        path=path,
        content=content,
        content_hash=sha256_text(content),
        trace_grounding_status=trace_status,
        gaps=gaps,
        provenance=CandidateSpecProvenance(
            requirement_id=requirement.requirement_id,
            impact_hash=sha256_json(impact),
            code_presentation_hash=sha256_json(code_presentation)
            if code_presentation is not None
            else None,
            trace_replay_hash=sha256_json(trace_replay) if trace_replay is not None else None,
            metadata={"module_id": module_id},
        ),
    )


def _candidate_tla_content(module_id: str, requirement: RequirementIRV2) -> str:
    module_name = "Candidate_" + _safe_tla_name(module_id)
    return (
        f"---- MODULE {module_name} ----\n"
        f"\\* Draft candidate spec for module {module_id}\n"
        f"\\* Requirement: {requirement.requirement_id}\n\n"
        "CandidateInvariant == TRUE\n\n"
        "====\n"
    )


def _safe_tla_name(value: str) -> str:
    cleaned = "".join(char if char.isalnum() else "_" for char in value)
    if not cleaned:
        return "Module"
    if cleaned[0].isdigit():
        return "_" + cleaned
    return cleaned


def _safe_path_part(value: str) -> str:
    cleaned = PurePosixPath(_safe_tla_name(value)).name
    return cleaned or "module"
