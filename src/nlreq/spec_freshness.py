from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .jsonutil import sha256_json
from .spec_drift import CodeSpecManifest
from .system_spec import SystemSpecRegistry


SPEC_FRESHNESS_SCHEMA_VERSION = "0.1"
SPEC_FRESHNESS_TOOL_VERSION = "0.1"
SPEC_FRESHNESS_V2_SCHEMA_VERSION = "0.2"


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


class SpecFreshnessLockEntryV2(BaseModel):
    model_config = ConfigDict(extra="forbid")

    module_id: str
    source_hashes: dict[str, str] = Field(default_factory=dict)
    spec_hashes: dict[str, str] = Field(default_factory=dict)
    dependency_module_ids: list[str] = Field(default_factory=list)
    manifest_entry_hash: str
    validated_at: str
    validation_artifact_hashes: dict[str, str] = Field(default_factory=dict)


class SpecFreshnessLockfileV2(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["0.2"] = SPEC_FRESHNESS_V2_SCHEMA_VERSION
    lock_id: str
    entries: list[SpecFreshnessLockEntryV2] = Field(default_factory=list)
    tool: str = "nlreq.spec_freshness"
    tool_version: str = SPEC_FRESHNESS_TOOL_VERSION

    @model_validator(mode="after")
    def validate_unique_modules(self) -> SpecFreshnessLockfileV2:
        module_ids = [entry.module_id for entry in self.entries]
        if len(module_ids) != len(set(module_ids)):
            raise ValueError("lockfile module_id values must be unique")
        return self


class SpecFreshnessDriftStatusV2(BaseModel):
    model_config = ConfigDict(extra="forbid")

    module_id: str
    status: Literal[
        "fresh",
        "stale",
        "missing_lock",
        "missing_file",
        "validation_expired",
    ]
    closure_effect: Literal["allow", "block"]
    changed_sources: list[str] = Field(default_factory=list)
    changed_specs: list[str] = Field(default_factory=list)
    stale_due_to_dependencies: list[str] = Field(default_factory=list)
    validated_at: str | None = None
    validation_age_hours: float | None = None
    reason: str | None = None


class SpecFreshnessDriftCiReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["0.2"] = SPEC_FRESHNESS_V2_SCHEMA_VERSION
    result: Literal["passed", "blocked"]
    closure_effect: Literal["allow", "block"]
    statuses: list[SpecFreshnessDriftStatusV2] = Field(default_factory=list)
    stale_metrics: dict[str, int] = Field(default_factory=dict)


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


def build_spec_freshness_lockfile_v2(
    *,
    manifest: CodeSpecManifest,
    registry: SystemSpecRegistry,
    project_root: Path,
    lock_id: str = "spec-freshness",
    validated_at: str = "2026-06-03T00:00:00Z",
    validation_artifact_hashes: dict[str, str] | None = None,
) -> SpecFreshnessLockfileV2:
    v1 = build_spec_freshness_lockfile(
        manifest=manifest,
        registry=registry,
        project_root=project_root,
        lock_id=lock_id,
    )
    return SpecFreshnessLockfileV2(
        lock_id=lock_id,
        entries=[
            SpecFreshnessLockEntryV2(
                module_id=entry.module_id,
                source_hashes=entry.source_hashes,
                spec_hashes=entry.spec_hashes,
                dependency_module_ids=entry.dependency_module_ids,
                manifest_entry_hash=entry.manifest_entry_hash,
                validated_at=validated_at,
                validation_artifact_hashes=validation_artifact_hashes or {},
            )
            for entry in v1.entries
        ],
    )


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


def validate_spec_freshness_lockfile_v2(
    *,
    manifest: CodeSpecManifest,
    registry: SystemSpecRegistry,
    lockfile: SpecFreshnessLockfileV2,
    project_root: Path,
    now: str | None = None,
    max_validation_age_hours: float | None = None,
) -> SpecFreshnessDriftCiReport:
    current = build_spec_freshness_lockfile_v2(
        manifest=manifest,
        registry=registry,
        project_root=project_root,
        lock_id=lockfile.lock_id,
        validated_at=now or _utc_now(),
    )
    expected_by_module = {entry.module_id: entry for entry in lockfile.entries}
    current_by_module = {entry.module_id: entry for entry in current.entries}
    statuses: list[SpecFreshnessDriftStatusV2] = []
    for module_id, current_entry in current_by_module.items():
        expected = expected_by_module.get(module_id)
        if expected is None:
            statuses.append(
                SpecFreshnessDriftStatusV2(
                    module_id=module_id,
                    status="missing_lock",
                    closure_effect="block",
                    reason="module is not present in the freshness lockfile",
                )
            )
            continue
        changed_sources = _changed(expected.source_hashes, current_entry.source_hashes)
        changed_specs = _changed(expected.spec_hashes, current_entry.spec_hashes)
        validation_age = _validation_age_hours(expected.validated_at, now)
        if changed_sources or changed_specs:
            statuses.append(
                SpecFreshnessDriftStatusV2(
                    module_id=module_id,
                    status="stale",
                    closure_effect="block",
                    changed_sources=changed_sources,
                    changed_specs=changed_specs,
                    validated_at=expected.validated_at,
                    validation_age_hours=validation_age,
                    reason="source or spec hash differs from lockfile",
                )
            )
        elif (
            max_validation_age_hours is not None
            and validation_age is not None
            and validation_age > max_validation_age_hours
        ):
            statuses.append(
                SpecFreshnessDriftStatusV2(
                    module_id=module_id,
                    status="validation_expired",
                    closure_effect="block",
                    validated_at=expected.validated_at,
                    validation_age_hours=validation_age,
                    reason="freshness validation is older than policy allows",
                )
            )
        else:
            statuses.append(
                SpecFreshnessDriftStatusV2(
                    module_id=module_id,
                    status="fresh",
                    closure_effect="allow",
                    validated_at=expected.validated_at,
                    validation_age_hours=validation_age,
                )
            )
    for module_id in sorted(set(expected_by_module) - set(current_by_module)):
        statuses.append(
            SpecFreshnessDriftStatusV2(
                module_id=module_id,
                status="missing_file",
                closure_effect="block",
                validated_at=expected_by_module[module_id].validated_at,
                validation_age_hours=_validation_age_hours(
                    expected_by_module[module_id].validated_at, now
                ),
                reason="locked module is not present in the current manifest",
            )
        )
    statuses = _propagate_freshness_dependencies(statuses, expected_by_module)
    blocked = any(status.closure_effect == "block" for status in statuses)
    metrics = {
        "fresh": sum(1 for status in statuses if status.status == "fresh"),
        "stale": sum(1 for status in statuses if status.status == "stale"),
        "missing_lock": sum(1 for status in statuses if status.status == "missing_lock"),
        "missing_file": sum(1 for status in statuses if status.status == "missing_file"),
        "validation_expired": sum(
            1 for status in statuses if status.status == "validation_expired"
        ),
    }
    return SpecFreshnessDriftCiReport(
        result="blocked" if blocked else "passed",
        closure_effect="block" if blocked else "allow",
        statuses=statuses,
        stale_metrics=metrics,
    )


def build_spec_drift_ci_report(
    *,
    manifest: CodeSpecManifest,
    registry: SystemSpecRegistry,
    lockfile: SpecFreshnessLockfileV2,
    project_root: Path,
    now: str | None = None,
    max_validation_age_hours: float | None = None,
) -> SpecFreshnessDriftCiReport:
    return validate_spec_freshness_lockfile_v2(
        manifest=manifest,
        registry=registry,
        lockfile=lockfile,
        project_root=project_root,
        now=now,
        max_validation_age_hours=max_validation_age_hours,
    )


def _changed(expected: dict[str, str], current: dict[str, str]) -> list[str]:
    keys = sorted(set(expected) | set(current))
    return [key for key in keys if expected.get(key) != current.get(key)]


def _sha256_path(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def _propagate_freshness_dependencies(
    statuses: list[SpecFreshnessDriftStatusV2],
    expected_by_module: dict[str, SpecFreshnessLockEntryV2],
) -> list[SpecFreshnessDriftStatusV2]:
    blocked_modules = {
        status.module_id for status in statuses if status.closure_effect == "block"
    }
    propagated: list[SpecFreshnessDriftStatusV2] = []
    for status in statuses:
        expected = expected_by_module.get(status.module_id)
        dependency_module_ids = expected.dependency_module_ids if expected is not None else []
        dependencies = [
            module_id
            for module_id in dependency_module_ids
            if module_id in blocked_modules
        ]
        if status.closure_effect == "allow" and dependencies:
            propagated.append(
                status.model_copy(
                    update={
                        "status": "stale",
                        "closure_effect": "block",
                        "stale_due_to_dependencies": dependencies,
                        "reason": "dependency freshness drift propagates to module",
                    }
                )
            )
        else:
            propagated.append(status)
    return propagated


def _validation_age_hours(validated_at: str, now: str | None) -> float | None:
    if now is None:
        return None
    try:
        validated = _parse_timestamp(validated_at)
        current = _parse_timestamp(now)
    except ValueError:
        return None
    return max((current - validated).total_seconds() / 3600, 0.0)


def _parse_timestamp(value: str) -> datetime:
    normalized = value.replace("Z", "+00:00")
    parsed = datetime.fromisoformat(normalized)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
