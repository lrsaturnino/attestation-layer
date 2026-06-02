from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from .benchmark_reporting import BenchmarkEvaluationReport
from .public_sdk import REQUIRED_PUBLIC_AUDIENCES, PublicDocumentationIndex
from .reference_demo import ReferenceDemoReport
from .threat_model import ThreatModelReport, threat_model_release_findings


CONCLUSION_CERTIFICATION_SCHEMA_VERSION = "0.1"
CONCLUSION_CERTIFICATION_TOOL_VERSION = "0.1"


class ConclusionCriterionStatus(BaseModel):
    model_config = ConfigDict(extra="forbid")

    criterion_id: str
    status: Literal["passed", "failed", "scoped_out"]
    required: bool = True
    evidence: list[str] = Field(default_factory=list)
    findings: list[str] = Field(default_factory=list)
    limitation: str | None = None


class ConclusionCertificationReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["0.1"] = CONCLUSION_CERTIFICATION_SCHEMA_VERSION
    release_id: str
    result: Literal["certified", "blocked"]
    criteria: list[ConclusionCriterionStatus] = Field(default_factory=list)
    blocking_findings: list[str] = Field(default_factory=list)
    evidence_level_claims: list[str] = Field(default_factory=list)
    known_limitations: list[str] = Field(default_factory=list)
    tool: str = "nlreq.conclusion_certification"
    tool_version: str = CONCLUSION_CERTIFICATION_TOOL_VERSION


def build_conclusion_certification_report(
    *,
    release_id: str,
    benchmark: BenchmarkEvaluationReport,
    threat_model: ThreatModelReport,
    demo: ReferenceDemoReport,
    docs: PublicDocumentationIndex,
    schemas_frozen: bool,
) -> ConclusionCertificationReport:
    benchmark_findings = _benchmark_findings(benchmark)
    threat_findings = threat_model_release_findings(threat_model)
    demo_findings = _reference_demo_findings(demo)
    docs_findings = _public_docs_findings(docs)
    schema_findings = [] if schemas_frozen else ["schema freeze evidence was not provided"]

    criteria = [
        ConclusionCriterionStatus(
            criterion_id="benchmark-evaluation",
            status="failed" if benchmark_findings else "passed",
            evidence=[benchmark.base_report_hash],
            findings=benchmark_findings,
        ),
        ConclusionCriterionStatus(
            criterion_id="threat-model",
            status="failed" if threat_model.result != "complete" or threat_findings else "passed",
            evidence=[scenario.scenario_id for scenario in threat_model.scenarios],
            findings=(
                (["threat model result is not complete"] if threat_model.result != "complete" else [])
                + threat_findings
            ),
        ),
        ConclusionCriterionStatus(
            criterion_id="reference-demo",
            status="failed" if demo.result != "reproducible" or demo_findings else "passed",
            evidence=[demo.demo_id],
            findings=(["reference demo is not reproducible"] if demo.result != "reproducible" else [])
            + demo_findings,
        ),
        ConclusionCriterionStatus(
            criterion_id="public-docs",
            status="failed" if docs_findings else "passed",
            evidence=[entry.doc_id for entry in docs.docs],
            findings=docs_findings,
        ),
        ConclusionCriterionStatus(
            criterion_id="schema-freeze",
            status="failed" if schema_findings else "passed",
            evidence=["schemas/"],
            findings=schema_findings,
        ),
    ]
    blocking_findings = [
        f"{criterion.criterion_id}: {finding}"
        for criterion in criteria
        if criterion.required and criterion.status == "failed"
        for finding in (criterion.findings or ["criterion failed"])
    ]
    blocked = bool(blocking_findings)
    return ConclusionCertificationReport(
        release_id=release_id,
        result="blocked" if blocked else "certified",
        criteria=criteria,
        blocking_findings=blocking_findings,
        evidence_level_claims=[
            "BOUNDED_CHECKED means bounded model checking with recorded bounds.",
            "PROVEN_INDUCTIVE is unavailable unless a proof-producing backend emits it.",
            "Trace replay and runtime traces are grounding evidence, not theorem proofs.",
        ],
        known_limitations=[
            "Arbitrary natural language remains out of scope without controlled rewrite approval.",
            "Adapter certification does not prove semantic completeness for every program.",
        ],
    )


def _benchmark_findings(benchmark: BenchmarkEvaluationReport) -> list[str]:
    findings = []
    if benchmark.result != "passed":
        findings.append("benchmark evaluation did not pass")
    if benchmark.total_cases <= 0:
        findings.append("benchmark evaluation has no cases")
    failed_metrics = [metric.name for metric in benchmark.metrics if not metric.passed]
    if failed_metrics:
        findings.append(f"benchmark metrics failed: {', '.join(sorted(failed_metrics))}")
    return findings


def _reference_demo_findings(demo: ReferenceDemoReport) -> list[str]:
    findings = []
    if demo.requirement_count < 2:
        findings.append("reference demo must include at least two requirements")
    if not demo.has_accept_and_refuse:
        findings.append("reference demo must include accepted and refused requirements")
    if demo.command_count <= 0:
        findings.append("reference demo must declare reproducibility commands")
    if demo.missing_artifacts:
        findings.append(f"reference demo has missing artifacts: {', '.join(demo.missing_artifacts)}")
    if demo.decision_mismatches:
        findings.append(
            "reference demo has decision mismatches: "
            + ", ".join(sorted(demo.decision_mismatches))
        )
    if demo.unchecked_reports:
        findings.append(
            "reference demo has unchecked report artifacts: "
            + ", ".join(sorted(demo.unchecked_reports))
        )
    return findings


def _public_docs_findings(docs: PublicDocumentationIndex) -> list[str]:
    findings = []
    if not docs.docs:
        findings.append("public documentation index has no docs")
    if not docs.examples:
        findings.append("public documentation index has no examples")
    audiences = {doc.audience for doc in docs.docs}
    missing_audiences = sorted(set(REQUIRED_PUBLIC_AUDIENCES) - audiences)
    if missing_audiences:
        findings.append(f"public documentation is missing audiences: {', '.join(missing_audiences)}")
    docs_without_schema_refs = sorted(doc.doc_id for doc in docs.docs if not doc.schema_refs)
    if docs_without_schema_refs:
        findings.append(
            "public documentation entries lack schema references: "
            + ", ".join(docs_without_schema_refs)
        )
    examples_without_coverage = sorted(example.example_id for example in docs.examples if not example.covers)
    if examples_without_coverage:
        findings.append(
            "public SDK examples lack coverage tags: "
            + ", ".join(examples_without_coverage)
        )
    return findings
