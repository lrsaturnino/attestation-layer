from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


REFERENCE_DEMO_SCHEMA_VERSION = "0.1"
REFERENCE_DEMO_TOOL_VERSION = "0.1"


class ReferenceDemoRequirement(BaseModel):
    model_config = ConfigDict(extra="forbid")

    requirement_id: str
    expected_decision: Literal["accepted", "refused", "unknown"]
    controlled_text_path: str
    expected_report_path: str | None = None


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


def build_reference_demo_report(
    manifest: ReferenceDemoManifest,
    *,
    existing_paths: set[str],
) -> ReferenceDemoReport:
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
    return ReferenceDemoReport(
        demo_id=manifest.demo_id,
        result="blocked" if missing else "reproducible",
        missing_artifacts=missing,
        requirement_count=len(manifest.requirements),
    )
