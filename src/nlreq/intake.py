from __future__ import annotations

import difflib
from typing import TYPE_CHECKING, Literal

from pydantic import BaseModel, ConfigDict, Field

from .jsonutil import sha256_json, sha256_text

if TYPE_CHECKING:
    from .llm_client import LlmClient


INTAKE_SCHEMA_VERSION = "0.1"
INTAKE_TOOL_VERSION = "0.1"
INTAKE_RUNTIME_SCHEMA_VERSION = "0.1"
REWRITE_REPLAY_SCHEMA_VERSION = "0.1"

IntakeRuntimeState = Literal["drafted", "proposed", "approved", "rejected", "superseded"]


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


class IntakeStateTransition(BaseModel):
    model_config = ConfigDict(extra="forbid")

    from_state: IntakeRuntimeState | None = None
    to_state: IntakeRuntimeState
    actor: str | None = None
    occurred_at: str
    reason: str
    artifact_hashes: dict[str, str] = Field(default_factory=dict)


class FreeFormIntakeRuntimeRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["0.1"] = INTAKE_RUNTIME_SCHEMA_VERSION
    intake: FreeFormIntakeArtifact
    state: IntakeRuntimeState
    proposal_ids: list[str] = Field(default_factory=list)
    selected_proposal_id: str | None = None
    selected_controlled_text_hash: str | None = None
    transitions: list[IntakeStateTransition] = Field(default_factory=list)
    tool: str = "nlreq.intake"
    tool_version: str = INTAKE_TOOL_VERSION


class RewritePromptRegistryEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    prompt_id: str
    prompt: str
    prompt_hash: str
    purpose: str
    created_at: str
    metadata: dict[str, str] = Field(default_factory=dict)


class RewritePromptRegistry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["0.1"] = REWRITE_REPLAY_SCHEMA_VERSION
    registry_id: str
    entries: list[RewritePromptRegistryEntry]


class RewriteReplayAttempt(BaseModel):
    model_config = ConfigDict(extra="forbid")

    proposal_id: str
    intake_id: str
    original_text_hash: str
    proposed_controlled_text: str
    proposed_controlled_text_hash: str
    diff: str
    diff_hash: str
    producer: RewriteProducerMetadata
    retained_output_hash: str
    status: Literal["needs_approval", "approved", "rejected"]


class RewriteApprovalReplayRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    approval_id: str
    proposal_id: str
    decision: Literal["approved", "rejected"]
    reviewed_original_text_hash: str
    approved_controlled_text_hash: str
    approved_diff_hash: str
    approved_by: str
    approved_at: str


class RewriteReplayBundle(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["0.1"] = REWRITE_REPLAY_SCHEMA_VERSION
    bundle_id: str
    intake: FreeFormIntakeArtifact
    attempts: list[RewriteReplayAttempt]
    approvals: list[RewriteApprovalReplayRecord] = Field(default_factory=list)
    prompt_registry: RewritePromptRegistry | None = None
    selected_proposal_id: str | None = None
    selected_controlled_text_hash: str | None = None
    replay_hashes: dict[str, str] = Field(default_factory=dict)
    notes: list[str] = Field(default_factory=list)
    tool: str = "nlreq.intake"
    tool_version: str = INTAKE_TOOL_VERSION


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


def create_intake_runtime_record(
    *,
    intake: FreeFormIntakeArtifact,
    occurred_at: str,
    actor: str | None = None,
) -> FreeFormIntakeRuntimeRecord:
    return FreeFormIntakeRuntimeRecord(
        intake=intake,
        state="drafted",
        transitions=[
            IntakeStateTransition(
                to_state="drafted",
                actor=actor,
                occurred_at=occurred_at,
                reason="free-form intake retained as draft",
                artifact_hashes={"intake": sha256_json(intake)},
            )
        ],
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


def record_rewrite_proposal(
    record: FreeFormIntakeRuntimeRecord,
    proposal: ControlledRewriteProposal,
    *,
    actor: str | None,
    occurred_at: str,
) -> FreeFormIntakeRuntimeRecord:
    _assert_record_can_transition(record)
    _assert_proposal_matches_intake(record.intake, proposal)
    if proposal.status == "rejected":
        raise ValueError("rejected rewrite proposal cannot enter proposed state")
    proposal_ids = [*record.proposal_ids]
    if proposal.proposal_id not in proposal_ids:
        proposal_ids.append(proposal.proposal_id)
    return record.model_copy(
        update={
            "state": "proposed",
            "proposal_ids": proposal_ids,
            "transitions": [
                *record.transitions,
                IntakeStateTransition(
                    from_state=record.state,
                    to_state="proposed",
                    actor=actor,
                    occurred_at=occurred_at,
                    reason="controlled rewrite proposal recorded",
                    artifact_hashes={"proposal": sha256_json(proposal)},
                ),
            ],
        }
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


def record_rewrite_decision(
    record: FreeFormIntakeRuntimeRecord,
    proposal: ControlledRewriteProposal,
    approval: ControlledRewriteApproval,
) -> FreeFormIntakeRuntimeRecord:
    _assert_record_can_transition(record)
    _assert_proposal_matches_intake(record.intake, proposal)
    if proposal.proposal_id not in record.proposal_ids:
        raise ValueError("rewrite proposal was not recorded in this intake runtime")
    artifact_hashes = {
        "proposal": sha256_json(proposal),
        "approval": sha256_json(approval),
    }
    if approval.decision == "approved":
        controlled_text_for_parsing(proposal, approval)
        return record.model_copy(
            update={
                "state": "approved",
                "selected_proposal_id": proposal.proposal_id,
                "selected_controlled_text_hash": proposal.proposed_controlled_text_hash,
                "transitions": [
                    *record.transitions,
                    IntakeStateTransition(
                        from_state=record.state,
                        to_state="approved",
                        actor=approval.approved_by,
                        occurred_at=approval.approved_at,
                        reason="controlled rewrite approved and selected",
                        artifact_hashes=artifact_hashes,
                    ),
                ],
            }
        )
    if approval.proposal_id != proposal.proposal_id:
        raise ValueError("approval does not reference this proposal")
    return record.model_copy(
        update={
            "state": "rejected",
            "transitions": [
                *record.transitions,
                IntakeStateTransition(
                    from_state=record.state,
                    to_state="rejected",
                    actor=approval.approved_by,
                    occurred_at=approval.approved_at,
                    reason="controlled rewrite rejected",
                    artifact_hashes=artifact_hashes,
                ),
            ],
        }
    )


def supersede_intake_runtime_record(
    record: FreeFormIntakeRuntimeRecord,
    *,
    actor: str | None,
    occurred_at: str,
    reason: str,
) -> FreeFormIntakeRuntimeRecord:
    _assert_record_can_transition(record)
    return record.model_copy(
        update={
            "state": "superseded",
            "selected_proposal_id": None,
            "selected_controlled_text_hash": None,
            "transitions": [
                *record.transitions,
                IntakeStateTransition(
                    from_state=record.state,
                    to_state="superseded",
                    actor=actor,
                    occurred_at=occurred_at,
                    reason=reason,
                ),
            ],
        }
    )


def controlled_text_for_runtime_parsing(
    record: FreeFormIntakeRuntimeRecord,
    proposal: ControlledRewriteProposal,
    approval: ControlledRewriteApproval,
) -> str:
    if record.state != "approved":
        raise ValueError("intake runtime must be approved before parsing")
    if record.selected_proposal_id != proposal.proposal_id:
        raise ValueError("proposal is not the selected controlled rewrite")
    if record.selected_controlled_text_hash != proposal.proposed_controlled_text_hash:
        raise ValueError("selected controlled text hash does not match proposal")
    return controlled_text_for_parsing(proposal, approval)


def controlled_text_for_parsing(
    proposal: ControlledRewriteProposal,
    approval: ControlledRewriteApproval | None,
) -> str:
    if proposal.status == "rejected":
        raise ValueError("rejected rewrite proposal cannot be selected for parsing")
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


def build_prompt_registry_entry(
    *,
    prompt_id: str,
    prompt: str,
    purpose: str,
    created_at: str,
    metadata: dict[str, str] | None = None,
) -> RewritePromptRegistryEntry:
    return RewritePromptRegistryEntry(
        prompt_id=prompt_id,
        prompt=prompt,
        prompt_hash=sha256_text(prompt),
        purpose=purpose,
        created_at=created_at,
        metadata=metadata or {},
    )


def build_rewrite_replay_bundle(
    *,
    bundle_id: str,
    intake: FreeFormIntakeArtifact,
    proposals: list[ControlledRewriteProposal],
    approvals: list[ControlledRewriteApproval] | None = None,
    prompt_registry: RewritePromptRegistry | None = None,
    selected_proposal_id: str | None = None,
    notes: list[str] | None = None,
) -> RewriteReplayBundle:
    approval_records = [
        RewriteApprovalReplayRecord(
            approval_id=approval.approval_id,
            proposal_id=approval.proposal_id,
            decision=approval.decision,
            reviewed_original_text_hash=approval.reviewed_original_text_hash,
            approved_controlled_text_hash=approval.approved_controlled_text_hash,
            approved_diff_hash=approval.approved_diff_hash,
            approved_by=approval.approved_by,
            approved_at=approval.approved_at,
        )
        for approval in approvals or []
    ]
    attempts: list[RewriteReplayAttempt] = []
    for proposal in proposals:
        _assert_proposal_matches_intake(intake, proposal)
        attempts.append(
            RewriteReplayAttempt(
                proposal_id=proposal.proposal_id,
                intake_id=proposal.intake_id,
                original_text_hash=proposal.original_text_hash,
                proposed_controlled_text=proposal.proposed_controlled_text,
                proposed_controlled_text_hash=proposal.proposed_controlled_text_hash,
                diff=proposal.diff,
                diff_hash=proposal.diff_hash,
                producer=proposal.producer,
                retained_output_hash=sha256_text(proposal.proposed_controlled_text),
                status=proposal.status,
            )
        )
    selected_hash = None
    if selected_proposal_id is not None:
        selected = next(
            (proposal for proposal in proposals if proposal.proposal_id == selected_proposal_id),
            None,
        )
        if selected is None:
            raise ValueError("selected_proposal_id is not present in replay proposals")
        selected_hash = selected.proposed_controlled_text_hash
    replay_hashes = {
        "intake": sha256_json(intake),
        "attempts": sha256_json(attempts),
        "approvals": sha256_json(approval_records),
    }
    if prompt_registry is not None:
        replay_hashes["prompt_registry"] = sha256_json(prompt_registry)
    return RewriteReplayBundle(
        bundle_id=bundle_id,
        intake=intake,
        attempts=attempts,
        approvals=approval_records,
        prompt_registry=prompt_registry,
        selected_proposal_id=selected_proposal_id,
        selected_controlled_text_hash=selected_hash,
        replay_hashes=replay_hashes,
        notes=notes or [],
    )


def build_dsl_grammar_summary() -> str:
    """Return a compact DSL v3 grammar description for LLM prompts.

    The string is deterministic and version-pinned so prompt_hash is stable
    across runs.  It is intentionally concise — just enough for the LLM to
    produce parseable output, not a full spec.
    """
    return (
        "Controlled-requirement DSL v3 grammar (produce exactly one requirement block):\n"
        "\n"
        "requirement CLAIM_CLASS:\n"
        "  scope SCOPE_NAME\n"
        "  when PREMISE\n"
        "  then OBLIGATION\n"
        "\n"
        "CLAIM_CLASS (choose one):\n"
        "  authorization_precondition | state_precondition | state_postcondition\n"
        "  | numeric_invariant | event_state_correspondence\n"
        "  | bounded_temporal | cross_module_causal_obligation\n"
        "\n"
        "PREMISE examples:\n"
        "  actor is authorized | actor is not authorized\n"
        "  actor is approved | actor is not approved\n"
        "  value > 10 | value <= 100\n"
        "\n"
        "OBLIGATION examples:\n"
        "  action must succeed\n"
        "  action must reject before state_name\n"
        "  state name must be value\n"
        "  emit EVENT_NAME within N UNIT   (UNIT: seconds | minutes | hours | days)\n"
        "  keep name > value | keep name <= value\n"
        "\n"
        "Rules:\n"
        "  - Use only the vocabulary above; do not invent new keywords.\n"
        "  - Every identifier must match [a-z][a-z0-9_]* (snake_case, lowercase).\n"
        "  - Produce exactly one requirement block, nothing else.\n"
    )


def build_rewrite_prompt(prose: str, grammar_summary: str) -> str:
    """Build the prompt string sent to the LLM for a controlled rewrite.

    Deterministic — same inputs always produce the same output — so
    prompt_hash is stable and goldens remain reproducible.
    """
    return (
        "You are a precise technical writer converting free-form requirement prose "
        "into a controlled DSL v3 requirement.\n\n"
        "GRAMMAR:\n"
        + grammar_summary
        + "\nPROSE:\n"
        + prose.strip()
        + "\n\nProduce ONLY the controlled DSL v3 text, no explanation or commentary."
    )


def draft_controlled_rewrite_with_llm(
    *,
    intake: FreeFormIntakeArtifact,
    client: LlmClient,
    proposal_id: str,
    timestamp: str,
    model: str | None = None,
) -> ControlledRewriteProposal:
    """Produce a controlled rewrite proposal by calling an LlmClient.

    The LLM output is UNTRUSTED.  The returned proposal has status
    ``needs_approval``; callers must gate it through the human
    approval/hash-binding step before passing to the parser.

    PA-4.T2 TODO: wire a real anthropic.Anthropic() client here once the
    'anthropic' package is added to pyproject.toml dependencies.  Until then,
    supply a RecordedLlmClient for offline use or UnavailableLlmClient for
    graceful failure.

    Args:
        intake: The free-form intake artifact the proposal is linked to.
        client: An LlmClient-compatible object; use RecordedLlmClient for
            offline/golden tests.
        proposal_id: Unique identifier for the proposal artifact.
        timestamp: ISO-8601 timestamp string for provenance.
        model: Model identifier recorded in provenance (optional).

    Returns:
        A ControlledRewriteProposal with status ``needs_approval``.
    """
    grammar_summary = build_dsl_grammar_summary()
    prompt = build_rewrite_prompt(intake.original_text, grammar_summary)
    proposed_text = client.propose_controlled_rewrite(intake.original_text, grammar_summary)
    return create_controlled_rewrite_proposal(
        intake=intake,
        proposal_id=proposal_id,
        proposed_controlled_text=proposed_text,
        timestamp=timestamp,
        method="llm",
        model=model,
        prompt=prompt,
    )


def unified_text_diff(original: str, proposed: str) -> str:
    return "".join(
        difflib.unified_diff(
            original.splitlines(keepends=True),
            proposed.splitlines(keepends=True),
            fromfile="free-form",
            tofile="controlled",
        )
    )


def _assert_record_can_transition(record: FreeFormIntakeRuntimeRecord) -> None:
    if record.state == "superseded":
        raise ValueError("superseded intake runtime cannot transition")


def _assert_proposal_matches_intake(
    intake: FreeFormIntakeArtifact,
    proposal: ControlledRewriteProposal,
) -> None:
    if proposal.intake_id != intake.intake_id:
        raise ValueError("proposal intake_id does not match intake")
    if proposal.original_text_hash != intake.original_text_hash:
        raise ValueError("proposal original text hash does not match intake")
