from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from .models import BackendResult, Counterexample, EvidenceLevel, Predicate, RequirementIR, RequirementIRV2, SourceSpan
from .system_spec import SystemSpecRegistry, build_system_spec_registry_report, specs_for_impact
from .impact import ImpactAnalysisArtifact
from .translator import LoweredFormalArtifact


SYSTEM_CHECKER_SCHEMA_VERSION = "0.1"


class SystemConsistencyResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["0.1"] = SYSTEM_CHECKER_SCHEMA_VERSION
    requirement_id: str
    result: BackendResult
    counterexamples: list[Counterexample] = Field(default_factory=list)
    spec_ids: list[str] = Field(default_factory=list)


class RequirementContradiction(BaseModel):
    model_config = ConfigDict(extra="forbid")

    contradiction_type: Literal["opposite_predicate"]
    requirement_ids: list[str]
    fragments: list[str]
    source_spans: list[SourceSpan] = Field(default_factory=list)


class RequirementSetConsistencyReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["0.1"] = SYSTEM_CHECKER_SCHEMA_VERSION
    result: Literal["valid", "contradiction"]
    contradictions: list[RequirementContradiction] = Field(default_factory=list)


def check_system_consistency(
    *,
    requirement: RequirementIRV2,
    lowered: LoweredFormalArtifact,
    registry: SystemSpecRegistry,
    impact: ImpactAnalysisArtifact,
    project_root: Path,
) -> SystemConsistencyResult:
    specs = specs_for_impact(registry, impact)
    registry_report = build_system_spec_registry_report(
        registry,
        project_root=project_root,
        module_ids=impact.affected_modules,
    )
    spec_ids = [spec.spec_id for spec in specs]
    if lowered.status != "lowered":
        return _system_result(
            requirement.requirement_id,
            "unsupported",
            spec_ids,
            {"reason": "lowered artifact is refused"},
        )
    bad_specs = [status for status in registry_report.statuses if status.status != "fresh"]
    if bad_specs:
        return _system_result(
            requirement.requirement_id,
            "unsupported",
            spec_ids,
            {
                "reason": "system specs are missing, stale, or unreviewed",
                "spec_statuses": [status.model_dump(mode="json", exclude_none=True) for status in bad_specs],
            },
        )

    for spec in specs:
        text = (project_root / spec.path).read_text()
        if "NLREQ_TIMEOUT" in text:
            return _system_result(
                requirement.requirement_id,
                "timeout",
                spec_ids,
                {"spec_id": spec.spec_id, "reason": "checker timeout marker"},
            )
        marker = f"NLREQ_COUNTEREXAMPLE:{requirement.requirement_id}"
        if marker in text:
            counterexample = Counterexample(
                counterexample_id=f"{spec.spec_id}:{requirement.requirement_id}",
                backend="system_checker",
                claim_id=requirement.requirement_id,
                description="system spec declares a counterexample marker for requirement",
                metadata={"spec_id": spec.spec_id, "marker": marker},
            )
            result = _system_result(
                requirement.requirement_id,
                "counterexample",
                spec_ids,
                {"spec_id": spec.spec_id, "marker": marker},
            )
            return result.model_copy(update={"counterexamples": [counterexample]})

    return _system_result(
        requirement.requirement_id,
        "valid",
        spec_ids,
        {"checked": "deterministic_s_and_r_boundary"},
    )


def check_requirement_set_consistency(requirements: list[RequirementIR]) -> RequirementSetConsistencyReport:
    contradictions: list[RequirementContradiction] = []
    seen: dict[tuple[str, tuple[str, ...]], tuple[str, Predicate]] = {}
    opposites = {
        "authorized": "not_authorized",
        "not_authorized": "authorized",
        "approved": "not_approved",
        "not_approved": "approved",
        "eq": "neq",
        "neq": "eq",
    }
    for ir in requirements:
        for predicate in ir.claim.condition:
            args = tuple(str(arg.value) for arg in predicate.args)
            opposite = (opposites.get(predicate.op, ""), args)
            if opposite in seen:
                other_id, other_predicate = seen[opposite]
                contradictions.append(
                    RequirementContradiction(
                        contradiction_type="opposite_predicate",
                        requirement_ids=[other_id, ir.requirement_id],
                        fragments=[other_predicate.source_span.text, predicate.source_span.text],
                        source_spans=[other_predicate.source_span, predicate.source_span],
                    )
                )
            seen[(predicate.op, args)] = (ir.requirement_id, predicate)
    return RequirementSetConsistencyReport(
        result="contradiction" if contradictions else "valid",
        contradictions=contradictions,
    )


def _system_result(
    requirement_id: str,
    status: Literal["valid", "counterexample", "timeout", "unsupported"],
    spec_ids: list[str],
    details: dict[str, object],
) -> SystemConsistencyResult:
    return SystemConsistencyResult(
        requirement_id=requirement_id,
        spec_ids=spec_ids,
        result=BackendResult(
            backend="system_checker",
            status=status,
            evidence_level=EvidenceLevel.CONSISTENCY_CHECKED if status == "valid" else None,
            details=details,
        ),
    )
