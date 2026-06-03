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


class CompositionArtifactRef(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal["tla_module", "tla_config", "backend_result"]
    path: str | None = None
    sha256: str
    backend_checkable: bool = True


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
    composition_artifacts: list[CompositionArtifactRef] = Field(default_factory=list)
    preserved_invariants: list[str] = Field(default_factory=list)
    namespace_policy: list[str] = Field(default_factory=list)
    backend_result_hash: str
    blockers: list[str] = Field(default_factory=list)
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
    artifacts = _composition_artifacts(consistency)
    blockers = _composition_blockers(spec_refs, consistency)
    return SandRCompositionReport(
        requirement_id=requirement.requirement_id,
        result=consistency.result.status,
        composition_id=f"s-and-r:{requirement.requirement_id}:{_short_hash(requirement_hash + backend_hash)}",
        requirement_hash=requirement_hash,
        lowered_hash=lowered_hash,
        impact_hash=impact_hash,
        system_specs=spec_refs,
        composition_artifacts=artifacts,
        preserved_invariants=_preserved_invariants(consistency),
        namespace_policy=[
            "Requirement projection is wrapped in a requirement-scoped module name.",
            "Reviewed system spec hashes are retained as composition comments and report fields.",
            "Requirement operators keep generated names; system spec operators are not rewritten.",
        ],
        backend_result_hash=backend_hash,
        blockers=blockers,
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


def _composition_artifacts(consistency: SystemConsistencyResult) -> list[CompositionArtifactRef]:
    details = consistency.result.details
    artifacts = [
        CompositionArtifactRef(kind="backend_result", sha256=sha256_json(consistency.result))
    ]
    artifact_dir = details.get("artifact_dir")
    for kind, name_key, hash_key in [
        ("tla_module", "module", "module_hash"),
        ("tla_config", "config", "config_hash"),
    ]:
        artifact_hash = details.get(hash_key)
        if not isinstance(artifact_hash, str):
            continue
        name = details.get(name_key)
        path = None
        if isinstance(artifact_dir, str) and isinstance(name, str):
            path = (Path(artifact_dir) / name).as_posix()
        artifacts.append(
            CompositionArtifactRef(
                kind=kind,  # type: ignore[arg-type]
                path=path,
                sha256=artifact_hash,
                backend_checkable=consistency.result.status != "unsupported",
            )
        )
    return artifacts


def _preserved_invariants(consistency: SystemConsistencyResult) -> list[str]:
    details = consistency.result.details
    raw = details.get("preserved_invariants")
    if isinstance(raw, list):
        return [str(item) for item in raw]
    if details.get("mode") == "solver_backed":
        return ["SystemAndRequirement", "SystemSpecAssumptions", "RequirementHolds"]
    return ["RequirementHolds"]


def _composition_blockers(
    spec_refs: list[ComposedSystemSpecRef],
    consistency: SystemConsistencyResult,
) -> list[str]:
    blockers = [
        f"{spec.spec_id}: spec is {spec.freshness}"
        for spec in spec_refs
        if spec.freshness != "fresh"
    ]
    blockers.extend(
        f"{spec.spec_id}: review status is {spec.review_status}"
        for spec in spec_refs
        if spec.review_status != "reviewed"
    )
    if consistency.result.status in {"timeout", "unsupported", "invalid"}:
        reason = consistency.result.details.get("reason")
        if isinstance(reason, str):
            blockers.append(reason)
        else:
            blockers.append(f"backend result status is {consistency.result.status}")
    return blockers


def _short_hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:12]
