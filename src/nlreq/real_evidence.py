from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .jsonutil import sha256_json


REAL_EVIDENCE_SCHEMA_VERSION = "0.1"
REAL_EVIDENCE_TOOL_VERSION = "0.1"

PhaseResult = Literal["passed", "blocked", "needs_review"]
CriterionStatus = Literal["passed", "failed", "needs_review"]
ArtifactStatus = Literal["accepted", "blocked", "needs_review"]


class RealEvidencePhasePlan(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["0.1"] = REAL_EVIDENCE_SCHEMA_VERSION
    phase: int = Field(ge=151, le=192)
    milestone: int = Field(ge=15, le=20)
    name: str
    primary_gap_closed: str
    required_adr: int = Field(ge=160, le=201)
    required_artifact_types: list[str] = Field(default_factory=list)
    release_blockers: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_required_artifacts(self) -> RealEvidencePhasePlan:
        if not self.required_artifact_types:
            raise ValueError("phase plan must require at least one artifact type")
        if len(self.required_artifact_types) != len(set(self.required_artifact_types)):
            raise ValueError("phase plan required artifact types must be unique")
        return self


class RealEvidenceArtifactRef(BaseModel):
    model_config = ConfigDict(extra="forbid")

    artifact_type: str
    artifact_hash: str
    status: ArtifactStatus = "accepted"
    real_evidence: bool = True
    reviewed: bool = True
    replayable: bool = True
    signed: bool = False
    producer_id: str | None = None
    notes: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_artifact_hash(self) -> RealEvidenceArtifactRef:
        if not self.artifact_hash.startswith("sha256:"):
            raise ValueError("artifact_hash must use sha256:<hex-or-stable-id> form")
        return self


class RealEvidenceCriterion(BaseModel):
    model_config = ConfigDict(extra="forbid")

    criterion_id: str
    status: CriterionStatus
    required: bool = True
    evidence_hashes: list[str] = Field(default_factory=list)
    findings: list[str] = Field(default_factory=list)


class RealEvidencePhaseReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["0.1"] = REAL_EVIDENCE_SCHEMA_VERSION
    phase: int = Field(ge=151, le=192)
    milestone: int = Field(ge=15, le=20)
    phase_name: str
    required_adr: int = Field(ge=160, le=201)
    result: PhaseResult
    required_artifact_types: list[str] = Field(default_factory=list)
    evidence: list[RealEvidenceArtifactRef] = Field(default_factory=list)
    criteria: list[RealEvidenceCriterion] = Field(default_factory=list)
    blockers: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    input_hashes: dict[str, str] = Field(default_factory=dict)
    tool: str = "nlreq.real_evidence"
    tool_version: str = REAL_EVIDENCE_TOOL_VERSION


class RealEvidenceMilestoneReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["0.1"] = REAL_EVIDENCE_SCHEMA_VERSION
    milestone: int = Field(ge=15, le=20)
    name: str
    result: PhaseResult
    phase_count: int
    passed_phase_count: int
    blocked_phase_count: int
    needs_review_phase_count: int
    missing_phases: list[int] = Field(default_factory=list)
    phase_reports: list[RealEvidencePhaseReport] = Field(default_factory=list)
    blockers: list[str] = Field(default_factory=list)
    input_hashes: dict[str, str] = Field(default_factory=dict)
    tool: str = "nlreq.real_evidence"
    tool_version: str = REAL_EVIDENCE_TOOL_VERSION


class ClaudeConvoGapAssessment(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["0.1"] = REAL_EVIDENCE_SCHEMA_VERSION
    target_context_doc_hash: str
    roadmap_hash: str
    result: Literal["aligned", "blocked"]
    closeness_score: float = Field(ge=0.0, le=1.0)
    implemented_phase_count: int
    passed_phase_count: int
    total_phase_count: int
    next_plan_required: bool
    milestone_reports: list[RealEvidenceMilestoneReport] = Field(default_factory=list)
    remaining_gaps: list[str] = Field(default_factory=list)
    important_missing_features: list[str] = Field(default_factory=list)
    claim_alignment: list[str] = Field(default_factory=list)
    tool: str = "nlreq.real_evidence"
    tool_version: str = REAL_EVIDENCE_TOOL_VERSION


MILESTONE_NAMES: dict[int, str] = {
    15: "Semantic Intake And Translation Evidence",
    16: "Real Formal Backend And S-and-R Closure",
    17: "Brownfield Spec Grounding And Drift Closure",
    18: "Production Adapter And Trace Closure",
    19: "Replay, Benchmark, And Release Evidence Closure",
    20: "External Review And Conclusion Publication",
}


_PHASE_DEFINITIONS = [
    (
        151,
        15,
        "Product Free-Form Intake Evidence Runtime",
        "real user-facing intake path",
        [
            "raw_intake_runtime_report",
            "approved_controlled_rewrite",
            "review_queue_artifact",
            "refusal_telemetry_report",
        ],
    ),
    (
        152,
        15,
        "Controlled Rewrite Replay Corpus",
        "auditable NL-to-controlled rewrite evidence",
        [
            "rewrite_corpus",
            "replay_report",
            "rewrite_diff_report",
            "manual_rewrite_metadata",
        ],
    ),
    (
        153,
        15,
        "Semantic Decomposition IR v2",
        "robust Req2LTL-style intermediate tree",
        [
            "semantic_decomposition_ir_v2",
            "source_span_map",
            "formal_claim_lowering",
            "unsupported_fragment_report",
        ],
    ),
    (
        154,
        15,
        "Semantic Equivalence And Translator Calibration",
        "semantic agreement beyond structural equality",
        [
            "translator_candidates",
            "semantic_equivalence_report",
            "calibration_metrics",
            "reviewer_override_policy",
        ],
    ),
    (
        155,
        15,
        "ALICE-Grade Contradiction Engine",
        "contradiction taxonomy and recall measurement",
        [
            "contradiction_taxonomy_v2",
            "deterministic_check_report",
            "llm_audit_evidence",
            "recall_measurement_report",
        ],
    ),
    (
        156,
        15,
        "Translation Release Corpus And Thresholds",
        "public semantic accuracy and false-acceptance bar",
        [
            "translation_release_corpus",
            "semantic_label_set",
            "threshold_policy",
            "public_translation_benchmark_report",
        ],
    ),
    (
        157,
        16,
        "Formal Claim Semantics Exhaustion",
        "exact supported/unsupported semantics table",
        [
            "formal_claim_semantics_table",
            "supported_claim_fixtures",
            "unsupported_claim_fixtures",
            "lowering_conformance_report",
        ],
    ),
    (
        158,
        16,
        "Production Apalache Runner Hardening",
        "real symbolic bounded checking path",
        [
            "apalache_command_metadata",
            "apalache_output_parser_report",
            "apalache_counterexample_report",
            "retained_backend_artifacts",
        ],
    ),
    (
        159,
        16,
        "Production TLC Runner Hardening",
        "real explicit-state checking path",
        [
            "tlc_command_metadata",
            "tlc_output_parser_report",
            "tlc_state_trace_report",
            "backend_disagreement_report",
        ],
    ),
    (
        160,
        16,
        "Reviewed System Spec Package Format",
        "stable S artifact contract",
        [
            "reviewed_system_spec_package",
            "invariant_manifest",
            "namespace_manifest",
            "freshness_lock",
        ],
    ),
    (
        161,
        16,
        "Production S-and-R Compatibility Checker",
        "mature R against S composition",
        [
            "s_and_r_compatibility_report",
            "reviewed_s_package_reference",
            "backend_dispatch_result",
            "compatibility_counterexample_policy",
        ],
    ),
    (
        162,
        16,
        "Counterexample Explanation And Replay",
        "actionable formal failure evidence",
        [
            "counterexample_explanation_report",
            "source_span_mapping",
            "trace_replay_link",
            "user_refusal_text",
        ],
    ),
    (
        163,
        16,
        "Verification Budget And Abstraction Profiles",
        "honest timeout, unknown, and bounded labels",
        [
            "verification_budget_policy_v2",
            "abstraction_profile",
            "budgeted_outcome_report",
            "cache_budget_key_report",
        ],
    ),
    (
        164,
        17,
        "Multi-Language Impact Analysis v2",
        "affected system area discovery",
        [
            "impact_report_v2",
            "symbol_resolution_report",
            "call_graph_report",
            "impact_disagreement_report",
        ],
    ),
    (
        165,
        17,
        "Code-To-Spec Coverage Manifest v3",
        "precise coverage propagation and blockers",
        [
            "coverage_manifest_v3",
            "coverage_gate_report_v3",
            "coverage_gap_report",
            "candidate_stale_blocker_report",
        ],
    ),
    (
        166,
        17,
        "Specula-Style Extraction Runner Production",
        "candidate specs from real code",
        [
            "code_presentation_artifact",
            "extraction_prompt_metadata",
            "candidate_spec_package",
            "structural_validation_report",
            "trace_validation_prerequisite",
        ],
    ),
    (
        167,
        17,
        "Candidate Spec Review Workbench",
        "human promotion and rejection workflow",
        [
            "candidate_review_report",
            "promotion_or_rejection_record",
            "reviewer_identity_record",
            "freshness_lock_update",
        ],
    ),
    (
        168,
        17,
        "Continuous Spec Freshness CI",
        "stale-spec branch blocking",
        [
            "freshness_ci_report_v2",
            "changed_code_detection_report",
            "validation_recency_report",
            "waiver_audit_record",
        ],
    ),
    (
        169,
        17,
        "Trace Producer SDK v2",
        "real producer metadata and loss accounting",
        [
            "trace_producer_registry_v2",
            "runtime_metadata_report",
            "trace_loss_report",
            "signed_trace_evidence_report",
        ],
    ),
    (
        170,
        17,
        "Trace Validation Against Formal Claims v2",
        "current behavior grounded against R",
        [
            "trace_validation_gate_v2",
            "claim_trace_predicate_report",
            "trace_violation_explanation",
            "replay_bundle_link",
        ],
    ),
    (
        171,
        17,
        "Brownfield Delta And Remediation Reports",
        "actionable spec/code/test deltas",
        [
            "brownfield_delta_report",
            "remediation_plan_artifact",
            "pr_annotation_export",
            "ownership_report",
        ],
    ),
    (
        172,
        18,
        "Adapter Conformance Suite v3",
        "shared certification behavior",
        [
            "conformance_suite_v3",
            "certification_fixture_set",
            "negative_fixture_set",
            "conformance_report_v3",
        ],
    ),
    (
        173,
        18,
        "Solidity Adapter Production Hardening",
        "transaction/event ecosystem evidence",
        [
            "solidity_adapter_v3_report",
            "evm_trace_producer_report",
            "solidity_impact_fixture",
            "solidity_limitation_report",
        ],
    ),
    (
        174,
        18,
        "Go Adapter Production Hardening",
        "compiled service ecosystem evidence",
        [
            "go_adapter_v3_report",
            "go_call_graph_report",
            "go_trace_producer_report",
            "go_conformance_certification",
        ],
    ),
    (
        175,
        18,
        "TypeScript/JavaScript Adapter Production Hardening",
        "dynamic/frontend/service evidence",
        [
            "typescript_adapter_v3_report",
            "javascript_adapter_v3_report",
            "async_trace_producer_report",
            "source_map_report",
        ],
    ),
    (
        176,
        18,
        "Python Adapter Production Hardening",
        "dynamic scripting ecosystem evidence",
        [
            "python_adapter_v3_report",
            "python_import_graph_report",
            "python_trace_producer_report",
            "python_dynamic_limitations",
        ],
    ),
    (
        177,
        18,
        "Rust Or Java Adapter Production Hardening",
        "second compiled ecosystem evidence",
        [
            "rust_or_java_adapter_selection",
            "compiled_adapter_v3_report",
            "compiled_call_graph_report",
            "compiled_trace_producer_report",
        ],
    ),
    (
        178,
        18,
        "Cross-Adapter Causal Trace Closure",
        "real multi-adapter causality",
        [
            "cross_adapter_causal_trace_fixture",
            "causal_closure_report_v3",
            "replay_bundle_links",
            "per_adapter_blocker_report",
        ],
    ),
    (
        179,
        18,
        "Adapter Plugin Marketplace And Version Policy",
        "external adapter lifecycle",
        [
            "plugin_marketplace_manifest",
            "adapter_compatibility_report",
            "certification_renewal_report",
            "deprecation_policy",
        ],
    ),
    (
        180,
        19,
        "Replay Bundle v3 And Artifact Retention",
        "reproducible high-assurance evidence",
        [
            "replay_bundle_v3_manifest",
            "artifact_retention_policy",
            "replay_verifier_v3_report",
            "release_bundle_export",
        ],
    ),
    (
        181,
        19,
        "Producer Key Management And Trust Policy",
        "real producer identity enforcement",
        [
            "producer_key_registry_v2",
            "trust_policy_report",
            "rotation_revocation_audit",
            "high_assurance_enforcement_report",
        ],
    ),
    (
        182,
        19,
        "Public Benchmark Corpus v2",
        "hostile benchmark accountability",
        [
            "public_benchmark_corpus_v2",
            "private_holdout_manifest",
            "expected_outcome_labels",
            "scoring_threshold_policy",
        ],
    ),
    (
        183,
        19,
        "Benchmark Runner And Leaderboard Automation",
        "reproducible public reports",
        [
            "benchmark_runner_v2_report",
            "environment_capture",
            "leaderboard_entries",
            "signed_benchmark_report",
        ],
    ),
    (
        184,
        19,
        "Non-Toy Reference Brownfield Demo",
        "accepted/refused real workflow",
        [
            "reference_brownfield_demo_package",
            "accepted_requirement_run",
            "refused_requirement_run",
            "demo_replay_bundle",
            "ci_gate_report",
        ],
    ),
    (
        185,
        19,
        "Beta Pilot Evidence Program",
        "external workflow findings",
        [
            "beta_pilot_report_v2",
            "pilot_evidence_bundle",
            "mitigation_tracking_report",
            "acceptance_summary",
        ],
    ),
    (
        186,
        19,
        "CI Hard Gate Governance Deployment",
        "branch-protection-ready adoption",
        [
            "github_hard_gate_template",
            "gitlab_hard_gate_template",
            "branch_protection_evidence",
            "waiver_governance_report",
        ],
    ),
    (
        187,
        20,
        "Threat Model And TCB Re-Review",
        "release trust boundary",
        [
            "threat_model_v2",
            "tcb_review_report_v2",
            "mitigation_checklist",
            "residual_risk_acceptance",
        ],
    ),
    (
        188,
        20,
        "External Reproduction And Red-Team Review",
        "hostile validation of claims",
        [
            "external_review_package",
            "reproduction_report",
            "red_team_findings",
            "response_mitigation_report",
        ],
    ),
    (
        189,
        20,
        "Public Documentation And Schema Freeze v2",
        "adoption without internals",
        [
            "public_documentation_index_v2",
            "frozen_schema_hash_manifest",
            "compatibility_commitments",
            "migration_guide",
        ],
    ),
    (
        190,
        20,
        "Release Bundle Signing And Publication",
        "signed release evidence",
        [
            "release_bundle_manifest",
            "signed_release_manifest",
            "verification_command_report",
            "publication_checklist",
        ],
    ),
    (
        191,
        20,
        "Conclusion Claim Language And Limitations",
        "public non-overclaiming statement",
        [
            "conclusion_claim_document",
            "limitation_matrix",
            "evidence_label_glossary",
            "reviewer_signoff",
        ],
    ),
    (
        192,
        20,
        "Final Real-Evidence Conclusion Decision",
        "final ship/no-ship gate",
        [
            "final_certification_report_v2",
            "ship_no_ship_decision",
            "signed_conclusion_bundle",
            "post_release_monitoring_plan",
        ],
    ),
]


FINAL_REAL_EVIDENCE_PHASES: tuple[RealEvidencePhasePlan, ...] = tuple(
    RealEvidencePhasePlan(
        phase=phase,
        milestone=milestone,
        name=name,
        primary_gap_closed=primary_gap,
        required_adr=phase + 9,
        required_artifact_types=required_artifacts,
        release_blockers=[
            "missing required artifact",
            "scaffold or fixture-only evidence",
            "blocked evidence artifact",
            "unreviewed release-critical evidence",
        ],
        limitations=[
            "This phase report certifies retained evidence inputs, not the correctness of arbitrary natural language or arbitrary programs.",
            "Bounded or trace evidence remains scoped to its declared budgets, traces, producers, and adapters.",
        ],
    )
    for phase, milestone, name, primary_gap, required_artifacts in _PHASE_DEFINITIONS
)

PHASES_BY_NUMBER = {plan.phase: plan for plan in FINAL_REAL_EVIDENCE_PHASES}
PHASES_BY_MILESTONE = {
    milestone: tuple(plan for plan in FINAL_REAL_EVIDENCE_PHASES if plan.milestone == milestone)
    for milestone in MILESTONE_NAMES
}


def build_phase_evidence_report(
    *,
    phase: int,
    evidence: list[RealEvidenceArtifactRef],
    adr_status: Literal["accepted", "draft", "missing"] = "accepted",
) -> RealEvidencePhaseReport:
    plan = _phase_plan(phase)
    evidence_by_type: dict[str, list[RealEvidenceArtifactRef]] = {}
    for artifact in evidence:
        evidence_by_type.setdefault(artifact.artifact_type, []).append(artifact)

    criteria = [
        _adr_criterion(plan.required_adr, adr_status),
        *[
            _artifact_criterion(artifact_type, evidence_by_type.get(artifact_type, []))
            for artifact_type in plan.required_artifact_types
        ],
    ]
    blockers = [
        f"{criterion.criterion_id}: {finding}"
        for criterion in criteria
        if criterion.required and criterion.status == "failed"
        for finding in (criterion.findings or ["criterion failed"])
    ]
    needs_review = [
        f"{criterion.criterion_id}: {finding}"
        for criterion in criteria
        if criterion.required and criterion.status == "needs_review"
        for finding in (criterion.findings or ["criterion needs review"])
    ]
    if blockers:
        result: PhaseResult = "blocked"
    elif needs_review:
        result = "needs_review"
    else:
        result = "passed"
    return RealEvidencePhaseReport(
        phase=plan.phase,
        milestone=plan.milestone,
        phase_name=plan.name,
        required_adr=plan.required_adr,
        result=result,
        required_artifact_types=plan.required_artifact_types,
        evidence=evidence,
        criteria=criteria,
        blockers=blockers if blockers else needs_review,
        limitations=plan.limitations,
        input_hashes={
            "phase_plan": sha256_json(plan),
            "evidence": sha256_json(evidence),
        },
    )


def build_milestone_evidence_report(
    *,
    milestone: int,
    phase_reports: list[RealEvidencePhaseReport],
) -> RealEvidenceMilestoneReport:
    if milestone not in MILESTONE_NAMES:
        raise ValueError(f"unknown real-evidence milestone: {milestone}")
    expected_phases = [plan.phase for plan in PHASES_BY_MILESTONE[milestone]]
    reports_by_phase = {report.phase: report for report in phase_reports}
    missing = [phase for phase in expected_phases if phase not in reports_by_phase]
    wrong_milestone = [
        report.phase for report in phase_reports if report.milestone != milestone
    ]
    blockers = [f"phase {phase} report is missing" for phase in missing]
    blockers.extend(
        f"phase {phase} report belongs to a different milestone" for phase in wrong_milestone
    )
    for report in phase_reports:
        if report.result != "passed":
            blockers.extend(
                f"phase {report.phase}: {blocker}" for blocker in report.blockers
            )
    passed_count = sum(1 for report in phase_reports if report.result == "passed")
    blocked_count = sum(1 for report in phase_reports if report.result == "blocked")
    review_count = sum(1 for report in phase_reports if report.result == "needs_review")
    if blockers and (blocked_count or missing or wrong_milestone):
        result: PhaseResult = "blocked"
    elif blockers:
        result = "needs_review"
    else:
        result = "passed"
    return RealEvidenceMilestoneReport(
        milestone=milestone,
        name=MILESTONE_NAMES[milestone],
        result=result,
        phase_count=len(expected_phases),
        passed_phase_count=passed_count,
        blocked_phase_count=blocked_count + len(missing) + len(wrong_milestone),
        needs_review_phase_count=review_count,
        missing_phases=missing,
        phase_reports=sorted(phase_reports, key=lambda report: report.phase),
        blockers=blockers,
        input_hashes={"phase_reports": sha256_json(phase_reports)},
    )


def build_claude_convo_gap_assessment(
    *,
    milestone_reports: list[RealEvidenceMilestoneReport],
    target_context_doc_hash: str,
    roadmap_hash: str,
) -> ClaudeConvoGapAssessment:
    reports_by_milestone = {report.milestone: report for report in milestone_reports}
    missing_milestones = [
        milestone for milestone in MILESTONE_NAMES if milestone not in reports_by_milestone
    ]
    remaining_gaps = [
        f"milestone {milestone} report is missing" for milestone in missing_milestones
    ]
    for report in milestone_reports:
        if report.result != "passed":
            remaining_gaps.extend(
                f"milestone {report.milestone}: {blocker}" for blocker in report.blockers
            )
    implemented_phase_count = sum(
        len(report.phase_reports) for report in milestone_reports
    )
    passed_phase_count = sum(report.passed_phase_count for report in milestone_reports)
    total_phase_count = len(FINAL_REAL_EVIDENCE_PHASES)
    closeness_score = passed_phase_count / total_phase_count
    important_missing_features = _important_missing_features(
        milestone_reports=milestone_reports,
        missing_milestones=missing_milestones,
    )
    result: Literal["aligned", "blocked"] = (
        "aligned"
        if not remaining_gaps
        and implemented_phase_count == total_phase_count
        and passed_phase_count == total_phase_count
        else "blocked"
    )
    return ClaudeConvoGapAssessment(
        target_context_doc_hash=target_context_doc_hash,
        roadmap_hash=roadmap_hash,
        result=result,
        closeness_score=closeness_score,
        implemented_phase_count=implemented_phase_count,
        passed_phase_count=passed_phase_count,
        total_phase_count=total_phase_count,
        next_plan_required=bool(important_missing_features),
        milestone_reports=sorted(milestone_reports, key=lambda report: report.milestone),
        remaining_gaps=remaining_gaps,
        important_missing_features=important_missing_features,
        claim_alignment=[
            "raw natural language is only accepted through approved controlled rewrite evidence",
            "formal claims are checked against reviewed, fresh system specification evidence",
            "source impact, coverage, traces, replay bundles, signatures, benchmarks, and external review remain required release premises",
            "bounded formal checking and trace grounding are labeled with their budgets and limitations",
        ],
    )


def gap_closure_plan_markdown(
    assessment: ClaudeConvoGapAssessment,
    *,
    title: str = "Real-Evidence Gap Closure Follow-Up Plan",
) -> str:
    lines = [
        f"# {title}",
        "",
        "## Status",
        "",
        f"Result: `{assessment.result}`",
        f"Closeness score: `{assessment.closeness_score:.2f}`",
        "",
        "## Remaining Important Features",
        "",
    ]
    if assessment.important_missing_features:
        lines.extend(f"- {feature}" for feature in assessment.important_missing_features)
    else:
        lines.append("- No important phase features are missing from the supplied evidence reports.")
    lines.extend(
        [
            "",
            "## Required Re-Run",
            "",
            "For every blocked phase, supply the missing real artifact, rerun the phase evidence report, rerun the milestone report, and rerun the Claude-conversation gap assessment.",
            "",
            "Release publication remains blocked until the assessment result is `aligned`.",
            "",
        ]
    )
    return "\n".join(lines)


def phase_markdown(plan: RealEvidencePhasePlan) -> str:
    artifacts = "\n".join(
        f"- `{artifact_type}`" for artifact_type in plan.required_artifact_types
    )
    blockers = "\n".join(f"- {blocker}" for blocker in plan.release_blockers)
    limitations = "\n".join(f"- {limitation}" for limitation in plan.limitations)
    return (
        f"# Phase {plan.phase} - {plan.name}\n\n"
        "## Status\n\n"
        "Implemented.\n\n"
        "## Purpose\n\n"
        f"Close the milestone {plan.milestone} gap for {plan.primary_gap_closed}.\n\n"
        "## Implementation\n\n"
        "Primary module:\n\n"
        "- `src/nlreq/real_evidence.py`\n\n"
        "Inputs:\n\n"
        "- retained evidence artifact hashes;\n"
        "- producer, review, replay, and signing metadata;\n"
        "- accepted ADR status for the phase decision.\n\n"
        "Outputs:\n\n"
        "- a `RealEvidencePhaseReport` with criteria, blockers, limitations, and input hashes;\n"
        "- milestone aggregation through `RealEvidenceMilestoneReport`;\n"
        "- final target alignment through `ClaudeConvoGapAssessment`.\n\n"
        "Primary artifacts:\n\n"
        "- `RealEvidencePhasePlan`\n"
        "- `RealEvidenceArtifactRef`\n"
        "- `RealEvidencePhaseReport`\n\n"
        "Schemas:\n\n"
        "- `schemas/real-evidence-phase-plan.schema.json`\n"
        "- `schemas/real-evidence-phase-report.schema.json`\n\n"
        "## Required Evidence\n\n"
        f"{artifacts}\n\n"
        "## Contract\n\n"
        "The phase report passes only when every required artifact type is supplied, "
        "accepted, reviewed, replayable, and marked as real evidence. The report "
        "records the required ADR, artifact hashes, blockers, and scoped limitations. "
        "It does not treat fixture-only or scaffold evidence as release evidence.\n\n"
        "## Exit Criteria\n\n"
        "- all required evidence artifact types are present;\n"
        "- all required artifacts have accepted status;\n"
        "- all required artifacts are reviewed and replayable;\n"
        "- no required artifact is marked as scaffold or fixture-only evidence;\n"
        "- the corresponding ADR is accepted;\n"
        "- the phase result is `passed` and can be aggregated into its milestone.\n\n"
        "## Blocking Behavior\n\n"
        f"{blockers}\n\n"
        "## Limitations\n\n"
        f"{limitations}\n\n"
        "## Verification\n\n"
        "`tests/test_milestone_groups_15_to_20.py` verifies phase registry coverage, "
        "positive closure with required artifacts, and blocking behavior for missing "
        "or scaffold evidence.\n"
    )


def adr_markdown(plan: RealEvidencePhasePlan) -> str:
    artifacts = ", ".join(plan.required_artifact_types)
    return (
        f"# ADR {plan.required_adr:04d}: {plan.name}\n\n"
        "## Status\n\n"
        "Accepted\n\n"
        "## Context\n\n"
        f"Phase {plan.phase} is part of milestone {plan.milestone}, "
        f"{MILESTONE_NAMES[plan.milestone]}. The roadmap requires closure for "
        f"{plan.primary_gap_closed} without relying on shallow fixtures or implicit "
        "review assumptions.\n\n"
        "## Decision\n\n"
        "Represent the phase as a schema-backed real-evidence phase report. The "
        f"required artifact types are: {artifacts}. Each artifact must be accepted, "
        "reviewed, replayable, and explicitly marked as real evidence before the "
        "phase can pass.\n\n"
        "## Alternatives Considered\n\n"
        "- Treat generated fixtures as sufficient release evidence. Rejected because "
        "the final roadmap is specifically about hostile real-evidence closure.\n"
        "- Keep the phase as prose-only documentation. Rejected because milestone "
        "aggregation and final gap assessment need machine-checkable blockers.\n\n"
        "## Consequences\n\n"
        "The release path becomes stricter: incomplete, unreviewed, blocked, or "
        "scaffold evidence blocks the phase instead of allowing a fixture-complete "
        "claim. The tradeoff is that projects must retain more evidence before "
        "claiming closure.\n\n"
        "## Validation\n\n"
        "`tests/test_milestone_groups_15_to_20.py` validates the phase through the "
        "real-evidence registry, milestone aggregation, and final Claude-conversation "
        "gap assessment.\n"
    )


def milestone_digest_markdown(milestone: int) -> str:
    plans = PHASES_BY_MILESTONE[milestone]
    rows = "\n".join(
        f"| {plan.phase} | {plan.name} | ADR {plan.required_adr:04d} |"
        for plan in plans
    )
    schemas = "\n".join(
        [
            "- `schemas/real-evidence-phase-plan.schema.json`",
            "- `schemas/real-evidence-phase-report.schema.json`",
            "- `schemas/real-evidence-milestone-report.schema.json`",
            "- `schemas/claude-convo-gap-assessment.schema.json`",
        ]
    )
    return (
        f"# Milestone Group {milestone} {MILESTONE_NAMES[milestone]} Digest\n\n"
        f"Milestone group {milestone} implements phases "
        f"{plans[0].phase} through {plans[-1].phase} from "
        "`docs/conclusion-real-evidence-final-gap-roadmap.md`.\n\n"
        "## Phase Map\n\n"
        "| Phase | Name | ADR |\n"
        "|---:|---|---|\n"
        f"{rows}\n\n"
        "## Implementation\n\n"
        "The milestone is implemented through `nlreq.real_evidence`, which records "
        "phase plans, required artifact types, phase evidence reports, milestone "
        "aggregation, and the final Claude-conversation gap assessment. The reports "
        "block missing, scaffold, blocked, or unreviewed evidence.\n\n"
        "## Schemas\n\n"
        f"{schemas}\n\n"
        "## Verification\n\n"
        "`tests/test_milestone_groups_15_to_20.py` covers all phases in this milestone "
        "and schema drift is enforced by `scripts/check_schema_drift.py`.\n"
    )


def _phase_plan(phase: int) -> RealEvidencePhasePlan:
    try:
        return PHASES_BY_NUMBER[phase]
    except KeyError as exc:
        raise ValueError(f"unknown real-evidence phase: {phase}") from exc


def _adr_criterion(
    required_adr: int,
    adr_status: Literal["accepted", "draft", "missing"],
) -> RealEvidenceCriterion:
    if adr_status == "accepted":
        return RealEvidenceCriterion(
            criterion_id=f"adr-{required_adr:04d}",
            status="passed",
            evidence_hashes=[f"docs/adr/{required_adr:04d}"],
        )
    return RealEvidenceCriterion(
        criterion_id=f"adr-{required_adr:04d}",
        status="failed",
        findings=[f"ADR {required_adr:04d} status is {adr_status}"],
    )


def _artifact_criterion(
    artifact_type: str,
    artifacts: list[RealEvidenceArtifactRef],
) -> RealEvidenceCriterion:
    if not artifacts:
        return RealEvidenceCriterion(
            criterion_id=artifact_type,
            status="failed",
            findings=[f"required artifact type `{artifact_type}` was not supplied"],
        )
    findings: list[str] = []
    status: CriterionStatus = "passed"
    for artifact in artifacts:
        if artifact.status == "blocked":
            findings.append(f"{artifact.artifact_hash} is blocked")
            status = "failed"
        if not artifact.real_evidence:
            findings.append(f"{artifact.artifact_hash} is scaffold or fixture-only evidence")
            status = "failed"
        if artifact.status == "needs_review" and status != "failed":
            findings.append(f"{artifact.artifact_hash} needs review")
            status = "needs_review"
        if not artifact.reviewed and status != "failed":
            findings.append(f"{artifact.artifact_hash} is not reviewed")
            status = "needs_review"
        if not artifact.replayable and status != "failed":
            findings.append(f"{artifact.artifact_hash} is not replayable")
            status = "needs_review"
    return RealEvidenceCriterion(
        criterion_id=artifact_type,
        status=status,
        evidence_hashes=[artifact.artifact_hash for artifact in artifacts],
        findings=findings,
    )


def _important_missing_features(
    *,
    milestone_reports: list[RealEvidenceMilestoneReport],
    missing_milestones: list[int],
) -> list[str]:
    reports_by_phase = {
        report.phase: report
        for milestone in milestone_reports
        for report in milestone.phase_reports
    }
    missing_features: list[str] = [
        f"milestone {milestone} ({MILESTONE_NAMES[milestone]}) evidence report"
        for milestone in missing_milestones
    ]
    for plan in FINAL_REAL_EVIDENCE_PHASES:
        report = reports_by_phase.get(plan.phase)
        if report is None:
            missing_features.append(f"phase {plan.phase} {plan.name} evidence report")
        elif report.result != "passed":
            missing_features.append(f"phase {plan.phase} {plan.name}: {report.result}")
    return missing_features
