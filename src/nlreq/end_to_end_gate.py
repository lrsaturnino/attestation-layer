from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from .coverage_alignment import build_spec_coverage_report, build_trace_alignment_report
from .cvc5_backend import cvc5_check_formal_claim_premises
from .delta_extractor import build_delta_report
from .dsl_v2 import DslV2Parser
from .formal_backend import FormalBackendBudget, FormalBackendExecution
from .formal_claim import (
    FormalClaim,
    FormalClaimLoweringReport,
    build_formal_claim,
    build_proof_dispatch_plan_from_formal_claim,
    formal_claim_fragment_bound_predicate,
)
from .formal_claim_backend import build_premise_consistency_agreement
from .formal_claim_smt import smt_check_formal_claim_predicate_fragments
from .impact import analyze_source_impact
from .source_impact import analyze_source_impact_with_context
from .jsonutil import sha256_json, sha256_text, write_json
from .models import BackendResult, EvidenceLevel, RequirementIRV2, SourceSpan
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
from .system_checker import (
    check_solver_backed_system_consistency,
    default_apalache_s_and_r_execution,
    not_applicable_system_consistency,
    unsupported_system_consistency_without_invariant,
)
from .system_spec import SystemSpecRegistry, specs_for_impact
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
    # not_applicable: no reviewed S is relevant to the impacted modules, so there is no S to
    # conjoin and no S ∧ R obligation to discharge — a passing (non-blocking) outcome, distinct
    # from "valid" (verified against a real S) and from unsupported/timeout (a real S we could
    # not determine — including a relevant S that declares no invariant — which falls through
    # to the unknown set below and blocks).
    "s_and_r_composition": {"valid", "not_applicable", "passed"},
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


def _system_consistency_floor_baseline(system_status: str) -> BackendResult | None:
    """A CONSISTENCY_CHECKED baseline that discharges the default proof dispatch's
    system-consistency premises when the consolidated S ∧ R stage concluded the requirement
    is consistent with the system.

    The default dispatch (``build_proof_dispatch_plan``) routes a requirement's premises to
    the ``system_checker`` producer at the ``CONSISTENCY_CHECKED`` floor. The solver-backed
    stage instead emits its verdict under ``solver_system_checker`` at SMT_CHECKED /
    BOUNDED_CHECKED — a stronger level that does not match the floor route, so on its own it
    cannot discharge those premises. When the stage established consistency (``valid``) or
    determined there is no system obligation to discharge (``not_applicable``), this baseline
    lets the floor premises discharge on the weaker claim that the stronger verdict — recorded
    separately under ``solver_system_checker`` — subsumes. A non-consistent verdict
    (counterexample / timeout / unsupported) yields no baseline: the premises stay open and
    the gate blocks on the real result.
    """
    if system_status not in {"valid", "not_applicable"}:
        return None
    if system_status == "not_applicable":
        details: dict[str, object] = {
            "mode": "not_applicable",
            "reason": (
                "no reviewed system spec is relevant to the impacted modules; there is no S "
                "to conjoin, so S ∧ R has no obligation to discharge"
            ),
        }
    else:
        details = {
            "mode": "solver_backed_baseline",
            "reason": (
                "solver-backed S ∧ R returned valid; the stronger verdict is recorded under "
                "solver_system_checker and subsumes this CONSISTENCY_CHECKED floor"
            ),
        }
    return BackendResult(
        backend="system_checker",
        status="valid",
        evidence_level=EvidenceLevel.CONSISTENCY_CHECKED,
        details=details,
    )


def _cover_s_and_r_fragments(result: BackendResult, claim: FormalClaim) -> BackendResult:
    """Tag a solver-backed S ∧ R result with the fragment IDs its module actually bound.

    Only the ``solver_system_checker`` result discharges formal_claim routes, and it covers a
    fragment exactly when that fragment's ``Pred_*`` operator appears in the result's recorded
    ``bound_predicates`` — the operators the composition inlined into the checked ``Inv``. The
    backing metadata (bounds, command, run-recorded tool_version) is preserved by copying onto
    the existing ``details``; constructing a fresh result would drop it and trip PB-9's backing
    checks. Results without ``bound_predicates`` (the in-process Z3 fixture, the CONSISTENCY
    floor baseline, a refused composition) are returned unchanged — they cover nothing.
    """
    if result.backend != "solver_system_checker":
        return result
    bound = set(result.details.get("bound_predicates", []))
    if not bound:
        return result
    covered = [
        fragment.fragment_id
        for fragment in [*claim.premises, *claim.obligations]
        if formal_claim_fragment_bound_predicate(fragment) in bound
    ]
    if not covered:
        return result
    return result.model_copy(
        update={"details": {**result.details, "covered_fragment_ids": covered}}
    )


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
    `solver_execution` overrides the checker for the solver-backed S ∧ R check; when omitted,
    S ∧ R runs by default on a real Apalache check of the composed module
    (default_apalache_s_and_r_execution), degrading to tool_error (blocks) if the binary is
    absent. Pass `solver_execution=FormalBackendExecution(checker_id="z3")` to opt into the
    in-process Z3 development/fixture path, which does not evaluate S's transition system. S ∧ R
    is skipped as not-applicable only when no reviewed system spec relevant to the impact
    declares an invariant. `execution` is never reused for S ∧ R, so a self-consistency-only
    run never triggers it.
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

    # System consistency S ∧ R is checked by a real model checker by default — never by
    # grepping the spec text for markers (that path is check_system_consistency_fixture, offline
    # tests only). The default checker is a real Apalache run over the composed S ∧ R module
    # (default_apalache_s_and_r_execution): only a bounded model check of S's own Init/Next
    # actually exercises the narrowing. The in-process Z3 path is an explicit development/fixture
    # mode a caller opts into with solver_execution=FormalBackendExecution(checker_id="z3"); it
    # never evaluates S's transition system, so it is not S ∧ R evidence. When Apalache is not
    # installed the run degrades to tool_error (UNVERIFIED, blocks) — never a silent pass.
    # `execution` drives the self-consistency check and is deliberately NOT reused here, so a
    # self-consistency-only run never triggers S ∧ R.
    #
    # A reviewed spec contributes a checkable S ∧ R obligation only when it declares an
    # invariant to preserve. The three outcomes are decided from the registry, not from a
    # marker in a spec file, and are deliberately NOT collapsed:
    #   - At least one relevant spec declares an invariant → run the real solver-backed check.
    #   - A relevant spec governs the impacted modules but none declares an invariant → refuse
    #     (unsupported, blocks). A reviewed S that asserts nothing checkable cannot be silently
    #     accepted — that would be a vacuous S ∧ R pass. (Was previously collapsed into
    #     not_applicable, letting a relevant-but-assertionless spec pass.)
    #   - No reviewed spec is relevant at all → not-applicable (non-blocking): there is no S to
    #     conjoin, so there is genuinely no obligation to discharge.
    relevant_specs = specs_for_impact(registry, impact)
    checkable_specs = [spec for spec in relevant_specs if spec.invariants]
    if checkable_specs:
        system_consistency = check_solver_backed_system_consistency(
            requirement=requirement,
            lowered=lowered,
            registry=registry,
            impact=impact,
            project_root=project_root,
            budget=budget,
            execution=solver_execution
            or default_apalache_s_and_r_execution(
                artifact_dir=(artifact_dir / "s-and-r").as_posix()
            ),
        )
        system_status = system_consistency.result.status
    elif relevant_specs:
        system_consistency = unsupported_system_consistency_without_invariant(
            requirement=requirement, registry=registry, impact=impact
        )
        system_status = system_consistency.result.status
    else:
        system_consistency = not_applicable_system_consistency(
            requirement=requirement, registry=registry, impact=impact
        )
        system_status = "not_applicable"
    record("system_consistency", "system-consistency.json", system_consistency)

    delta = build_delta_report(
        self_consistency=self_consistency,
        system_consistency=system_consistency,
        spec_coverage=coverage,
        trace_replay=trace_replay,
    )
    record("delta_report", "delta-report.json", delta)

    system_backend_results = backend_results_from_system_consistency(system_consistency)
    # The default proof dispatch routes system-consistency premises to the system_checker
    # producer at the CONSISTENCY_CHECKED floor, which the solver-backed result (emitted under
    # solver_system_checker at SMT_CHECKED/BOUNDED_CHECKED) does not match. When the stage
    # concluded the requirement is consistent (valid) or that there is no obligation to
    # discharge (not_applicable), add the floor baseline so those premises can close; the
    # stronger solver verdict remains recorded separately. A non-consistent verdict adds no
    # baseline, leaving the premises open so the gate blocks on the real result.
    floor_baseline = _system_consistency_floor_baseline(system_status)
    if floor_baseline is not None:
        system_backend_results = [*system_backend_results, floor_baseline]
    # When the FormalClaim report is lowered, also SMT-check predicate/comparison
    # fragments. These produce core_smt BackendResults with per-fragment covered_fragment_ids
    # so formal_claim-routed premises can be discharged without relying on the system-
    # consistency result (which only covers system_checker routes).
    formal_claim_preview = build_formal_claim(requirement)
    # The cross-backend premise-consistency agreement (PB-6.T3) is computed only when the claim
    # lowered, and only as an ADDITIVE cross-check: it runs the claim's comparison/membership
    # premises through two independent SMT encoders (z3 as core_smt, cvc5) and records whether they
    # reach the same valid/invalid verdict. It is NOT the discharge path — those same premises are
    # discharged independently by smt_check_formal_claim_predicate_fragments below — so when cvc5 is
    # absent (the agreement degrades to needs_review, non-blocking) no premise is left unverified.
    # Only a genuine opposite-verdict divergence (status "disagreed") gates closure; non_overlap (no
    # comparison/membership premise, so no shared question) and needs_review (one backend) do not.
    backend_agreement: BackendAgreementReport | None = None
    if formal_claim_preview.result == "lowered" and formal_claim_preview.formal_claim is not None:
        # The theory-aware backends discharge the SMT premises per the PB-7 routing
        # (formal_claim._backend_for_fragment_kind): comparison premises route to ``smt-theories``
        # (the z3 Int/Real results below) and set-membership premises to ``cvc5`` (its native
        # finite-set theory). Both backends produce one result per contributing premise carrying
        # ``covered_fragment_ids``, so each routed premise is discharged by the distinct producer its
        # kind needs — not all funneled through one backend.
        #
        # smt_check_formal_claim_predicate_fragments still emits real SMT_CHECKED results for ground
        # comparison fragments. Its predicate/rejection_order "unsupported" results are inert: those
        # fragments route to solver_system_checker (the S ∧ R discharge below), so an
        # smt-theories/apalache result matches no route. They are harmless to closure
        # (evidence_level=None, no producer blocker) but linger in backend_results as dead provenance.
        smt_fragment_results = smt_check_formal_claim_predicate_fragments(
            formal_claim_preview.formal_claim
        )
        # cvc5 discharges set-literal-membership premises (and re-checks comparisons, whose results
        # are inert since comparison routes to smt-theories). When cvc5 is not installed these degrade
        # to ``unsupported`` results carrying no evidence level, so a membership premise stays
        # undischarged and the gate blocks rather than silently passing — never a faked discharge.
        cvc5_fragment_results = cvc5_check_formal_claim_premises(
            formal_claim_preview.formal_claim
        )
        backend_agreement = build_premise_consistency_agreement(
            formal_claim_preview.formal_claim
        )
        record("backend_agreement", "backend-agreement.json", backend_agreement)
        # Discharge the formal fragments the S ∧ R model check ACTUALLY verified. The solver
        # result (solver_system_checker, BOUNDED_CHECKED) covers a fragment only when that
        # fragment's Pred_* operator was bound into the composed module the checker ran —
        # read from the result's own recorded ``bound_predicates``, never a static kind
        # table. A stateless S that binds only the premise predicate covers the predicate but
        # leaves the rejection-order obligation open (its outcome predicate was not bound); a
        # stateful S that binds the forbidden outcome covers both. A counterexample/timeout
        # marks the fragments covered as well, so _evaluate_premise blocks them (named) on the
        # real verdict rather than reporting "no result". Tying coverage to what was checked
        # keeps a false high-assurance label impossible.
        system_backend_results = [
            _cover_s_and_r_fragments(result, formal_claim_preview.formal_claim)
            for result in system_backend_results
        ]
    else:
        smt_fragment_results = []
        cvc5_fragment_results = []
    all_backend_results = [*system_backend_results, *smt_fragment_results, *cvc5_fragment_results]

    proof, formal_claim_report = build_proof_with_formal_claim_dispatch(
        requirement=requirement,
        backend_results=all_backend_results,
        coverage=coverage,
        trace_alignment=trace_alignment,
        backend_agreement=backend_agreement,
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
        "system_consistency": system_status,
        "formal_claim": formal_claim_report.result,
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
        system_status=system_status,
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
    # s_and_r_composition reads the consolidated, solver-backed system_consistency status
    # (valid / counterexample / unsupported / timeout / not_applicable).  "unsupported" /
    # "timeout" map to "unknown" in the extended gate, distinguishing "a real S we could not
    # determine" from "valid" (verified) and "not_applicable" (no obligation to discharge).
    s_and_r_status = statuses.get("system_consistency", "missing")
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
    # System consistency S ∧ R is solver-backed by default (see run_end_to_end_requirement_gate).
    # Its status is load-bearing in both directions:
    # - valid → verified against S; no blocker.
    # - not_applicable → no reviewed S is relevant to the impacted modules; there is no S to
    #   conjoin and no obligation to discharge; no blocker.
    # - counterexample / invalid → definitive refusal; the requirement contradicts S.
    # - unsupported / timeout / needs_review → a real S that could not be determined (including
    #   a relevant S that declares no invariant); block as unknown until a determinate result
    #   exists.  Silently ignoring these would let an inconclusive run read as acceptance, which
    #   conflicts with the honesty discipline.
    if system_status in {"counterexample", "invalid"}:
        blockers.append(
            EndToEndGateBlocker(
                stage="system_consistency",
                status="refused",
                message=(
                    f"system-consistency S ∧ R check returned {system_status!r}; "
                    "requirement is inconsistent with system constraints"
                ),
            )
        )
    elif system_status in {"unsupported", "timeout", "needs_review", "unknown"}:
        blockers.append(
            EndToEndGateBlocker(
                stage="system_consistency",
                status="unknown",
                message=(
                    f"system-consistency S ∧ R check returned {system_status!r}; "
                    "check is inconclusive — gate is blocked pending a determinate result"
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


# Stages whose blocker is a downstream consequence of an upstream verdict, not an
# independent finding. proof_object/closure_gate report "refused" whenever the proof did
# not fully close — which happens for ANY non-acceptance, including the merely-inconclusive
# case (premises left open because system-consistency was unsupported, so no evidence was
# supplied). Letting their refusal drive the gate decision would relabel "we could not
# determine" as "we confirmed a violation". So a refusal from these stages alone never
# escalates the decision past what the root-cause stages established.
#
# This exclusion is sound only while a non-closed proof is always inconclusive: today every
# undischarged premise is open or blocked because its backend returned "unsupported", never
# because a backend produced a contradiction. Once a fragment backend can refute a premise,
# a proof_object refusal may be a genuine confirmed violation; the exclusion will then need
# to distinguish a blocked-inconclusive proof from a blocked-contradicted one rather than
# excluding the stage wholesale.
_CONSEQUENTIAL_DECISION_STAGES = frozenset({"proof_object", "closure_gate"})


def _decision(blockers: list[EndToEndGateBlocker]) -> Literal["accepted", "refused", "unknown"]:
    if not blockers:
        return "accepted"
    # A definitive refusal from a root-cause stage — a solver-backed S ∧ R counterexample, a
    # trace-replay violation, a coverage/alignment gap — is confirmed bad evidence. Refuse
    # immediately; do NOT let an inconclusive "unknown" elsewhere mask it. The consequential
    # proof_object/closure_gate refusals are excluded so a downstream block (which always
    # accompanies a non-acceptance) cannot turn an inconclusive run into a false "refused".
    if any(
        b.status == "refused" and b.stage not in _CONSEQUENTIAL_DECISION_STAGES
        for b in blockers
    ):
        return "refused"
    if any(blocker.status == "unknown" for blocker in blockers):
        return "unknown"
    return "refused"
