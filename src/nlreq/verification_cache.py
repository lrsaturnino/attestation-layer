from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .jsonutil import sha256_json


VERIFICATION_CACHE_SCHEMA_VERSION = "0.1"
VERIFICATION_CACHE_V2_SCHEMA_VERSION = "0.2"
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


class VerificationCachePolicyV2(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["0.2"] = VERIFICATION_CACHE_V2_SCHEMA_VERSION
    policy_id: str = "real-evidence-cache-v2"
    cacheable_stages: list[str] = Field(
        default_factory=lambda: [
            "semantic_translation",
            "formal_backend",
            "trace_validation",
            "adapter_evidence",
        ]
    )
    max_parallelism: int = Field(default=4, gt=0)
    ci_runtime_budget_ms: int = Field(default=300_000, gt=0)


class ParallelDispatchTask(BaseModel):
    model_config = ConfigDict(extra="forbid")

    task_id: str
    stage: str
    input_hashes: dict[str, str]
    tool_versions: dict[str, str]
    timeout_ms: int = Field(default=60_000, gt=0)
    estimated_runtime_ms: int = Field(default=0, ge=0)


class ParallelDispatchDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")

    task_id: str
    stage: str
    cache_key_hash: str
    cache_status: Literal["hit", "miss", "not_cacheable"]
    artifact_hash: str | None = None
    run_slot: int | None = None


class ParallelDispatchPlan(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["0.2"] = VERIFICATION_CACHE_V2_SCHEMA_VERSION
    plan_id: str
    result: Literal["ready", "blocked"]
    policy_hash: str
    max_parallelism: int
    cache_hits: int = 0
    cache_misses: int = 0
    estimated_runtime_ms: int = 0
    ci_runtime_budget_ms: int
    within_budget: bool = True
    decisions: list[ParallelDispatchDecision] = Field(default_factory=list)
    findings: list[str] = Field(default_factory=list)
    input_hashes: dict[str, str] = Field(default_factory=dict)
    tool: str = "nlreq.verification_cache"
    tool_version: str = VERIFICATION_CACHE_TOOL_VERSION


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


def build_parallel_dispatch_plan(
    *,
    plan_id: str,
    tasks: list[ParallelDispatchTask],
    cache_index: VerificationCacheIndex,
    policy: VerificationCachePolicyV2 | None = None,
) -> ParallelDispatchPlan:
    policy = policy or VerificationCachePolicyV2()
    policy_hash = sha256_json(policy)
    decisions: list[ParallelDispatchDecision] = []
    slot_runtimes = [0 for _ in range(policy.max_parallelism)]
    findings: list[str] = []

    for task in tasks:
        if not task.input_hashes:
            findings.append(f"{task.task_id}: input hashes are required for cache-safe dispatch")
        key = build_verification_cache_key(
            stage=task.stage,
            input_hashes=task.input_hashes,
            tool_versions=task.tool_versions,
            policy_hash=policy_hash,
        )
        key_hash = cache_key_hash(key)
        if task.stage not in policy.cacheable_stages:
            slot = _assign_dispatch_slot(slot_runtimes, task.estimated_runtime_ms)
            decisions.append(
                ParallelDispatchDecision(
                    task_id=task.task_id,
                    stage=task.stage,
                    cache_key_hash=key_hash,
                    cache_status="not_cacheable",
                    run_slot=slot,
                )
            )
            continue

        lookup = lookup_cache(cache_index, key)
        if lookup.status == "hit" and lookup.record is not None:
            decisions.append(
                ParallelDispatchDecision(
                    task_id=task.task_id,
                    stage=task.stage,
                    cache_key_hash=key_hash,
                    cache_status="hit",
                    artifact_hash=lookup.record.artifact_hash,
                )
            )
        else:
            slot = _assign_dispatch_slot(slot_runtimes, task.estimated_runtime_ms)
            decisions.append(
                ParallelDispatchDecision(
                    task_id=task.task_id,
                    stage=task.stage,
                    cache_key_hash=key_hash,
                    cache_status="miss",
                    run_slot=slot,
                )
            )

    estimated_runtime = max(slot_runtimes) if slot_runtimes else 0
    within_budget = estimated_runtime <= policy.ci_runtime_budget_ms
    if not within_budget:
        findings.append(
            f"estimated runtime {estimated_runtime}ms exceeds CI budget {policy.ci_runtime_budget_ms}ms"
        )
    return ParallelDispatchPlan(
        plan_id=plan_id,
        result="blocked" if findings else "ready",
        policy_hash=policy_hash,
        max_parallelism=policy.max_parallelism,
        cache_hits=sum(1 for decision in decisions if decision.cache_status == "hit"),
        cache_misses=sum(1 for decision in decisions if decision.cache_status != "hit"),
        estimated_runtime_ms=estimated_runtime,
        ci_runtime_budget_ms=policy.ci_runtime_budget_ms,
        within_budget=within_budget,
        decisions=decisions,
        findings=findings,
        input_hashes={
            "tasks": sha256_json(tasks),
            "cache_index": sha256_json(cache_index),
            "policy": policy_hash,
        },
    )


def _assign_dispatch_slot(slot_runtimes: list[int], runtime_ms: int) -> int:
    slot_index = min(range(len(slot_runtimes)), key=lambda index: slot_runtimes[index])
    slot_runtimes[slot_index] += runtime_ms
    return slot_index + 1
