from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from .semantic_agreement import SemanticAgreementReport
from .semantic_translation import SemanticTranslationReport
from .models import SourceSpan


TRANSLATION_REPAIR_SCHEMA_VERSION = "0.1"
TRANSLATION_REPAIR_TOOL_VERSION = "0.1"


class TranslationRepairHighlight(BaseModel):
    model_config = ConfigDict(extra="forbid")

    highlight_id: str
    stage: str
    message: str
    source_spans: list[SourceSpan] = Field(default_factory=list)
    no_span_reason: str | None = None


class TranslationRepairPrompt(BaseModel):
    model_config = ConfigDict(extra="forbid")

    prompt_id: str
    question: str
    target_stage: str
    source_spans: list[SourceSpan] = Field(default_factory=list)
    next_actions: list[str] = Field(default_factory=list)


class TranslationRepairReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["0.1"] = TRANSLATION_REPAIR_SCHEMA_VERSION
    requirement_id: str
    decision: Literal["no_repair_needed", "repair_required", "review_required"]
    refusal_code: str | None = None
    highlights: list[TranslationRepairHighlight] = Field(default_factory=list)
    prompts: list[TranslationRepairPrompt] = Field(default_factory=list)
    next_actions: list[str] = Field(default_factory=list)
    tool: str = "nlreq.translation_repair"
    tool_version: str = TRANSLATION_REPAIR_TOOL_VERSION


def build_translation_repair_report(
    *,
    translation: SemanticTranslationReport | None = None,
    agreement: SemanticAgreementReport | None = None,
) -> TranslationRepairReport:
    if translation is None and agreement is None:
        raise ValueError("translation repair requires a translation or agreement report")
    requirement_id = translation.requirement_id if translation is not None else agreement.requirement_id  # type: ignore[union-attr]
    highlights: list[TranslationRepairHighlight] = []
    prompts: list[TranslationRepairPrompt] = []
    next_actions: list[str] = []
    refusal_code: str | None = None

    if translation is not None and translation.result != "accepted":
        refusal_code = translation.refusal_code
        for finding in translation.ambiguity_findings:
            highlights.append(
                TranslationRepairHighlight(
                    highlight_id=f"translation.{finding.finding_id}",
                    stage="semantic_translation",
                    message=finding.reason,
                    source_spans=finding.source_spans,
                    no_span_reason=None if finding.source_spans else "parser-level finding has no stable source span",
                )
            )
            prompts.append(
                TranslationRepairPrompt(
                    prompt_id=f"repair.{finding.finding_id}",
                    question=finding.clarification_question,
                    target_stage="semantic_translation",
                    source_spans=finding.source_spans,
                    next_actions=["Rewrite the requirement as approved controlled DSL v3 text."],
                )
            )
        if translation.formal_claim_report is not None:
            for fragment in translation.formal_claim_report.unsupported_fragments:
                highlights.append(
                    TranslationRepairHighlight(
                        highlight_id=f"formal.{fragment.node_id}",
                        stage="formal_claim_lowering",
                        message=fragment.reason,
                        source_spans=fragment.source_spans,
                        no_span_reason=None if fragment.source_spans else "unsupported fragment has no span",
                    )
                )
                prompts.append(
                    TranslationRepairPrompt(
                        prompt_id=f"repair.{fragment.node_id}",
                        question="Which supported controlled construct should replace this fragment?",
                        target_stage="formal_claim_lowering",
                        source_spans=fragment.source_spans,
                        next_actions=fragment.next_actions,
                    )
                )
        next_actions.append("Submit corrected controlled text or a reviewed rewrite approval.")

    if agreement is not None and not agreement.acceptance_allowed:
        refusal_code = refusal_code or "NLR-TRANSLATION-DISAGREEMENT"
        for index, comparison in enumerate(agreement.comparisons, start=1):
            if comparison.status != "agreed":
                highlights.append(
                    TranslationRepairHighlight(
                        highlight_id=f"agreement.{index}",
                        stage="semantic_agreement",
                        message=comparison.message,
                        source_spans=comparison.source_spans,
                        no_span_reason=None if comparison.source_spans else "comparison is claim-level",
                    )
                )
                prompts.append(
                    TranslationRepairPrompt(
                        prompt_id=f"repair.agreement.{index}",
                        question="Which formal claim candidate preserves the controlled requirement intent?",
                        target_stage="semantic_agreement",
                        source_spans=comparison.source_spans,
                        next_actions=["Resolve the disagreement with a hash-bound reviewer selection."],
                    )
                )
        for blocker in agreement.blockers:
            highlights.append(
                TranslationRepairHighlight(
                    highlight_id=f"agreement.blocker.{len(highlights) + 1}",
                    stage="semantic_agreement",
                    message=blocker,
                    no_span_reason="agreement blocker is not tied to a single source span",
                )
            )
        next_actions.append("Resolve semantic agreement blockers before accepting the requirement.")

    if agreement is not None and agreement.status == "resolved_by_review":
        decision: Literal["no_repair_needed", "repair_required", "review_required"] = "no_repair_needed"
    elif any(prompt.target_stage == "semantic_agreement" for prompt in prompts):
        decision = "review_required"
    elif prompts:
        decision = "repair_required"
    else:
        decision = "no_repair_needed"

    return TranslationRepairReport(
        requirement_id=requirement_id,
        decision=decision,
        refusal_code=refusal_code,
        highlights=highlights,
        prompts=prompts,
        next_actions=next_actions,
    )

