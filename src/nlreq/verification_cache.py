from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .jsonutil import sha256_json


VERIFICATION_CACHE_SCHEMA_VERSION = "0.1"
VERIFICATION_CACHE_TOOL_VERSION = "0.1"


class VerificationCacheKey(BaseModel):
    model_config = ConfigDict(extra="forbid")

    stage: str
    input_hashes: dict[str, str]
    tool_versions: dict[str, str]
    policy_hash: str | None = None


class VerificationCacheRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    cache_key_hash: str
    artifact_hash: str
    stage: str
    hit_count: int = Field(default=0, ge=0)
    metadata: dict[str, Any] = Field(default_factory=dict)


class VerificationCacheIndex(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["0.1"] = VERIFICATION_CACHE_SCHEMA_VERSION
    records: list[VerificationCacheRecord] = Field(default_factory=list)
    tool: str = "nlreq.verification_cache"
    tool_version: str = VERIFICATION_CACHE_TOOL_VERSION

    @model_validator(mode="after")
    def validate_unique_keys(self) -> VerificationCacheIndex:
        keys = [record.cache_key_hash for record in self.records]
        if len(keys) != len(set(keys)):
            raise ValueError("cache key hashes must be unique")
        return self


class VerificationCacheLookup(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["hit", "miss"]
    cache_key_hash: str
    record: VerificationCacheRecord | None = None


def build_verification_cache_key(
    *,
    stage: str,
    input_hashes: dict[str, str],
    tool_versions: dict[str, str],
    policy_hash: str | None = None,
) -> VerificationCacheKey:
    return VerificationCacheKey(
        stage=stage,
        input_hashes=dict(sorted(input_hashes.items())),
        tool_versions=dict(sorted(tool_versions.items())),
        policy_hash=policy_hash,
    )


def cache_key_hash(key: VerificationCacheKey) -> str:
    return sha256_json(key)


def lookup_cache(index: VerificationCacheIndex, key: VerificationCacheKey) -> VerificationCacheLookup:
    key_hash = cache_key_hash(key)
    for record in index.records:
        if record.cache_key_hash == key_hash:
            return VerificationCacheLookup(status="hit", cache_key_hash=key_hash, record=record)
    return VerificationCacheLookup(status="miss", cache_key_hash=key_hash)


def record_cache_artifact(
    index: VerificationCacheIndex,
    key: VerificationCacheKey,
    *,
    artifact_hash: str,
    metadata: dict[str, Any] | None = None,
) -> VerificationCacheIndex:
    key_hash = cache_key_hash(key)
    records = [
        record.model_copy(update={"hit_count": record.hit_count + 1})
        if record.cache_key_hash == key_hash
        else record
        for record in index.records
    ]
    if not any(record.cache_key_hash == key_hash for record in index.records):
        records.append(
            VerificationCacheRecord(
                cache_key_hash=key_hash,
                artifact_hash=artifact_hash,
                stage=key.stage,
                metadata=metadata or {},
            )
        )
    return index.model_copy(update={"records": records})
