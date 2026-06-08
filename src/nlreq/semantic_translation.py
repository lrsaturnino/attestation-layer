from __future__ import annotations

from typing import TYPE_CHECKING, Literal

from pydantic import BaseModel, ConfigDict, Field

from .audit_client import AuditVerdict
from .dsl_v3 import DslV3ParseError, DslV3Parser, canonicalize_dsl_v3_text
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
    # Whole-controlled-requirement fallback span(s) for stage-level (hash/process) refusals
    # that have no single offending fragment to localize — unapproved controlled text,
    # unaudited decomposition, translator-agreement blockers. The whole controlled
    # requirement IS the actionable unit in those modes, so the PA-10 product refusal
    # surface renders it inline instead of a spanless "unavailable" finding. Empty on
    # accepted reports and on fragment-bearing refusals (which localize per fragment).
    refusal_source_spans: list[SourceSpan] = Field(default_factory=list)
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
            # No parsed fragment exists yet (rejected at hash-binding), so the whole
            # controlled rewrite is the actionable unit to approve and bind.
            refusal_source_spans=[_whole_controlled_requirement_span(controlled_text)],
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
        parse_span = _span_for_parse_error(canonicalize_dsl_v3_text(controlled_text), exc)
        ambiguity = SemanticAmbiguityFinding(
            finding_id="parse-unsupported",
            reason=str(exc),
            source_spans=[parse_span] if parse_span is not None else [],
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
            # Fall back to the whole controlled requirement when the parse error carries
            # no resolvable line/column (generic LarkError), so the refusal still localizes.
            refusal_source_spans=[_whole_controlled_requirement_span(controlled_text)],
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
        # Whole-requirement fallback for a formal-claim refusal whose unsupported
        # fragments happen to lack their own span; empty-effect on the accepted path.
        refusal_source_spans=[_whole_controlled_requirement_span(controlled_text)],
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
    refusal_source_spans: list[SourceSpan] | None = None,
) -> SemanticTranslationReport:
    """Return a REFUSED_AMBIGUOUS report for ensemble signature disagreement.

    Use this when ≥2 independent translation candidates produce FormalClaim
    signatures that do not agree under alpha-renaming and commutativity
    normalisation.  The report carries source spans, clarification questions
    mapped from the disagreement paths, and all available prior-stage provenance
    so callers can reconstruct the full translation history.

    All provenance params are optional for backward-compatibility with call sites
    that only supply requirement_id and disagreements (e.g. end_to_end_gate).

    ``refusal_source_spans`` is the whole-requirement fallback the PA-10 product surface
    renders when a per-disagreement span is unavailable. When the caller does not pass it,
    it is derived from the parsed ``requirement_ir`` root span so both the standalone
    ensemble path and the gate path (which supplies ``requirement_ir``) localize without
    threading the controlled text through.
    """
    effective_id = translation_id or f"semantic-translation-{requirement_id}"
    effective_fallback_spans = refusal_source_spans
    if effective_fallback_spans is None and requirement_ir is not None:
        effective_fallback_spans = list(requirement_ir.semantic_ir.source_spans)
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
        refusal_source_spans=effective_fallback_spans or [],
        stages=all_stages,
        input_hashes=input_hashes or {},
        ensemble_candidate_provenances=ensemble_candidate_provenances or [],
        ensemble_candidate_audit_verdicts=ensemble_candidate_audit_verdicts or [],
    )


def refuse_low_confidence_cross_language(
    *,
    requirement_id: str,
    language: str,
    fragment: str,
    translation_id: str | None = None,
    prose: str | None = None,
) -> SemanticTranslationReport:
    """Refuse a non-English draft the model could not confidently translate (PA-11).

    When drafting from non-English prose, the model emits a clarify sentinel rather than
    guess at a fragment it cannot map to the controlled grammar. This turns that signal
    into a clarification refusal — never a guessed controlled rewrite reaching the parser.
    The offending fragment is localized to a span over the original prose where possible,
    so the PA-10 product refusal surface renders it inline with next_actions.
    """
    effective_id = translation_id or f"semantic-translation-{requirement_id}"
    clarification = (
        f"The drafter could not confidently translate a fragment of the '{language}' "
        f"requirement: '{fragment}'. Clarify the fragment or supply an approved controlled rewrite."
    )
    finding = SemanticAmbiguityFinding(
        finding_id="cross-language-uncertain",
        reason=f"low-confidence cross-language fragment in '{language}' prose: {fragment}",
        source_spans=_spans_for_fragment(prose, fragment),
        clarification_question=clarification,
    )
    return SemanticTranslationReport(
        translation_id=effective_id,
        requirement_id=requirement_id,
        result="refused",
        syntactically_valid=False,
        refusal_code="NLR-CROSS-LANGUAGE-UNCERTAIN",
        ambiguity_findings=[finding],
        clarification_questions=[clarification],
        refusal_source_spans=_spans_for_fragment(prose, fragment),
        stages=[
            SemanticTranslationStage(
                stage="canonicalize",
                status="failed",
                message=(
                    f"low-confidence cross-language draft in '{language}'; "
                    "refusing rather than guessing the controlled rewrite"
                ),
            )
        ],
        input_hashes={"source_prose": sha256_text(prose)} if prose is not None else {},
    )


def _whole_controlled_requirement_span(controlled_text: str) -> SourceSpan:
    """Localize a stage-level refusal to the whole controlled requirement (PA-10).

    Hash/process blockers — unapproved controlled text, unaudited decomposition,
    translator-agreement — have no single offending fragment: the whole controlled
    requirement is the actionable unit the author/reviewer must act on. The trailing
    newline is dropped so the rendered fragment is clean and matches the parser's
    root-node span convention (which strips line endings), keeping the displayed
    fragment identical whether it is derived here or from the parsed IR root.
    """
    text = controlled_text.rstrip("\n")
    return SourceSpan(
        document="controlled_requirement",
        start_char=0,
        end_char=len(text),
        text=text,
    )


def _spans_for_fragment(prose: str | None, fragment: str) -> list[SourceSpan]:
    if prose is not None:
        index = prose.find(fragment)
        if index >= 0:
            return [
                SourceSpan(
                    document="source_prose",
                    start_char=index,
                    end_char=index + len(fragment),
                    text=fragment,
                )
            ]
    # No prose context (or fragment not found verbatim): localize to the fragment itself.
    return [
        SourceSpan(
            document="source_prose",
            start_char=0,
            end_char=len(fragment),
            text=fragment,
        )
    ]


def _is_trusted_candidate(result: "DecompositionResult") -> bool:
    """Whether a decomposition candidate may drive a formal-claim comparison.

    A candidate is trusted only with real audit evidence:
      - explicit approval (approval.status == "approved"), AND
      - is_audited is True, AND
      - a present audit verdict that structurally passes — it covers all clauses
        and invents no premises.

    A boolean is_audited=True with no audit_verdict is NOT trusted: the verdict is
    the evidence, the flag alone is not.  The structural fields are checked directly
    (matching how apply_audit derives the gate) rather than trusting the verdict
    string.
    """
    if result.approval is None or result.approval.status != "approved":
        return False
    if not result.is_audited:
        return False
    if result.audit_verdict is None:
        return False
    return (
        result.audit_verdict.covers_all_clauses
        and not result.audit_verdict.invented_premises
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
    2. Any candidate that is not approved AND audited with a present, structurally
       passing audit verdict (covers all clauses, no invented premises) causes the
       ensemble to return needs_review — a boolean is_audited flag without a verdict
       is not trusted evidence.  The untrusted result is a process blocker, not a
       semantic finding.
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

    # Trust check: a candidate may drive a formal-claim comparison only with real audit
    # evidence — explicit approval AND a present, structurally passing audit verdict.
    # A boolean is_audited=True with no verdict is NOT trusted: the verdict is the
    # evidence, the flag alone is not.
    untrusted = [r for r in results if not _is_trusted_candidate(r)]
    if untrusted:
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
            refusal_source_spans=[_whole_controlled_requirement_span(controlled_text)],
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
                        f"{len(untrusted)} of {len(results)} decomposition candidate(s) are "
                        "unapproved or lack a present, passing audit verdict; audit evidence "
                        "required before claim inference"
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
            refusal_source_spans=[_whole_controlled_requirement_span(controlled_text)],
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
            refusal_source_spans=[_whole_controlled_requirement_span(controlled_text)],
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


def _span_for_parse_error(
    canonical_text: str, exc: DslV3ParseError
) -> SourceSpan | None:
    """Resolve a DSL v3 parse error's line/column to a SourceSpan over the offending line.

    The parser canonicalises the controlled text before parsing, so the error's
    ``line``/``column`` (Lark, 1-based) index the *canonicalised* text — this helper
    must therefore receive that same canonical text so the offsets line up. The span
    covers the whole offending line (a more useful "fragment" to render than a single
    column), with ``text`` set to the offending line so refusal renderers can show it
    verbatim. Returns ``None`` when the error carries no position (the generic
    ``LarkError`` branch) or the line is blank/out of range, so the caller emits a
    ``no_span_reason`` rather than a contorted empty span.
    """
    if exc.line is None or exc.column is None:
        return None
    lines = canonical_text.splitlines(keepends=True)
    if exc.line < 1 or exc.line > len(lines):
        return None
    start_of_line = sum(len(item) for item in lines[: exc.line - 1])
    offending = lines[exc.line - 1].rstrip("\r\n")
    if not offending.strip():
        return None
    return SourceSpan(
        document="controlled_requirement",
        start_char=start_of_line,
        end_char=start_of_line + len(offending),
        text=offending,
    )


def _parse_repair_question(exc: DslV3ParseError) -> str:
    if exc.line is not None and exc.column is not None:
        return (
            "Rewrite the requirement in DSL v3 form: requirement <claim_class>, "
            "scope, when predicates, then obligations."
        )
    return "Clarify the requirement using supported controlled-language constructs."
