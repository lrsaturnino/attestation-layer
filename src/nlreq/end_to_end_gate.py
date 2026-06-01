from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from .coverage_alignment import build_spec_coverage_report, build_trace_alignment_report
from .delta_extractor import build_delta_report
from .dsl_v2 import DslV2Parser
from .formal_backend import FormalBackendBudget, FormalBackendExecution
from .impact import analyze_source_impact
from .impact_v2 import analyze_source_impact_v2
from .jsonutil import sha256_json, write_json
from .proof_closure import (
    backend_results_from_system_consistency,
    build_proof_object,
    evaluate_closure_gate,
)
from .requirement_self_consistency import check_requirement_self_consistency
from .source_adapter import SourceLanguageAdapter, SourceManifest
from .system_checker import check_system_consistency
from .system_spec import SystemSpecRegistry
from .trace_replay import build_trace_replay_report
from .translator import lower_ir_v2_to_tla
from .translator_agreement import (
    TranslationAgreementInput,
    TranslationCandidate,
    build_translation_agreement_report,
)


END_TO_END_GATE_SCHEMA_VERSION = "0.1"


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
) -> EndToEndRequirementGateReport:
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

    parser = DslV2Parser()
    requirement = parser.parse_ir(controlled_text, requirement_id=requirement_id, title=title)
    record("requirement_ir", "requirement.ir.json", requirement)

    reparsed = parser.parse_ir(controlled_text, requirement_id=requirement_id, title=title)
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
    record("translation_agreement_input", "translation-agreement-input.json", translation_input)
    translation = build_translation_agreement_report(translation_input)
    record("translation_agreement", "translation-agreement.json", translation)

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

    impact_v2 = analyze_source_impact_v2(
        source_adapter,
        source_manifest,
        symbols=symbols,
        traces=traces,
    )
    record("source_impact_v2", "source-impact-v2.json", impact_v2)

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

    delta = build_delta_report(
        self_consistency=self_consistency,
        system_consistency=system_consistency,
        spec_coverage=coverage,
        trace_replay=trace_replay,
    )
    record("delta_report", "delta-report.json", delta)

    proof = build_proof_object(
        requirement=requirement,
        backend_results=backend_results_from_system_consistency(system_consistency),
        coverage=coverage,
        trace_alignment=trace_alignment,
    )
    record("proof_object", "proof-object.json", proof)

    closure = evaluate_closure_gate(proof, downstream_action=downstream_action)
    record("closure_gate", "closure-gate.json", closure)

    statuses = {
        "translation_agreement": translation.status,
        "requirement_self_consistency": self_consistency.status,
        "source_impact": "completed",
        "source_impact_v2": "completed",
        "spec_coverage": coverage.result,
        "trace_alignment": trace_alignment.result,
        "trace_replay": trace_replay.result,
        "system_consistency": system_consistency.result.status,
        "delta_report": "completed",
        "proof_object": proof.status,
        "closure_gate": closure.result,
    }
    blockers = _blockers(
        translation_status=translation.status,
        self_consistency_status=self_consistency.status,
        coverage_result=coverage.result,
        trace_alignment_result=trace_alignment.result,
        trace_replay_result=trace_replay.result,
        system_status=system_consistency.result.status,
        proof_status=proof.status,
        closure_result=closure.result,
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
    if any(blocker.status == "unknown" for blocker in blockers):
        return "unknown"
    return "refused"
