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


class CrossLanguageSandRSlice(BaseModel):
    model_config = ConfigDict(extra="forbid")

    language: str
    adapter_id: str
    composition: SandRCompositionReport


class CrossLanguageCompositionReport(BaseModel):
    """Aggregate of the PER-LANGUAGE ``S ∧ R`` composition reports a cross-language requirement
    discharges (PC-13). One :class:`SandRCompositionReport` per vertical (Solidity, Go), each the
    real Apalache narrowing of THAT language's reviewed ``S`` against its slice of the requirement —
    never one combined module. ``result`` is ``valid`` only when every per-language ``S ∧ R`` is
    ``valid``; a single ``counterexample``/``timeout``/``unsupported`` makes the aggregate
    ``blocked`` and surfaces that language's blocker, so the cross-language composition cannot read as
    closed while either vertical's system check failed.
    """

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["0.1"] = SYSTEM_COMPOSITION_SCHEMA_VERSION
    requirement_id: str
    result: Literal["valid", "blocked"]
    languages: list[str] = Field(default_factory=list)
    slices: list[CrossLanguageSandRSlice] = Field(default_factory=list)
    blockers: list[str] = Field(default_factory=list)
    tool: str = "nlreq.system_composition"
    tool_version: str = SYSTEM_COMPOSITION_TOOL_VERSION


def build_cross_language_composition_report(
    *,
    requirement_id: str,
    slices: list[CrossLanguageSandRSlice],
) -> CrossLanguageCompositionReport:
    """Fold per-language ``S ∧ R`` composition reports into one cross-language composition report.

    The aggregate is ``valid`` only when every vertical's ``S ∧ R`` result is ``valid``. Each
    non-valid vertical contributes a blocker (its own composition blockers, or a status note), so a
    counterexample in either language blocks the whole cross-language composition. The per-language
    slices are retained verbatim for replay/audit.
    """
    blockers: list[str] = []
    for item in slices:
        status = item.composition.result
        if status != "valid":
            if item.composition.blockers:
                blockers.extend(
                    f"{item.language}: {blocker}" for blocker in item.composition.blockers
                )
            else:
                blockers.append(f"{item.language}: S ∧ R result is {status}")
    return CrossLanguageCompositionReport(
        requirement_id=requirement_id,
        result="blocked" if blockers else "valid",
        languages=[item.language for item in slices],
        slices=slices,
        blockers=blockers,
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
    # The solver-backed S ∧ R check emits the real invariant operators it conjoined into
    # the composed module's Inv (RequirementHolds plus each reviewed system invariant).
    # Read those names rather than inventing the retired SystemSpecAssumptions tautology.
    raw = details.get("preserved_invariants")
    if isinstance(raw, list):
        return [str(item) for item in raw]
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
