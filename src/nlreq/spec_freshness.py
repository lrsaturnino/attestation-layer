from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from .jsonutil import sha256_json
from .models import NormalizedTraceArtifact
from .spec_drift import CodeSpecManifest
from .system_spec import SpecTraceContract, SystemSpecRegistry


SPEC_FRESHNESS_SCHEMA_VERSION = "0.1"
SPEC_FRESHNESS_TOOL_VERSION = "0.1"
SPEC_FRESHNESS_V2_SCHEMA_VERSION = "0.2"
SPEC_REVALIDATION_SCHEMA_VERSION = "0.1"
SPEC_FRESHNESS_VERIFICATION_SCHEMA_VERSION = "0.1"


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


# --- PC-12: the spec-revalidate RELEASE path ------------------------------------------------------
# Staleness BLOCKS S ∧ R (spec_drift.mark_stale_specs + the lockfile checkers above); the functions
# below are the only honest way to CLEAR it. A stale covered module is released when — and only
# when — the PC-11 spec↔trace validation (`classify_spec_code_alignment`) re-runs over the module's
# CURRENT real traces and every reviewed spec covering the module REPRODUCES them ("satisfies");
# `violates_with_delta` and `no_coverage` both keep the module stale. The run is recorded as a
# SpecRevalidationRecord whose hash the rebuilt lockfile binds, so a blind hash rebaseline
# (`build_spec_freshness_lockfile_v2` over the edited tree) is INSUFFICIENT: the validation-aware
# checker (`verify_spec_freshness_validation`) requires a record that binds the locked source/spec
# hashes, re-loads the hash-bound contract + traces artifacts, requires source-bound real-tool trace
# provenance, and RE-RUNS the replay — it never trusts a recorded verdict.
#
# Residual (documented, not closeable in data alone): nothing in a recorded artifact can prove the
# traces were extracted AFTER the source edit — a caller could replay yesterday's real forge output
# against today's source. The honest production path re-runs the ecosystem tool at revalidation
# time; this is the same in-process ceiling adapter_certification.trace_has_real_tool_provenance
# documents for the capability gate.


class SpecRevalidationSpecResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    spec_id: str
    classification: Literal["satisfies", "violates_with_delta", "no_coverage"] | None = None
    reasons: list[str] = Field(default_factory=list)
    spec_hash: str | None = None
    contract_path: str | None = None
    contract_hash: str | None = None


class SpecRevalidationModuleResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    module_id: str
    outcome: Literal["revalidated", "rejected"]
    source_hashes: dict[str, str] = Field(default_factory=dict)
    spec_results: list[SpecRevalidationSpecResult] = Field(default_factory=list)
    reasons: list[str] = Field(default_factory=list)


class SpecRevalidationRecord(BaseModel):
    """The recorded evidence of one spec-revalidate run — the artifact the lockfile hash-binds.

    ``traces_path``/``contract_path`` are project-root-relative so the validation-aware checker can
    re-load the exact artifacts the run replayed and re-run the replay itself.
    """

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["0.1"] = SPEC_REVALIDATION_SCHEMA_VERSION
    lock_id: str
    validated_at: str
    traces_path: str
    traces_hash: str
    tool: str = "nlreq.spec_freshness"
    tool_version: str = SPEC_FRESHNESS_TOOL_VERSION
    results: list[SpecRevalidationModuleResult] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_relative_paths(self) -> SpecRevalidationRecord:
        _require_relative_path(self.traces_path, "traces_path")
        for result in self.results:
            for spec_result in result.spec_results:
                if spec_result.contract_path is not None:
                    _require_relative_path(spec_result.contract_path, "contract_path")
        return self


class SpecRevalidationReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["0.1"] = SPEC_REVALIDATION_SCHEMA_VERSION
    result: Literal["revalidated", "rejected"]
    record: SpecRevalidationRecord
    record_hash: str
    record_path: str
    updated_manifest: CodeSpecManifest | None = None
    updated_registry: SystemSpecRegistry | None = None
    updated_lockfile: SpecFreshnessLockfileV2 | None = None


def revalidate_spec_freshness(
    *,
    manifest: CodeSpecManifest,
    registry: SystemSpecRegistry,
    lockfile: SpecFreshnessLockfileV2,
    project_root: Path,
    contracts: list[SpecTraceContract],
    contract_paths: dict[str, str],
    traces: NormalizedTraceArtifact,
    traces_path: str,
    record_path: str,
    validated_at: str | None = None,
    module_ids: list[str] | None = None,
) -> SpecRevalidationReport:
    """Re-validate covered modules against their CURRENT real traces and rebuild the baseline (PC-12).

    For each targeted manifest entry, every reviewed spec covering the module is replayed — via its
    supplied :class:`SpecTraceContract` — against ``traces`` with the PC-11 validator; the module is
    ``revalidated`` only when every spec ``satisfies`` (every declared obligation witnessed, none
    contradicted) AND the traces carry source-bound real-tool provenance. Any other outcome —
    ``violates_with_delta``, ``no_coverage``, a missing/unreviewed spec, a missing contract,
    unprovenanced traces — rejects the module and the baseline is NOT rebuilt for it.

    The updated manifest/registry/lockfile are returned only when EVERY targeted module revalidated:
    the manifest re-baselines the recorded source hashes, the registry releases ``freshness`` back to
    ``fresh`` for the validated specs, and the lockfile binds the revalidation record (which the
    caller must write at ``record_path`` with ``jsonutil.write_json`` so its file hash equals
    ``record_hash``), the traces artifact, and each contract artifact. Non-targeted modules keep
    their old lockfile entries VERBATIM, so a drifted non-targeted module stays blocked.
    """
    stamp = validated_at or _utc_now()
    _parse_timestamp(stamp)
    _require_relative_path(traces_path, "traces_path")
    _require_relative_path(record_path, "record_path")
    contracts_by_spec: dict[str, SpecTraceContract] = {}
    for contract in contracts:
        if contract.spec_id in contracts_by_spec:
            raise ValueError(f"duplicate spec-trace contract for spec {contract.spec_id}")
        contracts_by_spec[contract.spec_id] = contract
        if contract.spec_id not in contract_paths:
            raise ValueError(f"no contract_paths entry for spec {contract.spec_id}")
    selected_ids = set(module_ids) if module_ids is not None else None
    if selected_ids is not None:
        known = {entry.module_id for entry in manifest.entries}
        unknown = sorted(selected_ids - known)
        if unknown:
            raise ValueError(f"modules not in the manifest: {', '.join(unknown)}")
    traces_hash = _existing_file_hash(project_root, traces_path)
    if traces_hash is None:
        raise ValueError(f"traces artifact {traces_path} is not a file under the project root")
    run_reasons = _trace_provenance_reasons(traces)
    specs_by_id = {spec.spec_id: spec for spec in registry.specs}
    results: list[SpecRevalidationModuleResult] = []
    for entry in manifest.entries:
        if selected_ids is not None and entry.module_id not in selected_ids:
            continue
        results.append(
            _revalidate_entry(
                entry,
                specs_by_id=specs_by_id,
                contracts_by_spec=contracts_by_spec,
                contract_paths=contract_paths,
                traces=traces,
                project_root=project_root,
                run_reasons=run_reasons,
            )
        )
    record = SpecRevalidationRecord(
        lock_id=lockfile.lock_id,
        validated_at=stamp,
        traces_path=traces_path,
        traces_hash=traces_hash,
        results=results,
    )
    record_hash = sha256_json(record)
    revalidated = bool(results) and all(result.outcome == "revalidated" for result in results)
    if not revalidated:
        return SpecRevalidationReport(
            result="rejected",
            record=record,
            record_hash=record_hash,
            record_path=record_path,
        )
    results_by_module = {result.module_id: result for result in results}
    updated_manifest = CodeSpecManifest(
        entries=[
            entry.model_copy(
                update={"recorded_source_hashes": dict(results_by_module[entry.module_id].source_hashes)}
            )
            if entry.module_id in results_by_module
            else entry
            for entry in manifest.entries
        ]
    )
    revalidated_spec_ids = {
        spec_result.spec_id
        for result in results
        for spec_result in result.spec_results
    }
    updated_registry = registry.model_copy(
        update={
            "specs": [
                spec.model_copy(update={"freshness": "fresh"})
                if spec.spec_id in revalidated_spec_ids
                else spec
                for spec in registry.specs
            ]
        }
    )
    old_lock_by_module = {entry.module_id: entry for entry in lockfile.entries}
    lock_entries: list[SpecFreshnessLockEntryV2] = []
    for entry in updated_manifest.entries:
        result = results_by_module.get(entry.module_id)
        if result is None:
            old = old_lock_by_module.get(entry.module_id)
            if old is not None:
                lock_entries.append(old)
            continue
        artifact_hashes = {record_path: record_hash, traces_path: traces_hash}
        spec_hashes: dict[str, str] = {}
        for spec_result in result.spec_results:
            if spec_result.contract_path is not None and spec_result.contract_hash is not None:
                artifact_hashes[spec_result.contract_path] = spec_result.contract_hash
            if spec_result.spec_hash is not None:
                spec_hashes[spec_result.spec_id] = spec_result.spec_hash
        lock_entries.append(
            SpecFreshnessLockEntryV2(
                module_id=entry.module_id,
                source_hashes=dict(result.source_hashes),
                spec_hashes=spec_hashes,
                dependency_module_ids=entry.dependency_module_ids,
                manifest_entry_hash=sha256_json(entry),
                validated_at=stamp,
                validation_artifact_hashes=artifact_hashes,
            )
        )
    updated_lockfile = SpecFreshnessLockfileV2(lock_id=lockfile.lock_id, entries=lock_entries)
    return SpecRevalidationReport(
        result="revalidated",
        record=record,
        record_hash=record_hash,
        record_path=record_path,
        updated_manifest=updated_manifest,
        updated_registry=updated_registry,
        updated_lockfile=updated_lockfile,
    )


def _revalidate_entry(
    entry,
    *,
    specs_by_id,
    contracts_by_spec: dict[str, SpecTraceContract],
    contract_paths: dict[str, str],
    traces: NormalizedTraceArtifact,
    project_root: Path,
    run_reasons: list[str],
) -> SpecRevalidationModuleResult:
    reasons = list(run_reasons)
    source_hashes: dict[str, str] = {}
    for source_path in entry.source_paths:
        current = _existing_file_hash(project_root, source_path)
        if current is None:
            reasons.append(f"covered source path {source_path} is missing")
            continue
        source_hashes[source_path] = current
    spec_results: list[SpecRevalidationSpecResult] = []
    for spec_id in entry.spec_ids:
        spec_results.append(
            _revalidate_spec(
                spec_id,
                module_id=entry.module_id,
                specs_by_id=specs_by_id,
                contracts_by_spec=contracts_by_spec,
                contract_paths=contract_paths,
                traces=traces,
                project_root=project_root,
            )
        )
    rejected = bool(reasons) or any(spec_result.reasons for spec_result in spec_results)
    return SpecRevalidationModuleResult(
        module_id=entry.module_id,
        outcome="rejected" if rejected else "revalidated",
        source_hashes=source_hashes,
        spec_results=spec_results,
        reasons=reasons,
    )


def _revalidate_spec(
    spec_id: str,
    *,
    module_id: str,
    specs_by_id,
    contracts_by_spec: dict[str, SpecTraceContract],
    contract_paths: dict[str, str],
    traces: NormalizedTraceArtifact,
    project_root: Path,
) -> SpecRevalidationSpecResult:
    # Deferred import: trace_validation imports this module for its CI report type, so binding the
    # PC-11 classifier at call time avoids the cycle without duplicating the classification.
    from .trace_validation import classify_spec_code_alignment

    reasons: list[str] = []
    spec = specs_by_id.get(spec_id)
    spec_hash: str | None = None
    if spec is None:
        reasons.append(f"spec {spec_id} is not registered")
    else:
        if spec.review_status != "reviewed":
            reasons.append(f"spec {spec_id} review_status is {spec.review_status}, not reviewed")
        if module_id not in spec.module_ids:
            reasons.append(f"spec {spec_id} does not cover module {module_id}")
        spec_hash = _existing_file_hash(project_root, spec.path)
        if spec_hash is None:
            reasons.append(f"spec file {spec.path} is missing")
    contract = contracts_by_spec.get(spec_id)
    contract_path = contract_paths.get(spec_id)
    contract_hash: str | None = None
    classification: Literal["satisfies", "violates_with_delta", "no_coverage"] | None = None
    if contract is None:
        reasons.append(f"no spec-trace contract was supplied for spec {spec_id}")
    else:
        contract_hash = (
            _existing_file_hash(project_root, contract_path) if contract_path is not None else None
        )
        if contract_hash is None:
            reasons.append(
                f"spec-trace contract artifact for spec {spec_id} is not a file under the project root"
            )
        alignment = classify_spec_code_alignment(contract=contract, traces=traces)
        classification = alignment.classification
        if alignment.classification != "satisfies":
            reasons.append(
                f"the current traces do not reproduce spec {spec_id} "
                f"({alignment.classification}): {alignment.reason}"
            )
    return SpecRevalidationSpecResult(
        spec_id=spec_id,
        classification=classification,
        reasons=reasons,
        spec_hash=spec_hash,
        contract_path=contract_path,
        contract_hash=contract_hash,
    )


class SpecFreshnessVerificationStatus(BaseModel):
    model_config = ConfigDict(extra="forbid")

    module_id: str
    status: Literal[
        "fresh",
        "stale",
        "missing_lock",
        "missing_file",
        "validation_expired",
        "unvalidated",
    ]
    closure_effect: Literal["allow", "block"]
    changed_sources: list[str] = Field(default_factory=list)
    changed_specs: list[str] = Field(default_factory=list)
    stale_due_to_dependencies: list[str] = Field(default_factory=list)
    validated_at: str | None = None
    validation_age_hours: float | None = None
    validation_artifacts: list[str] = Field(default_factory=list)
    reason: str | None = None


class SpecFreshnessVerificationReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["0.1"] = SPEC_FRESHNESS_VERIFICATION_SCHEMA_VERSION
    result: Literal["passed", "blocked"]
    closure_effect: Literal["allow", "block"]
    statuses: list[SpecFreshnessVerificationStatus] = Field(default_factory=list)
    stale_metrics: dict[str, int] = Field(default_factory=dict)


def verify_spec_freshness_validation(
    *,
    manifest: CodeSpecManifest,
    registry: SystemSpecRegistry,
    lockfile: SpecFreshnessLockfileV2,
    project_root: Path,
    now: str | None = None,
    max_validation_age_hours: float | None = None,
) -> SpecFreshnessVerificationReport:
    """The validation-aware freshness gate: hash freshness AND recorded, re-runnable validation.

    Extends :func:`validate_spec_freshness_lockfile_v2` (the Cargo.lock-style hash invariant) by
    requiring every hash-fresh module to carry verifiable revalidation evidence: a hash-bound
    :class:`SpecRevalidationRecord` that binds the LOCKED source/spec hashes and the lock id, a
    hash-bound traces artifact with source-bound real-tool provenance, and hash-bound spec-trace
    contracts whose replay against those traces is RE-RUN here and must classify ``satisfies``.
    A module whose hashes match the lockfile but whose validation evidence is absent, unbound, or
    non-reproducing is ``unvalidated`` and BLOCKS — which is exactly what makes a blind
    ``build_spec_freshness_lockfile_v2`` rebaseline insufficient to clear staleness.
    """
    base = validate_spec_freshness_lockfile_v2(
        manifest=manifest,
        registry=registry,
        lockfile=lockfile,
        project_root=project_root,
        now=now,
        max_validation_age_hours=max_validation_age_hours,
    )
    expected_by_module = {entry.module_id: entry for entry in lockfile.entries}
    statuses: list[SpecFreshnessVerificationStatus] = []
    for status in base.statuses:
        carried = SpecFreshnessVerificationStatus(
            module_id=status.module_id,
            status=status.status,
            closure_effect=status.closure_effect,
            changed_sources=status.changed_sources,
            changed_specs=status.changed_specs,
            stale_due_to_dependencies=status.stale_due_to_dependencies,
            validated_at=status.validated_at,
            validation_age_hours=status.validation_age_hours,
            reason=status.reason,
        )
        if status.status != "fresh":
            statuses.append(carried)
            continue
        entry = expected_by_module[status.module_id]
        failure, artifacts = _validation_evidence_failure(
            entry, registry=registry, lockfile=lockfile, project_root=project_root
        )
        if failure is not None:
            statuses.append(
                carried.model_copy(
                    update={
                        "status": "unvalidated",
                        "closure_effect": "block",
                        "reason": failure,
                    }
                )
            )
        else:
            statuses.append(carried.model_copy(update={"validation_artifacts": artifacts}))
    statuses = _propagate_verification_dependencies(statuses, expected_by_module)
    blocked = any(status.closure_effect == "block" for status in statuses)
    metrics = {
        key: sum(1 for status in statuses if status.status == key)
        for key in (
            "fresh",
            "stale",
            "missing_lock",
            "missing_file",
            "validation_expired",
            "unvalidated",
        )
    }
    return SpecFreshnessVerificationReport(
        result="blocked" if blocked else "passed",
        closure_effect="block" if blocked else "allow",
        statuses=statuses,
        stale_metrics=metrics,
    )


def _validation_evidence_failure(
    entry: SpecFreshnessLockEntryV2,
    *,
    registry: SystemSpecRegistry,
    lockfile: SpecFreshnessLockfileV2,
    project_root: Path,
) -> tuple[str | None, list[str]]:
    """Why the entry's recorded validation evidence does NOT verify (None when it does).

    Returns the verified artifact paths on success for the report's transparency surface.
    """
    # Deferred import: trace_validation imports this module for its CI report type, so binding the
    # PC-11 classifier at call time avoids the cycle.
    from .trace_validation import classify_spec_code_alignment

    if not entry.spec_hashes:
        return ("no reviewed spec hashes are locked for the module", [])
    if not entry.validation_artifact_hashes:
        return (
            "lock entry records no validation artifacts; run spec-revalidate to rebuild the baseline",
            [],
        )
    for relpath in sorted(entry.validation_artifact_hashes):
        recorded = entry.validation_artifact_hashes[relpath]
        current = _existing_file_hash(project_root, relpath)
        if current is None:
            return (f"validation artifact {relpath} is missing", [])
        if current != recorded:
            return (f"validation artifact {relpath} does not match its recorded hash", [])
    record = _load_revalidation_record(entry, project_root)
    if record is None:
        return ("no spec revalidation record is among the validation artifacts", [])
    if record.lock_id != lockfile.lock_id:
        return (
            f"revalidation record lock_id {record.lock_id} does not bind lockfile {lockfile.lock_id}",
            [],
        )
    if record.validated_at != entry.validated_at:
        return ("revalidation record timestamp does not bind the lock entry's validated_at", [])
    result = next(
        (item for item in record.results if item.module_id == entry.module_id), None
    )
    if result is None:
        return ("revalidation record has no result for the module", [])
    if result.outcome != "revalidated":
        return ("revalidation record did not revalidate the module", [])
    if result.source_hashes != entry.source_hashes:
        return (
            "revalidation record does not bind the locked source hashes; "
            "revalidate against the current source",
            [],
        )
    recorded_spec_hashes = {
        spec_result.spec_id: spec_result.spec_hash for spec_result in result.spec_results
    }
    for spec_id, want in entry.spec_hashes.items():
        if recorded_spec_hashes.get(spec_id) != want:
            return (f"revalidation record does not bind spec {spec_id} at its locked hash", [])
    specs_by_id = {spec.spec_id: spec for spec in registry.specs}
    for spec_id in entry.spec_hashes:
        spec = specs_by_id.get(spec_id)
        if spec is None or spec.review_status != "reviewed" or entry.module_id not in spec.module_ids:
            return (f"spec {spec_id} is not a reviewed registry spec covering the module", [])
    traces_hash = _existing_file_hash(project_root, record.traces_path)
    if traces_hash is None:
        return (f"recorded traces artifact {record.traces_path} is missing", [])
    if traces_hash != record.traces_hash:
        return (f"recorded traces artifact {record.traces_path} does not match its recorded hash", [])
    try:
        traces = NormalizedTraceArtifact.model_validate_json(
            (project_root / record.traces_path).read_text()
        )
    except ValidationError:
        return (f"recorded traces artifact {record.traces_path} is not a normalized trace artifact", [])
    unprovenanced = _trace_provenance_reasons(traces)
    if unprovenanced:
        return (unprovenanced[0], [])
    for spec_id in sorted(entry.spec_hashes):
        spec_result = next(
            (item for item in result.spec_results if item.spec_id == spec_id), None
        )
        if spec_result is None or spec_result.contract_path is None:
            return (f"revalidation record carries no contract artifact for spec {spec_id}", [])
        contract_hash = _existing_file_hash(project_root, spec_result.contract_path)
        if contract_hash is None:
            return (f"contract artifact {spec_result.contract_path} is missing", [])
        if contract_hash != spec_result.contract_hash:
            return (
                f"contract artifact {spec_result.contract_path} does not match its recorded hash",
                [],
            )
        try:
            contract = SpecTraceContract.model_validate_json(
                (project_root / spec_result.contract_path).read_text()
            )
        except ValidationError:
            return (
                f"contract artifact {spec_result.contract_path} is not a spec-trace contract",
                [],
            )
        if contract.spec_id != spec_id:
            return (
                f"contract artifact {spec_result.contract_path} binds spec {contract.spec_id}, "
                f"not {spec_id}",
                [],
            )
        alignment = classify_spec_code_alignment(contract=contract, traces=traces)
        if alignment.classification != "satisfies":
            return (
                f"recorded traces do not reproduce spec {spec_id} "
                f"({alignment.classification}): {alignment.reason}",
                [],
            )
    return (None, sorted(entry.validation_artifact_hashes))


def _load_revalidation_record(
    entry: SpecFreshnessLockEntryV2, project_root: Path
) -> SpecRevalidationRecord | None:
    for relpath in sorted(entry.validation_artifact_hashes):
        path = project_root / relpath
        if not path.is_file():
            continue
        try:
            return SpecRevalidationRecord.model_validate_json(path.read_text())
        except ValidationError:
            continue
    return None


def _propagate_verification_dependencies(
    statuses: list[SpecFreshnessVerificationStatus],
    expected_by_module: dict[str, SpecFreshnessLockEntryV2],
) -> list[SpecFreshnessVerificationStatus]:
    blocked_modules = {
        status.module_id for status in statuses if status.closure_effect == "block"
    }
    propagated: list[SpecFreshnessVerificationStatus] = []
    for status in statuses:
        expected = expected_by_module.get(status.module_id)
        dependency_module_ids = expected.dependency_module_ids if expected is not None else []
        dependencies = [
            module_id for module_id in dependency_module_ids if module_id in blocked_modules
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


def _trace_provenance_reasons(traces: NormalizedTraceArtifact) -> list[str]:
    from .adapter_certification import trace_has_real_tool_provenance

    if not traces.root:
        return ["no traces were supplied to revalidate against"]
    unprovenanced = [
        trace.trace_id
        for trace in traces.root
        if not trace_has_real_tool_provenance(trace)
    ]
    if unprovenanced:
        return [
            "traces lack source-bound real-tool provenance: " + ", ".join(sorted(unprovenanced))
        ]
    return []


def _existing_file_hash(project_root: Path, relpath: str) -> str | None:
    _require_relative_path(relpath, "artifact path")
    path = (project_root / relpath).resolve(strict=False)
    if not path.is_file():
        return None
    return _sha256_path(path)


def _require_relative_path(value: str, label: str) -> None:
    parsed = PurePosixPath(value)
    if parsed.is_absolute() or ".." in parsed.parts:
        raise ValueError(f"{label} must be project-root-relative: {value}")
