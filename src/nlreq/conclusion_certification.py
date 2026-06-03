from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from .artifact_store import ReplayVerificationReport
from .benchmark_reporting import (
    BenchmarkEvaluationReport,
    ExtendedBenchmarkEvaluationReport,
    PublicBenchmarkReleaseReport,
)
from .ci_pr_gate import ExtendedCiPrGateReport
from .cross_language import CrossLanguageProofObjectV2
from .end_to_end_gate import ExtendedEndToEndRequirementGateReport
from .jsonutil import sha256_json
from .policy_governance import CiPolicyGovernanceReportV2
from .public_sdk import REQUIRED_PUBLIC_AUDIENCES, PublicDocumentationIndex
from .public_sdk import PublicDocumentationFreezeReport
from .reference_demo import (
    ExtendedReferenceDemoReport,
    ReferenceBrownfieldPilotReport,
    ReferenceDemoReport,
)
from .threat_model import (
    ExtendedTcbReviewReport,
    ThreatModelReport,
    threat_model_release_findings,
)
from .verification_cache import ParallelDispatchPlan


CONCLUSION_CERTIFICATION_SCHEMA_VERSION = "0.1"
CONCLUSION_CERTIFICATION_TOOL_VERSION = "0.1"
EXTENDED_CONCLUSION_CERTIFICATION_SCHEMA_VERSION = "0.1"
FINAL_REAL_EVIDENCE_CERTIFICATION_SCHEMA_VERSION = "0.2"


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


class ExtendedConclusionCertificationReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["0.1"] = EXTENDED_CONCLUSION_CERTIFICATION_SCHEMA_VERSION
    release_id: str
    result: Literal["certified", "blocked"]
    criteria: list[ConclusionCriterionStatus] = Field(default_factory=list)
    blocking_findings: list[str] = Field(default_factory=list)
    release_bundle_hash: str | None = None
    signed_release_bundle_hash: str | None = None
    evidence_level_claims: list[str] = Field(default_factory=list)
    known_limitations: list[str] = Field(default_factory=list)
    input_hashes: dict[str, str] = Field(default_factory=dict)
    tool: str = "nlreq.conclusion_certification"
    tool_version: str = CONCLUSION_CERTIFICATION_TOOL_VERSION


class FinalRealEvidenceConclusionCertificationReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["0.2"] = FINAL_REAL_EVIDENCE_CERTIFICATION_SCHEMA_VERSION
    release_id: str
    result: Literal["certified", "blocked"]
    criteria: list[ConclusionCriterionStatus] = Field(default_factory=list)
    blocking_findings: list[str] = Field(default_factory=list)
    release_bundle_hash: str | None = None
    signed_release_bundle_hash: str | None = None
    public_claim: str
    public_claim_boundaries: list[str] = Field(default_factory=list)
    input_hashes: dict[str, str] = Field(default_factory=dict)
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


def build_extended_conclusion_certification_report(
    *,
    release_id: str,
    gate: ExtendedEndToEndRequirementGateReport,
    ci: ExtendedCiPrGateReport,
    benchmark: ExtendedBenchmarkEvaluationReport,
    demo: ExtendedReferenceDemoReport,
    docs: PublicDocumentationFreezeReport,
    tcb_review: ExtendedTcbReviewReport,
    schemas_frozen: bool,
    producer_evidence_present: bool,
    release_bundle_hash: str | None,
    signed_release_bundle_hash: str | None = None,
    require_signed_release_bundle: bool = True,
) -> ExtendedConclusionCertificationReport:
    criteria = [
        ConclusionCriterionStatus(
            criterion_id="extended-requirement-gate",
            status="failed" if _extended_gate_findings(gate) else "passed",
            evidence=[gate.base_gate_hash or ""],
            findings=_extended_gate_findings(gate),
        ),
        ConclusionCriterionStatus(
            criterion_id="ci-adoption",
            status="failed" if _ci_findings(ci) else "passed",
            evidence=[ci.stable_json_hash],
            findings=_ci_findings(ci),
        ),
        ConclusionCriterionStatus(
            criterion_id="extended-benchmark",
            status="failed" if _extended_benchmark_findings(benchmark) else "passed",
            evidence=[benchmark.base_report_hash],
            findings=_extended_benchmark_findings(benchmark),
        ),
        ConclusionCriterionStatus(
            criterion_id="reference-demo",
            status="failed" if _extended_demo_findings(demo) else "passed",
            evidence=[demo.base_demo_hash],
            findings=_extended_demo_findings(demo),
        ),
        ConclusionCriterionStatus(
            criterion_id="public-docs-freeze",
            status="failed" if docs.findings or docs.result != "passed" else "passed",
            evidence=[docs.coverage_report_hash],
            findings=(
                (["public documentation freeze did not pass"] if docs.result != "passed" else [])
                + docs.findings
            ),
        ),
        ConclusionCriterionStatus(
            criterion_id="tcb-review",
            status="failed" if tcb_review.findings or tcb_review.result != "complete" else "passed",
            evidence=[tcb_review.threat_model_hash],
            findings=(
                (["TCB review is not complete"] if tcb_review.result != "complete" else [])
                + tcb_review.findings
            ),
        ),
        ConclusionCriterionStatus(
            criterion_id="schema-freeze",
            status="passed" if schemas_frozen else "failed",
            evidence=["schemas/"],
            findings=[] if schemas_frozen else ["schema freeze evidence was not provided"],
        ),
        ConclusionCriterionStatus(
            criterion_id="producer-evidence",
            status="passed" if producer_evidence_present else "failed",
            evidence=["producer-registry"],
            findings=[] if producer_evidence_present else ["producer evidence validation was not provided"],
        ),
        ConclusionCriterionStatus(
            criterion_id="release-bundle",
            status="failed" if _release_bundle_findings(
                release_bundle_hash=release_bundle_hash,
                signed_release_bundle_hash=signed_release_bundle_hash,
                require_signed_release_bundle=require_signed_release_bundle,
            ) else "passed",
            evidence=[value for value in [release_bundle_hash, signed_release_bundle_hash] if value],
            findings=_release_bundle_findings(
                release_bundle_hash=release_bundle_hash,
                signed_release_bundle_hash=signed_release_bundle_hash,
                require_signed_release_bundle=require_signed_release_bundle,
            ),
        ),
    ]
    blocking_findings = [
        f"{criterion.criterion_id}: {finding}"
        for criterion in criteria
        if criterion.required and criterion.status == "failed"
        for finding in (criterion.findings or ["criterion failed"])
    ]
    return ExtendedConclusionCertificationReport(
        release_id=release_id,
        result="blocked" if blocking_findings else "certified",
        criteria=criteria,
        blocking_findings=blocking_findings,
        release_bundle_hash=release_bundle_hash,
        signed_release_bundle_hash=signed_release_bundle_hash,
        evidence_level_claims=[
            "Extended conclusion certifies only the declared artifact set.",
            "BOUNDED_CHECKED remains bounded evidence with recorded limits.",
            "TRACE_VALIDATED grounds observed behavior and is not an inductive proof.",
            "PROVEN_INDUCTIVE requires a proof-producing backend artifact.",
        ],
        known_limitations=[
            "Unsupported controlled-language fragments are refused or marked unknown.",
            "Reference demo coverage does not imply correctness for all brownfield systems.",
            "CI hard-gate adoption depends on the host platform enforcing machine-readable output.",
        ],
        input_hashes={
            "gate": sha256_json(gate),
            "ci": sha256_json(ci),
            "benchmark": sha256_json(benchmark),
            "demo": sha256_json(demo),
            "docs": sha256_json(docs),
            "tcb_review": sha256_json(tcb_review),
            "release_bundle_hash": sha256_json(release_bundle_hash),
            "signed_release_bundle_hash": sha256_json(signed_release_bundle_hash),
        },
    )


def build_final_real_evidence_conclusion_certification_report(
    *,
    release_id: str,
    cross_language: CrossLanguageProofObjectV2,
    replay: ReplayVerificationReport,
    dispatch: ParallelDispatchPlan,
    public_benchmark: PublicBenchmarkReleaseReport,
    reference_demo: ReferenceBrownfieldPilotReport,
    governance: CiPolicyGovernanceReportV2,
    schemas_frozen: bool,
    release_bundle_hash: str | None,
    signed_release_bundle_hash: str | None,
    scaffold_evidence_hashes: list[str] | None = None,
    public_claim: str = "Scoped real-evidence conclusion for supported requirements.",
) -> FinalRealEvidenceConclusionCertificationReport:
    scaffold_evidence_hashes = scaffold_evidence_hashes or []
    criteria = [
        _final_criterion(
            "cross-language-causal-proof",
            cross_language.closure_status == "closed" and cross_language.result == "accepted",
            [cross_language.proof_id],
            cross_language.blockers,
            "cross-language proof did not close",
        ),
        _final_criterion(
            "replay-and-signing",
            replay.result == "valid",
            replay.verified_artifact_hashes,
            replay.findings,
            "replay verification did not pass",
        ),
        _final_criterion(
            "performance-dispatch",
            dispatch.result == "ready" and dispatch.within_budget,
            [dispatch.plan_id],
            dispatch.findings,
            "performance dispatch plan is not ready",
        ),
        _final_criterion(
            "public-benchmark",
            public_benchmark.result == "publishable",
            [public_benchmark.suite_id],
            public_benchmark.findings,
            "public benchmark report is not publishable",
        ),
        _final_criterion(
            "reference-brownfield-demo",
            reference_demo.result == "accepted",
            [reference_demo.demo_id],
            reference_demo.blocking_findings,
            "reference brownfield demo was not accepted",
        ),
        _final_criterion(
            "ci-policy-governance",
            governance.result == "passed",
            [governance.governance_id],
            governance.findings,
            "CI policy governance did not pass",
        ),
        ConclusionCriterionStatus(
            criterion_id="schema-freeze",
            status="passed" if schemas_frozen else "failed",
            evidence=["schemas/"],
            findings=[] if schemas_frozen else ["schema freeze evidence was not provided"],
        ),
        ConclusionCriterionStatus(
            criterion_id="signed-release-bundle",
            status="passed" if release_bundle_hash and signed_release_bundle_hash else "failed",
            evidence=[value for value in [release_bundle_hash, signed_release_bundle_hash] if value],
            findings=_release_bundle_findings(
                release_bundle_hash=release_bundle_hash,
                signed_release_bundle_hash=signed_release_bundle_hash,
                require_signed_release_bundle=True,
            ),
        ),
        ConclusionCriterionStatus(
            criterion_id="no-scaffold-evidence",
            status="passed" if not scaffold_evidence_hashes else "failed",
            evidence=scaffold_evidence_hashes,
            findings=(
                []
                if not scaffold_evidence_hashes
                else ["final certification cannot include scaffold evidence"]
            ),
        ),
    ]
    blocking_findings = [
        f"{criterion.criterion_id}: {finding}"
        for criterion in criteria
        if criterion.required and criterion.status == "failed"
        for finding in (criterion.findings or ["criterion failed"])
    ]
    return FinalRealEvidenceConclusionCertificationReport(
        release_id=release_id,
        result="blocked" if blocking_findings else "certified",
        criteria=criteria,
        blocking_findings=blocking_findings,
        release_bundle_hash=release_bundle_hash,
        signed_release_bundle_hash=signed_release_bundle_hash,
        public_claim=public_claim,
        public_claim_boundaries=[
            "Only supported controlled requirements are covered.",
            "Bounded checking remains bounded and is not an inductive proof.",
            "Runtime traces ground observed behavior and do not prove all executions.",
            "Adapter certification covers declared capabilities and limitations.",
            "Generated candidate specs remain untrusted unless reviewed and promoted.",
        ],
        input_hashes={
            "cross_language": sha256_json(cross_language),
            "replay": sha256_json(replay),
            "dispatch": sha256_json(dispatch),
            "public_benchmark": sha256_json(public_benchmark),
            "reference_demo": sha256_json(reference_demo),
            "governance": sha256_json(governance),
            "schemas_frozen": sha256_json(schemas_frozen),
            "release_bundle_hash": sha256_json(release_bundle_hash),
            "signed_release_bundle_hash": sha256_json(signed_release_bundle_hash),
            "scaffold_evidence_hashes": sha256_json(scaffold_evidence_hashes),
        },
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


def _final_criterion(
    criterion_id: str,
    passed: bool,
    evidence: list[str],
    raw_findings: object,
    default_finding: str,
) -> ConclusionCriterionStatus:
    findings = _stringify_findings(raw_findings)
    if not passed and not findings:
        findings = [default_finding]
    return ConclusionCriterionStatus(
        criterion_id=criterion_id,
        status="passed" if passed else "failed",
        evidence=evidence,
        findings=findings,
    )


def _stringify_findings(raw_findings: object) -> list[str]:
    if raw_findings is None:
        return []
    if isinstance(raw_findings, list):
        values = raw_findings
    else:
        values = [raw_findings]
    rendered: list[str] = []
    for value in values:
        if isinstance(value, str):
            rendered.append(value)
        elif hasattr(value, "message"):
            rendered.append(str(getattr(value, "message")))
        else:
            rendered.append(str(value))
    return rendered


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


def _extended_gate_findings(gate: ExtendedEndToEndRequirementGateReport) -> list[str]:
    findings = []
    if gate.decision != "accepted":
        findings.append(f"extended gate decision is {gate.decision}")
    if not gate.downstream_action_allowed:
        findings.append("extended gate does not allow downstream action")
    if gate.missing_stage_count:
        findings.append(f"extended gate has {gate.missing_stage_count} missing stages")
    if gate.refused_stage_count:
        findings.append(f"extended gate has {gate.refused_stage_count} refused stages")
    if gate.unknown_stage_count:
        findings.append(f"extended gate has {gate.unknown_stage_count} unknown stages")
    return findings


def _ci_findings(ci: ExtendedCiPrGateReport) -> list[str]:
    findings = []
    if ci.mode != "hard_gate":
        findings.append("release certification requires hard_gate CI mode")
    if ci.result != "passed":
        findings.append(f"CI adoption result is {ci.result}")
    if ci.enforcement != "blocking":
        findings.append("CI enforcement is not blocking")
    findings.extend(f"CI blocked check: {check}" for check in ci.blocked_checks)
    findings.extend(f"CI missing check: {check}" for check in ci.missing_checks)
    return findings


def _extended_benchmark_findings(benchmark: ExtendedBenchmarkEvaluationReport) -> list[str]:
    findings = []
    if benchmark.result != "passed":
        findings.append("extended benchmark did not pass")
    if benchmark.missing_dimensions:
        findings.append(
            "extended benchmark missing dimensions: "
            + ", ".join(benchmark.missing_dimensions)
        )
    if benchmark.failed_dimensions:
        findings.append(
            "extended benchmark failed dimensions: "
            + ", ".join(benchmark.failed_dimensions)
        )
    return findings


def _extended_demo_findings(demo: ExtendedReferenceDemoReport) -> list[str]:
    findings = []
    if demo.result != "reproducible":
        findings.append("extended reference demo is not reproducible")
    if demo.missing_gate_reports:
        findings.append("demo missing gate reports: " + ", ".join(demo.missing_gate_reports))
    if demo.missing_replay_bundles:
        findings.append(
            "demo missing replay bundles: " + ", ".join(demo.missing_replay_bundles)
        )
    if demo.stage_failures:
        findings.append("demo stage failures: " + ", ".join(demo.stage_failures))
    if demo.decision_mismatches:
        findings.append("demo decision mismatches: " + ", ".join(demo.decision_mismatches))
    return findings


def _release_bundle_findings(
    *,
    release_bundle_hash: str | None,
    signed_release_bundle_hash: str | None,
    require_signed_release_bundle: bool,
) -> list[str]:
    findings = []
    if not release_bundle_hash:
        findings.append("release bundle hash was not provided")
    if require_signed_release_bundle and not signed_release_bundle_hash:
        findings.append("signed release bundle hash was not provided")
    return findings
