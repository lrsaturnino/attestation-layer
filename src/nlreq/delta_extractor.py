from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from .coverage_alignment import SpecCoverageReport
from .requirement_self_consistency import RequirementSelfConsistencyResult
from .spec_drift import SpecDriftReport
from .system_checker import SystemConsistencyResult
from .trace_replay import TraceReplayReport


DELTA_EXTRACTOR_SCHEMA_VERSION = "0.1"


class DeltaItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    delta_id: str
    category: Literal["requirement", "spec", "code", "test", "trace"]
    severity: Literal["blocking", "review"]
    source: str
    summary: str
    required_action: str
    refs: dict[str, str] = Field(default_factory=dict)


class DeltaReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["0.1"] = DELTA_EXTRACTOR_SCHEMA_VERSION
    result: Literal["no_changes", "changes_required"]
    deltas: list[DeltaItem] = Field(default_factory=list)


def build_delta_report(
    *,
    self_consistency: RequirementSelfConsistencyResult | None = None,
    system_consistency: SystemConsistencyResult | None = None,
    spec_coverage: SpecCoverageReport | None = None,
    trace_replay: TraceReplayReport | None = None,
    spec_drift: SpecDriftReport | None = None,
) -> DeltaReport:
    deltas: list[DeltaItem] = []
    if self_consistency is not None:
        deltas.extend(_self_consistency_deltas(self_consistency))
    if system_consistency is not None:
        deltas.extend(_system_consistency_deltas(system_consistency))
    if spec_coverage is not None:
        deltas.extend(_coverage_deltas(spec_coverage))
    if trace_replay is not None:
        deltas.extend(_trace_replay_deltas(trace_replay))
    if spec_drift is not None:
        deltas.extend(_drift_deltas(spec_drift))
    return DeltaReport(
        result="changes_required" if deltas else "no_changes",
        deltas=deltas,
    )


def delta_report_markdown(report: DeltaReport) -> str:
    lines = ["# Delta Report", "", f"Result: `{report.result}`", ""]
    if not report.deltas:
        lines.append("No required deltas.")
        return "\n".join(lines) + "\n"
    lines.extend(["| ID | Category | Severity | Source | Summary |", "|---|---|---|---|---|"])
    for delta in report.deltas:
        lines.append(
            "| {delta_id} | {category} | {severity} | {source} | {summary} |".format(
                delta_id=delta.delta_id,
                category=delta.category,
                severity=delta.severity,
                source=delta.source,
                summary=_escape(delta.summary),
            )
        )
    lines.extend(["", "## Required Actions", ""])
    for delta in report.deltas:
        lines.append(f"- `{delta.delta_id}`: {delta.required_action}")
    return "\n".join(lines) + "\n"


def _self_consistency_deltas(report: RequirementSelfConsistencyResult) -> list[DeltaItem]:
    if report.status == "valid":
        return []
    return [
        DeltaItem(
            delta_id=f"delta:requirement:{report.requirement_id}",
            category="requirement",
            severity="blocking",
            source="requirement_self_consistency",
            summary=f"Requirement self-consistency is {report.status}",
            required_action="revise or clarify the requirement before system composition",
            refs={"requirement_id": report.requirement_id, "status": report.status},
        )
    ]


def _system_consistency_deltas(report: SystemConsistencyResult) -> list[DeltaItem]:
    if report.result.status == "valid":
        return []
    category = "code" if report.result.status == "counterexample" else "spec"
    return [
        DeltaItem(
            delta_id=f"delta:{category}:{report.requirement_id}",
            category=category,  # type: ignore[arg-type]
            severity="blocking",
            source="system_consistency",
            summary=f"System consistency is {report.result.status}",
            required_action="inspect counterexamples and update code, specs, or requirement",
            refs={"requirement_id": report.requirement_id, "status": report.result.status},
        )
    ]


def _coverage_deltas(report: SpecCoverageReport) -> list[DeltaItem]:
    deltas: list[DeltaItem] = []
    for module in report.modules:
        if module.status != "covered":
            deltas.append(
                DeltaItem(
                    delta_id=f"delta:spec:{module.module_id}",
                    category="spec",
                    severity="blocking",
                    source="spec_coverage",
                    summary=f"Module {module.module_id} coverage is {module.status}",
                    required_action="add, review, or refresh the module system spec",
                    refs={"module_id": module.module_id, "status": module.status},
                )
            )
    return deltas


def _trace_replay_deltas(report: TraceReplayReport) -> list[DeltaItem]:
    deltas: list[DeltaItem] = []
    for observation in report.observations:
        if observation.status == "satisfied":
            continue
        category = "trace" if observation.status in {"uncovered", "unsupported"} else "code"
        deltas.append(
            DeltaItem(
                delta_id=f"delta:{category}:{observation.trace_id}",
                category=category,  # type: ignore[arg-type]
                severity="blocking",
                source="trace_replay",
                summary=f"Trace {observation.trace_id} replay is {observation.status}",
                required_action="refresh traces or fix behavior to satisfy replayed requirement",
                refs={
                    "trace_id": observation.trace_id,
                    "status": observation.status,
                    "requirement_id": observation.requirement_id,
                },
            )
        )
    return deltas


def _drift_deltas(report: SpecDriftReport) -> list[DeltaItem]:
    deltas: list[DeltaItem] = []
    for status in report.statuses:
        if status.status == "fresh":
            continue
        deltas.append(
            DeltaItem(
                delta_id=f"delta:spec-drift:{status.module_id}",
                category="spec",
                severity="blocking",
                source="spec_drift",
                summary=f"Module {status.module_id} drift is {status.status}",
                required_action="; ".join(status.required_refresh_actions)
                or "refresh affected specs",
                refs={"module_id": status.module_id, "status": status.status},
            )
        )
    return deltas


def _escape(value: str) -> str:
    return value.replace("|", "\\|").replace("\n", " ")
