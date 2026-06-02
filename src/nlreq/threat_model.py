from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from .jsonutil import sha256_json


THREAT_MODEL_SCHEMA_VERSION = "0.1"
THREAT_MODEL_TOOL_VERSION = "0.1"
EXTENDED_TCB_REVIEW_SCHEMA_VERSION = "0.1"
TcbCategory = Literal[
    "parser",
    "ir_validator",
    "translator",
    "formal_backend",
    "source_adapter",
    "trace_producer",
    "artifact_store",
    "producer_registry",
    "ci_gate",
    "human_review",
]
ThreatKind = Literal[
    "spoofing",
    "tampering",
    "replay",
    "prompt_injection",
    "stale_spec",
    "forged_evidence",
    "malicious_adapter",
]
REQUIRED_TCB_CATEGORIES: tuple[str, ...] = (
    "parser",
    "ir_validator",
    "translator",
    "formal_backend",
    "source_adapter",
    "trace_producer",
    "artifact_store",
    "producer_registry",
    "ci_gate",
    "human_review",
)
REQUIRED_THREAT_KINDS: tuple[str, ...] = (
    "spoofing",
    "tampering",
    "replay",
    "prompt_injection",
    "stale_spec",
    "forged_evidence",
    "malicious_adapter",
)
REQUIRED_RELEASE_ARTIFACTS: tuple[str, ...] = (
    "extended_gate",
    "ci_gate",
    "benchmark",
    "reference_demo",
    "public_docs",
    "certification_bundle",
)


class TcbComponent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    component_id: str
    category: TcbCategory
    trust_assumption: str
    failure_impact: str


class ThreatScenario(BaseModel):
    model_config = ConfigDict(extra="forbid")

    scenario_id: str
    threat: ThreatKind
    affected_components: list[str] = Field(default_factory=list)
    mitigation: str
    residual_risk: str
    benchmark_required: bool = False


class ThreatModelReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["0.1"] = THREAT_MODEL_SCHEMA_VERSION
    result: Literal["complete", "needs_review"]
    tcb: list[TcbComponent] = Field(default_factory=list)
    scenarios: list[ThreatScenario] = Field(default_factory=list)
    security_checklist: list[str] = Field(default_factory=list)
    release_claims: list[str] = Field(default_factory=list)
    audit_findings: list[str] = Field(default_factory=list)
    tool: str = "nlreq.threat_model"
    tool_version: str = THREAT_MODEL_TOOL_VERSION


class ExtendedTcbReviewReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["0.1"] = EXTENDED_TCB_REVIEW_SCHEMA_VERSION
    result: Literal["complete", "needs_review"]
    threat_model_hash: str
    tcb_categories: list[str] = Field(default_factory=list)
    adversarial_assumptions: list[str] = Field(default_factory=list)
    evidence_attack_scenarios: list[str] = Field(default_factory=list)
    release_artifact_hashes: dict[str, str] = Field(default_factory=dict)
    missing_release_artifacts: list[str] = Field(default_factory=list)
    accepted_residual_risks: list[str] = Field(default_factory=list)
    findings: list[str] = Field(default_factory=list)
    input_hashes: dict[str, str] = Field(default_factory=dict)
    tool: str = "nlreq.threat_model"
    tool_version: str = THREAT_MODEL_TOOL_VERSION


def threat_model_release_findings(report: ThreatModelReport) -> list[str]:
    categories = {component.category for component in report.tcb}
    missing_categories = sorted(set(REQUIRED_TCB_CATEGORIES) - categories)
    findings = [
        f"missing TCB categories: {', '.join(missing_categories)}"
    ] if missing_categories else []

    component_ids = {component.component_id for component in report.tcb}
    unknown_refs = sorted(
        {
            component_id
            for scenario in report.scenarios
            for component_id in scenario.affected_components
            if component_id not in component_ids
        }
    )
    if unknown_refs:
        findings.append(f"scenario references unknown TCB components: {', '.join(unknown_refs)}")

    threat_kinds = {scenario.threat for scenario in report.scenarios}
    missing_threats = sorted(set(REQUIRED_THREAT_KINDS) - threat_kinds)
    if missing_threats:
        findings.append(f"missing threat scenarios: {', '.join(missing_threats)}")

    benchmark_threats = {scenario.threat for scenario in report.scenarios if scenario.benchmark_required}
    missing_benchmark_threats = sorted(set(REQUIRED_THREAT_KINDS) - benchmark_threats)
    if missing_benchmark_threats:
        findings.append(
            "missing benchmark-required threat scenarios: "
            + ", ".join(missing_benchmark_threats)
        )

    if not report.security_checklist:
        findings.append("security checklist is empty")
    if not report.release_claims:
        findings.append("release claim boundaries are empty")
    return findings


def build_extended_tcb_review_report(
    threat_model: ThreatModelReport,
    *,
    release_artifact_hashes: dict[str, str] | None = None,
    accepted_residual_risks: list[str] | None = None,
    required_release_artifacts: tuple[str, ...] | list[str] = REQUIRED_RELEASE_ARTIFACTS,
) -> ExtendedTcbReviewReport:
    release_artifact_hashes = release_artifact_hashes or {}
    accepted_residual_risks = accepted_residual_risks or []
    findings = threat_model_release_findings(threat_model)
    missing_release_artifacts = sorted(
        set(required_release_artifacts) - set(release_artifact_hashes)
    )
    if missing_release_artifacts:
        findings.append(
            "missing release artifact hashes: " + ", ".join(missing_release_artifacts)
        )
    residual_risks = [scenario.residual_risk for scenario in threat_model.scenarios]
    unaccepted_risks = sorted(set(residual_risks) - set(accepted_residual_risks))
    if unaccepted_risks:
        findings.append("unaccepted residual risks remain: " + str(len(unaccepted_risks)))
    return ExtendedTcbReviewReport(
        result="needs_review" if findings else "complete",
        threat_model_hash=sha256_json(threat_model),
        tcb_categories=sorted({component.category for component in threat_model.tcb}),
        adversarial_assumptions=[
            component.trust_assumption for component in threat_model.tcb
        ],
        evidence_attack_scenarios=[
            scenario.scenario_id
            for scenario in threat_model.scenarios
            if scenario.threat in {"forged_evidence", "tampering", "replay", "malicious_adapter"}
        ],
        release_artifact_hashes=release_artifact_hashes,
        missing_release_artifacts=missing_release_artifacts,
        accepted_residual_risks=accepted_residual_risks,
        findings=findings,
        input_hashes={
            "threat_model": sha256_json(threat_model),
            "release_artifact_hashes": sha256_json(release_artifact_hashes),
            "accepted_residual_risks": sha256_json(accepted_residual_risks),
        },
    )


def build_default_threat_model() -> ThreatModelReport:
    components = [
        TcbComponent(
            component_id="controlled-parser",
            category="parser",
            trust_assumption="Parser implements the accepted controlled grammar deterministically.",
            failure_impact="Requirement meaning can be misrepresented before formal checks.",
        ),
        TcbComponent(
            component_id="ir-validator",
            category="ir_validator",
            trust_assumption="Schema validation rejects malformed or adapter-specific semantic IR.",
            failure_impact="Invalid IR can enter proof dispatch.",
        ),
        TcbComponent(
            component_id="translator-workbench",
            category="translator",
            trust_assumption="Translator output is untrusted until deterministic agreement, approval, and parsing succeed.",
            failure_impact="Ambiguous or injected natural language can be accepted as a different requirement.",
        ),
        TcbComponent(
            component_id="formal-backends",
            category="formal_backend",
            trust_assumption="Backend wrappers faithfully record command, bounds, versions, and outcomes.",
            failure_impact="False closure if a failed or bounded check is mislabeled.",
        ),
        TcbComponent(
            component_id="source-adapters",
            category="source_adapter",
            trust_assumption="Adapters report unsupported, ambiguous, and missing symbols explicitly.",
            failure_impact="Affected code can be omitted from proof scope.",
        ),
        TcbComponent(
            component_id="trace-producers",
            category="trace_producer",
            trust_assumption="Registered producers emit complete normalized traces for their declared runtime.",
            failure_impact="Trace replay can validate stale or incomplete observations.",
        ),
        TcbComponent(
            component_id="artifact-store",
            category="artifact_store",
            trust_assumption="Stored artifacts are addressed by content hash and retained for replay.",
            failure_impact="Reports can reference evidence that cannot be reproduced.",
        ),
        TcbComponent(
            component_id="producer-registry",
            category="producer_registry",
            trust_assumption="Producer identity and high-assurance eligibility are loaded from reviewed key registries.",
            failure_impact="Forged or low-assurance evidence can be accepted as release evidence.",
        ),
        TcbComponent(
            component_id="ci-gate",
            category="ci_gate",
            trust_assumption="Downstream action enforcement uses the machine-readable gate result.",
            failure_impact="Rejected or unknown requirements can merge despite open proof.",
        ),
        TcbComponent(
            component_id="human-review",
            category="human_review",
            trust_assumption="Humans review controlled rewrites, waivers, specs, and release limitations before approval.",
            failure_impact="A misleading rewrite, stale spec, or unsafe waiver can be accepted despite tool warnings.",
        ),
    ]
    scenarios = [
        ThreatScenario(
            scenario_id="TM-001",
            threat="forged_evidence",
            affected_components=["formal-backends", "producer-registry", "artifact-store"],
            mitigation="Require registered producers, artifact hashes, and signed envelopes in high-assurance mode.",
            residual_risk="Local low-assurance developer mode can still produce unsigned evidence labels.",
            benchmark_required=True,
        ),
        ThreatScenario(
            scenario_id="TM-002",
            threat="stale_spec",
            affected_components=["source-adapters", "formal-backends"],
            mitigation="Spec freshness lockfile and registry status block closure on stale hashes.",
            residual_risk="Incorrect module-to-spec mapping remains a review responsibility.",
            benchmark_required=True,
        ),
        ThreatScenario(
            scenario_id="TM-003",
            threat="malicious_adapter",
            affected_components=["source-adapters", "trace-producers"],
            mitigation="Adapter certification and trace producer registration expose adapter identity and unsupported outcomes.",
            residual_risk="A certified adapter can still contain semantic bugs not covered by fixtures.",
            benchmark_required=True,
        ),
        ThreatScenario(
            scenario_id="TM-004",
            threat="prompt_injection",
            affected_components=["translator-workbench", "controlled-parser", "human-review"],
            mitigation="LLM output is untrusted and must pass deterministic parser, provenance, approval, and agreement gates.",
            residual_risk="Human reviewers can approve a misleading rewrite.",
            benchmark_required=True,
        ),
        ThreatScenario(
            scenario_id="TM-005",
            threat="spoofing",
            affected_components=["producer-registry", "ci-gate"],
            mitigation="Bind producer ids to reviewed keys and verify machine-readable CI inputs before action gates.",
            residual_risk="A trusted producer key can still be compromised outside the attestation layer.",
            benchmark_required=True,
        ),
        ThreatScenario(
            scenario_id="TM-006",
            threat="tampering",
            affected_components=["artifact-store", "formal-backends", "ci-gate"],
            mitigation="Hash-link retained artifacts and re-check content hashes during lookup and certification.",
            residual_risk="Tampering before hash capture remains in scope for producer validation and command metadata review.",
            benchmark_required=True,
        ),
        ThreatScenario(
            scenario_id="TM-007",
            threat="replay",
            affected_components=["artifact-store", "producer-registry", "ci-gate"],
            mitigation="Include input hashes, tool versions, policy hashes, and release ids in evidence and cache keys.",
            residual_risk="A replayed valid artifact can still be misleading if reviewers ignore scoped limitations.",
            benchmark_required=True,
        ),
    ]
    report = ThreatModelReport(
        result="complete",
        tcb=components,
        scenarios=scenarios,
        security_checklist=[
            "High-assurance evidence has producer validation and signature status.",
            "All retained artifacts resolve by content hash.",
            "Stale specs and missing traces block closure.",
            "Prompt-derived text cannot bypass controlled approval.",
            "CI gate enforces the machine-readable result, not Markdown text.",
        ],
        release_claims=[
            "Conclusion certification covers the released artifact set and declared adapters only.",
            "Bounded model-checking evidence is labeled separately from inductive proof evidence.",
            "Human-approved waivers and residual risks remain visible in release evidence.",
        ],
    )
    findings = threat_model_release_findings(report)
    return report.model_copy(
        update={
            "result": "needs_review" if findings else "complete",
            "audit_findings": findings,
        }
    )
