from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .end_to_end_gate import (
    EXTENDED_GATE_REQUIRED_STAGES,
    ExtendedEndToEndRequirementGateReport,
)
from .jsonutil import sha256_json


REFERENCE_DEMO_SCHEMA_VERSION = "0.1"
REFERENCE_DEMO_TOOL_VERSION = "0.1"
EXTENDED_REFERENCE_DEMO_SCHEMA_VERSION = "0.1"


class ReferenceDemoRequirement(BaseModel):
    model_config = ConfigDict(extra="forbid")

    requirement_id: str
    expected_decision: Literal["accepted", "refused", "unknown"]
    controlled_text_path: str
    expected_report_path: str | None = None


class ReferenceDemoDecisionCheck(BaseModel):
    model_config = ConfigDict(extra="forbid")

    requirement_id: str
    expected_decision: Literal["accepted", "refused", "unknown"]
    actual_decision: Literal["accepted", "refused", "unknown"] | None = None
    status: Literal["matched", "mismatched", "missing_report", "not_checked"]
    report_path: str | None = None


class ReferenceDemoManifest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["0.1"] = REFERENCE_DEMO_SCHEMA_VERSION
    demo_id: str
    title: str
    source_root: str
    requirements: list[ReferenceDemoRequirement] = Field(default_factory=list)
    system_specs: list[str] = Field(default_factory=list)
    trace_artifacts: list[str] = Field(default_factory=list)
    commands: list[list[str]] = Field(default_factory=list)
    reproducibility_notes: list[str] = Field(default_factory=list)
    tool: str = "nlreq.reference_demo"
    tool_version: str = REFERENCE_DEMO_TOOL_VERSION

    @model_validator(mode="after")
    def validate_demo_has_both_outcomes(self) -> ReferenceDemoManifest:
        decisions = {requirement.expected_decision for requirement in self.requirements}
        if self.requirements and not {"accepted", "refused"}.issubset(decisions):
            raise ValueError("reference demo must include accepted and refused requirements")
        return self


class ReferenceDemoReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["0.1"] = REFERENCE_DEMO_SCHEMA_VERSION
    demo_id: str
    result: Literal["reproducible", "blocked"]
    missing_artifacts: list[str] = Field(default_factory=list)
    requirement_count: int = 0
    artifact_count: int = 0
    command_count: int = 0
    has_accept_and_refuse: bool = False
    decision_checks: list[ReferenceDemoDecisionCheck] = Field(default_factory=list)
    decision_mismatches: list[str] = Field(default_factory=list)
    unchecked_reports: list[str] = Field(default_factory=list)


class ExtendedReferenceDemoGateRun(BaseModel):
    model_config = ConfigDict(extra="forbid")

    requirement_id: str
    decision: Literal["accepted", "refused", "unknown"]
    gate_report_hash: str
    missing_stages: list[str] = Field(default_factory=list)
    failed_stages: list[str] = Field(default_factory=list)
    replay_bundle_hash: str | None = None


class ExtendedReferenceDemoReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["0.1"] = EXTENDED_REFERENCE_DEMO_SCHEMA_VERSION
    demo_id: str
    result: Literal["reproducible", "blocked"]
    base_demo_hash: str
    required_pipeline_stages: list[str] = Field(default_factory=list)
    gate_runs: list[ExtendedReferenceDemoGateRun] = Field(default_factory=list)
    missing_gate_reports: list[str] = Field(default_factory=list)
    missing_replay_bundles: list[str] = Field(default_factory=list)
    stage_failures: list[str] = Field(default_factory=list)
    decision_mismatches: list[str] = Field(default_factory=list)
    command_count: int = 0
    input_hashes: dict[str, str] = Field(default_factory=dict)
    tool: str = "nlreq.reference_demo"
    tool_version: str = REFERENCE_DEMO_TOOL_VERSION


def build_reference_demo_report(
    manifest: ReferenceDemoManifest,
    *,
    existing_paths: set[str],
    actual_decisions_by_requirement: dict[str, Literal["accepted", "refused", "unknown"]] | None = None,
) -> ReferenceDemoReport:
    actual_decisions_by_requirement = actual_decisions_by_requirement or {}
    required_paths = [
        manifest.source_root,
        *manifest.system_specs,
        *manifest.trace_artifacts,
        *[item.controlled_text_path for item in manifest.requirements],
        *[
            item.expected_report_path
            for item in manifest.requirements
            if item.expected_report_path is not None
        ],
    ]
    missing = [path for path in required_paths if path not in existing_paths]
    decisions = {requirement.expected_decision for requirement in manifest.requirements}
    decision_checks = [
        _build_decision_check(requirement, actual_decisions_by_requirement)
        for requirement in manifest.requirements
    ]
    decision_mismatches = [
        check.requirement_id
        for check in decision_checks
        if check.status == "mismatched"
    ]
    unchecked_reports = [
        check.requirement_id
        for check in decision_checks
        if check.status == "missing_report"
    ]
    blocked = bool(missing or decision_mismatches or unchecked_reports or not {"accepted", "refused"}.issubset(decisions))
    return ReferenceDemoReport(
        demo_id=manifest.demo_id,
        result="blocked" if blocked else "reproducible",
        missing_artifacts=missing,
        requirement_count=len(manifest.requirements),
        artifact_count=len(required_paths),
        command_count=len(manifest.commands),
        has_accept_and_refuse={"accepted", "refused"}.issubset(decisions),
        decision_checks=decision_checks,
        decision_mismatches=decision_mismatches,
        unchecked_reports=unchecked_reports,
    )


def build_extended_reference_demo_report(
    manifest: ReferenceDemoManifest,
    base_report: ReferenceDemoReport,
    *,
    gate_reports: list[ExtendedEndToEndRequirementGateReport],
    replay_bundle_hashes: dict[str, str] | None = None,
    required_pipeline_stages: tuple[str, ...] | list[str] = EXTENDED_GATE_REQUIRED_STAGES,
) -> ExtendedReferenceDemoReport:
    replay_bundle_hashes = replay_bundle_hashes or {}
    reports_by_requirement = {report.requirement_id: report for report in gate_reports}
    missing_gate_reports = sorted(
        requirement.requirement_id
        for requirement in manifest.requirements
        if requirement.requirement_id not in reports_by_requirement
    )
    gate_runs = [
        _extended_gate_run(
            report,
            replay_bundle_hash=replay_bundle_hashes.get(report.requirement_id),
            required_pipeline_stages=required_pipeline_stages,
        )
        for report in gate_reports
    ]
    expected_decisions = {
        requirement.requirement_id: requirement.expected_decision
        for requirement in manifest.requirements
    }
    decision_mismatches = sorted(
        run.requirement_id
        for run in gate_runs
        if expected_decisions.get(run.requirement_id) != run.decision
    )
    missing_replay_bundles = sorted(
        run.requirement_id for run in gate_runs if run.replay_bundle_hash is None
    )
    stage_failures = sorted(
        f"{run.requirement_id}:{stage}"
        for run in gate_runs
        if expected_decisions.get(run.requirement_id) == "accepted"
        for stage in [*run.missing_stages, *run.failed_stages]
    )
    blocked = bool(
        base_report.result != "reproducible"
        or missing_gate_reports
        or missing_replay_bundles
        or stage_failures
        or decision_mismatches
        or manifest.commands == []
    )
    return ExtendedReferenceDemoReport(
        demo_id=manifest.demo_id,
        result="blocked" if blocked else "reproducible",
        base_demo_hash=sha256_json(base_report),
        required_pipeline_stages=list(required_pipeline_stages),
        gate_runs=gate_runs,
        missing_gate_reports=missing_gate_reports,
        missing_replay_bundles=missing_replay_bundles,
        stage_failures=stage_failures,
        decision_mismatches=decision_mismatches,
        command_count=len(manifest.commands),
        input_hashes={
            "manifest": sha256_json(manifest),
            "base_report": sha256_json(base_report),
            "gate_reports": sha256_json(gate_reports),
            "replay_bundle_hashes": sha256_json(replay_bundle_hashes),
        },
    )


def _extended_gate_run(
    report: ExtendedEndToEndRequirementGateReport,
    *,
    replay_bundle_hash: str | None,
    required_pipeline_stages: tuple[str, ...] | list[str],
) -> ExtendedReferenceDemoGateRun:
    stages_by_name = {stage.stage: stage for stage in report.stages}
    missing_stages = sorted(
        stage for stage in required_pipeline_stages if stage not in stages_by_name
    )
    failed_stages = sorted(
        stage.stage
        for stage in report.stages
        if stage.stage in required_pipeline_stages and stage.status != "passed"
    )
    return ExtendedReferenceDemoGateRun(
        requirement_id=report.requirement_id,
        decision=report.decision,
        gate_report_hash=sha256_json(report),
        missing_stages=missing_stages,
        failed_stages=failed_stages,
        replay_bundle_hash=replay_bundle_hash,
    )


def _build_decision_check(
    requirement: ReferenceDemoRequirement,
    actual_decisions_by_requirement: dict[str, Literal["accepted", "refused", "unknown"]],
) -> ReferenceDemoDecisionCheck:
    if requirement.expected_report_path is None:
        return ReferenceDemoDecisionCheck(
            requirement_id=requirement.requirement_id,
            expected_decision=requirement.expected_decision,
            status="not_checked",
        )
    actual = actual_decisions_by_requirement.get(requirement.requirement_id)
    if actual is None:
        return ReferenceDemoDecisionCheck(
            requirement_id=requirement.requirement_id,
            expected_decision=requirement.expected_decision,
            status="missing_report",
            report_path=requirement.expected_report_path,
        )
    return ReferenceDemoDecisionCheck(
        requirement_id=requirement.requirement_id,
        expected_decision=requirement.expected_decision,
        actual_decision=actual,
        status="matched" if actual == requirement.expected_decision else "mismatched",
        report_path=requirement.expected_report_path,
    )
