from __future__ import annotations

from itertools import combinations
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from .jsonutil import sha256_json
from .models import BackendResult, EvidenceLevel


BACKEND_AGREEMENT_SCHEMA_VERSION = "0.1"


BackendAgreementPolicy = Literal["blocking", "report_only"]

# How two overlapping results are judged to agree (PB-6.T3):
#   "bounded" — model-checker results: status AND the bounded evidence (bounds, evidence level,
#       counterexamples, unsupported constructs) are all semantic. A depth-6 "valid" and a depth-8
#       "valid" are not the same assurance, so a bounds difference is a real disagreement.
#   "verdict" — decidable-question results (the FormalClaim premise-consistency check answered by two
#       independent SMT backends): only the verdict (valid/invalid) is semantic. The two encoders
#       legitimately differ on logic label, encoded form, and evidence metadata for the *same* yes/no
#       answer, so those are recorded but never themselves a disagreement; only opposite verdicts on
#       the same question (the same overlap_key) block. This is the verdict-first redesign: a planted
#       z3-vs-cvc5 divergence fails the gate for a semantic verdict mismatch, not for incidentals.
BackendAgreementMode = Literal["bounded", "verdict"]

# The decided verdicts of a decidable consistency question; any other status (needs_review,
# unsupported, timeout, counterexample) means a backend did not decide it, so there is nothing to
# agree or disagree about — the pair is non_overlap rather than a false disagreement.
_DECIDED_VERDICTS = frozenset({"valid", "invalid"})


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
    mode: BackendAgreementMode = "bounded",
) -> BackendAgreementReport:
    observations = [
        _observation(result, override_overlap_key=overlap_key) for result in backend_results
    ]
    if len(observations) < 2:
        # Fewer than two backends ran, so there is no second opinion to cross-check. The absence of
        # a cross-check is not a disagreement — it is additive and must never block closure — so the
        # status records that no comparison happened while closure_effect stays "allow".
        return BackendAgreementReport(
            policy=policy,
            status="needs_review",
            closure_effect=_closure_effect(policy, blocked=False),
            observations=observations,
        )

    comparisons = [
        _compare_observations(left, right, mode=mode)
        for left, right in combinations(observations, 2)
    ]
    disagreements = [comparison for comparison in comparisons if comparison.status == "disagreed"]
    blockers = [
        f"{comparison.left_backend} disagrees with {comparison.right_backend}: "
        + "; ".join(comparison.reasons)
        for comparison in disagreements
    ]
    overlapping = [comparison for comparison in comparisons if comparison.status != "non_overlap"]
    if disagreements:
        status: Literal["agreed", "disagreed", "non_overlap", "needs_review"] = "disagreed"
    elif overlapping:
        status = "agreed"
    else:
        status = "non_overlap"

    # Only a real disagreement — two backends reaching opposite conclusions on the same question —
    # blocks closure. non_overlap (the pair declared no shared question) and the single-backend
    # needs_review above are the *absence* of a cross-check, not a disagreement, so they carry
    # closure_effect="allow" and no blockers; each non_overlap comparison still records *why* it did
    # not overlap on its own reasons. This keeps closure_effect authoritative: a consumer honors it
    # directly instead of re-deriving which statuses block. report_only downgrades even a real
    # disagreement to a report rather than a block.
    return BackendAgreementReport(
        policy=policy,
        status=status,
        closure_effect=_closure_effect(policy, blocked=bool(disagreements)),
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
    left: BackendAgreementObservation,
    right: BackendAgreementObservation,
    *,
    mode: BackendAgreementMode = "bounded",
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

    if mode == "verdict":
        return _compare_verdicts(left, right)

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


def _compare_verdicts(
    left: BackendAgreementObservation, right: BackendAgreementObservation
) -> BackendAgreementComparison:
    """Verdict-first comparison of two results on the same decidable question (same overlap_key).

    Only the verdict is semantic. Two independent SMT backends encode the same premise-consistency
    question differently (different logic label, different evidence metadata, different encoded form)
    yet must reach the same yes/no answer; those incidentals are recorded but never a disagreement.

      - both decided (valid/invalid) and equal     -> agreed
      - both decided and opposite                  -> disagreed (a real encoder divergence: block)
      - one or both did not decide the verdict     -> non_overlap (nothing to agree about)
    """
    if left.status in _DECIDED_VERDICTS and right.status in _DECIDED_VERDICTS:
        if left.status == right.status:
            return BackendAgreementComparison(
                left_backend=left.backend,
                right_backend=right.backend,
                overlap_key=left.overlap_key,
                status="agreed",
                compared_fields=["status"],
            )
        return BackendAgreementComparison(
            left_backend=left.backend,
            right_backend=right.backend,
            overlap_key=left.overlap_key,
            status="disagreed",
            reasons=[f"verdict differs: {left.status!r} vs {right.status!r}"],
            compared_fields=["status"],
        )
    return BackendAgreementComparison(
        left_backend=left.backend,
        right_backend=right.backend,
        overlap_key=left.overlap_key,
        status="non_overlap",
        reasons=[
            "a backend did not decide a verdict on the shared question "
            f"(left {left.status!r}, right {right.status!r})"
        ],
        compared_fields=["status"],
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
