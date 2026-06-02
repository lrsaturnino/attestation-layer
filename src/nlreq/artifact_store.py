from __future__ import annotations

import hashlib
import shutil
from pathlib import Path, PurePosixPath
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


ARTIFACT_STORE_SCHEMA_VERSION = "0.1"
ARTIFACT_STORE_TOOL_VERSION = "0.1"


class ArtifactRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    artifact_hash: str
    logical_name: str
    media_type: str = "application/json"
    store_path: str
    size_bytes: int = Field(ge=0)
    retained: bool = True
    raw: bool = False
    normalized: bool = False
    metadata: dict[str, str] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_store_path(self) -> ArtifactRecord:
        parsed = PurePosixPath(self.store_path)
        if parsed.is_absolute() or ".." in parsed.parts:
            raise ValueError("store_path must be store-root-relative")
        return self


class ArtifactStoreManifest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["0.1"] = ARTIFACT_STORE_SCHEMA_VERSION
    store_id: str
    records: list[ArtifactRecord] = Field(default_factory=list)
    tool: str = "nlreq.artifact_store"
    tool_version: str = ARTIFACT_STORE_TOOL_VERSION

    @model_validator(mode="after")
    def validate_unique_hashes(self) -> ArtifactStoreManifest:
        hashes = [record.artifact_hash for record in self.records]
        if len(hashes) != len(set(hashes)):
            raise ValueError("artifact hashes must be unique")
        return self


class ArtifactLookupResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["found", "missing", "hash_mismatch"]
    artifact_hash: str
    path: str | None = None
    record: ArtifactRecord | None = None
    reason: str | None = None


class ReplayBundleManifest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["0.1"] = ARTIFACT_STORE_SCHEMA_VERSION
    bundle_id: str
    source_store_id: str
    records: list[ArtifactRecord] = Field(default_factory=list)


def put_artifact(
    *,
    store_root: Path,
    source_path: Path,
    logical_name: str,
    media_type: str = "application/json",
    raw: bool = False,
    normalized: bool = False,
    metadata: dict[str, str] | None = None,
) -> ArtifactRecord:
    data = source_path.read_bytes()
    artifact_hash = _sha256_bytes(data)
    relative = _path_for_hash(artifact_hash, source_path.suffix)
    target = store_root / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    if not target.exists():
        target.write_bytes(data)
    return ArtifactRecord(
        artifact_hash=artifact_hash,
        logical_name=logical_name,
        media_type=media_type,
        store_path=relative,
        size_bytes=len(data),
        raw=raw,
        normalized=normalized,
        metadata=metadata or {},
    )


def lookup_artifact(
    *,
    store_root: Path,
    manifest: ArtifactStoreManifest,
    artifact_hash: str,
) -> ArtifactLookupResult:
    record = next((item for item in manifest.records if item.artifact_hash == artifact_hash), None)
    if record is None:
        return ArtifactLookupResult(status="missing", artifact_hash=artifact_hash, reason="not in manifest")
    path = store_root / record.store_path
    if not path.is_file():
        return ArtifactLookupResult(status="missing", artifact_hash=artifact_hash, record=record, reason="file missing")
    current = _sha256_bytes(path.read_bytes())
    if current != artifact_hash:
        return ArtifactLookupResult(
            status="hash_mismatch",
            artifact_hash=artifact_hash,
            path=path.as_posix(),
            record=record,
            reason="stored file hash differs from manifest",
        )
    return ArtifactLookupResult(status="found", artifact_hash=artifact_hash, path=path.as_posix(), record=record)


def export_replay_bundle(
    *,
    store_root: Path,
    manifest: ArtifactStoreManifest,
    bundle_root: Path,
    bundle_id: str,
) -> ReplayBundleManifest:
    bundle_records: list[ArtifactRecord] = []
    for record in manifest.records:
        lookup = lookup_artifact(store_root=store_root, manifest=manifest, artifact_hash=record.artifact_hash)
        if lookup.status != "found" or lookup.path is None:
            continue
        target = bundle_root / record.store_path
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(lookup.path, target)
        bundle_records.append(record)
    return ReplayBundleManifest(
        bundle_id=bundle_id,
        source_store_id=manifest.store_id,
        records=bundle_records,
    )


def _path_for_hash(artifact_hash: str, suffix: str) -> str:
    digest = artifact_hash.removeprefix("sha256:")
    safe_suffix = suffix if suffix else ".artifact"
    return f"objects/{digest[:2]}/{digest}{safe_suffix}"


def _sha256_bytes(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()
