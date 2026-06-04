from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from .coverage_alignment import build_spec_coverage_report, build_trace_alignment_report
from .delta_extractor import build_delta_report
from .dsl_v2 import DslV2Parser
from .formal_backend import FormalBackendBudget, FormalBackendExecution
from .formal_claim import (
    FormalClaimLoweringReport,
    build_formal_claim,
    build_proof_dispatch_plan_from_formal_claim,
)
from .formal_claim_smt import smt_check_formal_claim_predicate_fragments
from .impact import analyze_source_impact
from .source_impact import analyze_source_impact_with_context
from .jsonutil import sha256_json, sha256_text, write_json
from .models import BackendResult, RequirementIRV2, SourceSpan
from .proof_closure import (
    BackendAgreementReport,
    EvidenceProducerMapping,
    ProofObject,
    SpecCoverageReport,
    TraceAlignmentReport,
    backend_results_from_system_consistency,
    build_proof_object,
    evaluate_closure_gate,
)
from .requirement_self_consistency import check_requirement_self_consistency
from .source_adapter import SourceLanguageAdapter, SourceManifest
from .system_checker import check_system_consistency, check_solver_backed_system_consistency
from .system_spec import SystemSpecRegistry
from .trace_replay import build_trace_replay_report
from .translator import lower_ir_v2_to_tla
from .semantic_translation import refuse_ambiguous_ensemble, remap_disagreement_spans_to_original
from .translator_agreement import (
    TranslationAgreementInput,
    TranslationCandidate,
    build_translation_agreement_report,
)


END_TO_END_GATE_SCHEMA_VERSION = "0.1"
EXTENDED_END_TO_END_GATE_SCHEMA_VERSION = "0.1"
EXTENDED_GATE_TOOL_VERSION = "0.1"

EXTENDED_GATE_REQUIRED_STAGES: tuple[str, ...] = (
    "controlled_intake",
    "semantic_translation",
    "formal_claim",
    "requirement_self_consistency",
    "s_and_r_composition",
    "spec_freshness",
    "trace_validation",
    "adapter_evidence",
    "proof_closure",
    "release_action_gate",
)

_EXTENDED_STAGE_ACCEPTED_STATUSES: dict[str, set[str]] = {
    "controlled_intake": {"approved", "passed"},
    "semantic_translation": {"accepted", "agreed", "passed"},
    "formal_claim": {"lowered", "passed"},
    "requirement_self_consistency": {"valid", "passed"},
    "s_and_r_composition": {"valid", "passed"},
    "spec_freshness": {"fresh", "passed"},
    "trace_validation": {"passed", "satisfied"},
    "adapter_evidence": {"certified", "passed"},
    "proof_closure": {"closed", "passed"},
    "release_action_gate": {"passed"},
}

_EXTENDED_STAGE_UNKNOWN_STATUSES: set[str] = {
    "unknown",
    "needs_review",
    "unsupported",
    "timeout",
    "tool_error",
    "missing",
}


class EndToEndGateArtifactRef(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    path: str
    content_hash: str


class EndToEndGateBlocker(BaseModel):
    model_config = ConfigDict(extra="forbid")

    stage: str
    status: str
    message: str
    source_spans: list[SourceSpan] = Field(default_factory=list)


class EndToEndRequirementGateReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["0.1"] = END_TO_END_GATE_SCHEMA_VERSION
    requirement_id: str
    decision: Literal["accepted", "refused", "unknown"]
    downstream_action: str
    downstream_action_allowed: bool
    proof_status: Literal["closed", "open", "blocked"]
    closure_result: Literal["passed", "blocked"]
    artifacts: list[EndToEndGateArtifactRef] = Field(default_factory=list)
    statuses: dict[str, str] = Field(default_factory=dict)
    blockers: list[EndToEndGateBlocker] = Field(default_factory=list)


class ExtendedGateStageResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    stage: str
    raw_status: str | None = None
    status: Literal["passed", "refused", "unknown", "missing"]
    required: bool = True
    artifact_hash: str | None = None
    artifact_path: str | None = None
    evidence_level: str | None = None
    refusal_code: str | None = None
    message: str


class ExtendedEndToEndRequirementGateReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["0.1"] = EXTENDED_END_TO_END_GATE_SCHEMA_VERSION
    requirement_id: str
    pipeline_profile: Literal["extended_conclusion"] = "extended_conclusion"
    artifact_layout_version: Literal["extended-release-v1"] = "extended-release-v1"
    decision: Literal["accepted", "refused", "unknown"]
    downstream_action: str
    downstream_action_allowed: bool
    base_gate_hash: str | None = None
    required_stage_count: int = 0
    passed_stage_count: int = 0
    refused_stage_count: int = 0
    unknown_stage_count: int = 0
    missing_stage_count: int = 0
    stages: list[ExtendedGateStageResult] = Field(default_factory=list)
    blockers: list[EndToEndGateBlocker] = Field(default_factory=list)
    refusal_summary: list[str] = Field(default_factory=list)
    input_hashes: dict[str, str] = Field(default_factory=dict)
    tool: str = "nlreq.end_to_end_gate"
    tool_version: str = EXTENDED_GATE_TOOL_VERSION


ExtendedRequirementGateReport = ExtendedEndToEndRequirementGateReport


def build_proof_with_formal_claim_dispatch(
    *,
    requirement: RequirementIRV2,
    backend_results: list[BackendResult],
    coverage: SpecCoverageReport | None = None,
    trace_alignment: TraceAlignmentReport | None = None,
    backend_agreement: BackendAgreementReport | None = None,
    producer_mapping: EvidenceProducerMapping | None = None,
) -> tuple[ProofObject, FormalClaimLoweringReport]:
    """Build a ProofObject using FormalClaim-derived dispatch when the claim class is supported.

    When build_formal_claim returns 'lowered', the dispatch plan carries formal fragment IDs
    so ProofObject.premises[*].premise_id maps to FormalClaim fragments rather than raw
    semantic node IDs. When the claim class is unsupported (result='refused'), falls back to
    the default semantic-node dispatch — equivalent to calling build_proof_object directly.

    This is the production entry point that gates and tests should use to ensure FormalClaim
    dispatch is exercised through a real code path, not only in test-only manual dispatch.
    """
    formal_claim_report = build_formal_claim(requirement)
    dispatch = (
        build_proof_dispatch_plan_from_formal_claim(formal_claim_report.formal_claim)
        if formal_claim_report.result == "lowered" and formal_claim_report.formal_claim is not None
        else None
    )
    proof = build_proof_object(
        requirement=requirement,
        backend_results=backend_results,
        coverage=coverage,
        trace_alignment=trace_alignment,
        backend_agreement=backend_agreement,
        producer_mapping=producer_mapping,
        dispatch=dispatch,
    )
    return proof, formal_claim_report


def run_end_to_end_requirement_gate(
    *,
    controlled_text: str,
    requirement_id: str,
    title: str,
    source_adapter: SourceLanguageAdapter,
    source_manifest: SourceManifest,
    symbols: list[str],
    registry: SystemSpecRegistry,
    project_root: Path,
    artifact_dir: Path,
    downstream_action: str = "merge",
    self_check_backend: str = "tla-runner",
    budget: FormalBackendBudget | None = None,
    execution: FormalBackendExecution | None = None,
    solver_execution: FormalBackendExecution | None = None,
    requirement_ir: RequirementIRV2 | None = None,
    translation_agreement: TranslationAgreementInput | None = None,
) -> EndToEndRequirementGateReport:
    """Run the full end-to-end requirement gate.

    When requirement_ir is provided, the gate skips the DslV2Parser parse step and
    uses the supplied IR directly. This enables callers holding a DSL v3 or
    otherwise pre-parsed RequirementIRV2 to exercise the full gate including
    FormalClaim dispatch without re-encoding through the v2 DSL parser.

    When translation_agreement is provided, the gate uses the supplied
    TranslationAgreementInput instead of constructing its own candidates. When
    the resulting report status is "disagreed", the gate records a
    SemanticTranslationReport with refusal_code NLR-REFUSED-AMBIGUOUS and
    adds a blocker so the gate decision is "refused".

    `execution` controls the self-consistency formal backend (TLA runner or custom).
    `solver_execution` controls the solver-backed S∧R check (e.g. checker_id="z3").
    When only `execution` is supplied and it has a checker_id, it drives both paths
    (legacy behaviour). When both are supplied, `solver_execution` is used exclusively
    for `check_solver_backed_system_consistency`.
    """
    artifact_dir.mkdir(parents=True, exist_ok=True)
    artifacts: list[EndToEndGateArtifactRef] = []

    def record(name: str, filename: str, value) -> None:
        path = artifact_dir / filename
        write_json(path, value)
        artifacts.append(
            EndToEndGateArtifactRef(
                name=name,
                path=path.as_posix(),
                content_hash=sha256_json(value),
            )
        )

    if requirement_ir is not None:
        requirement = requirement_ir
    else:
        parser = DslV2Parser()
        requirement = parser.parse_ir(controlled_text, requirement_id=requirement_id, title=title)

    if translation_agreement is not None:
        # Use the caller-supplied multi-candidate input for real ensemble comparison.
        translation_input = translation_agreement
    elif requirement_ir is not None:
        # Single-source IR: no independent second candidate available.
        translation_input = TranslationAgreementInput(
            candidates=[
                TranslationCandidate(
                    translator_id="provided-ir-single-source",
                    method="deterministic",
                    requirement=requirement,
                    provenance={"source": "caller_provided_ir"},
                ),
            ]
        )
    else:
        # Two independent parse invocations of the same deterministic DSL v2 text.
        # These will always agree for a deterministic parser, but they are genuinely
        # separate calls — not the same object reference duplicated.
        reparsed = DslV2Parser().parse_ir(
            controlled_text, requirement_id=requirement_id, title=title
        )
        translation_input = TranslationAgreementInput(
            candidates=[
                TranslationCandidate(
                    translator_id="dsl-v2-primary",
                    method="deterministic",
                    requirement=requirement,
                    provenance={"source": "end_to_end_gate"},
                ),
                TranslationCandidate(
                    translator_id="dsl-v2-reparse",
                    method="deterministic",
                    requirement=reparsed,
                    provenance={"source": "end_to_end_gate"},
                ),
            ]
        )
    record("requirement_ir", "requirement.ir.json", requirement)
    record("translation_agreement_input", "translation-agreement-input.json", translation_input)
    translation = build_translation_agreement_report(translation_input)
    record("translation_agreement", "translation-agreement.json", translation)

    if translation.status == "disagreed":
        gate_input_hashes = {
            "controlled_text": sha256_text(controlled_text),
            "requirement_ir": sha256_json(requirement),
        }
        remapped_disagreements = remap_disagreement_spans_to_original(
            translation.disagreements, requirement
        )
        ambiguous_refusal = refuse_ambiguous_ensemble(
            requirement_id=requirement_id,
            translation_id=f"gate-translation-{requirement_id}",
            disagreements=remapped_disagreements,
            requirement_ir=requirement,
            input_hashes=gate_input_hashes,
        )
        record("translation_refusal", "translation-refusal.json", ambiguous_refusal)
        # A disagreed translation is a hard stop — downstream stages (lowering, SMT,
        # traces, system check, proof, closure) must not run against an untrusted IR.
        return EndToEndRequirementGateReport(
            requirement_id=requirement_id,
            decision="refused",
            downstream_action=downstream_action,
            downstream_action_allowed=False,
            proof_status="blocked",
            closure_result="blocked",
            artifacts=artifacts,
            statuses={"translation_agreement": translation.status},
            blockers=[
                EndToEndGateBlocker(
                    stage="translation_agreement",
                    status="refused",
                    message=f"translation_agreement status is {translation.status}; expected agreed",
                )
            ],
        )

    lowered = lower_ir_v2_to_tla(requirement)
    record("lowered_formal", "lowered-formal.json", lowered)

    self_consistency = check_requirement_self_consistency(
        requirement,
        backend_id=self_check_backend,
        budget=budget,
        execution=execution,
    )
    record("requirement_self_consistency", "requirement-self-consistency.json", self_consistency)

    traces = source_adapter.extract_traces(source_manifest)
    record("normalized_traces", "normalized-traces.json", traces)

    impact = analyze_source_impact(source_adapter, source_manifest, symbols=symbols)
    record("source_impact", "source-impact.json", impact)

    impact_context = analyze_source_impact_with_context(
        source_adapter,
        source_manifest,
        symbols=symbols,
        traces=traces,
    )
    record("source_impact_context", "source-impact-context.json", impact_context)

    coverage = build_spec_coverage_report(
        impact=impact,
        registry=registry,
        project_root=project_root,
    )
    record("spec_coverage", "spec-coverage.json", coverage)

    trace_alignment = build_trace_alignment_report(
        requirement=requirement,
        traces=traces,
        coverage=coverage,
    )
    record("trace_alignment", "trace-alignment.json", trace_alignment)

    trace_replay = build_trace_replay_report(
        requirement=requirement,
        traces=traces,
        coverage=coverage,
    )
    record("trace_replay", "trace-replay.json", trace_replay)

    system_consistency = check_system_consistency(
        requirement=requirement,
        lowered=lowered,
        registry=registry,
        impact=impact,
        project_root=project_root,
    )
    record("system_consistency", "system-consistency.json", system_consistency)

    # When a solver execution is available, run the solver-backed S∧R check as additional
    # evidence alongside the marker-based result.  `solver_execution` takes priority; if
    # not supplied, fall back to `execution` when it carries a checker_id (legacy mode).
    # A counterexample/invalid from the solver is load-bearing: it blocks the gate even
    # when the marker check passes (safety direction).
    _effective_solver_exec = solver_execution or (
        execution if execution is not None and execution.checker_id else None
    )
    solver_system_result: list[BackendResult] = []
    if _effective_solver_exec is not None:
        solver_consistency = check_solver_backed_system_consistency(
            requirement=requirement,
            lowered=lowered,
            registry=registry,
            impact=impact,
            project_root=project_root,
            budget=budget,
            execution=_effective_solver_exec,
        )
        record("solver_system_consistency", "solver-system-consistency.json", solver_consistency)
        solver_system_result = [solver_consistency.result]

    delta = build_delta_report(
        self_consistency=self_consistency,
        system_consistency=system_consistency,
        spec_coverage=coverage,
        trace_replay=trace_replay,
    )
    record("delta_report", "delta-report.json", delta)

    system_backend_results = backend_results_from_system_consistency(system_consistency)
    # When the FormalClaim report is lowered, also SMT-check predicate/comparison
    # fragments. These produce core_smt BackendResults with covered_fragment_ids so
    # formal_claim-routed premises can be discharged without relying on the system-
    # consistency result (which only covers system_checker routes).
    formal_claim_preview = build_formal_claim(requirement)
    if formal_claim_preview.result == "lowered" and formal_claim_preview.formal_claim is not None:
        smt_fragment_results = smt_check_formal_claim_predicate_fragments(
            formal_claim_preview.formal_claim
        )
        # Enrich solver result with covered_fragment_ids for provenance traceability.
        # The solver's S∧R check operates at requirement level and covers all predicate/
        # obligation fragments — recording the IDs makes the scope explicit in the ProofObject.
        # This does NOT change route matching: predicate fragments route to core_smt/apalache
        # (formal_claim mode requires an exact backend match), so they remain blocked until
        # a real Apalache run discharges them.
        if solver_system_result and formal_claim_preview.formal_claim is not None:
            all_fragment_ids = [
                f.fragment_id
                for f in [
                    *formal_claim_preview.formal_claim.premises,
                    *formal_claim_preview.formal_claim.obligations,
                ]
            ]
            solver_system_result = [
                r.model_copy(update={"details": {**r.details, "covered_fragment_ids": all_fragment_ids}})
                for r in solver_system_result
            ]
    else:
        smt_fragment_results = []
    all_backend_results = [*system_backend_results, *solver_system_result, *smt_fragment_results]

    proof, formal_claim_report = build_proof_with_formal_claim_dispatch(
        requirement=requirement,
        backend_results=all_backend_results,
        coverage=coverage,
        trace_alignment=trace_alignment,
    )
    record("formal_claim_artifact", "formal-claim.json", formal_claim_report)
    record("proof_object", "proof-object.json", proof)

    closure = evaluate_closure_gate(proof, downstream_action=downstream_action)
    record("closure_gate", "closure-gate.json", closure)

    statuses = {
        "translation_agreement": translation.status,
        "requirement_self_consistency": self_consistency.status,
        "source_impact": "completed",
        "source_impact_context": "completed",
        "spec_coverage": coverage.result,
        "trace_alignment": trace_alignment.result,
        "trace_replay": trace_replay.result,
        "system_consistency": system_consistency.result.status,
        "formal_claim": formal_claim_report.result,
        "delta_report": "completed",
        "proof_object": proof.status,
        "closure_gate": closure.result,
    }
    solver_status_for_blocker: str | None = None
    if solver_system_result:
        solver_status_for_blocker = solver_system_result[0].status
        statuses["solver_system_consistency"] = solver_status_for_blocker
    blockers = _blockers(
        translation_status=translation.status,
        self_consistency_status=self_consistency.status,
        coverage_result=coverage.result,
        trace_alignment_result=trace_alignment.result,
        trace_replay_result=trace_replay.result,
        system_status=system_consistency.result.status,
        proof_status=proof.status,
        closure_result=closure.result,
        solver_system_status=solver_status_for_blocker,
    )
    decision = _decision(blockers)
    return EndToEndRequirementGateReport(
        requirement_id=requirement_id,
        decision=decision,
        downstream_action=downstream_action,
        downstream_action_allowed=decision == "accepted",
        proof_status=proof.status,
        closure_result=closure.result,
        artifacts=artifacts,
        statuses=statuses,
        blockers=blockers,
    )


def build_extended_requirement_gate_report(
    gate: EndToEndRequirementGateReport,
    *,
    required_stages: tuple[str, ...] | list[str] = EXTENDED_GATE_REQUIRED_STAGES,
    stage_statuses: dict[str, str] | None = None,
    artifact_hashes: dict[str, str] | None = None,
    artifact_paths: dict[str, str] | None = None,
    evidence_levels: dict[str, str] | None = None,
) -> ExtendedEndToEndRequirementGateReport:
    """Build the stricter release/adoption gate view for milestone group 9."""

    required_stage_list = list(required_stages)
    merged_statuses = _extended_gate_default_statuses(gate)
    merged_statuses.update(stage_statuses or {})
    artifact_hashes = artifact_hashes or {}
    artifact_paths = artifact_paths or {}
    evidence_levels = evidence_levels or {}

    stages = [
        _build_extended_stage_result(
            stage=stage,
            raw_status=merged_statuses.get(stage),
            artifact_hash=artifact_hashes.get(stage),
            artifact_path=artifact_paths.get(stage),
            evidence_level=evidence_levels.get(stage),
        )
        for stage in required_stage_list
    ]
    blockers = [
        EndToEndGateBlocker(
            stage=stage.stage,
            status="unknown" if stage.status in {"unknown", "missing"} else "refused",
            message=stage.message,
        )
        for stage in stages
        if stage.required and stage.status != "passed"
    ]
    decision = _decision(blockers)
    downstream_action_allowed = (
        decision == "accepted"
        and gate.downstream_action_allowed
        and all(stage.status == "passed" for stage in stages if stage.required)
    )
    return ExtendedEndToEndRequirementGateReport(
        requirement_id=gate.requirement_id,
        decision=decision,
        downstream_action=gate.downstream_action,
        downstream_action_allowed=downstream_action_allowed,
        base_gate_hash=sha256_json(gate),
        required_stage_count=len(required_stage_list),
        passed_stage_count=sum(1 for stage in stages if stage.status == "passed"),
        refused_stage_count=sum(1 for stage in stages if stage.status == "refused"),
        unknown_stage_count=sum(1 for stage in stages if stage.status == "unknown"),
        missing_stage_count=sum(1 for stage in stages if stage.status == "missing"),
        stages=stages,
        blockers=blockers,
        refusal_summary=[blocker.message for blocker in blockers],
        input_hashes={
            "base_gate": sha256_json(gate),
            "required_stages": sha256_json(required_stage_list),
            "stage_statuses": sha256_json(stage_statuses or {}),
            "artifact_hashes": sha256_json(artifact_hashes),
        },
    )


def _extended_gate_default_statuses(gate: EndToEndRequirementGateReport) -> dict[str, str]:
    statuses = dict(gate.statuses)
    trace_status = "passed"
    if statuses.get("trace_alignment") != "passed" or statuses.get("trace_replay") != "passed":
        trace_status = statuses.get("trace_replay") or statuses.get("trace_alignment") or "missing"
    # s_and_r_composition prefers the solver-backed result when available: the solver ran and
    # its status (valid/counterexample/unsupported/timeout) is more informative than the marker
    # check.  Solver "unsupported"/"timeout" maps to "unknown" in the extended gate, correctly
    # distinguishing "tried but couldn't determine" from "marker says valid" (no solver run).
    s_and_r_status = (
        statuses.get("solver_system_consistency")
        or statuses.get("system_consistency", "missing")
    )
    return {
        "semantic_translation": statuses.get("semantic_agreement")
        or statuses.get("translation_agreement", "missing"),
        "requirement_self_consistency": statuses.get(
            "requirement_self_consistency", "missing"
        ),
        "s_and_r_composition": s_and_r_status,
        "trace_validation": trace_status,
        "proof_closure": statuses.get("proof_object", "missing"),
        "release_action_gate": statuses.get("closure_gate", "missing"),
    }


def _build_extended_stage_result(
    *,
    stage: str,
    raw_status: str | None,
    artifact_hash: str | None,
    artifact_path: str | None,
    evidence_level: str | None,
) -> ExtendedGateStageResult:
    if raw_status is None:
        return ExtendedGateStageResult(
            stage=stage,
            status="missing",
            message=f"{stage} evidence is missing from the extended gate pipeline",
            refusal_code=_extended_refusal_code(stage),
        )
    accepted_statuses = _EXTENDED_STAGE_ACCEPTED_STATUSES.get(stage, {"passed"})
    if raw_status in accepted_statuses:
        return ExtendedGateStageResult(
            stage=stage,
            raw_status=raw_status,
            status="passed",
            artifact_hash=artifact_hash,
            artifact_path=artifact_path,
            evidence_level=evidence_level,
            message=f"{stage} passed with status {raw_status}",
        )
    if raw_status in _EXTENDED_STAGE_UNKNOWN_STATUSES:
        status: Literal["passed", "refused", "unknown", "missing"] = "unknown"
    else:
        status = "refused"
    return ExtendedGateStageResult(
        stage=stage,
        raw_status=raw_status,
        status=status,
        artifact_hash=artifact_hash,
        artifact_path=artifact_path,
        evidence_level=evidence_level,
        refusal_code=_extended_refusal_code(stage),
        message=f"{stage} status is {raw_status}; expected one of {sorted(accepted_statuses)}",
    )


def _extended_refusal_code(stage: str) -> str:
    return "NLR-EXT-GATE-" + stage.upper().replace("_", "-")


def _blockers(
    *,
    translation_status: str,
    self_consistency_status: str,
    coverage_result: str,
    trace_alignment_result: str,
    trace_replay_result: str,
    system_status: str,
    proof_status: str,
    closure_result: str,
    solver_system_status: str | None = None,
) -> list[EndToEndGateBlocker]:
    blockers: list[EndToEndGateBlocker] = []
    _append_if_not(
        blockers,
        stage="translation_agreement",
        status=translation_status,
        expected="agreed",
        unknown_statuses={"needs_review"},
    )
    _append_if_not(
        blockers,
        stage="requirement_self_consistency",
        status=self_consistency_status,
        expected="valid",
        unknown_statuses={"unsupported", "timeout", "tool_error"},
    )
    _append_if_not(blockers, stage="spec_coverage", status=coverage_result, expected="passed")
    _append_if_not(
        blockers,
        stage="trace_alignment",
        status=trace_alignment_result,
        expected="passed",
    )
    _append_if_not(blockers, stage="trace_replay", status=trace_replay_result, expected="passed")
    _append_if_not(
        blockers,
        stage="system_consistency",
        status=system_status,
        expected="valid",
        unknown_statuses={"unsupported", "timeout", "needs_review"},
    )
    # Solver-backed S∧R evidence is load-bearing in the hard direction: a counterexample
    # or invalid result from the solver MUST refuse the gate regardless of the marker check.
    # Valid/unsupported/timeout/unknown from the solver do not generate blockers —
    # gate acceptance on the positive path still rests on the marker check and proof closure.
    if solver_system_status in {"counterexample", "invalid"}:
        blockers.append(
            EndToEndGateBlocker(
                stage="solver_system_consistency",
                status="refused",
                message=(
                    f"solver-backed S∧R check returned {solver_system_status!r}; "
                    "requirement is inconsistent with system constraints"
                ),
            )
        )
    _append_if_not(blockers, stage="proof_object", status=proof_status, expected="closed")
    _append_if_not(blockers, stage="closure_gate", status=closure_result, expected="passed")
    return blockers


def _append_if_not(
    blockers: list[EndToEndGateBlocker],
    *,
    stage: str,
    status: str,
    expected: str,
    unknown_statuses: set[str] | None = None,
) -> None:
    if status == expected:
        return
    outcome = "unknown" if status in (unknown_statuses or set()) else "refused"
    blockers.append(
        EndToEndGateBlocker(
            stage=stage,
            status=outcome,
            message=f"{stage} status is {status}; expected {expected}",
        )
    )


def _decision(blockers: list[EndToEndGateBlocker]) -> Literal["accepted", "refused", "unknown"]:
    if not blockers:
        return "accepted"
    # A solver-backed counterexample is definitive evidence of a violation. Refuse
    # immediately — do not allow unknown stages to mask a confirmed bad result.
    if any(
        b.stage == "solver_system_consistency" and b.status == "refused"
        for b in blockers
    ):
        return "refused"
    if any(blocker.status == "unknown" for blocker in blockers):
        return "unknown"
    return "refused"
