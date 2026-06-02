from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from .dsl_v3 import DslV3ParseError, DslV3Parser
from .formal_claim import FormalClaimLoweringReport, build_formal_claim
from .jsonutil import sha256_json, sha256_text
from .models import RequirementIRV2, SourceSpan


SEMANTIC_TRANSLATION_SCHEMA_VERSION = "0.1"
SEMANTIC_TRANSLATION_TOOL_VERSION = "0.1"


class SemanticTranslationStage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    stage: Literal["canonicalize", "parse_semantic_tree", "lower_formal_claim"]
    status: Literal["passed", "failed", "needs_review"]
    message: str
    artifact_hash: str | None = None


class SemanticAmbiguityFinding(BaseModel):
    model_config = ConfigDict(extra="forbid")

    finding_id: str
    reason: str
    source_spans: list[SourceSpan] = Field(default_factory=list)
    clarification_question: str


class SemanticTranslationReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["0.1"] = SEMANTIC_TRANSLATION_SCHEMA_VERSION
    translation_id: str
    requirement_id: str
    result: Literal["accepted", "refused", "needs_review"]
    syntactically_valid: bool
    semantic_tree_hash: str | None = None
    formal_claim_hash: str | None = None
    refusal_code: str | None = None
    requirement_ir: RequirementIRV2 | None = None
    formal_claim_report: FormalClaimLoweringReport | None = None
    ambiguity_findings: list[SemanticAmbiguityFinding] = Field(default_factory=list)
    clarification_questions: list[str] = Field(default_factory=list)
    stages: list[SemanticTranslationStage] = Field(default_factory=list)
    input_hashes: dict[str, str] = Field(default_factory=dict)
    tool: str = "nlreq.semantic_translation"
    tool_version: str = SEMANTIC_TRANSLATION_TOOL_VERSION


def translate_controlled_requirement_to_formal_claim(
    *,
    controlled_text: str,
    requirement_id: str,
    title: str,
    translation_id: str | None = None,
) -> SemanticTranslationReport:
    source_hash = sha256_text(controlled_text)
    effective_translation_id = translation_id or f"semantic-translation-{requirement_id}"
    stages = [
        SemanticTranslationStage(
            stage="canonicalize",
            status="passed",
            message="controlled text accepted for deterministic DSL v3 parsing",
            artifact_hash=source_hash,
        )
    ]
    try:
        requirement = DslV3Parser().parse_ir(
            controlled_text,
            requirement_id=requirement_id,
            title=title,
        )
    except DslV3ParseError as exc:
        question = _parse_repair_question(exc)
        ambiguity = SemanticAmbiguityFinding(
            finding_id="parse-unsupported",
            reason=str(exc),
            clarification_question=question,
        )
        return SemanticTranslationReport(
            translation_id=effective_translation_id,
            requirement_id=requirement_id,
            result="refused",
            syntactically_valid=False,
            refusal_code="NLR-PARSE-UNSUPPORTED",
            ambiguity_findings=[ambiguity],
            clarification_questions=[question],
            stages=[
                *stages,
                SemanticTranslationStage(
                    stage="parse_semantic_tree",
                    status="failed",
                    message=str(exc),
                ),
            ],
            input_hashes={"controlled_text": source_hash},
        )

    semantic_hash = sha256_json(requirement.semantic_ir)
    stages.append(
        SemanticTranslationStage(
            stage="parse_semantic_tree",
            status="passed",
            message="controlled text parsed to semantic IR",
            artifact_hash=semantic_hash,
        )
    )
    formal_claim_report = build_formal_claim(requirement)
    formal_claim_hash = (
        sha256_json(formal_claim_report.formal_claim)
        if formal_claim_report.formal_claim is not None
        else None
    )
    if formal_claim_report.result == "lowered":
        result: Literal["accepted", "refused", "needs_review"] = "accepted"
        stage_status: Literal["passed", "failed", "needs_review"] = "passed"
    elif formal_claim_report.result == "needs_review":
        result = "needs_review"
        stage_status = "needs_review"
    else:
        result = "refused"
        stage_status = "failed"
    stages.append(
        SemanticTranslationStage(
            stage="lower_formal_claim",
            status=stage_status,
            message=f"formal claim lowering {formal_claim_report.result}",
            artifact_hash=formal_claim_hash,
        )
    )
    return SemanticTranslationReport(
        translation_id=effective_translation_id,
        requirement_id=requirement_id,
        result=result,
        syntactically_valid=True,
        semantic_tree_hash=semantic_hash,
        formal_claim_hash=formal_claim_hash,
        refusal_code=formal_claim_report.refusal_code,
        requirement_ir=requirement,
        formal_claim_report=formal_claim_report,
        stages=stages,
        input_hashes={
            "controlled_text": source_hash,
            "semantic_tree": semantic_hash,
            **({"formal_claim": formal_claim_hash} if formal_claim_hash else {}),
        },
    )


def _parse_repair_question(exc: DslV3ParseError) -> str:
    if exc.line is not None and exc.column is not None:
        return (
            "Rewrite the requirement in DSL v3 form: requirement <claim_class>, "
            "scope, when predicates, then obligations."
        )
    return "Clarify the requirement using supported controlled-language constructs."

