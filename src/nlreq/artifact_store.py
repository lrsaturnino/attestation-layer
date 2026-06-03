from __future__ import annotations

import hashlib
import shutil
from pathlib import Path, PurePosixPath
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .jsonutil import sha256_json
from .signed_evidence import (
    ProducerKeyRegistry,
    SignedEvidenceEnvelope,
    verify_signed_evidence,
)


ARTIFACT_STORE_SCHEMA_VERSION = "0.1"
ARTIFACT_STORE_V2_SCHEMA_VERSION = "0.2"
ARTIFACT_STORE_TOOL_VERSION = "0.1"
HIGH_ASSURANCE_REPLAY_LEVELS = {"BOUNDED_CHECKED", "PROVEN_INDUCTIVE"}


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


class ReplayCommandMetadata(BaseModel):
    model_config = ConfigDict(extra="forbid")

    command: list[str] = Field(default_factory=list)
    working_directory: str | None = None
    environment: dict[str, str] = Field(default_factory=dict)
    tool_versions: dict[str, str] = Field(default_factory=dict)


class ReplayBundleManifestV2(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["0.2"] = ARTIFACT_STORE_V2_SCHEMA_VERSION
    bundle_id: str
    source_store_id: str
    command: ReplayCommandMetadata
    records: list[ArtifactRecord] = Field(default_factory=list)
    signed_envelopes: list[SignedEvidenceEnvelope] = Field(default_factory=list)
    input_hashes: dict[str, str] = Field(default_factory=dict)
    tool: str = "nlreq.artifact_store"
    tool_version: str = ARTIFACT_STORE_TOOL_VERSION


class ReplayVerificationFinding(BaseModel):
    model_config = ConfigDict(extra="forbid")

    category: Literal["artifact", "signature", "producer", "command"]
    artifact_hash: str | None = None
    envelope_id: str | None = None
    blocking: bool = True
    message: str


class ReplayVerificationReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["0.2"] = ARTIFACT_STORE_V2_SCHEMA_VERSION
    bundle_id: str
    result: Literal["valid", "blocked"]
    verified_artifact_hashes: list[str] = Field(default_factory=list)
    missing_artifact_hashes: list[str] = Field(default_factory=list)
    verified_envelope_ids: list[str] = Field(default_factory=list)
    findings: list[ReplayVerificationFinding] = Field(default_factory=list)
    input_hashes: dict[str, str] = Field(default_factory=dict)
    tool: str = "nlreq.artifact_store"
    tool_version: str = ARTIFACT_STORE_TOOL_VERSION


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


def build_replay_bundle_manifest_v2(
    *,
    bundle_id: str,
    source_store_id: str,
    command: ReplayCommandMetadata,
    records: list[ArtifactRecord],
    signed_envelopes: list[SignedEvidenceEnvelope] | None = None,
) -> ReplayBundleManifestV2:
    signed_envelopes = signed_envelopes or []
    return ReplayBundleManifestV2(
        bundle_id=bundle_id,
        source_store_id=source_store_id,
        command=command,
        records=records,
        signed_envelopes=signed_envelopes,
        input_hashes={
            "command": sha256_json(command),
            "records": sha256_json(records),
            "signed_envelopes": sha256_json(signed_envelopes),
        },
    )


def verify_replay_bundle(
    *,
    bundle_root: Path,
    bundle: ReplayBundleManifestV2,
    registry: ProducerKeyRegistry,
    secrets_by_key_id: dict[str, str],
    require_signatures_for_high_assurance: bool = True,
) -> ReplayVerificationReport:
    manifest = ArtifactStoreManifest(
        store_id=bundle.source_store_id,
        records=bundle.records,
    )
    findings: list[ReplayVerificationFinding] = []
    verified_artifacts: list[str] = []
    missing_artifacts: list[str] = []
    verified_envelopes: list[str] = []

    if not bundle.command.command:
        findings.append(
            ReplayVerificationFinding(
                category="command",
                message="replay command metadata is missing",
            )
        )

    envelopes_by_artifact = _envelopes_by_artifact(bundle.signed_envelopes)
    for record in bundle.records:
        lookup = lookup_artifact(
            store_root=bundle_root,
            manifest=manifest,
            artifact_hash=record.artifact_hash,
        )
        if lookup.status != "found":
            missing_artifacts.append(record.artifact_hash)
            findings.append(
                ReplayVerificationFinding(
                    category="artifact",
                    artifact_hash=record.artifact_hash,
                    message=lookup.reason or lookup.status,
                )
            )
            continue
        verified_artifacts.append(record.artifact_hash)
        if _requires_high_assurance_signature(record, require_signatures_for_high_assurance):
            producer_id = record.metadata.get("producer_id")
            if not producer_id:
                findings.append(
                    ReplayVerificationFinding(
                        category="producer",
                        artifact_hash=record.artifact_hash,
                        message="high-assurance replay artifact is missing producer_id metadata",
                    )
                )
                continue
            envelope = envelopes_by_artifact.get(record.artifact_hash)
            if envelope is None:
                findings.append(
                    ReplayVerificationFinding(
                        category="signature",
                        artifact_hash=record.artifact_hash,
                        message="high-assurance replay artifact is missing signed envelope",
                    )
                )
                continue
            if envelope.producer_id != producer_id:
                findings.append(
                    ReplayVerificationFinding(
                        category="producer",
                        artifact_hash=record.artifact_hash,
                        envelope_id=envelope.envelope_id,
                        message="signed envelope producer does not match artifact metadata",
                    )
                )
                continue
            signature = verify_signed_evidence(
                envelope=envelope,
                registry=registry,
                secrets_by_key_id=secrets_by_key_id,
                require_high_assurance_trust=True,
            )
            if signature.result != "valid":
                findings.append(
                    ReplayVerificationFinding(
                        category="signature",
                        artifact_hash=record.artifact_hash,
                        envelope_id=envelope.envelope_id,
                        message="; ".join(signature.reasons) or signature.result,
                    )
                )
                continue
            verified_envelopes.append(envelope.envelope_id)

    return ReplayVerificationReport(
        bundle_id=bundle.bundle_id,
        result="blocked" if any(finding.blocking for finding in findings) else "valid",
        verified_artifact_hashes=sorted(verified_artifacts),
        missing_artifact_hashes=sorted(missing_artifacts),
        verified_envelope_ids=sorted(verified_envelopes),
        findings=findings,
        input_hashes={
            "bundle": sha256_json(bundle),
            "registry": sha256_json(registry),
        },
    )


def _path_for_hash(artifact_hash: str, suffix: str) -> str:
    digest = artifact_hash.removeprefix("sha256:")
    safe_suffix = suffix if suffix else ".artifact"
    return f"objects/{digest[:2]}/{digest}{safe_suffix}"


def _sha256_bytes(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def _requires_high_assurance_signature(
    record: ArtifactRecord,
    require_signatures_for_high_assurance: bool,
) -> bool:
    return (
        require_signatures_for_high_assurance
        and record.metadata.get("evidence_level") in HIGH_ASSURANCE_REPLAY_LEVELS
    )


def _envelopes_by_artifact(
    envelopes: list[SignedEvidenceEnvelope],
) -> dict[str, SignedEvidenceEnvelope]:
    indexed: dict[str, SignedEvidenceEnvelope] = {}
    for envelope in envelopes:
        artifact_hash = envelope.payload.get("artifact_hash")
        if isinstance(artifact_hash, str):
            indexed[artifact_hash] = envelope
    return indexed
