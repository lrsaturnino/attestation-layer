from __future__ import annotations

import hashlib
from pathlib import Path, PurePosixPath
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .system_spec import SystemSpecRegistry


SPEC_DRIFT_SCHEMA_VERSION = "0.1"


class CodeSpecManifestEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    module_id: str
    source_paths: list[str] = Field(min_length=1)
    spec_ids: list[str] = Field(min_length=1)
    dependency_module_ids: list[str] = Field(default_factory=list)
    recorded_source_hashes: dict[str, str] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_paths(self) -> CodeSpecManifestEntry:
        for path in self.source_paths:
            parsed = PurePosixPath(path)
            if parsed.is_absolute() or ".." in parsed.parts:
                raise ValueError("source_paths must be project-root-relative")
        return self


class CodeSpecManifest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["0.1"] = SPEC_DRIFT_SCHEMA_VERSION
    entries: list[CodeSpecManifestEntry] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_unique_modules(self) -> CodeSpecManifest:
        module_ids = [entry.module_id for entry in self.entries]
        if len(module_ids) != len(set(module_ids)):
            raise ValueError("module_id values must be unique")
        return self


class SpecDriftStatus(BaseModel):
    model_config = ConfigDict(extra="forbid")

    module_id: str
    status: Literal["fresh", "stale", "missing_source"]
    spec_ids: list[str]
    changed_paths: list[str] = Field(default_factory=list)
    dependency_module_ids: list[str] = Field(default_factory=list)
    stale_due_to_dependencies: list[str] = Field(default_factory=list)
    recorded_source_hashes: dict[str, str] = Field(default_factory=dict)
    current_source_hashes: dict[str, str] = Field(default_factory=dict)
    required_refresh_actions: list[str] = Field(default_factory=list)


class SpecDriftReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["0.1"] = SPEC_DRIFT_SCHEMA_VERSION
    result: Literal["passed", "blocked"]
    statuses: list[SpecDriftStatus] = Field(default_factory=list)


def build_spec_drift_report(
    manifest: CodeSpecManifest,
    *,
    project_root: Path,
) -> SpecDriftReport:
    statuses = [_direct_status(entry, project_root=project_root) for entry in manifest.entries]
    stale_modules = {
        status.module_id
        for status in statuses
        if status.status in {"stale", "missing_source"}
    }
    propagated: list[SpecDriftStatus] = []
    for status in statuses:
        dependencies = [
            module_id for module_id in status.dependency_module_ids if module_id in stale_modules
        ]
        if status.status == "fresh" and dependencies:
            propagated.append(
                status.model_copy(
                    update={
                        "status": "stale",
                        "stale_due_to_dependencies": dependencies,
                        "required_refresh_actions": [
                            f"refresh specs {', '.join(status.spec_ids)} after dependency drift"
                        ],
                    }
                )
            )
        else:
            propagated.append(status)
    blocked = any(status.status != "fresh" for status in propagated)
    return SpecDriftReport(result="blocked" if blocked else "passed", statuses=propagated)


def mark_stale_specs(registry: SystemSpecRegistry, report: SpecDriftReport) -> SystemSpecRegistry:
    stale_spec_ids = {
        spec_id
        for status in report.statuses
        if status.status != "fresh"
        for spec_id in status.spec_ids
    }
    specs = [
        spec.model_copy(update={"freshness": "stale"})
        if spec.spec_id in stale_spec_ids
        else spec
        for spec in registry.specs
    ]
    return registry.model_copy(update={"specs": specs})


def _direct_status(entry: CodeSpecManifestEntry, *, project_root: Path) -> SpecDriftStatus:
    current_hashes: dict[str, str] = {}
    changed_paths: list[str] = []
    missing_paths: list[str] = []
    for source_path in entry.source_paths:
        path = (project_root / source_path).resolve(strict=False)
        if not path.is_file():
            missing_paths.append(source_path)
            continue
        current = _sha256_file(path)
        current_hashes[source_path] = current
        recorded = entry.recorded_source_hashes.get(source_path)
        if recorded != current:
            changed_paths.append(source_path)
    if missing_paths:
        return SpecDriftStatus(
            module_id=entry.module_id,
            status="missing_source",
            spec_ids=entry.spec_ids,
            changed_paths=missing_paths,
            dependency_module_ids=entry.dependency_module_ids,
            recorded_source_hashes=entry.recorded_source_hashes,
            current_source_hashes=current_hashes,
            required_refresh_actions=[
                f"restore or re-map missing source paths for module {entry.module_id}"
            ],
        )
    if changed_paths:
        return SpecDriftStatus(
            module_id=entry.module_id,
            status="stale",
            spec_ids=entry.spec_ids,
            changed_paths=changed_paths,
            dependency_module_ids=entry.dependency_module_ids,
            recorded_source_hashes=entry.recorded_source_hashes,
            current_source_hashes=current_hashes,
            required_refresh_actions=[
                f"refresh specs {', '.join(entry.spec_ids)} for changed source"
            ],
        )
    return SpecDriftStatus(
        module_id=entry.module_id,
        status="fresh",
        spec_ids=entry.spec_ids,
        dependency_module_ids=entry.dependency_module_ids,
        recorded_source_hashes=entry.recorded_source_hashes,
        current_source_hashes=current_hashes,
    )


def _sha256_file(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()
