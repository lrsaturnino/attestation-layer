from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from .impact import ImpactAnalysisArtifact
from .jsonutil import sha256_json
from .models import RequirementIRV2
from .system_checker import SystemConsistencyResult
from .system_spec import SystemSpecRegistry, specs_for_impact
from .translator import LoweredFormalArtifact


SYSTEM_COMPOSITION_SCHEMA_VERSION = "0.1"
SYSTEM_COMPOSITION_TOOL_VERSION = "0.1"


class ComposedSystemSpecRef(BaseModel):
    model_config = ConfigDict(extra="forbid")

    spec_id: str
    path: str
    formalism: str
    current_hash: str | None = None
    recorded_hash: str | None = None
    review_status: str
    freshness: str


class SandRCompositionReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["0.1"] = SYSTEM_COMPOSITION_SCHEMA_VERSION
    requirement_id: str
    result: Literal["valid", "counterexample", "timeout", "unsupported", "invalid"]
    composition_id: str
    requirement_hash: str
    lowered_hash: str
    impact_hash: str
    system_specs: list[ComposedSystemSpecRef] = Field(default_factory=list)
    backend_result_hash: str
    limitations: list[str] = Field(default_factory=list)
    tool: str = "nlreq.system_composition"
    tool_version: str = SYSTEM_COMPOSITION_TOOL_VERSION


def build_s_and_r_composition_report(
    *,
    requirement: RequirementIRV2,
    lowered: LoweredFormalArtifact,
    registry: SystemSpecRegistry,
    impact: ImpactAnalysisArtifact,
    project_root: Path,
    consistency: SystemConsistencyResult,
) -> SandRCompositionReport:
    spec_refs = [
        _spec_ref(spec, project_root=project_root)
        for spec in specs_for_impact(registry, impact)
    ]
    requirement_hash = sha256_json(requirement)
    lowered_hash = sha256_json(lowered)
    impact_hash = sha256_json(impact)
    backend_hash = sha256_json(consistency.result)
    return SandRCompositionReport(
        requirement_id=requirement.requirement_id,
        result=consistency.result.status,
        composition_id=f"s-and-r:{requirement.requirement_id}:{_short_hash(requirement_hash + backend_hash)}",
        requirement_hash=requirement_hash,
        lowered_hash=lowered_hash,
        impact_hash=impact_hash,
        system_specs=spec_refs,
        backend_result_hash=backend_hash,
        limitations=[
            "Composition is bounded or backend-scoped unless a proof-producing backend says otherwise.",
            "Draft or stale specs cannot satisfy the composition precondition.",
        ],
    )


def _spec_ref(spec, *, project_root: Path) -> ComposedSystemSpecRef:
    path = project_root / spec.path
    current_hash = _sha256_file(path) if path.is_file() else None
    return ComposedSystemSpecRef(
        spec_id=spec.spec_id,
        path=spec.path,
        formalism=spec.formalism,
        current_hash=current_hash,
        recorded_hash=spec.recorded_hash,
        review_status=spec.review_status,
        freshness=spec.freshness,
    )


def _sha256_file(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def _short_hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:12]
