from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from .end_to_end_gate import EndToEndRequirementGateReport
from .models import SourceSpan


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
]


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
