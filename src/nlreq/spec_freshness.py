from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .jsonutil import sha256_json
from .spec_drift import CodeSpecManifest
from .system_spec import SystemSpecRegistry


SPEC_FRESHNESS_SCHEMA_VERSION = "0.1"
SPEC_FRESHNESS_TOOL_VERSION = "0.1"


class SpecFreshnessLockEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    module_id: str
    source_hashes: dict[str, str] = Field(default_factory=dict)
    spec_hashes: dict[str, str] = Field(default_factory=dict)
    dependency_module_ids: list[str] = Field(default_factory=list)
    manifest_entry_hash: str


class SpecFreshnessLockfile(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["0.1"] = SPEC_FRESHNESS_SCHEMA_VERSION
    lock_id: str
    entries: list[SpecFreshnessLockEntry] = Field(default_factory=list)
    tool: str = "nlreq.spec_freshness"
    tool_version: str = SPEC_FRESHNESS_TOOL_VERSION

    @model_validator(mode="after")
    def validate_unique_modules(self) -> SpecFreshnessLockfile:
        module_ids = [entry.module_id for entry in self.entries]
        if len(module_ids) != len(set(module_ids)):
            raise ValueError("lockfile module_id values must be unique")
        return self


class SpecFreshnessLockStatus(BaseModel):
    model_config = ConfigDict(extra="forbid")

    module_id: str
    status: Literal["fresh", "stale", "missing_lock", "missing_file"]
    changed_sources: list[str] = Field(default_factory=list)
    changed_specs: list[str] = Field(default_factory=list)
    reason: str | None = None


class SpecFreshnessLockReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["0.1"] = SPEC_FRESHNESS_SCHEMA_VERSION
    result: Literal["passed", "blocked"]
    statuses: list[SpecFreshnessLockStatus] = Field(default_factory=list)


def build_spec_freshness_lockfile(
    *,
    manifest: CodeSpecManifest,
    registry: SystemSpecRegistry,
    project_root: Path,
    lock_id: str = "spec-freshness",
) -> SpecFreshnessLockfile:
    specs_by_id = {spec.spec_id: spec for spec in registry.specs}
    entries: list[SpecFreshnessLockEntry] = []
    for entry in manifest.entries:
        source_hashes = {
            source_path: _sha256_path(project_root / source_path)
            for source_path in entry.source_paths
            if (project_root / source_path).is_file()
        }
        spec_hashes = {
            spec_id: _sha256_path(project_root / specs_by_id[spec_id].path)
            for spec_id in entry.spec_ids
            if spec_id in specs_by_id and (project_root / specs_by_id[spec_id].path).is_file()
        }
        entries.append(
            SpecFreshnessLockEntry(
                module_id=entry.module_id,
                source_hashes=source_hashes,
                spec_hashes=spec_hashes,
                dependency_module_ids=entry.dependency_module_ids,
                manifest_entry_hash=sha256_json(entry),
            )
        )
    return SpecFreshnessLockfile(lock_id=lock_id, entries=entries)


def validate_spec_freshness_lockfile(
    *,
    manifest: CodeSpecManifest,
    registry: SystemSpecRegistry,
    lockfile: SpecFreshnessLockfile,
    project_root: Path,
) -> SpecFreshnessLockReport:
    current = build_spec_freshness_lockfile(
        manifest=manifest,
        registry=registry,
        project_root=project_root,
        lock_id=lockfile.lock_id,
    )
    expected_by_module = {entry.module_id: entry for entry in lockfile.entries}
    current_by_module = {entry.module_id: entry for entry in current.entries}
    statuses: list[SpecFreshnessLockStatus] = []
    for module_id, current_entry in current_by_module.items():
        expected = expected_by_module.get(module_id)
        if expected is None:
            statuses.append(
                SpecFreshnessLockStatus(
                    module_id=module_id,
                    status="missing_lock",
                    reason="module is not present in the freshness lockfile",
                )
            )
            continue
        changed_sources = _changed(expected.source_hashes, current_entry.source_hashes)
        changed_specs = _changed(expected.spec_hashes, current_entry.spec_hashes)
        if changed_sources or changed_specs:
            statuses.append(
                SpecFreshnessLockStatus(
                    module_id=module_id,
                    status="stale",
                    changed_sources=changed_sources,
                    changed_specs=changed_specs,
                    reason="source or spec hash differs from lockfile",
                )
            )
        else:
            statuses.append(SpecFreshnessLockStatus(module_id=module_id, status="fresh"))
    for module_id in sorted(set(expected_by_module) - set(current_by_module)):
        statuses.append(
            SpecFreshnessLockStatus(
                module_id=module_id,
                status="missing_file",
                reason="locked module is not present in the current manifest",
            )
        )
    return SpecFreshnessLockReport(
        result="blocked" if any(status.status != "fresh" for status in statuses) else "passed",
        statuses=statuses,
    )


def _changed(expected: dict[str, str], current: dict[str, str]) -> list[str]:
    keys = sorted(set(expected) | set(current))
    return [key for key in keys if expected.get(key) != current.get(key)]


def _sha256_path(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()
