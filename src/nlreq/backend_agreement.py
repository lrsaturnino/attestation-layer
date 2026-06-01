from __future__ import annotations

from itertools import combinations
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from .jsonutil import sha256_json
from .models import BackendResult, EvidenceLevel


BACKEND_AGREEMENT_SCHEMA_VERSION = "0.1"


BackendAgreementPolicy = Literal["blocking", "report_only"]


class BackendAgreementObservation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    backend: str
    result_hash: str
    status: str
    evidence_level: EvidenceLevel | None = None
    overlap_key: str | None = None
    target: str | None = None
    bounds: dict[str, Any] = Field(default_factory=dict)
    unsupported_constructs: list[dict[str, Any]] = Field(default_factory=list)
    counterexamples: list[dict[str, Any]] = Field(default_factory=list)


class BackendAgreementComparison(BaseModel):
    model_config = ConfigDict(extra="forbid")

    left_backend: str
    right_backend: str
    status: Literal["agreed", "disagreed", "non_overlap"]
    overlap_key: str | None = None
    reasons: list[str] = Field(default_factory=list)
    compared_fields: list[str] = Field(default_factory=list)


class BackendAgreementReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["0.1"] = BACKEND_AGREEMENT_SCHEMA_VERSION
    policy: BackendAgreementPolicy = "blocking"
    status: Literal["agreed", "disagreed", "non_overlap", "needs_review"]
    closure_effect: Literal["allow", "block", "report_only"]
    observations: list[BackendAgreementObservation] = Field(default_factory=list)
    comparisons: list[BackendAgreementComparison] = Field(default_factory=list)
    blockers: list[str] = Field(default_factory=list)


def build_backend_agreement_report(
    backend_results: list[BackendResult],
    *,
    policy: BackendAgreementPolicy = "blocking",
    overlap_key: str | None = None,
) -> BackendAgreementReport:
    observations = [
        _observation(result, override_overlap_key=overlap_key) for result in backend_results
    ]
    if len(observations) < 2:
        blockers = ["backend agreement requires at least two backend results"]
        return BackendAgreementReport(
            policy=policy,
            status="needs_review",
            closure_effect=_closure_effect(policy, blocked=True),
            observations=observations,
            blockers=blockers,
        )

    comparisons = [
        _compare_observations(left, right) for left, right in combinations(observations, 2)
    ]
    blockers = [
        f"{comparison.left_backend} disagrees with {comparison.right_backend}: "
        + "; ".join(comparison.reasons)
        for comparison in comparisons
        if comparison.status == "disagreed"
    ]
    overlapping = [comparison for comparison in comparisons if comparison.status != "non_overlap"]
    if blockers:
        status: Literal["agreed", "disagreed", "non_overlap", "needs_review"] = "disagreed"
    elif overlapping:
        status = "agreed"
    else:
        status = "non_overlap"
        blockers.append("no backend result pair declared overlapping semantics")

    return BackendAgreementReport(
        policy=policy,
        status=status,
        closure_effect=_closure_effect(policy, blocked=bool(blockers)),
        observations=observations,
        comparisons=comparisons,
        blockers=blockers,
    )


def _observation(
    result: BackendResult, *, override_overlap_key: str | None
) -> BackendAgreementObservation:
    details = result.details
    return BackendAgreementObservation(
        backend=result.backend,
        result_hash=sha256_json(result),
        status=result.status,
        evidence_level=result.evidence_level,
        overlap_key=override_overlap_key or _string_detail(details, "overlap_key"),
        target=_string_detail(details, "target") or _string_detail(details, "formal_target"),
        bounds=_bounds(details),
        unsupported_constructs=_dict_list(details.get("unsupported_constructs")),
        counterexamples=_counterexamples(details),
    )


def _compare_observations(
    left: BackendAgreementObservation, right: BackendAgreementObservation
) -> BackendAgreementComparison:
    if left.overlap_key is None or right.overlap_key is None:
        return BackendAgreementComparison(
            left_backend=left.backend,
            right_backend=right.backend,
            status="non_overlap",
            reasons=["both results must declare an overlap_key before comparison"],
        )
    if left.overlap_key != right.overlap_key:
        return BackendAgreementComparison(
            left_backend=left.backend,
            right_backend=right.backend,
            status="non_overlap",
            reasons=[
                f"overlap_key differs: {left.overlap_key!r} vs {right.overlap_key!r}"
            ],
        )

    compared_fields = ["status", "evidence_level", "bounds", "unsupported_constructs"]
    reasons: list[str] = []
    if left.status != right.status:
        reasons.append(f"status differs: {left.status!r} vs {right.status!r}")
    if left.evidence_level != right.evidence_level:
        reasons.append(
            f"evidence_level differs: {_level_value(left.evidence_level)!r} "
            f"vs {_level_value(right.evidence_level)!r}"
        )
    if left.bounds != right.bounds:
        reasons.append("bounds differ")
    if left.unsupported_constructs != right.unsupported_constructs:
        reasons.append("unsupported constructs differ")
    if left.counterexamples or right.counterexamples:
        compared_fields.append("counterexamples")
        if left.counterexamples != right.counterexamples:
            reasons.append("counterexamples differ")

    return BackendAgreementComparison(
        left_backend=left.backend,
        right_backend=right.backend,
        overlap_key=left.overlap_key,
        status="disagreed" if reasons else "agreed",
        reasons=reasons,
        compared_fields=compared_fields,
    )


def _closure_effect(policy: BackendAgreementPolicy, *, blocked: bool) -> str:
    if not blocked:
        return "allow"
    if policy == "report_only":
        return "report_only"
    return "block"


def _string_detail(details: dict[str, Any], key: str) -> str | None:
    value = details.get(key)
    return value if isinstance(value, str) and value else None


def _bounds(details: dict[str, Any]) -> dict[str, Any]:
    bounds: dict[str, Any] = {}
    nested = details.get("bounds")
    if isinstance(nested, dict):
        bounds.update(nested)
    budget = details.get("budget")
    if isinstance(budget, dict):
        for key in sorted(budget):
            if key in {"timeout_seconds", "max_states", "max_depth", "memory_budget_mb"}:
                bounds[key] = budget[key]
    for key in ("timeout_seconds", "max_states", "max_depth", "memory_budget_mb"):
        if key in details:
            bounds[key] = details[key]
    return bounds


def _counterexamples(details: dict[str, Any]) -> list[dict[str, Any]]:
    explicit = details.get("counterexamples")
    if isinstance(explicit, list):
        return _dict_list(explicit)
    single = details.get("counterexample")
    if isinstance(single, dict):
        return [single]
    trace = details.get("counterexample_trace")
    if isinstance(trace, list):
        return [{"trace": trace}]
    return []


def _dict_list(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _level_value(level: EvidenceLevel | None) -> str | None:
    return level.value if level is not None else None
