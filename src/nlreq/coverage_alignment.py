from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from .impact import ImpactAnalysisArtifact
from .models import NormalizedTraceArtifact, RequirementIRV2, SemanticNode
from .system_spec import SystemSpecRegistry, build_system_spec_registry_report


COVERAGE_ALIGNMENT_SCHEMA_VERSION = "0.1"


class ModuleCoverageStatus(BaseModel):
    model_config = ConfigDict(extra="forbid")

    module_id: str
    status: Literal["covered", "missing", "stale", "unreviewed"]
    spec_ids: list[str] = Field(default_factory=list)
    reason: str | None = None


class SpecCoverageReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["0.1"] = COVERAGE_ALIGNMENT_SCHEMA_VERSION
    result: Literal["passed", "blocked"]
    threshold: float
    covered_modules: int
    total_modules: int
    coverage_ratio: float
    modules: list[ModuleCoverageStatus] = Field(default_factory=list)


class TraceAlignmentStatus(BaseModel):
    model_config = ConfigDict(extra="forbid")

    trace_id: str
    status: Literal["aligned", "violating", "uncovered", "unsupported"]
    requirement_id: str
    action: str | None = None
    reason: str | None = None


class TraceAlignmentReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["0.1"] = COVERAGE_ALIGNMENT_SCHEMA_VERSION
    result: Literal["passed", "blocked"]
    alignments: list[TraceAlignmentStatus] = Field(default_factory=list)


def build_spec_coverage_report(
    *,
    impact: ImpactAnalysisArtifact,
    registry: SystemSpecRegistry,
    project_root: Path,
    threshold: float = 1.0,
) -> SpecCoverageReport:
    registry_report = build_system_spec_registry_report(
        registry,
        project_root=project_root,
        module_ids=impact.affected_modules,
    )
    statuses: list[ModuleCoverageStatus] = []
    for module_id in impact.affected_modules:
        matching = [
            status for status in registry_report.statuses if module_id in status.module_ids
        ]
        fresh = [status for status in matching if status.status == "fresh"]
        if fresh:
            statuses.append(
                ModuleCoverageStatus(
                    module_id=module_id,
                    status="covered",
                    spec_ids=[status.spec_id for status in fresh],
                )
            )
            continue
        if not matching:
            statuses.append(
                ModuleCoverageStatus(
                    module_id=module_id,
                    status="missing",
                    reason="no system spec registered for affected module",
                )
            )
            continue
        status = matching[0]
        mapped_status = "unreviewed" if status.status == "unreviewed" else "stale"
        if status.status == "missing":
            mapped_status = "missing"
        statuses.append(
            ModuleCoverageStatus(
                module_id=module_id,
                status=mapped_status,  # type: ignore[arg-type]
                spec_ids=[status.spec_id],
                reason=status.reason,
            )
        )
    total = len(statuses)
    covered = sum(1 for status in statuses if status.status == "covered")
    ratio = covered / total if total else 1.0
    return SpecCoverageReport(
        result="passed" if ratio >= threshold else "blocked",
        threshold=threshold,
        covered_modules=covered,
        total_modules=total,
        coverage_ratio=ratio,
        modules=statuses,
    )


def build_trace_alignment_report(
    *,
    requirement: RequirementIRV2,
    traces: NormalizedTraceArtifact,
    coverage: SpecCoverageReport,
) -> TraceAlignmentReport:
    action = _requirement_action(requirement.semantic_ir)
    alignments: list[TraceAlignmentStatus] = []
    for trace in traces.root:
        if coverage.result != "passed":
            alignments.append(
                TraceAlignmentStatus(
                    trace_id=trace.trace_id,
                    status="unsupported",
                    requirement_id=requirement.requirement_id,
                    action=action,
                    reason="spec coverage did not pass",
                )
            )
            continue
        if trace.metadata.get("alignment_violation") is True:
            alignments.append(
                TraceAlignmentStatus(
                    trace_id=trace.trace_id,
                    status="violating",
                    requirement_id=requirement.requirement_id,
                    action=action,
                    reason="trace declared alignment violation",
                )
            )
            continue
        observed = action is not None and any(event.action == action for event in trace.events)
        alignments.append(
            TraceAlignmentStatus(
                trace_id=trace.trace_id,
                status="aligned" if observed else "uncovered",
                requirement_id=requirement.requirement_id,
                action=action,
                reason=None if observed else "requirement action was not observed",
            )
        )
    blocked = any(item.status != "aligned" for item in alignments)
    return TraceAlignmentReport(
        result="blocked" if blocked else "passed",
        alignments=alignments,
    )


def _requirement_action(node: SemanticNode) -> str | None:
    if node.kind == "action" and node.name:
        return node.name
    for child in [*node.scope, node.premise, node.obligation, node.action, node.must, *node.children]:
        if isinstance(child, SemanticNode):
            found = _requirement_action(child)
            if found:
                return found
    return None
