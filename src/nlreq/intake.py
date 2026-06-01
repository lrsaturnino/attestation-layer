from __future__ import annotations

import difflib
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from .jsonutil import sha256_text


INTAKE_SCHEMA_VERSION = "0.1"
INTAKE_TOOL_VERSION = "0.1"


class FreeFormIntakeArtifact(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["0.1"] = INTAKE_SCHEMA_VERSION
    intake_id: str
    original_text: str
    original_text_hash: str
    submitted_by: str | None = None
    submitted_at: str
    language: str = "en"
    metadata: dict[str, str] = Field(default_factory=dict)


class RewriteProducerMetadata(BaseModel):
    model_config = ConfigDict(extra="forbid")

    method: Literal["manual", "llm", "rule_based"] = "manual"
    model: str | None = None
    prompt_hash: str | None = None
    prompt: str | None = None
    tool: str = "nlreq.intake"
    tool_version: str = INTAKE_TOOL_VERSION
    timestamp: str
    metadata: dict[str, str] = Field(default_factory=dict)


class ControlledRewriteProposal(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["0.1"] = INTAKE_SCHEMA_VERSION
    proposal_id: str
    intake_id: str
    original_text_hash: str
    proposed_controlled_text: str
    proposed_controlled_text_hash: str
    diff: str
    diff_hash: str
    producer: RewriteProducerMetadata
    status: Literal["needs_approval", "approved", "rejected"] = "needs_approval"


class ControlledRewriteApproval(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["0.1"] = INTAKE_SCHEMA_VERSION
    approval_id: str
    proposal_id: str
    decision: Literal["approved", "rejected"]
    approved_by: str
    approved_at: str
    approved_controlled_text_hash: str
    approved_diff_hash: str
    reviewed_original_text_hash: str
    notes: list[str] = Field(default_factory=list)


def create_free_form_intake(
    *,
    intake_id: str,
    original_text: str,
    submitted_at: str,
    submitted_by: str | None = None,
    language: str = "en",
    metadata: dict[str, str] | None = None,
) -> FreeFormIntakeArtifact:
    return FreeFormIntakeArtifact(
        intake_id=intake_id,
        original_text=original_text,
        original_text_hash=sha256_text(original_text),
        submitted_by=submitted_by,
        submitted_at=submitted_at,
        language=language,
        metadata=metadata or {},
    )


def create_controlled_rewrite_proposal(
    *,
    intake: FreeFormIntakeArtifact,
    proposal_id: str,
    proposed_controlled_text: str,
    timestamp: str,
    method: Literal["manual", "llm", "rule_based"] = "manual",
    model: str | None = None,
    prompt: str | None = None,
    metadata: dict[str, str] | None = None,
) -> ControlledRewriteProposal:
    diff = unified_text_diff(intake.original_text, proposed_controlled_text)
    return ControlledRewriteProposal(
        proposal_id=proposal_id,
        intake_id=intake.intake_id,
        original_text_hash=intake.original_text_hash,
        proposed_controlled_text=proposed_controlled_text,
        proposed_controlled_text_hash=sha256_text(proposed_controlled_text),
        diff=diff,
        diff_hash=sha256_text(diff),
        producer=RewriteProducerMetadata(
            method=method,
            model=model,
            prompt=prompt,
            prompt_hash=sha256_text(prompt) if prompt is not None else None,
            timestamp=timestamp,
            metadata=metadata or {},
        ),
    )


def approve_controlled_rewrite(
    proposal: ControlledRewriteProposal,
    *,
    approval_id: str,
    approved_by: str,
    approved_at: str,
    decision: Literal["approved", "rejected"] = "approved",
    notes: list[str] | None = None,
) -> ControlledRewriteApproval:
    return ControlledRewriteApproval(
        approval_id=approval_id,
        proposal_id=proposal.proposal_id,
        decision=decision,
        approved_by=approved_by,
        approved_at=approved_at,
        approved_controlled_text_hash=proposal.proposed_controlled_text_hash,
        approved_diff_hash=proposal.diff_hash,
        reviewed_original_text_hash=proposal.original_text_hash,
        notes=notes or [],
    )


def controlled_text_for_parsing(
    proposal: ControlledRewriteProposal,
    approval: ControlledRewriteApproval | None,
) -> str:
    if approval is None or approval.decision != "approved":
        raise ValueError("controlled rewrite must be explicitly approved before parsing")
    if approval.proposal_id != proposal.proposal_id:
        raise ValueError("approval does not reference this proposal")
    if approval.reviewed_original_text_hash != proposal.original_text_hash:
        raise ValueError("approval hash does not match original intake text")
    if approval.approved_controlled_text_hash != proposal.proposed_controlled_text_hash:
        raise ValueError("approval hash does not match proposed controlled text")
    if approval.approved_diff_hash != proposal.diff_hash:
        raise ValueError("approval hash does not match proposed diff")
    return proposal.proposed_controlled_text


def unified_text_diff(original: str, proposed: str) -> str:
    return "".join(
        difflib.unified_diff(
            original.splitlines(keepends=True),
            proposed.splitlines(keepends=True),
            fromfile="free-form",
            tofile="controlled",
        )
    )
