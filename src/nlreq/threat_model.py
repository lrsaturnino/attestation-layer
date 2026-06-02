from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


THREAT_MODEL_SCHEMA_VERSION = "0.1"
THREAT_MODEL_TOOL_VERSION = "0.1"


class TcbComponent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    component_id: str
    category: Literal[
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
    trust_assumption: str
    failure_impact: str


class ThreatScenario(BaseModel):
    model_config = ConfigDict(extra="forbid")

    scenario_id: str
    threat: Literal[
        "spoofing",
        "tampering",
        "replay",
        "prompt_injection",
        "stale_spec",
        "forged_evidence",
        "malicious_adapter",
    ]
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
    tool: str = "nlreq.threat_model"
    tool_version: str = THREAT_MODEL_TOOL_VERSION


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
            component_id="ci-gate",
            category="ci_gate",
            trust_assumption="Downstream action enforcement uses the machine-readable gate result.",
            failure_impact="Rejected or unknown requirements can merge despite open proof.",
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
            affected_components=["translator"],
            mitigation="LLM output is untrusted and must pass deterministic parser, provenance, approval, and agreement gates.",
            residual_risk="Human reviewers can approve a misleading rewrite.",
            benchmark_required=True,
        ),
    ]
    return ThreatModelReport(
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
    )
