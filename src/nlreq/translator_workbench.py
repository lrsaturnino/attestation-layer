from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from .dsl_v3 import DslV3Parser
from .jsonutil import sha256_json, sha256_text
from .models import Approval, RequirementIRV2
from .translator_agreement import TranslationAgreementInput, TranslationCandidate, build_translation_agreement_report


TRANSLATOR_WORKBENCH_SCHEMA_VERSION = "0.1"


class TranslatorCandidateV2(BaseModel):
    model_config = ConfigDict(extra="forbid")

    candidate_id: str
    translator_id: str
    strategy: Literal["deterministic_parser", "llm_semantic_decomposition", "rule_based_post_processor", "second_model_audit"]
    method: Literal["deterministic", "manual", "llm"]
    requirement: RequirementIRV2
    source_text_hash: str
    approval: Approval | None = None
    replay_metadata: dict[str, str] = Field(default_factory=dict)


class TranslatorRunArtifact(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["0.1"] = TRANSLATOR_WORKBENCH_SCHEMA_VERSION
    run_id: str
    requirement_id: str
    source_text_hash: str
    candidates: list[TranslatorCandidateV2] = Field(default_factory=list)
    selected_candidate_id: str | None = None


class TranslatorSelectionArtifact(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["0.1"] = TRANSLATOR_WORKBENCH_SCHEMA_VERSION
    run_id: str
    selected_candidate_id: str
    selected_candidate_hash: str
    approval: Approval


def build_deterministic_translator_run(
    *,
    run_id: str,
    controlled_text: str,
    requirement_id: str,
    title: str,
) -> TranslatorRunArtifact:
    requirement = DslV3Parser().parse_ir(controlled_text, requirement_id=requirement_id, title=title)
    candidate = TranslatorCandidateV2(
        candidate_id="candidate-dsl-v3",
        translator_id="dsl-v3-parser",
        strategy="deterministic_parser",
        method="deterministic",
        requirement=requirement,
        source_text_hash=sha256_text(controlled_text),
        replay_metadata={"tool": "nlreq.dsl_v3", "replay": "deterministic"},
    )
    return TranslatorRunArtifact(
        run_id=run_id,
        requirement_id=requirement_id,
        source_text_hash=sha256_text(controlled_text),
        candidates=[candidate],
    )


def compare_translator_run(run: TranslatorRunArtifact):
    return build_translation_agreement_report(
        TranslationAgreementInput(
            candidates=[
                TranslationCandidate(
                    translator_id=candidate.translator_id,
                    method=candidate.method,
                    requirement=candidate.requirement,
                    approval=candidate.approval,
                    provenance={
                        "candidate_id": candidate.candidate_id,
                        "strategy": candidate.strategy,
                    },
                )
                for candidate in run.candidates
            ]
        )
    )


def select_translator_candidate(
    run: TranslatorRunArtifact,
    *,
    candidate_id: str,
    approved_by: str,
    approved_at: str,
) -> tuple[TranslatorRunArtifact, TranslatorSelectionArtifact]:
    candidate = next((item for item in run.candidates if item.candidate_id == candidate_id), None)
    if candidate is None:
        raise ValueError(f"unknown translator candidate: {candidate_id}")
    if candidate.method == "llm" and (candidate.approval is None or candidate.approval.status != "approved"):
        raise ValueError("LLM candidate cannot be selected without explicit candidate approval")
    approval = Approval(status="approved", approved_by=approved_by, approved_at=approved_at)
    selection = TranslatorSelectionArtifact(
        run_id=run.run_id,
        selected_candidate_id=candidate_id,
        selected_candidate_hash=sha256_json(candidate.requirement),
        approval=approval,
    )
    return run.model_copy(update={"selected_candidate_id": candidate_id}), selection
