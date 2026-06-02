from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from .benchmark_reporting import BenchmarkEvaluationReport
from .public_sdk import PublicDocumentationIndex
from .reference_demo import ReferenceDemoReport
from .threat_model import ThreatModelReport


CONCLUSION_CERTIFICATION_SCHEMA_VERSION = "0.1"
CONCLUSION_CERTIFICATION_TOOL_VERSION = "0.1"


class ConclusionCriterionStatus(BaseModel):
    model_config = ConfigDict(extra="forbid")

    criterion_id: str
    status: Literal["passed", "failed", "scoped_out"]
    evidence: list[str] = Field(default_factory=list)
    limitation: str | None = None


class ConclusionCertificationReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["0.1"] = CONCLUSION_CERTIFICATION_SCHEMA_VERSION
    release_id: str
    result: Literal["certified", "blocked"]
    criteria: list[ConclusionCriterionStatus] = Field(default_factory=list)
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
    criteria = [
        ConclusionCriterionStatus(
            criterion_id="benchmark-evaluation",
            status="passed" if benchmark.result == "passed" else "failed",
            evidence=[benchmark.base_report_hash],
        ),
        ConclusionCriterionStatus(
            criterion_id="threat-model",
            status="passed" if threat_model.result == "complete" else "failed",
            evidence=[scenario.scenario_id for scenario in threat_model.scenarios],
        ),
        ConclusionCriterionStatus(
            criterion_id="reference-demo",
            status="passed" if demo.result == "reproducible" else "failed",
            evidence=[demo.demo_id],
        ),
        ConclusionCriterionStatus(
            criterion_id="public-docs",
            status="passed" if docs.docs and docs.examples else "failed",
            evidence=[entry.doc_id for entry in docs.docs],
        ),
        ConclusionCriterionStatus(
            criterion_id="schema-freeze",
            status="passed" if schemas_frozen else "failed",
            evidence=["schemas/"],
        ),
    ]
    blocked = any(item.status == "failed" for item in criteria)
    return ConclusionCertificationReport(
        release_id=release_id,
        result="blocked" if blocked else "certified",
        criteria=criteria,
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
