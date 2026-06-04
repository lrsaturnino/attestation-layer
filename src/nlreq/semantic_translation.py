from __future__ import annotations

from typing import TYPE_CHECKING, Literal

from pydantic import BaseModel, ConfigDict, Field

from .dsl_v3 import DslV3ParseError, DslV3Parser
from .formal_claim import FormalClaimLoweringReport, build_formal_claim
from .jsonutil import sha256_json, sha256_text
from .models import RequirementIRV2, SemanticNode, SourceSpan
from .translator_agreement import TranslationDisagreement

if TYPE_CHECKING:
    from .decomposition_client import DecompositionClient


SEMANTIC_TRANSLATION_SCHEMA_VERSION = "0.1"
SEMANTIC_TRANSLATION_TOOL_VERSION = "0.1"
SEMANTIC_DECOMPOSITION_SCHEMA_VERSION = "0.1"


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


class SemanticDecompositionNode(BaseModel):
    model_config = ConfigDict(extra="forbid")

    node_id: str
    role: Literal["root", "scope", "premise", "action", "obligation", "child"]
    kind: str
    label: str
    source_spans: list[SourceSpan] = Field(default_factory=list)
    children: list["SemanticDecompositionNode"] = Field(default_factory=list)


class SemanticDecompositionTree(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["0.1"] = SEMANTIC_DECOMPOSITION_SCHEMA_VERSION
    tree_id: str
    requirement_id: str
    source_ir_hash: str
    root: SemanticDecompositionNode
    input_hashes: dict[str, str] = Field(default_factory=dict)
    tool: str = "nlreq.semantic_translation"
    tool_version: str = SEMANTIC_TRANSLATION_TOOL_VERSION


class SemanticTranslationReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["0.1"] = SEMANTIC_TRANSLATION_SCHEMA_VERSION
    translation_id: str
    requirement_id: str
    result: Literal["accepted", "refused", "needs_review"]
    syntactically_valid: bool
    semantic_tree_hash: str | None = None
    semantic_decomposition_hash: str | None = None
    formal_claim_hash: str | None = None
    refusal_code: str | None = None
    requirement_ir: RequirementIRV2 | None = None
    semantic_decomposition: SemanticDecompositionTree | None = None
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
    approved_controlled_text_hash: str | None = None,
    require_approved_controlled_text: bool = False,
    decomposition_clients: "list[DecompositionClient] | None" = None,
) -> SemanticTranslationReport:
    source_hash = sha256_text(controlled_text)
    effective_translation_id = translation_id or f"semantic-translation-{requirement_id}"
    if require_approved_controlled_text and approved_controlled_text_hash != source_hash:
        return SemanticTranslationReport(
            translation_id=effective_translation_id,
            requirement_id=requirement_id,
            result="refused",
            syntactically_valid=False,
            refusal_code="NLR-UNAPPROVED-CONTROLLED-TEXT",
            clarification_questions=[
                "Approve the controlled rewrite and pass its exact controlled text hash before translation."
            ],
            stages=[
                SemanticTranslationStage(
                    stage="canonicalize",
                    status="failed",
                    message="controlled text hash is not bound to an approved rewrite",
                    artifact_hash=source_hash,
                )
            ],
            input_hashes={
                "controlled_text": source_hash,
                **(
                    {"approved_controlled_text": approved_controlled_text_hash}
                    if approved_controlled_text_hash is not None
                    else {}
                ),
            },
        )
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
    semantic_decomposition = build_semantic_decomposition_tree(
        requirement,
        tree_id=f"semantic-decomposition-{requirement.requirement_id}",
    )
    decomposition_hash = sha256_json(semantic_decomposition)
    stages.append(
        SemanticTranslationStage(
            stage="parse_semantic_tree",
            status="passed",
            message="controlled text parsed to explicit semantic decomposition tree",
            artifact_hash=decomposition_hash,
        )
    )

    # PA-5 ensemble check: when ≥2 independent decomposition clients are supplied,
    # run each, compare FormalClaim signatures, and refuse on divergence.  This
    # catches ambiguity in the controlled text before the claim reaches a backend.
    if decomposition_clients is not None and len(decomposition_clients) >= 2:
        ensemble_refusal = _check_decomposition_ensemble(
            controlled_text=controlled_text,
            requirement_id=requirement_id,
            title=title,
            translation_id=effective_translation_id,
            clients=decomposition_clients,
        )
        if ensemble_refusal is not None:
            return ensemble_refusal

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
        semantic_decomposition_hash=decomposition_hash,
        formal_claim_hash=formal_claim_hash,
        refusal_code=formal_claim_report.refusal_code,
        requirement_ir=requirement,
        semantic_decomposition=semantic_decomposition,
        formal_claim_report=formal_claim_report,
        stages=stages,
        input_hashes={
            "controlled_text": source_hash,
            **(
                {"approved_controlled_text": approved_controlled_text_hash}
                if approved_controlled_text_hash is not None
                else {}
            ),
            "semantic_tree": semantic_hash,
            "semantic_decomposition": decomposition_hash,
            **({"formal_claim": formal_claim_hash} if formal_claim_hash else {}),
        },
    )


def build_semantic_decomposition_tree(
    requirement: RequirementIRV2,
    *,
    tree_id: str | None = None,
) -> SemanticDecompositionTree:
    source_ir_hash = sha256_json(requirement)
    return SemanticDecompositionTree(
        tree_id=tree_id or f"semantic-decomposition-{requirement.requirement_id}",
        requirement_id=requirement.requirement_id,
        source_ir_hash=source_ir_hash,
        root=_decomposition_node(requirement.semantic_ir, role="root"),
        input_hashes={"requirement_ir": source_ir_hash},
    )


def _decomposition_node(
    node: SemanticNode,
    *,
    role: Literal["root", "scope", "premise", "action", "obligation", "child"],
) -> SemanticDecompositionNode:
    children: list[SemanticDecompositionNode] = []
    children.extend(_decomposition_node(child, role="scope") for child in node.scope)
    if node.premise is not None:
        children.append(_decomposition_node(node.premise, role="premise"))
    if node.action is not None:
        children.append(_decomposition_node(node.action, role="action"))
    if node.must is not None:
        children.append(_decomposition_node(node.must, role="obligation"))
    if node.obligation is not None:
        children.append(_decomposition_node(node.obligation, role="obligation"))
    children.extend(_decomposition_node(child, role="child") for child in node.children)
    return SemanticDecompositionNode(
        node_id=node.node_id,
        role=role,
        kind=node.kind,
        label=_semantic_node_label(node),
        source_spans=node.source_spans,
        children=children,
    )


def _semantic_node_label(node: SemanticNode) -> str:
    if node.name is not None:
        return node.name
    if node.kind in {"eq", "neq", "lt", "lte", "gt", "gte"} and len(node.args) >= 2:
        return f"{node.args[0].kind}:{node.args[0].value} {node.kind} {node.args[1].kind}:{node.args[1].value}"
    if node.kind == "within" and node.temporal_bound is not None:
        return f"within {node.temporal_bound.value} {node.temporal_bound.unit}"
    return node.kind


def refuse_ambiguous_ensemble(
    *,
    requirement_id: str,
    translation_id: str | None = None,
    disagreements: list[TranslationDisagreement],
) -> SemanticTranslationReport:
    """Return a REFUSED_AMBIGUOUS report for ensemble signature disagreement.

    Use this when ≥2 independent translation candidates produce FormalClaim
    signatures that do not agree under alpha-renaming and commutativity
    normalisation. The report carries source spans and clarification questions
    mapped from the disagreement paths.
    """
    effective_id = translation_id or f"semantic-translation-{requirement_id}"
    findings = [
        SemanticAmbiguityFinding(
            finding_id=f"ensemble-disagreement-{i}",
            reason=d.reason,
            source_spans=d.source_spans,
            clarification_question=(
                f"Clarify the intended formal structure at '{d.path}': "
                f"translator '{d.left_translator_id}' and '{d.right_translator_id}' disagree."
            ),
        )
        for i, d in enumerate(disagreements, start=1)
    ]
    clarification_questions = [f.clarification_question for f in findings]
    return SemanticTranslationReport(
        translation_id=effective_id,
        requirement_id=requirement_id,
        result="refused",
        syntactically_valid=True,
        refusal_code="NLR-REFUSED-AMBIGUOUS",
        ambiguity_findings=findings,
        clarification_questions=clarification_questions,
        stages=[
            SemanticTranslationStage(
                stage="lower_formal_claim",
                status="failed",
                message=(
                    f"ensemble translation disagreement: {len(disagreements)} disagreement(s) "
                    "across independent candidates; require clarification before accepting"
                ),
            )
        ],
    )


def _check_decomposition_ensemble(
    *,
    controlled_text: str,
    requirement_id: str,
    title: str,
    translation_id: str,
    clients: "list[DecompositionClient]",
) -> SemanticTranslationReport | None:
    """Run ≥2 independent decomposition clients and compare their FormalClaim signatures.

    Returns a REFUSED_AMBIGUOUS SemanticTranslationReport when approved candidates
    disagree, or None when they agree (allowing the caller to continue).
    """
    from .formal_claim import build_formal_claim, formal_claim_signature
    from .models import Approval
    from .translator_agreement import (
        TranslationAgreementInput,
        TranslationCandidate,
        build_translation_agreement_report,
    )

    candidates: list[TranslationCandidate] = []
    for i, client in enumerate(clients):
        ir = client.decompose_controlled_to_ir(controlled_text, requirement_id, title)
        candidates.append(
            TranslationCandidate(
                translator_id=f"ensemble-decomposition-{i}",
                method="llm",
                requirement=ir,
                # Ensemble clients are pre-approved by the caller's decision to
                # supply them; we do not require an external approval artifact here.
                approval=Approval(
                    status="approved",
                    approved_by="ensemble-runner",
                    approved_at="ensemble",
                ),
                provenance={"source": "decomposition_ensemble", "index": str(i)},
            )
        )

    agreement = build_translation_agreement_report(TranslationAgreementInput(candidates=candidates))
    if agreement.status == "disagreed":
        return refuse_ambiguous_ensemble(
            requirement_id=requirement_id,
            translation_id=translation_id,
            disagreements=agreement.disagreements,
        )
    return None


def _parse_repair_question(exc: DslV3ParseError) -> str:
    if exc.line is not None and exc.column is not None:
        return (
            "Rewrite the requirement in DSL v3 form: requirement <claim_class>, "
            "scope, when predicates, then obligations."
        )
    return "Clarify the requirement using supported controlled-language constructs."
