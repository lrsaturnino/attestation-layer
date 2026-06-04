from __future__ import annotations

from typing import TYPE_CHECKING, Literal

from pydantic import BaseModel, ConfigDict, Field

from .audit_client import AuditVerdict
from .dsl_v3 import DslV3ParseError, DslV3Parser
from .formal_claim import FormalClaimLoweringReport, build_formal_claim
from .jsonutil import sha256_json, sha256_text
from .models import RequirementIRV2, SemanticNode, SourceSpan
from .translator_agreement import TranslationDisagreement, spans_for_path

if TYPE_CHECKING:
    from .audit_client import AuditClient
    from .decomposition_client import DecompositionClient, DecompositionResult


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
    # Per-candidate provenance from the ensemble decomposition (PA-5/PA-6). Populated
    # whenever ≥2 clients are run, regardless of whether they agreed or refused.
    # Each entry mirrors the provenance dict from the corresponding DecompositionResult
    # so callers can verify fixture provenance flowed through the CLI path.
    ensemble_candidate_provenances: list[dict[str, str]] = Field(default_factory=list)
    # Per-candidate PA-6 audit verdicts, parallel to ensemble_candidate_provenances.
    # None for candidates that were already audited before the audit_client was applied
    # (e.g. recorded fixtures with is_audited=True) or when no audit_client was supplied.
    ensemble_candidate_audit_verdicts: list[AuditVerdict | None] = Field(default_factory=list)
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
    audit_client: "AuditClient | None" = None,
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

    # PA-5/PA-6 ensemble check: when ≥2 independent decomposition clients are supplied,
    # optionally audit each via audit_client (PA-6), then compare FormalClaim signatures
    # (PA-5) and refuse on divergence. Catches ambiguity before the claim reaches a backend.
    ensemble_candidate_provenances: list[dict[str, str]] = []
    ensemble_candidate_audit_verdicts: list[AuditVerdict | None] = []
    if decomposition_clients is not None and len(decomposition_clients) >= 2:
        ensemble_result, ensemble_candidate_provenances, ensemble_candidate_audit_verdicts = (
            _check_decomposition_ensemble(
                controlled_text=controlled_text,
                requirement_id=requirement_id,
                title=title,
                translation_id=effective_translation_id,
                clients=decomposition_clients,
                prior_stages=stages,
                source_hash=source_hash,
                approved_controlled_text_hash=approved_controlled_text_hash,
                semantic_hash=semantic_hash,
                decomposition_hash=decomposition_hash,
                requirement_ir=requirement,
                semantic_decomposition=semantic_decomposition,
                audit_client=audit_client,
            )
        )
        if ensemble_result is not None:
            return ensemble_result

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
        ensemble_candidate_provenances=ensemble_candidate_provenances,
        ensemble_candidate_audit_verdicts=ensemble_candidate_audit_verdicts,
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
    prior_stages: list[SemanticTranslationStage] | None = None,
    input_hashes: dict[str, str] | None = None,
    semantic_tree_hash: str | None = None,
    semantic_decomposition_hash: str | None = None,
    requirement_ir: RequirementIRV2 | None = None,
    semantic_decomposition: "SemanticDecompositionTree | None" = None,
    ensemble_candidate_provenances: list[dict[str, str]] | None = None,
    ensemble_candidate_audit_verdicts: list[AuditVerdict | None] | None = None,
) -> SemanticTranslationReport:
    """Return a REFUSED_AMBIGUOUS report for ensemble signature disagreement.

    Use this when ≥2 independent translation candidates produce FormalClaim
    signatures that do not agree under alpha-renaming and commutativity
    normalisation.  The report carries source spans, clarification questions
    mapped from the disagreement paths, and all available prior-stage provenance
    so callers can reconstruct the full translation history.

    All provenance params are optional for backward-compatibility with call sites
    that only supply requirement_id and disagreements (e.g. end_to_end_gate).
    """
    effective_id = translation_id or f"semantic-translation-{requirement_id}"
    findings = [
        SemanticAmbiguityFinding(
            finding_id=f"ensemble-disagreement-{i}",
            reason=d.reason,
            source_spans=d.source_spans,
            clarification_question=(
                f"Clarify the intended formal structure at '{d.path}': "
                f"translator '{d.left_translator_id}' and '{d.right_translator_id}' disagree. "
                "Rephrase the requirement to eliminate the ambiguous construct and re-submit."
            ),
        )
        for i, d in enumerate(disagreements, start=1)
    ]
    clarification_questions = [f.clarification_question for f in findings]
    all_stages = [
        *(prior_stages or []),
        SemanticTranslationStage(
            stage="lower_formal_claim",
            status="failed",
            message=(
                f"ensemble translation disagreement: {len(disagreements)} disagreement(s) "
                "across independent candidates; require clarification before accepting"
            ),
        ),
    ]
    return SemanticTranslationReport(
        translation_id=effective_id,
        requirement_id=requirement_id,
        result="refused",
        syntactically_valid=True,
        semantic_tree_hash=semantic_tree_hash,
        semantic_decomposition_hash=semantic_decomposition_hash,
        refusal_code="NLR-REFUSED-AMBIGUOUS",
        requirement_ir=requirement_ir,
        semantic_decomposition=semantic_decomposition,
        ambiguity_findings=findings,
        clarification_questions=clarification_questions,
        stages=all_stages,
        input_hashes=input_hashes or {},
        ensemble_candidate_provenances=ensemble_candidate_provenances or [],
        ensemble_candidate_audit_verdicts=ensemble_candidate_audit_verdicts or [],
    )


def _check_decomposition_ensemble(
    *,
    controlled_text: str,
    requirement_id: str,
    title: str,
    translation_id: str,
    clients: "list[DecompositionClient]",
    prior_stages: list[SemanticTranslationStage],
    source_hash: str,
    approved_controlled_text_hash: str | None,
    semantic_hash: str,
    decomposition_hash: str,
    requirement_ir: RequirementIRV2,
    semantic_decomposition: "SemanticDecompositionTree",
    audit_client: "AuditClient | None" = None,
) -> tuple[SemanticTranslationReport | None, list[dict[str, str]], list[AuditVerdict | None]]:
    """Run ≥2 independent decomposition clients and compare their FormalClaim signatures.

    Returns (report, candidate_provenances, candidate_audit_verdicts). report is None when
    all candidates agree and the caller may continue to claim lowering; the other two lists
    are always populated so the caller can attach them to the agreed-path report.

    Trust-boundary rules enforced here:
    1. When audit_client is supplied (PA-6), it is applied to any candidate that is not
       yet audited (is_audited=False) before the trust check.  audit_client uses the
       original approved controlled_text, never a candidate's re-expressed text.
    2. Any candidate that is not both approved and audited (is_audited=True) after the
       optional audit causes the ensemble to return needs_review — the unaudited result
       is a process blocker, not a semantic finding.
    3. Only after all candidates pass the trust check do we run the FormalClaim-signature
       comparison.  Disagreement then produces NLR-REFUSED-AMBIGUOUS with full provenance.

    Approvals are never synthesised here — they must be carried in each DecompositionResult.
    """
    from .decomposition_client import DecompositionResult
    from .translator_agreement import (
        TranslationAgreementInput,
        TranslationCandidate,
        build_translation_agreement_report,
    )

    full_input_hashes: dict[str, str] = {
        "controlled_text": source_hash,
        **(
            {"approved_controlled_text": approved_controlled_text_hash}
            if approved_controlled_text_hash is not None
            else {}
        ),
        "semantic_tree": semantic_hash,
        "semantic_decomposition": decomposition_hash,
    }

    results: list[DecompositionResult] = [
        client.decompose_controlled_to_ir(controlled_text, requirement_id, title)
        for client in clients
    ]

    # PA-6 audit gate: apply the audit client to any candidate not yet audited.
    # Uses the original approved controlled_text (authoritative), never the candidate's
    # re-expressed text.  Leaves already-audited candidates (e.g. recorded fixtures
    # with is_audited=True) unchanged so existing tests are not broken.
    if audit_client is not None:
        from .audit_client import apply_audit
        results = [
            apply_audit(r, audit_client, controlled_text) if not r.is_audited else r
            for r in results
        ]

    # Collect per-candidate provenance and audit verdicts so the report carries the full
    # chain regardless of whether the ensemble agreed, refused, or blocked on audit.
    candidate_provenances: list[dict[str, str]] = [r.provenance for r in results]
    candidate_audit_verdicts: list[AuditVerdict | None] = [r.audit_verdict for r in results]

    # Trust check: any unaudited or unapproved candidate blocks as needs_review.
    unaudited = [
        r for r in results
        if not r.is_audited
        or r.approval is None
        or r.approval.status != "approved"
    ]
    if unaudited:
        return SemanticTranslationReport(
            translation_id=translation_id,
            requirement_id=requirement_id,
            result="needs_review",
            syntactically_valid=True,
            semantic_tree_hash=semantic_hash,
            semantic_decomposition_hash=decomposition_hash,
            refusal_code="NLR-UNAUDITED-DECOMPOSITION",
            requirement_ir=requirement_ir,
            semantic_decomposition=semantic_decomposition,
            clarification_questions=[
                "Ensemble decomposition candidates must be audited (PA-6 audit) and explicitly "
                "approved before their IR can drive a formal-claim comparison. "
                "Supply audited results or omit the ensemble check to proceed."
            ],
            stages=[
                *prior_stages,
                SemanticTranslationStage(
                    stage="lower_formal_claim",
                    status="needs_review",
                    message=(
                        f"{len(unaudited)} of {len(results)} decomposition candidate(s) are "
                        "unaudited or unapproved; PA-6 audit required before claim inference"
                    ),
                ),
            ],
            input_hashes=full_input_hashes,
            ensemble_candidate_provenances=candidate_provenances,
            ensemble_candidate_audit_verdicts=candidate_audit_verdicts,
        ), candidate_provenances, candidate_audit_verdicts

    # All candidates are approved and audited: build TranslationCandidates from
    # actual DecompositionResult approval — never synthesise an Approval here.
    agreement_candidates: list[TranslationCandidate] = [
        TranslationCandidate(
            translator_id=f"ensemble-decomposition-{i}",
            method="llm",
            requirement=result.requirement,
            approval=result.approval,
            provenance={
                "source": "decomposition_ensemble",
                "index": str(i),
                **({"model": result.model_id} if result.model_id else {}),
                **({"prompt_hash": result.prompt_hash} if result.prompt_hash else {}),
                **result.provenance,
            },
        )
        for i, result in enumerate(results)
    ]

    agreement = build_translation_agreement_report(
        TranslationAgreementInput(candidates=agreement_candidates)
    )

    if agreement.status == "disagreed":
        remapped = remap_disagreement_spans_to_original(
            agreement.disagreements, requirement_ir
        )
        return refuse_ambiguous_ensemble(
            requirement_id=requirement_id,
            translation_id=translation_id,
            disagreements=remapped,
            prior_stages=prior_stages,
            input_hashes=full_input_hashes,
            semantic_tree_hash=semantic_hash,
            semantic_decomposition_hash=decomposition_hash,
            requirement_ir=requirement_ir,
            semantic_decomposition=semantic_decomposition,
            ensemble_candidate_provenances=candidate_provenances,
            ensemble_candidate_audit_verdicts=candidate_audit_verdicts,
        ), candidate_provenances, candidate_audit_verdicts

    if agreement.status == "needs_review":
        return SemanticTranslationReport(
            translation_id=translation_id,
            requirement_id=requirement_id,
            result="needs_review",
            syntactically_valid=True,
            semantic_tree_hash=semantic_hash,
            semantic_decomposition_hash=decomposition_hash,
            refusal_code="NLR-TRANSLATION-AGREEMENT-BLOCKED",
            requirement_ir=requirement_ir,
            semantic_decomposition=semantic_decomposition,
            clarification_questions=[
                f"Translator agreement blocked: {b}" for b in agreement.blockers
            ],
            stages=[
                *prior_stages,
                SemanticTranslationStage(
                    stage="lower_formal_claim",
                    status="needs_review",
                    message=f"translator agreement blocked: {'; '.join(agreement.blockers)}",
                ),
            ],
            input_hashes=full_input_hashes,
            ensemble_candidate_provenances=candidate_provenances,
            ensemble_candidate_audit_verdicts=candidate_audit_verdicts,
        ), candidate_provenances, candidate_audit_verdicts

    return None, candidate_provenances, candidate_audit_verdicts


def remap_disagreement_spans_to_original(
    disagreements: list[TranslationDisagreement],
    original_ir: RequirementIRV2,
) -> list[TranslationDisagreement]:
    """Remap disagreement source_spans to the original parsed requirement_ir where possible.

    Candidate IRs produced by LLM re-expression carry spans referencing model-output
    positions, not the original controlled text.  This function resolves each
    disagreement path against the original IR.  When the path resolves, the original
    spans replace the candidate spans.  When it does not (the candidate IR diverged
    structurally and the path has no counterpart), the candidate spans are kept and an
    explicit note is appended to the reason field so callers know the fallback was taken.
    """
    remapped: list[TranslationDisagreement] = []
    for d in disagreements:
        original_spans = spans_for_path(original_ir.semantic_ir, d.path)
        if original_spans:
            remapped.append(d.model_copy(update={"source_spans": original_spans}))
        else:
            fallback_reason = (
                d.reason
                + f" (span-fallback: no original-text counterpart at path {d.path!r};"
                " spans from candidate IR)"
            )
            remapped.append(d.model_copy(update={"reason": fallback_reason}))
    return remapped


def _parse_repair_question(exc: DslV3ParseError) -> str:
    if exc.line is not None and exc.column is not None:
        return (
            "Rewrite the requirement in DSL v3 form: requirement <claim_class>, "
            "scope, when predicates, then obligations."
        )
    return "Clarify the requirement using supported controlled-language constructs."
