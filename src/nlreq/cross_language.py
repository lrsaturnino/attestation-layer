from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from .coverage_alignment import (
    SpecCoverageReport,
    TraceAlignmentReport,
    TraceAlignmentStatus,
    build_spec_coverage_report,
)
from .formal_backend import FormalBackendBudget, FormalBackendExecution
from .impact import ImpactAnalysisArtifact
from .jsonutil import sha256_json
from .models import BackendResult, EvidenceLevel, NormalizedTraceArtifact, RequirementIRV2
from .proof_closure import (
    ClosureGateReport,
    ProofObject,
    build_cross_language_dispatch_plan,
    build_proof_object,
    evaluate_closure_gate,
)
from .source_adapter import SourceManifest
from .system_checker import (
    check_solver_backed_system_consistency,
    default_apalache_s_and_r_execution,
)
from .system_composition import (
    CrossLanguageCompositionReport,
    CrossLanguageSandRSlice,
    build_cross_language_composition_report,
    build_s_and_r_composition_report,
)
from .system_spec import SpecTraceContract, SystemSpecRegistry
from .trace_validation import classify_spec_code_alignment
from .translator import lower_ir_v2_to_tla


CROSS_LANGUAGE_SCHEMA_VERSION = "0.1"
CROSS_LANGUAGE_V2_SCHEMA_VERSION = "0.2"
CROSS_LANGUAGE_TOOL_VERSION = "0.1"


class CrossLanguageEvidenceSlice(BaseModel):
    model_config = ConfigDict(extra="forbid")

    adapter_id: str
    language: str
    runtime: str | None = None
    module_ids: list[str] = Field(default_factory=list)
    trace_ids: list[str] = Field(default_factory=list)


class CausalTraceLink(BaseModel):
    model_config = ConfigDict(extra="forbid")

    from_trace_id: str
    from_event_id: str
    to_trace_id: str
    to_event_id: str
    relation: Literal["causes", "follows", "correlates"]
    evidence: str


class CrossLanguageProofBlocker(BaseModel):
    model_config = ConfigDict(extra="forbid")

    category: Literal[
        "proof",
        "language_diversity",
        "trace_link",
        "adapter_evidence",
        "replay_bundle",
    ]
    message: str
    subject: str | None = None


class CrossLanguageProofObject(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["0.1"] = CROSS_LANGUAGE_SCHEMA_VERSION
    proof_id: str
    requirement_id: str
    result: Literal["passed", "blocked"]
    proof_status: Literal["closed", "open", "blocked"]
    slices: list[CrossLanguageEvidenceSlice] = Field(default_factory=list)
    causal_links: list[CausalTraceLink] = Field(default_factory=list)
    blockers: list[CrossLanguageProofBlocker] = Field(default_factory=list)
    input_hashes: dict[str, str] = Field(default_factory=dict)
    tool: str = "nlreq.cross_language"
    tool_version: str = CROSS_LANGUAGE_TOOL_VERSION


class AdapterEvidenceReference(BaseModel):
    model_config = ConfigDict(extra="forbid")

    evidence_id: str
    adapter_id: str
    artifact_hash: str
    evidence_level: str | None = None
    producer_id: str | None = None
    replay_bundle_hash: str | None = None


class CausalTraceLinkV2(BaseModel):
    model_config = ConfigDict(extra="forbid")

    link_id: str
    from_adapter_id: str
    from_trace_id: str
    from_event_id: str
    to_adapter_id: str
    to_trace_id: str
    to_event_id: str
    relation: Literal["causes", "follows", "correlates"]
    required: bool = True
    status: Literal["satisfied", "missing_source", "missing_target", "unverified"] = "unverified"
    evidence_hash: str | None = None


class CrossLanguageEvidenceSliceV2(BaseModel):
    model_config = ConfigDict(extra="forbid")

    adapter_id: str
    language: str
    runtime: str | None = None
    module_ids: list[str] = Field(default_factory=list)
    trace_ids: list[str] = Field(default_factory=list)
    evidence: list[AdapterEvidenceReference] = Field(default_factory=list)
    blockers: list[CrossLanguageProofBlocker] = Field(default_factory=list)


class CrossLanguageProofObjectV2(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["0.2"] = CROSS_LANGUAGE_V2_SCHEMA_VERSION
    proof_id: str
    requirement_id: str
    result: Literal["accepted", "refused", "unknown"]
    closure_status: Literal["closed", "blocked"]
    proof_status: Literal["closed", "open", "blocked"]
    adapter_count: int = 0
    language_count: int = 0
    slices: list[CrossLanguageEvidenceSliceV2] = Field(default_factory=list)
    causal_links: list[CausalTraceLinkV2] = Field(default_factory=list)
    blockers: list[CrossLanguageProofBlocker] = Field(default_factory=list)
    input_hashes: dict[str, str] = Field(default_factory=dict)
    tool: str = "nlreq.cross_language"
    tool_version: str = CROSS_LANGUAGE_TOOL_VERSION


def build_cross_language_proof_object(
    *,
    proof: ProofObject,
    manifests: list[SourceManifest],
    traces: list[NormalizedTraceArtifact] | None = None,
    causal_links: list[CausalTraceLink] | None = None,
) -> CrossLanguageProofObject:
    traces = traces or []
    causal_links = causal_links or []
    trace_ids_by_adapter: dict[str, list[str]] = {}
    event_ids = set()
    for artifact in traces:
        for trace in artifact.root:
            trace_ids_by_adapter.setdefault(trace.adapter_id, []).append(trace.trace_id)
            for event in trace.events:
                event_ids.add((trace.trace_id, event.event_id))

    slices = [
        CrossLanguageEvidenceSlice(
            adapter_id=manifest.adapter,
            language=manifest.language,
            runtime=manifest.runtime,
            module_ids=[module.module_id for module in manifest.modules],
            trace_ids=sorted(trace_ids_by_adapter.get(manifest.adapter, [])),
        )
        for manifest in manifests
    ]
    blockers: list[CrossLanguageProofBlocker] = []
    if proof.status != "closed":
        blockers.append(
            CrossLanguageProofBlocker(
                category="proof",
                subject=proof.proof_id,
                message="cross-language proof requires a closed proof object",
            )
        )
    if len({item.language for item in slices}) < 2:
        blockers.append(
            CrossLanguageProofBlocker(
                category="language_diversity",
                message="at least two source languages are required",
            )
        )
    for link in causal_links:
        if (link.from_trace_id, link.from_event_id) not in event_ids:
            blockers.append(
                CrossLanguageProofBlocker(
                    category="trace_link",
                    subject=f"{link.from_trace_id}:{link.from_event_id}",
                    message="causal link source event is missing",
                )
            )
        if (link.to_trace_id, link.to_event_id) not in event_ids:
            blockers.append(
                CrossLanguageProofBlocker(
                    category="trace_link",
                    subject=f"{link.to_trace_id}:{link.to_event_id}",
                    message="causal link target event is missing",
                )
            )
    return CrossLanguageProofObject(
        proof_id=proof.proof_id,
        requirement_id=proof.requirement_id,
        result="blocked" if blockers else "passed",
        proof_status=proof.status,
        slices=slices,
        causal_links=causal_links,
        blockers=blockers,
        input_hashes={
            "proof_object": sha256_json(proof),
            "source_manifests": sha256_json(manifests),
            "traces": sha256_json(traces),
            "causal_links": sha256_json(causal_links),
        },
    )


def build_cross_language_causal_proof_object(
    *,
    proof: ProofObject,
    manifests: list[SourceManifest],
    traces: list[NormalizedTraceArtifact] | None = None,
    evidence: list[AdapterEvidenceReference] | None = None,
    causal_links: list[CausalTraceLinkV2] | None = None,
    required_adapter_ids: list[str] | None = None,
    require_causal_links: bool = True,
) -> CrossLanguageProofObjectV2:
    """Build the stricter phase 144 multi-adapter closure object."""

    traces = traces or []
    evidence = evidence or []
    causal_links = causal_links or []
    required_adapter_ids = required_adapter_ids or []
    trace_ids_by_adapter, event_ids = _trace_indexes(traces)
    evidence_by_adapter: dict[str, list[AdapterEvidenceReference]] = {}
    for item in evidence:
        evidence_by_adapter.setdefault(item.adapter_id, []).append(item)

    slices = [
        CrossLanguageEvidenceSliceV2(
            adapter_id=manifest.adapter,
            language=manifest.language,
            runtime=manifest.runtime,
            module_ids=[module.module_id for module in manifest.modules],
            trace_ids=sorted(trace_ids_by_adapter.get(manifest.adapter, [])),
            evidence=sorted(
                evidence_by_adapter.get(manifest.adapter, []),
                key=lambda item: item.evidence_id,
            ),
        )
        for manifest in manifests
    ]
    blockers = _cross_language_v2_blockers(
        proof=proof,
        slices=slices,
        causal_links=causal_links,
        event_ids=event_ids,
        required_adapter_ids=required_adapter_ids,
        require_causal_links=require_causal_links,
    )
    normalized_links = [
        _causal_link_status(link, event_ids)
        for link in causal_links
    ]
    result: Literal["accepted", "refused", "unknown"] = "accepted"
    if blockers:
        result = "unknown" if any(blocker.category == "proof" for blocker in blockers) else "refused"
    return CrossLanguageProofObjectV2(
        proof_id=proof.proof_id,
        requirement_id=proof.requirement_id,
        result=result,
        closure_status="blocked" if blockers else "closed",
        proof_status=proof.status,
        adapter_count=len(slices),
        language_count=len({item.language for item in slices}),
        slices=slices,
        causal_links=normalized_links,
        blockers=blockers,
        input_hashes={
            "proof_object": sha256_json(proof),
            "source_manifests": sha256_json(manifests),
            "traces": sha256_json(traces),
            "evidence": sha256_json(evidence),
            "causal_links": sha256_json(causal_links),
            "required_adapter_ids": sha256_json(required_adapter_ids),
        },
    )


def _trace_indexes(
    traces: list[NormalizedTraceArtifact],
) -> tuple[dict[str, list[str]], set[tuple[str, str]]]:
    trace_ids_by_adapter: dict[str, list[str]] = {}
    event_ids: set[tuple[str, str]] = set()
    for artifact in traces:
        for trace in artifact.root:
            trace_ids_by_adapter.setdefault(trace.adapter_id, []).append(trace.trace_id)
            for event in trace.events:
                event_ids.add((trace.trace_id, event.event_id))
    return trace_ids_by_adapter, event_ids


def _cross_language_v2_blockers(
    *,
    proof: ProofObject,
    slices: list[CrossLanguageEvidenceSliceV2],
    causal_links: list[CausalTraceLinkV2],
    event_ids: set[tuple[str, str]],
    required_adapter_ids: list[str],
    require_causal_links: bool,
) -> list[CrossLanguageProofBlocker]:
    blockers: list[CrossLanguageProofBlocker] = []
    if proof.status != "closed":
        blockers.append(
            CrossLanguageProofBlocker(
                category="proof",
                subject=proof.proof_id,
                message="cross-language closure requires a closed proof object",
            )
        )
    if len({item.language for item in slices}) < 2:
        blockers.append(
            CrossLanguageProofBlocker(
                category="language_diversity",
                message="at least two source languages are required",
            )
        )
    present_adapter_ids = {item.adapter_id for item in slices}
    for adapter_id in sorted(set(required_adapter_ids) - present_adapter_ids):
        blockers.append(
            CrossLanguageProofBlocker(
                category="adapter_evidence",
                subject=adapter_id,
                message="required adapter evidence slice is missing",
            )
        )
    for item in slices:
        if not item.evidence:
            blockers.append(
                CrossLanguageProofBlocker(
                    category="adapter_evidence",
                    subject=item.adapter_id,
                    message="adapter slice has no retained evidence reference",
                )
            )
        if any(ref.replay_bundle_hash is None for ref in item.evidence):
            blockers.append(
                CrossLanguageProofBlocker(
                    category="replay_bundle",
                    subject=item.adapter_id,
                    message="adapter evidence is missing replay bundle hash",
                )
            )
    if require_causal_links and not causal_links:
        blockers.append(
            CrossLanguageProofBlocker(
                category="trace_link",
                message="at least one required causal trace link is required",
            )
        )
    for link in causal_links:
        status = _causal_link_status(link, event_ids).status
        if link.required and status != "satisfied":
            blockers.append(
                CrossLanguageProofBlocker(
                    category="trace_link",
                    subject=link.link_id,
                    message=f"required causal trace link is {status}",
                )
            )
    return blockers


def _causal_link_status(
    link: CausalTraceLinkV2,
    event_ids: set[tuple[str, str]],
) -> CausalTraceLinkV2:
    source_present = (link.from_trace_id, link.from_event_id) in event_ids
    target_present = (link.to_trace_id, link.to_event_id) in event_ids
    if not source_present:
        return link.model_copy(update={"status": "missing_source"})
    if not target_present:
        return link.model_copy(update={"status": "missing_target"})
    return link.model_copy(update={"status": "satisfied"})


# ---------------------------------------------------------------------------
# PC-13 — the cross-language capstone (SP3): one requirement whose per-language guards are
# discharged by REAL per-language S ∧ R runs and aggregated into ONE ProofObject whose closure
# gates a downstream action.
# ---------------------------------------------------------------------------

# A PC-11 spec↔code alignment classification maps to one trace-alignment status: a reviewed S that
# reproduces its language's real traces (``satisfies``) aligns; a spec contradicted by the traces
# (``violates_with_delta``) is violating; one the traces never witness (``no_coverage``) is uncovered.
_ALIGNMENT_TO_TRACE_STATUS: dict[str, Literal["aligned", "violating", "uncovered"]] = {
    "satisfies": "aligned",
    "violates_with_delta": "violating",
    "no_coverage": "uncovered",
}


@dataclass(frozen=True)
class CrossLanguageVertical:
    """One language's contribution to a cross-language requirement (PC-13).

    Each vertical discharges exactly one of the parent requirement's per-language guard nodes
    (``guard_node_id`` — an ``obligation.*`` conjunct of the cross-language ``and``). It carries the
    per-language CHECKABLE sub-claim (the formalization of that guard), the reviewed ``S`` registry and
    the call-graph impact for that language's module, the REAL extracted traces, and the reviewed
    spec's trace-observable contract (PC-11). The orchestrator runs a real Apalache ``S ∧ R`` for this
    vertical alone — never a combined module — and validates ``S`` reproduces these traces.

    ``execution`` defaults to a real Apalache ``S ∧ R`` run (``default_apalache_s_and_r_execution``)
    with a per-vertical artifact directory under ``project_root``; pass an explicit execution to point
    at a different checker or artifact location. When Apalache is absent the run degrades to a tool
    error (UNVERIFIED, blocks) — never a fabricated ``valid``.
    """

    language: str
    adapter_id: str
    guard_node_id: str
    sub_claim: RequirementIRV2
    registry: SystemSpecRegistry
    impact: ImpactAnalysisArtifact
    project_root: Path
    traces: NormalizedTraceArtifact
    spec_trace_contract: SpecTraceContract
    execution: FormalBackendExecution | None = None
    budget: FormalBackendBudget | None = None


class CrossLanguageVerticalEvidence(BaseModel):
    """The retained per-vertical evidence summary of a cross-language closure (PC-13)."""

    model_config = ConfigDict(extra="forbid")

    language: str
    adapter_id: str
    guard_node_id: str
    premise_id: str
    sub_claim_id: str
    s_and_r_status: str
    evidence_level: EvidenceLevel | None = None
    spec_ids: list[str] = Field(default_factory=list)
    trace_alignment: Literal["satisfies", "violates_with_delta", "no_coverage"]


class CrossLanguageClosureResult(BaseModel):
    """The aggregated result of a cross-language closure (PC-13 / SP3).

    ``proof`` is the ONE :class:`ProofObject` whose per-language premises are discharged across BOTH
    verticals (each by its OWN language's real ``S ∧ R`` BOUNDED_CHECKED result); ``gate`` is the
    PB-8 closure-as-action-gate decision over it. ``composition`` aggregates the per-language ``S ∧ R``
    composition reports; ``coverage`` and ``trace_alignment`` are the real registry-derived and
    PC-11-trace-derived reports that gate the proof. ``verticals`` retains each language's evidence.
    """

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["0.1"] = CROSS_LANGUAGE_SCHEMA_VERSION
    requirement_id: str
    proof: ProofObject
    gate: ClosureGateReport
    composition: CrossLanguageCompositionReport
    coverage: SpecCoverageReport
    trace_alignment: TraceAlignmentReport
    verticals: list[CrossLanguageVerticalEvidence] = Field(default_factory=list)


def close_cross_language_proof(
    *,
    requirement: RequirementIRV2,
    verticals: list[CrossLanguageVertical],
    downstream_action: str = "merge",
) -> CrossLanguageClosureResult:
    """Discharge a cross-language requirement's per-language guards via real per-language ``S ∧ R``
    and aggregate them into ONE :class:`ProofObject` whose closure gates a downstream action (PC-13).

    Pipeline, per the SP3 capstone:

    1. Build the per-language dispatch plan (:func:`build_cross_language_dispatch_plan`): one route per
       guard, routed to the solver-backed ``S ∧ R`` producer at ``BOUNDED_CHECKED`` in ``formal_claim``
       mode (so a guard is discharged ONLY by a result tagged with its premise_id).
    2. For EACH vertical: run a real Apalache ``S ∧ R`` over THAT language's reviewed ``S`` and its
       slice of the requirement; tag the result with its guard's premise_id (non-interchangeable);
       build the per-language ``S ∧ R`` composition report; derive real spec coverage from the registry;
       and classify whether ``S`` reproduces the language's REAL traces (PC-11).
    3. Aggregate the per-language coverage and PC-11 trace classifications into the proof's combined
       coverage and trace-alignment reports, and build the ONE ProofObject from BOTH ``S ∧ R`` results.
    4. Evaluate the closure gate over that proof.

    The proof closes only when every guard's own ``S ∧ R`` is ``valid`` at ``BOUNDED_CHECKED`` AND
    every reviewed ``S`` reproduces its real traces. A counterexample in either language leaves that
    guard's premise undischarged, the proof open/blocked, and the gate blocking the action.
    """
    plan = build_cross_language_dispatch_plan(requirement)
    route_by_node = {route.node_id: route for route in plan.routes}
    _validate_vertical_bindings(verticals, route_by_node)

    backend_results: list[BackendResult] = []
    composition_slices: list[CrossLanguageSandRSlice] = []
    coverage_reports: list[SpecCoverageReport] = []
    trace_statuses: list[TraceAlignmentStatus] = []
    vertical_evidence: list[CrossLanguageVerticalEvidence] = []

    for vertical in verticals:
        route = route_by_node[vertical.guard_node_id]
        lowered = lower_ir_v2_to_tla(vertical.sub_claim)
        execution = vertical.execution or default_apalache_s_and_r_execution(
            artifact_dir=(
                vertical.project_root / ".nlreq-xlang-artifacts" / vertical.language
            ).as_posix()
        )
        consistency = check_solver_backed_system_consistency(
            requirement=vertical.sub_claim,
            lowered=lowered,
            registry=vertical.registry,
            impact=vertical.impact,
            project_root=vertical.project_root,
            budget=vertical.budget,
            execution=execution,
        )
        backend_results.append(_tag_premise(consistency.result, route.premise_id))
        composition_slices.append(
            CrossLanguageSandRSlice(
                language=vertical.language,
                adapter_id=vertical.adapter_id,
                composition=build_s_and_r_composition_report(
                    requirement=vertical.sub_claim,
                    lowered=lowered,
                    registry=vertical.registry,
                    impact=vertical.impact,
                    project_root=vertical.project_root,
                    consistency=consistency,
                ),
            )
        )
        coverage_reports.append(
            build_spec_coverage_report(
                impact=vertical.impact,
                registry=vertical.registry,
                project_root=vertical.project_root,
            )
        )
        alignment = classify_spec_code_alignment(
            contract=vertical.spec_trace_contract, traces=vertical.traces
        )
        trace_statuses.append(_trace_alignment_status(vertical, alignment))
        vertical_evidence.append(
            CrossLanguageVerticalEvidence(
                language=vertical.language,
                adapter_id=vertical.adapter_id,
                guard_node_id=vertical.guard_node_id,
                premise_id=route.premise_id,
                sub_claim_id=vertical.sub_claim.requirement_id,
                s_and_r_status=consistency.result.status,
                evidence_level=consistency.result.evidence_level,
                spec_ids=consistency.spec_ids,
                trace_alignment=alignment.classification,
            )
        )

    coverage = _merge_coverage(coverage_reports)
    trace_alignment = _merge_trace_alignment(trace_statuses)
    proof = build_proof_object(
        requirement=requirement,
        backend_results=backend_results,
        coverage=coverage,
        trace_alignment=trace_alignment,
        dispatch=plan,
    )
    composition = build_cross_language_composition_report(
        requirement_id=requirement.requirement_id,
        slices=composition_slices,
    )
    gate = evaluate_closure_gate(proof, downstream_action=downstream_action)
    return CrossLanguageClosureResult(
        requirement_id=requirement.requirement_id,
        proof=proof,
        gate=gate,
        composition=composition,
        coverage=coverage,
        trace_alignment=trace_alignment,
        verticals=vertical_evidence,
    )


def _validate_vertical_bindings(
    verticals: list[CrossLanguageVertical],
    route_by_node: dict[str, object],
) -> None:
    """Fail fast on a misconfigured cross-language closure.

    Every vertical must bind to a real guard node of the requirement, and no two verticals may claim
    the same guard — otherwise a guard would be discharged by the wrong language's ``S ∧ R`` (or by
    two). A guard with NO vertical is left to proof closure: its premise stays undischarged and the
    proof does not close, which is the honest outcome (it is surfaced as an open premise, not hidden).
    """
    seen: set[str] = set()
    for vertical in verticals:
        if vertical.guard_node_id not in route_by_node:
            raise ValueError(
                f"cross-language vertical {vertical.language!r} binds guard node "
                f"{vertical.guard_node_id!r}, which is not a per-language guard of the requirement; "
                f"known guards: {sorted(route_by_node)}"
            )
        if vertical.guard_node_id in seen:
            raise ValueError(
                f"cross-language guard {vertical.guard_node_id!r} is claimed by more than one "
                "vertical; each guard is discharged by exactly one language's S ∧ R"
            )
        seen.add(vertical.guard_node_id)


def _tag_premise(result: BackendResult, premise_id: str) -> BackendResult:
    """Tag an ``S ∧ R`` result as covering one cross-language guard's premise.

    Copies ``covered_fragment_ids`` onto the EXISTING ``details`` (the end_to_end_gate pattern) so the
    bounded backing metadata — recorded bounds, the checker command, the run-recorded tool version —
    survives; constructing a fresh result would drop it and trip the BOUNDED_CHECKED backing checks.
    Under the ``formal_claim`` routing the cross-language plan uses, this tag is what lets the result
    discharge its guard — and ONLY its guard, since the other language's route names a different
    premise_id.
    """
    covered = sorted(
        set(result.details.get("covered_fragment_ids", [])) | {premise_id}
    )
    return result.model_copy(
        update={"details": {**result.details, "covered_fragment_ids": covered}}
    )


def _trace_alignment_status(
    vertical: CrossLanguageVertical,
    alignment,
) -> TraceAlignmentStatus:
    classification = alignment.classification
    return TraceAlignmentStatus(
        trace_id=f"{vertical.adapter_id}:{vertical.spec_trace_contract.spec_id}",
        status=_ALIGNMENT_TO_TRACE_STATUS[classification],
        requirement_id=vertical.sub_claim.requirement_id,
        action=None,
        reason=None if classification == "satisfies" else alignment.reason,
    )


def _merge_coverage(reports: list[SpecCoverageReport]) -> SpecCoverageReport:
    """Combine per-language coverage reports into the proof's single coverage report.

    Concatenates each vertical's module statuses and recomputes the ratio over the union, so the
    aggregate is ``passed`` only when EVERY language's impacted module is covered by a reviewed, fresh
    spec. The threshold is the strictest across the verticals (default 1.0).
    """
    modules = [status for report in reports for status in report.modules]
    total = len(modules)
    covered = sum(1 for status in modules if status.status == "covered")
    ratio = covered / total if total else 1.0
    threshold = max((report.threshold for report in reports), default=1.0)
    return SpecCoverageReport(
        result="passed" if ratio >= threshold else "blocked",
        threshold=threshold,
        covered_modules=covered,
        total_modules=total,
        coverage_ratio=ratio,
        modules=modules,
    )


def _merge_trace_alignment(statuses: list[TraceAlignmentStatus]) -> TraceAlignmentReport:
    """Combine per-language PC-11 trace classifications into the proof's trace-alignment report.

    ``passed`` only when every reviewed ``S`` reproduces its language's real traces (every status is
    ``aligned``); a single violating/uncovered language blocks, so a spec that does not match its
    code's traces cannot ground a cross-language closure.
    """
    blocked = any(status.status != "aligned" for status in statuses)
    return TraceAlignmentReport(
        result="blocked" if blocked else "passed",
        alignments=statuses,
    )
