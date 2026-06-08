from __future__ import annotations

from typing import Literal, get_args

from pydantic import BaseModel, ConfigDict, Field

from .end_to_end_gate import EndToEndRequirementGateReport
from .models import SourceSpan
from .semantic_translation import SemanticTranslationReport


REFUSAL_SCHEMA_VERSION = "0.1"

RefusalCode = Literal[
    "NLR-PARSE-UNSUPPORTED",
    "NLR-INTAKE-UNAPPROVED",
    "NLR-SEMANTIC-UNSUPPORTED",
    "NLR-SEMANTIC-AMBIGUOUS",
    "NLR-TRANSLATION-DISAGREEMENT",
    "NLR-SELF-CONTRADICTION",
    "NLR-FORMAL-UNKNOWN",
    "NLR-SYSTEM-INCONSISTENT",
    "NLR-SPEC-COVERAGE",
    "NLR-TRACE-MISMATCH",
    "NLR-EVIDENCE-PRODUCER",
    "NLR-CLOSURE-BLOCKED",
    # Pillar A drafting/translation refusal codes, emitted by semantic_translation.
    # Listed here so build_refusal_report_from_semantic_translation can preserve the
    # exact emitted code (no lossy remap onto a near-synonym) in the product surface.
    "NLR-UNAPPROVED-CONTROLLED-TEXT",
    "NLR-REFUSED-AMBIGUOUS",
    "NLR-UNAUDITED-DECOMPOSITION",
    "NLR-TRANSLATION-AGREEMENT-BLOCKED",
    # Multilingual intake (PA-11): a non-English fragment the drafter could not confidently
    # map to the controlled grammar; refuse with a clarification rather than guess.
    "NLR-CROSS-LANGUAGE-UNCERTAIN",
]

_KNOWN_REFUSAL_CODES = frozenset(get_args(RefusalCode))


class ProductRefusalFinding(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: RefusalCode
    category: Literal["refused", "unknown"]
    stage: str
    message: str
    source_spans: list[SourceSpan] = Field(default_factory=list)
    no_span_reason: str | None = None
    next_actions: list[str] = Field(default_factory=list)
    likely_owner: str


class ProductRefusalReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["0.1"] = REFUSAL_SCHEMA_VERSION
    requirement_id: str
    decision: Literal["accepted", "refused", "unknown"]
    findings: list[ProductRefusalFinding] = Field(default_factory=list)


def build_refusal_report_from_gate(report: EndToEndRequirementGateReport) -> ProductRefusalReport:
    return ProductRefusalReport(
        requirement_id=report.requirement_id,
        decision=report.decision,
        findings=[
            ProductRefusalFinding(
                code=_code_for_stage(blocker.stage, blocker.status),
                category="unknown" if blocker.status == "unknown" else "refused",
                stage=blocker.stage,
                message=blocker.message,
                source_spans=blocker.source_spans,
                no_span_reason=None
                if blocker.source_spans
                else "end-to-end blocker is stage-level; inspect linked artifacts for fragment spans",
                next_actions=_next_actions(blocker.stage, blocker.status),
                likely_owner=_owner_for_stage(blocker.stage),
            )
            for blocker in report.blockers
        ],
    )


def build_refusal_report_from_semantic_translation(
    report: SemanticTranslationReport,
) -> ProductRefusalReport:
    """Render a SemanticTranslationReport onto the product refusal surface.

    Pillar A drafting/translation refusals are emitted by semantic_translation with
    their own code vocabulary and fragment-level provenance (ambiguity findings and
    unsupported formal-claim fragments). This converter maps every refusal mode onto
    ProductRefusalFinding so each one carries actionable next_actions plus a real source
    span (PA-10): a per-fragment span where one exists, else the report's whole-controlled
    -requirement fallback span — never a bare "broken, try again", and never a spanless
    "unavailable" finding. (no_span_reason remains only for the cross-pillar end-to-end
    gate path in build_refusal_report_from_gate, whose blockers can be genuinely
    stage-level with no fragment to localize.)

    An accepted report yields an accepted decision with no findings; a needs_review
    report is surfaced as the ``unknown`` decision (a process blocker, not a defect).
    """
    decision: Literal["accepted", "refused", "unknown"] = (
        "accepted"
        if report.result == "accepted"
        else ("unknown" if report.result == "needs_review" else "refused")
    )
    if report.result == "accepted" or report.refusal_code is None:
        return ProductRefusalReport(
            requirement_id=report.requirement_id, decision=decision, findings=[]
        )
    code = _coerce_refusal_code(report.refusal_code)
    category: Literal["refused", "unknown"] = (
        "unknown" if report.result == "needs_review" else "refused"
    )
    stage = _semantic_refusal_stage(report)
    owner = _semantic_refusal_owner(code)
    base_actions = _semantic_refusal_next_actions(code)
    findings = _semantic_refusal_findings(report, code, category, stage, owner, base_actions)
    return ProductRefusalReport(
        requirement_id=report.requirement_id, decision=decision, findings=findings
    )


def _semantic_refusal_findings(
    report: SemanticTranslationReport,
    code: RefusalCode,
    category: Literal["refused", "unknown"],
    stage: str,
    owner: str,
    base_actions: list[str],
) -> list[ProductRefusalFinding]:
    # PA-10: every semantic-translation refusal carries a real source span. Fragment-bearing
    # refusals (parse errors, ensemble disagreements, unsupported formal-claim fragments)
    # localize per offending fragment; stage-level (hash/process) blockers — and any
    # fragment that happens to lack its own span — fall back to the report's whole-controlled
    # -requirement span. The whole requirement IS the actionable unit for those blockers, so
    # the product surface renders it inline rather than a spanless "unavailable" finding.
    fallback_spans = report.refusal_source_spans
    if report.ambiguity_findings:
        return [
            _finding(
                code, category, stage, owner,
                message=finding.reason,
                source_spans=finding.source_spans or fallback_spans,
                next_actions=_dedupe([finding.clarification_question, *base_actions]),
            )
            for finding in report.ambiguity_findings
        ]
    lowering = report.formal_claim_report
    if lowering is not None and lowering.unsupported_fragments:
        return [
            _finding(
                code, category, stage, owner,
                message=fragment.reason,
                source_spans=fragment.source_spans or fallback_spans,
                next_actions=_dedupe([*fragment.next_actions, *base_actions]),
            )
            for fragment in lowering.unsupported_fragments
        ]
    return [
        _finding(
            code, category, stage, owner,
            message=_semantic_refusal_message(report),
            source_spans=fallback_spans,
            next_actions=_dedupe([*report.clarification_questions, *base_actions]),
        )
    ]


def _finding(
    code: RefusalCode,
    category: Literal["refused", "unknown"],
    stage: str,
    owner: str,
    *,
    message: str,
    source_spans: list[SourceSpan],
    next_actions: list[str],
) -> ProductRefusalFinding:
    # no_span_reason is the last-resort explanation only when no span is available at all.
    # With the whole-requirement fallback populated at every refusal site, the semantic
    # -translation path always supplies a span; this stays defensive so a future spanless
    # site degrades to an explained finding rather than an empty, mute one.
    return ProductRefusalFinding(
        code=code,
        category=category,
        stage=stage,
        message=message,
        source_spans=source_spans,
        no_span_reason=None if source_spans else _no_span_reason(code),
        next_actions=next_actions,
        likely_owner=owner,
    )


def _coerce_refusal_code(raw: str) -> RefusalCode:
    # Preserve the emitted code when it is a known RefusalCode; otherwise fall back to
    # the generic closure-blocked code rather than fail validation on an unknown string.
    return raw if raw in _KNOWN_REFUSAL_CODES else "NLR-CLOSURE-BLOCKED"  # type: ignore[return-value]


def _semantic_refusal_stage(report: SemanticTranslationReport) -> str:
    for stage in reversed(report.stages):
        if stage.status in {"failed", "needs_review"}:
            return stage.stage
    return "semantic_translation"


def _semantic_refusal_message(report: SemanticTranslationReport) -> str:
    for stage in reversed(report.stages):
        if stage.status in {"failed", "needs_review"}:
            return stage.message
    return f"semantic translation {report.result}"


def _semantic_refusal_owner(code: RefusalCode) -> str:
    owners = {
        "NLR-PARSE-UNSUPPORTED": "requirement author",
        "NLR-REFUSED-AMBIGUOUS": "requirement author",
        "NLR-UNAPPROVED-CONTROLLED-TEXT": "requirement author",
        "NLR-UNAUDITED-DECOMPOSITION": "requirement reviewer",
        "NLR-TRANSLATION-AGREEMENT-BLOCKED": "requirement reviewer",
        "NLR-SEMANTIC-UNSUPPORTED": "formal reviewer",
        "NLR-CROSS-LANGUAGE-UNCERTAIN": "requirement author",
    }
    return owners.get(code, "release owner")


def _semantic_refusal_next_actions(code: RefusalCode) -> list[str]:
    actions = {
        "NLR-PARSE-UNSUPPORTED": [
            "Rewrite the highlighted fragment using supported DSL v3 constructs."
        ],
        "NLR-REFUSED-AMBIGUOUS": [
            "Resolve the flagged ambiguity and re-submit a single unambiguous controlled rewrite."
        ],
        "NLR-UNAPPROVED-CONTROLLED-TEXT": [
            "Approve the controlled rewrite and bind its exact text hash before translation."
        ],
        "NLR-UNAUDITED-DECOMPOSITION": [
            "Supply audited, approved decomposition candidates, or omit the ensemble check."
        ],
        "NLR-TRANSLATION-AGREEMENT-BLOCKED": [
            "Resolve the translator-agreement blocker before accepting the claim."
        ],
        "NLR-SEMANTIC-UNSUPPORTED": [
            "Express the requirement with a supported claim class and supported fragments."
        ],
        "NLR-CROSS-LANGUAGE-UNCERTAIN": [
            "Clarify the flagged non-English fragment or supply an approved controlled rewrite."
        ],
    }
    return actions.get(code, ["Address the refusal before the downstream action."])


def _no_span_reason(code: RefusalCode) -> str:
    reasons = {
        "NLR-UNAPPROVED-CONTROLLED-TEXT": (
            "controlled text rejected at hash-binding before parsing; no fragment to localize"
        ),
        "NLR-UNAUDITED-DECOMPOSITION": (
            "process blocker: ensemble candidates lack audit evidence; not a fragment-level defect"
        ),
        "NLR-TRANSLATION-AGREEMENT-BLOCKED": (
            "process blocker: translator-agreement gate; no single offending fragment"
        ),
    }
    return reasons.get(code, "stage-level refusal; inspect linked artifacts for fragment spans")


def _dedupe(items: list[str]) -> list[str]:
    seen: set[str] = set()
    unique: list[str] = []
    for item in items:
        normalized = item.strip()
        if normalized and normalized not in seen:
            seen.add(normalized)
            unique.append(normalized)
    return unique


def refusal_report_markdown(report: ProductRefusalReport) -> str:
    lines = [
        f"# Requirement {report.requirement_id} refusal report",
        "",
        f"Decision: `{report.decision}`",
        "",
    ]
    if not report.findings:
        lines.append("No refusal findings.")
        return "\n".join(lines) + "\n"
    for finding in report.findings:
        lines.extend(
            [
                f"## {finding.code}",
                "",
                f"- Stage: `{finding.stage}`",
                f"- Category: `{finding.category}`",
                f"- Owner: `{finding.likely_owner}`",
                f"- Message: {finding.message}",
            ]
        )
        if finding.source_spans:
            spans = ", ".join(f"{span.document}:{span.start_char}-{span.end_char}" for span in finding.source_spans)
            lines.append(f"- Source spans: {spans}")
        elif finding.no_span_reason:
            lines.append(f"- Source spans: unavailable ({finding.no_span_reason})")
        for action in finding.next_actions:
            lines.append(f"- Next action: {action}")
        lines.append("")
    return "\n".join(lines)


def _code_for_stage(stage: str, status: str) -> RefusalCode:
    if stage == "translation_agreement":
        return "NLR-TRANSLATION-DISAGREEMENT"
    if stage == "requirement_self_consistency":
        return "NLR-FORMAL-UNKNOWN" if status == "unknown" else "NLR-SELF-CONTRADICTION"
    if stage == "spec_coverage":
        return "NLR-SPEC-COVERAGE"
    if stage in {"trace_alignment", "trace_replay"}:
        return "NLR-TRACE-MISMATCH"
    if stage == "system_consistency":
        return "NLR-FORMAL-UNKNOWN" if status == "unknown" else "NLR-SYSTEM-INCONSISTENT"
    return "NLR-CLOSURE-BLOCKED"


def _owner_for_stage(stage: str) -> str:
    owners = {
        "translation_agreement": "requirement reviewer",
        "requirement_self_consistency": "formal reviewer",
        "spec_coverage": "adapter/evidence reviewer",
        "trace_alignment": "adapter/evidence reviewer",
        "trace_replay": "adapter/evidence reviewer",
        "system_consistency": "formal reviewer",
    }
    return owners.get(stage, "release owner")


def _next_actions(stage: str, status: str) -> list[str]:
    if stage == "translation_agreement":
        return ["Resolve translator disagreement or approve one reviewed candidate."]
    if stage == "requirement_self_consistency":
        return ["Revise contradictory fragments or supply a supported formal backend result."]
    if stage == "spec_coverage":
        return ["Add or refresh reviewed specs for affected modules."]
    if stage in {"trace_alignment", "trace_replay"}:
        return ["Regenerate normalized traces or adjust the requirement to match observed behavior."]
    if stage == "system_consistency":
        return ["Review the S-and-R counterexample, timeout, or unsupported fragment."]
    if status == "unknown":
        return ["Replace unknown evidence with a supported result or request a governed waiver."]
    return ["Close all blocking proof-object findings before the downstream action."]
