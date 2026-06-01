from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from .jsonutil import sha256_text


APPROVAL_WORKFLOW_SCHEMA_VERSION = "0.1"

ReviewerRole = Literal[
    "author",
    "requirement_reviewer",
    "formal_reviewer",
    "adapter_evidence_reviewer",
    "self_audit_reviewer",
]


class ArtifactReviewRef(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    path: str
    content_hash: str


class ReviewChecklistV2(BaseModel):
    model_config = ConfigDict(extra="forbid")

    controlled_form_matches_intent: Literal["pass", "fail", "n/a"] = "pass"
    semantic_diff_reviewed: Literal["pass", "fail", "n/a"] = "pass"
    source_spans_present: Literal["pass", "fail", "n/a"] = "pass"
    translator_disagreement_resolved: Literal["pass", "fail", "n/a"] = "n/a"
    evidence_labels_appropriate: Literal["pass", "fail", "n/a"] = "pass"
    refusal_actions_actionable: Literal["pass", "fail", "n/a"] = "pass"


class ReviewApprovalRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    role: ReviewerRole
    reviewer: str
    decision: Literal["approved", "needs_review", "rejected"]
    artifact_hashes: dict[str, str]
    checklist: ReviewChecklistV2
    approved_at: str
    self_audit: bool = False
    self_audit_delay_hours: int | None = None


class ApprovalWorkflowArtifact(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["0.1"] = APPROVAL_WORKFLOW_SCHEMA_VERSION
    review_id: str
    requirement_id: str
    status: Literal["open", "approved", "needs_review", "rejected", "stale"] = "open"
    artifact_refs: list[ArtifactReviewRef]
    approvals: list[ReviewApprovalRecord] = Field(default_factory=list)


class ReviewStatusReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["0.1"] = APPROVAL_WORKFLOW_SCHEMA_VERSION
    review_id: str
    status: Literal["open", "approved", "needs_review", "rejected", "stale"]
    stale_artifacts: list[str] = Field(default_factory=list)
    missing_roles: list[ReviewerRole] = Field(default_factory=list)


def open_review(
    *,
    review_id: str,
    requirement_id: str,
    artifact_refs: list[ArtifactReviewRef],
) -> ApprovalWorkflowArtifact:
    return ApprovalWorkflowArtifact(
        review_id=review_id,
        requirement_id=requirement_id,
        artifact_refs=artifact_refs,
    )


def approve_review(
    workflow: ApprovalWorkflowArtifact,
    *,
    role: ReviewerRole,
    reviewer: str,
    decision: Literal["approved", "needs_review", "rejected"],
    approved_at: str,
    current_artifact_refs: list[ArtifactReviewRef] | None = None,
    checklist: ReviewChecklistV2 | None = None,
    self_audit: bool = False,
    self_audit_delay_hours: int | None = None,
) -> ApprovalWorkflowArtifact:
    refs = current_artifact_refs or workflow.artifact_refs
    hashes = {ref.name: ref.content_hash for ref in refs}
    approval = ReviewApprovalRecord(
        role=role,
        reviewer=reviewer,
        decision=decision,
        artifact_hashes=hashes,
        checklist=checklist or ReviewChecklistV2(),
        approved_at=approved_at,
        self_audit=self_audit,
        self_audit_delay_hours=self_audit_delay_hours,
    )
    approvals = [item for item in workflow.approvals if item.role != role] + [approval]
    updated = workflow.model_copy(update={"artifact_refs": refs, "approvals": approvals})
    return updated.model_copy(update={"status": review_status(updated).status})


def review_status(
    workflow: ApprovalWorkflowArtifact,
    *,
    current_artifact_refs: list[ArtifactReviewRef] | None = None,
    required_roles: list[ReviewerRole] | None = None,
) -> ReviewStatusReport:
    refs = current_artifact_refs or workflow.artifact_refs
    current_hashes = {ref.name: ref.content_hash for ref in refs}
    stale = sorted(
        name
        for approval in workflow.approvals
        for name, approved_hash in approval.artifact_hashes.items()
        if current_hashes.get(name) != approved_hash
    )
    required = required_roles or ["requirement_reviewer"]
    approved_roles = {item.role for item in workflow.approvals if item.decision == "approved"}
    missing = [role for role in required if role not in approved_roles]
    if stale:
        status: Literal["open", "approved", "needs_review", "rejected", "stale"] = "stale"
    elif any(item.decision == "rejected" for item in workflow.approvals):
        status = "rejected"
    elif missing:
        status = "needs_review" if workflow.approvals else "open"
    else:
        status = "approved"
    return ReviewStatusReport(
        review_id=workflow.review_id,
        status=status,
        stale_artifacts=sorted(set(stale)),
        missing_roles=missing,
    )


def artifact_ref_from_path(name: str, path: Path) -> ArtifactReviewRef:
    content = path.read_text()
    return ArtifactReviewRef(name=name, path=path.as_posix(), content_hash=sha256_text(content))
