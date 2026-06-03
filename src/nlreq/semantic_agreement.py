from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from .formal_claim import FormalClaimLoweringReport, formal_claim_signature
from .jsonutil import sha256_json
from .models import Approval, SourceSpan


SEMANTIC_AGREEMENT_SCHEMA_VERSION = "0.1"
SEMANTIC_AGREEMENT_TOOL_VERSION = "0.1"


class FormalClaimAgreementCandidate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    candidate_id: str
    translator_id: str
    report: FormalClaimLoweringReport


class SemanticAgreementResolution(BaseModel):
    model_config = ConfigDict(extra="forbid")

    selected_candidate_id: str
    selected_candidate_hash: str | None = None
    reason: str
    approval: Approval


class SemanticAgreementComparison(BaseModel):
    model_config = ConfigDict(extra="forbid")

    left_candidate_id: str
    right_candidate_id: str
    status: Literal["agreed", "conflict", "needs_review"]
    profile: Literal[
        "canonical_formal_claim_equality",
        "alpha_identifier_equivalence",
        "commutative_claim_equivalence",
        "unsupported",
    ]
    message: str
    source_spans: list[SourceSpan] = Field(default_factory=list)


class SemanticAgreementReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["0.1"] = SEMANTIC_AGREEMENT_SCHEMA_VERSION
    requirement_id: str
    status: Literal["agreed", "disagreed", "needs_review", "resolved_by_review"]
    candidate_hashes: dict[str, str]
    comparisons: list[SemanticAgreementComparison] = Field(default_factory=list)
    blockers: list[str] = Field(default_factory=list)
    resolution: SemanticAgreementResolution | None = None
    acceptance_allowed: bool
    tool: str = "nlreq.semantic_agreement"
    tool_version: str = SEMANTIC_AGREEMENT_TOOL_VERSION


class SemanticAgreementCalibrationCase(BaseModel):
    model_config = ConfigDict(extra="forbid")

    case_id: str
    expected_same_meaning: bool
    report: SemanticAgreementReport


class SemanticAgreementCalibrationObservation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    case_id: str
    expected_same_meaning: bool
    acceptance_allowed: bool
    status: Literal["matched", "false_acceptance", "false_refusal"]
    agreement_status: Literal["agreed", "disagreed", "needs_review", "resolved_by_review"]
    profiles: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


class SemanticAgreementCalibrationReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["0.1"] = SEMANTIC_AGREEMENT_SCHEMA_VERSION
    result: Literal["passed", "failed"]
    total_cases: int
    matched_cases: int
    semantic_accuracy: float
    false_acceptance_count: int
    false_refusal_count: int
    false_acceptance_budget: int
    false_refusal_budget: int | None = None
    blockers: list[str] = Field(default_factory=list)
    observations: list[SemanticAgreementCalibrationObservation] = Field(default_factory=list)
    tool: str = "nlreq.semantic_agreement"
    tool_version: str = SEMANTIC_AGREEMENT_TOOL_VERSION


def build_semantic_agreement_report(
    candidates: list[FormalClaimAgreementCandidate],
    *,
    resolution: SemanticAgreementResolution | None = None,
) -> SemanticAgreementReport:
    if not candidates:
        raise ValueError("semantic agreement requires at least one candidate")
    requirement_id = candidates[0].report.requirement_id
    candidate_hashes = {candidate.candidate_id: sha256_json(candidate.report) for candidate in candidates}
    blockers: list[str] = []
    if len(candidates) < 2:
        blockers.append("semantic agreement requires at least two formal claim candidates")
    for candidate in candidates:
        if candidate.report.requirement_id != requirement_id:
            blockers.append("all formal claim candidates must target the same requirement_id")
        if candidate.report.result != "lowered" or candidate.report.formal_claim is None:
            blockers.append(f"candidate {candidate.candidate_id} did not lower to a formal claim")

    comparisons: list[SemanticAgreementComparison] = []
    if not blockers and len(candidates) >= 2:
        baseline = candidates[0]
        comparisons = [_compare(baseline, candidate) for candidate in candidates[1:]]

    has_conflict = any(comparison.status == "conflict" for comparison in comparisons)
    has_needs_review = bool(blockers) or any(
        comparison.status == "needs_review" for comparison in comparisons
    )
    if has_conflict:
        status: Literal["agreed", "disagreed", "needs_review", "resolved_by_review"] = "disagreed"
    elif has_needs_review:
        status = "needs_review"
    else:
        status = "agreed"

    effective_resolution = _resolution_with_hash(resolution, candidate_hashes)
    if status == "disagreed" and _resolution_is_valid(effective_resolution, candidate_hashes):
        status = "resolved_by_review"

    return SemanticAgreementReport(
        requirement_id=requirement_id,
        status=status,
        candidate_hashes=candidate_hashes,
        comparisons=comparisons,
        blockers=blockers,
        resolution=effective_resolution,
        acceptance_allowed=status in {"agreed", "resolved_by_review"},
    )


def build_semantic_agreement_calibration_report(
    cases: list[SemanticAgreementCalibrationCase],
    *,
    false_acceptance_budget: int = 0,
    false_refusal_budget: int | None = None,
) -> SemanticAgreementCalibrationReport:
    observations = [_calibration_observation(case) for case in cases]
    total = len(observations)
    matched = sum(1 for item in observations if item.status == "matched")
    false_acceptance = sum(1 for item in observations if item.status == "false_acceptance")
    false_refusal = sum(1 for item in observations if item.status == "false_refusal")
    blockers: list[str] = []
    if false_acceptance > false_acceptance_budget:
        blockers.append(
            f"false semantic acceptance budget exceeded: {false_acceptance} > {false_acceptance_budget}"
        )
    if false_refusal_budget is not None and false_refusal > false_refusal_budget:
        blockers.append(f"false semantic refusal budget exceeded: {false_refusal} > {false_refusal_budget}")
    return SemanticAgreementCalibrationReport(
        result="failed" if blockers else "passed",
        total_cases=total,
        matched_cases=matched,
        semantic_accuracy=_ratio(matched, total),
        false_acceptance_count=false_acceptance,
        false_refusal_count=false_refusal,
        false_acceptance_budget=false_acceptance_budget,
        false_refusal_budget=false_refusal_budget,
        blockers=blockers,
        observations=observations,
    )


def _compare(
    left: FormalClaimAgreementCandidate,
    right: FormalClaimAgreementCandidate,
) -> SemanticAgreementComparison:
    left_claim = left.report.formal_claim
    right_claim = right.report.formal_claim
    if left_claim is None or right_claim is None:
        return SemanticAgreementComparison(
            left_candidate_id=left.candidate_id,
            right_candidate_id=right.candidate_id,
            status="needs_review",
            profile="unsupported",
            message="formal claim missing from one candidate",
        )
    profiles = [
        ("canonical_formal_claim_equality", {"alpha_identifiers": False, "commutative": False}),
        ("alpha_identifier_equivalence", {"alpha_identifiers": True, "commutative": False}),
        ("commutative_claim_equivalence", {"alpha_identifiers": False, "commutative": True}),
    ]
    for profile, options in profiles:
        if formal_claim_signature(left_claim, **options) == formal_claim_signature(right_claim, **options):
            return SemanticAgreementComparison(
                left_candidate_id=left.candidate_id,
                right_candidate_id=right.candidate_id,
                status="agreed",
                profile=profile,  # type: ignore[arg-type]
                message=f"formal claims agree by {profile}",
            )
    return SemanticAgreementComparison(
        left_candidate_id=left.candidate_id,
        right_candidate_id=right.candidate_id,
        status="conflict",
        profile="unsupported",
        message="no supported semantic agreement profile proved equivalence",
        source_spans=[*left_claim.source_spans, *right_claim.source_spans],
    )


def _calibration_observation(
    case: SemanticAgreementCalibrationCase,
) -> SemanticAgreementCalibrationObservation:
    acceptance_allowed = case.report.acceptance_allowed
    if not case.expected_same_meaning and acceptance_allowed:
        status: Literal["matched", "false_acceptance", "false_refusal"] = "false_acceptance"
        notes = ["agreement accepted candidates labeled as semantically different"]
    elif case.expected_same_meaning and not acceptance_allowed:
        status = "false_refusal"
        notes = ["agreement blocked candidates labeled as semantically equivalent"]
    else:
        status = "matched"
        notes = []
    return SemanticAgreementCalibrationObservation(
        case_id=case.case_id,
        expected_same_meaning=case.expected_same_meaning,
        acceptance_allowed=acceptance_allowed,
        status=status,
        agreement_status=case.report.status,
        profiles=[comparison.profile for comparison in case.report.comparisons],
        notes=notes,
    )


def _ratio(numerator: int, denominator: int) -> float:
    if denominator == 0:
        return 0.0
    return numerator / denominator


def _resolution_with_hash(
    resolution: SemanticAgreementResolution | None,
    candidate_hashes: dict[str, str],
) -> SemanticAgreementResolution | None:
    if resolution is None:
        return None
    selected_hash = candidate_hashes.get(resolution.selected_candidate_id)
    if resolution.selected_candidate_hash is None and selected_hash is not None:
        return resolution.model_copy(update={"selected_candidate_hash": selected_hash})
    return resolution


def _resolution_is_valid(
    resolution: SemanticAgreementResolution | None,
    candidate_hashes: dict[str, str],
) -> bool:
    if resolution is None:
        return False
    if resolution.approval.status != "approved":
        return False
    selected_hash = candidate_hashes.get(resolution.selected_candidate_id)
    return selected_hash is not None and resolution.selected_candidate_hash == selected_hash
