from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .impact import ImpactAnalysisArtifact
from .models import NormalizedTraceArtifact, RequirementIRV2, SemanticNode
from .spec_drift import CodeSpecManifest
from .system_spec import (
    SystemSpecRegistry,
    build_system_spec_registry_report,
    unspecified_modules,
)


COVERAGE_ALIGNMENT_SCHEMA_VERSION = "0.1"
CODE_SPEC_COVERAGE_V2_SCHEMA_VERSION = "0.2"
SPEC_COVERAGE_GATE_SCHEMA_VERSION = "0.1"


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


class CodeSpecCoverageManifestEntryV2(BaseModel):
    model_config = ConfigDict(extra="forbid")

    module_id: str
    source_paths: list[str] = Field(default_factory=list)
    spec_ids: list[str] = Field(default_factory=list)
    review_status: Literal["reviewed", "candidate", "draft", "rejected", "missing"] = "missing"
    coverage_level: Literal["full", "partial", "none", "unsupported"] = "none"
    coverage_ratio: float = 0.0
    freshness: Literal["fresh", "stale", "unknown"] = "unknown"
    dependency_module_ids: list[str] = Field(default_factory=list)
    trace_ids: list[str] = Field(default_factory=list)
    covered_symbols: list[str] = Field(default_factory=list)
    unsupported_fragments: list[str] = Field(default_factory=list)
    metadata: dict[str, str] = Field(default_factory=dict)


class CodeSpecCoverageManifestV2(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["0.2"] = CODE_SPEC_COVERAGE_V2_SCHEMA_VERSION
    entries: list[CodeSpecCoverageManifestEntryV2] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_unique_modules(self) -> CodeSpecCoverageManifestV2:
        module_ids = [entry.module_id for entry in self.entries]
        if len(module_ids) != len(set(module_ids)):
            raise ValueError("coverage manifest module_id values must be unique")
        return self


class CoverageGateModuleStatusV2(BaseModel):
    model_config = ConfigDict(extra="forbid")

    module_id: str
    status: Literal[
        "covered",
        "missing",
        "partial",
        "candidate",
        "rejected",
        "unsupported",
        "stale",
        "dependency_gap",
    ]
    closure_effect: Literal["allow", "block", "review"]
    spec_ids: list[str] = Field(default_factory=list)
    dependency_module_ids: list[str] = Field(default_factory=list)
    gap_dependency_module_ids: list[str] = Field(default_factory=list)
    trace_ids: list[str] = Field(default_factory=list)
    review_status: str | None = None
    freshness: str | None = None
    coverage_ratio: float = 0.0
    reason: str | None = None


class CodeSpecCoverageGateReportV2(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["0.2"] = CODE_SPEC_COVERAGE_V2_SCHEMA_VERSION
    result: Literal["passed", "blocked", "needs_review"]
    closure_effect: Literal["allow", "block", "review"]
    threshold: float
    covered_modules: int
    total_modules: int
    coverage_ratio: float
    modules: list[CoverageGateModuleStatusV2] = Field(default_factory=list)


class SpeculaExtractionRequest(BaseModel):
    """A queued (placeholder) request to extract a candidate spec S for an unspec'd module (PC-10).

    Queuing only RECORDS the need for coverage; the actual Specula extraction is PC-5 (Solidity) /
    PC-8 (Go) and is out of scope here. ``status`` stays ``queued`` until that extraction runs,
    is trace-validated, reviewed, and promoted into the ``SystemSpecRegistry``.
    """

    model_config = ConfigDict(extra="forbid")

    module_id: str
    status: Literal["queued"] = "queued"
    requested_formalism: Literal["tla", "smt"] = "tla"
    reason: str


class SpecCoverageGateReport(BaseModel):
    """Per-module spec-coverage gate over the affected set (PC-10).

    ``needs_spec_coverage`` iff at least one affected module has NO registered system spec S. Such a
    requirement cannot be verified — there is no S to conjoin or run S ∧ R over — so the gate blocks
    with ``NEEDS_SPEC_COVERAGE`` and queues a (placeholder) Specula extraction per unspec'd module,
    and no S ∧ R runs. This is narrower than ``SpecCoverageReport`` (which also blocks on
    stale/unreviewed/missing-file specs); it isolates the genuinely-unspecified case so the gate can
    distinguish "no spec exists yet" from "a spec exists but is not yet usable".
    """

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["0.1"] = SPEC_COVERAGE_GATE_SCHEMA_VERSION
    result: Literal["covered", "needs_spec_coverage"]
    affected_modules: list[str]
    covered_modules: list[str]
    unspecified_modules: list[str]
    extraction_requests: list[SpeculaExtractionRequest] = Field(default_factory=list)


def build_spec_coverage_gate(
    *,
    impact: ImpactAnalysisArtifact,
    registry: SystemSpecRegistry,
) -> SpecCoverageGateReport:
    """Gate the affected set on per-module spec coverage, queuing extraction for unspec'd modules.

    A module is "unspec'd" when no registry entry lists it (see
    :func:`system_spec.unspecified_modules`) — distinct from a stale/unreviewed spec. Each unspec'd
    module gets one queued :class:`SpeculaExtractionRequest`; the gate result is
    ``needs_spec_coverage`` when any exists, else ``covered``.
    """
    affected = list(getattr(impact, "affected_modules"))
    unspecified = unspecified_modules(registry, affected)
    unspecified_set = set(unspecified)
    covered = [module_id for module_id in affected if module_id not in unspecified_set]
    extraction_requests = [
        SpeculaExtractionRequest(
            module_id=module_id,
            reason=(
                "affected module has no registered system spec S; queued for Specula extraction "
                "(PC-5 Solidity / PC-8 Go) — review and promote before S ∧ R can run"
            ),
        )
        for module_id in unspecified
    ]
    return SpecCoverageGateReport(
        result="needs_spec_coverage" if unspecified else "covered",
        affected_modules=sorted(affected),
        covered_modules=sorted(covered),
        unspecified_modules=unspecified,
        extraction_requests=extraction_requests,
    )


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


def migrate_code_spec_manifest_to_v2(
    manifest: CodeSpecManifest,
    *,
    registry: SystemSpecRegistry,
) -> CodeSpecCoverageManifestV2:
    specs_by_id = {spec.spec_id: spec for spec in registry.specs}
    entries: list[CodeSpecCoverageManifestEntryV2] = []
    for entry in manifest.entries:
        specs = [specs_by_id[spec_id] for spec_id in entry.spec_ids if spec_id in specs_by_id]
        review_status = _merged_review_status([spec.review_status for spec in specs])
        freshness = _merged_freshness([spec.freshness for spec in specs])
        coverage_level: Literal["full", "partial", "none", "unsupported"] = "full" if specs else "none"
        entries.append(
            CodeSpecCoverageManifestEntryV2(
                module_id=entry.module_id,
                source_paths=entry.source_paths,
                spec_ids=entry.spec_ids,
                review_status=review_status,
                coverage_level=coverage_level,
                coverage_ratio=1.0 if coverage_level == "full" else 0.0,
                freshness=freshness,
                dependency_module_ids=entry.dependency_module_ids,
                metadata={"migrated_from": "code-spec-manifest-0.1"},
            )
        )
    return CodeSpecCoverageManifestV2(entries=entries)


def build_code_spec_coverage_gate_report_v2(
    *,
    impact,
    manifest: CodeSpecCoverageManifestV2,
    threshold: float = 1.0,
) -> CodeSpecCoverageGateReportV2:
    entries_by_module = {entry.module_id: entry for entry in manifest.entries}
    affected_modules = list(getattr(impact, "affected_modules"))
    statuses = [
        _coverage_status_for_module(
            module_id,
            entries_by_module.get(module_id),
            threshold=threshold,
        )
        for module_id in affected_modules
    ]
    statuses = _propagate_coverage_dependency_gaps(statuses)
    total = len(statuses)
    covered = sum(1 for status in statuses if status.status == "covered")
    ratio = covered / total if total else 1.0
    closure_effect = _coverage_closure_effect(statuses)
    return CodeSpecCoverageGateReportV2(
        result="passed" if closure_effect == "allow" else ("blocked" if closure_effect == "block" else "needs_review"),
        closure_effect=closure_effect,
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


def _coverage_status_for_module(
    module_id: str,
    entry: CodeSpecCoverageManifestEntryV2 | None,
    *,
    threshold: float,
) -> CoverageGateModuleStatusV2:
    if entry is None:
        return CoverageGateModuleStatusV2(
            module_id=module_id,
            status="missing",
            closure_effect="block",
            reason="affected module is absent from coverage manifest v2",
        )
    base = {
        "module_id": module_id,
        "spec_ids": entry.spec_ids,
        "dependency_module_ids": entry.dependency_module_ids,
        "trace_ids": entry.trace_ids,
        "review_status": entry.review_status,
        "freshness": entry.freshness,
        "coverage_ratio": entry.coverage_ratio,
    }
    if entry.review_status in {"candidate", "draft", "missing"}:
        return CoverageGateModuleStatusV2(
            **base,
            status="candidate" if entry.review_status in {"candidate", "draft"} else "missing",
            closure_effect="block",
            reason="coverage is not reviewed",
        )
    if entry.review_status == "rejected":
        return CoverageGateModuleStatusV2(
            **base,
            status="rejected",
            closure_effect="block",
            reason="coverage entry was rejected",
        )
    if entry.freshness == "stale":
        return CoverageGateModuleStatusV2(
            **base,
            status="stale",
            closure_effect="block",
            reason="covered spec is stale",
        )
    if entry.coverage_level == "unsupported":
        return CoverageGateModuleStatusV2(
            **base,
            status="unsupported",
            closure_effect="block",
            reason="coverage manifest declares unsupported requirement fragments",
        )
    if entry.coverage_level != "full" or entry.coverage_ratio < threshold:
        return CoverageGateModuleStatusV2(
            **base,
            status="partial",
            closure_effect="block",
            reason="coverage ratio is below threshold",
        )
    return CoverageGateModuleStatusV2(
        **base,
        status="covered",
        closure_effect="allow",
    )


def _propagate_coverage_dependency_gaps(
    statuses: list[CoverageGateModuleStatusV2],
) -> list[CoverageGateModuleStatusV2]:
    by_module = {status.module_id: status for status in statuses}
    blocked_modules = {
        status.module_id for status in statuses if status.closure_effect != "allow"
    }
    propagated: list[CoverageGateModuleStatusV2] = []
    for status in statuses:
        gap_dependencies = [
            module_id
            for module_id in status.dependency_module_ids
            if module_id in blocked_modules or module_id not in by_module
        ]
        if status.closure_effect == "allow" and gap_dependencies:
            propagated.append(
                status.model_copy(
                    update={
                        "status": "dependency_gap",
                        "closure_effect": "block",
                        "gap_dependency_module_ids": gap_dependencies,
                        "reason": "dependency coverage gap propagates to affected module",
                    }
                )
            )
        else:
            propagated.append(status)
    return propagated


def _coverage_closure_effect(
    statuses: list[CoverageGateModuleStatusV2],
) -> Literal["allow", "block", "review"]:
    if any(status.closure_effect == "block" for status in statuses):
        return "block"
    if any(status.closure_effect == "review" for status in statuses):
        return "review"
    return "allow"


def _merged_review_status(
    statuses: list[str],
) -> Literal["reviewed", "candidate", "draft", "rejected", "missing"]:
    if not statuses:
        return "missing"
    if "rejected" in statuses:
        return "rejected"
    if all(status == "reviewed" for status in statuses):
        return "reviewed"
    if "draft" in statuses:
        return "draft"
    return "candidate"


def _merged_freshness(statuses: list[str]) -> Literal["fresh", "stale", "unknown"]:
    if not statuses:
        return "unknown"
    if "stale" in statuses:
        return "stale"
    if all(status == "fresh" for status in statuses):
        return "fresh"
    return "unknown"
