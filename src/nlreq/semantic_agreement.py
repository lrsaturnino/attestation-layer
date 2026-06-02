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

    if status == "disagreed" and _resolution_is_valid(resolution, candidates):
        status = "resolved_by_review"

    return SemanticAgreementReport(
        requirement_id=requirement_id,
        status=status,
        candidate_hashes=candidate_hashes,
        comparisons=comparisons,
        blockers=blockers,
        resolution=resolution,
        acceptance_allowed=status in {"agreed", "resolved_by_review"},
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


def _resolution_is_valid(
    resolution: SemanticAgreementResolution | None,
    candidates: list[FormalClaimAgreementCandidate],
) -> bool:
    if resolution is None:
        return False
    if resolution.approval.status != "approved":
        return False
    return resolution.selected_candidate_id in {candidate.candidate_id for candidate in candidates}
