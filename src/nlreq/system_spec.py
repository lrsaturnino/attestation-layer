from __future__ import annotations

import hashlib
from pathlib import Path, PurePosixPath
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .impact import ImpactAnalysisArtifact


SYSTEM_SPEC_REGISTRY_VERSION = "0.1"


class SystemSpecEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    spec_id: str
    module_ids: list[str] = Field(min_length=1)
    formalism: Literal["tla", "smt", "ltl", "alloy", "lean", "other"]
    path: str
    version: str
    review_status: Literal["draft", "reviewed", "rejected"]
    freshness: Literal["fresh", "stale", "unknown"] = "unknown"
    recorded_hash: str | None = None
    metadata: dict[str, str] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_path(self) -> SystemSpecEntry:
        parsed = PurePosixPath(self.path)
        if parsed.is_absolute() or ".." in parsed.parts:
            raise ValueError("system spec path must be project-root-relative")
        return self


class SystemSpecRegistry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["0.1"] = SYSTEM_SPEC_REGISTRY_VERSION
    specs: list[SystemSpecEntry] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_unique_ids(self) -> SystemSpecRegistry:
        spec_ids = [spec.spec_id for spec in self.specs]
        if len(spec_ids) != len(set(spec_ids)):
            raise ValueError("system spec ids must be unique")
        return self


class SystemSpecStatus(BaseModel):
    model_config = ConfigDict(extra="forbid")

    spec_id: str
    module_ids: list[str]
    path: str
    version: str
    formalism: str
    review_status: str
    freshness: str
    current_hash: str | None = None
    recorded_hash: str | None = None
    status: Literal["fresh", "stale", "missing", "unreviewed"]
    reason: str | None = None


class SystemSpecRegistryReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["0.1"] = SYSTEM_SPEC_REGISTRY_VERSION
    result: Literal["valid", "needs_review"]
    statuses: list[SystemSpecStatus] = Field(default_factory=list)


def load_system_spec_registry(path: Path) -> SystemSpecRegistry:
    return SystemSpecRegistry.model_validate_json(path.read_text())


def build_system_spec_registry_report(
    registry: SystemSpecRegistry,
    *,
    project_root: Path,
    module_ids: list[str] | None = None,
) -> SystemSpecRegistryReport:
    selected = set(module_ids or [])
    statuses = [
        _status_for_entry(entry, project_root=project_root)
        for entry in registry.specs
        if not selected or selected.intersection(entry.module_ids)
    ]
    result = "valid" if all(status.status == "fresh" for status in statuses) else "needs_review"
    return SystemSpecRegistryReport(result=result, statuses=statuses)


def specs_for_impact(
    registry: SystemSpecRegistry,
    impact: ImpactAnalysisArtifact,
) -> list[SystemSpecEntry]:
    affected = set(impact.affected_modules)
    return [entry for entry in registry.specs if affected.intersection(entry.module_ids)]


def _status_for_entry(entry: SystemSpecEntry, *, project_root: Path) -> SystemSpecStatus:
    path = (project_root / entry.path).resolve(strict=False)
    if not path.is_file():
        return SystemSpecStatus(
            spec_id=entry.spec_id,
            module_ids=entry.module_ids,
            path=entry.path,
            version=entry.version,
            formalism=entry.formalism,
            review_status=entry.review_status,
            freshness=entry.freshness,
            recorded_hash=entry.recorded_hash,
            status="missing",
            reason="spec file is missing",
        )
    current_hash = _sha256_file(path)
    if entry.review_status != "reviewed":
        status = "unreviewed"
        reason = "spec is not reviewed"
    elif entry.freshness != "fresh":
        status = "stale"
        reason = "spec freshness is not fresh"
    elif entry.recorded_hash is not None and entry.recorded_hash != current_hash:
        status = "stale"
        reason = "recorded hash does not match current spec"
    else:
        status = "fresh"
        reason = None
    return SystemSpecStatus(
        spec_id=entry.spec_id,
        module_ids=entry.module_ids,
        path=entry.path,
        version=entry.version,
        formalism=entry.formalism,
        review_status=entry.review_status,
        freshness=entry.freshness,
        current_hash=current_hash,
        recorded_hash=entry.recorded_hash,
        status=status,  # type: ignore[arg-type]
        reason=reason,
    )


def _sha256_file(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()
