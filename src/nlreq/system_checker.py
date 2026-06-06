from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from .contradiction_taxonomy import (
    RequirementContradiction,
    detect_cross_requirement_contradictions,
)
from .formal_backend import FormalBackendBudget, FormalBackendExecution
from .formal_lowering import (
    NumericInvariantObligation,
    OutcomePredicate,
    PostStateObligation,
    build_system_spec_contribution,
    compose_s_and_r_module,
    derive_numeric_invariant_obligation,
    derive_outcome_predicate,
    derive_post_state_obligation,
    obligation_consequent_is_real,
    next_has_steps,
    parse_obligation_predicates,
    validate_numeric_invariant_shape,
)
from .jsonutil import sha256_json, sha256_text
from .model_checker_runner import (
    ModelCheckerBudget,
    ModelCheckerCommand,
    run_model_checker,
)
from .models import (
    BackendResult,
    Counterexample,
    EvidenceLevel,
    RequirementIRV2,
    bounded_evidence_backing_complete,
)
from .system_spec import SystemSpecRegistry, build_system_spec_registry_report, specs_for_impact
from .impact import ImpactAnalysisArtifact
from .translator import LoweredFormalArtifact


SYSTEM_CHECKER_SCHEMA_VERSION = "0.1"


# Default symbolic search depth for the S ∧ R bounded check when the caller supplies no
# ``max_depth`` budget. Recorded into the run's ``bounds`` and rendered into ``--length`` from
# the *same* effective budget, so the depth the checker actually searched can never disagree
# with the depth the run claims (see check_solver_backed_system_consistency / _runner_budget).
DEFAULT_S_AND_R_DEPTH = 6


# Single source of truth for the Apalache command that checks a composed S ∧ R module.
# The narrowing composition emits S's own transition system under Init/Next, the conjoined
# S ∧ R state invariant as Inv, and pins identifier constants in ConstInit. The checker must
# be told all four (--cinit/--init/--next/--inv) or it would check a different system than the
# one composed — e.g. with the scope identifiers left unbound — and could miss or invent a
# counterexample. The default gate (end_to_end_gate), the retained benchmark corpus
# (benchmarks/s-and-r/.../manifest.json), and the real-Apalache tests all reference this so
# they cannot drift apart. ``--length`` bounds the symbolic search depth and is rendered from
# the effective budget's ``max_depth`` (``{max_depth}`` token) so the searched depth equals the
# recorded ``bounds.max_depth``; ``{module}`` is substituted with the composed module's filename.
# Both tokens are always substituted by _solver_checker_command before execution.
APALACHE_S_AND_R_COMMAND: tuple[str, ...] = (
    "apalache-mc",
    "check",
    "--cinit=ConstInit",
    "--init=Init",
    "--next=Next",
    "--inv=Inv",
    "--length={max_depth}",
    "{module}",
)


def default_apalache_s_and_r_execution(
    *, artifact_dir: str | None = None
) -> FormalBackendExecution:
    """Build the gate's default solver execution for S ∧ R: a real Apalache run over the
    composed module, carrying the pinned version command so every run records a non-null tool
    version. This — not the in-process Z3 path — is the default checker, because only a bounded
    model check of the composed transition system actually exercises the S ∧ R narrowing. The
    Z3 path remains available as an explicit development/fixture mode
    (``FormalBackendExecution(checker_id="z3")``); it parses the lowered obligation under S's
    predicate assignments but never evaluates S's Init/Next, so it is not S ∧ R evidence.

    When Apalache is not installed the run degrades to ``tool_error`` (UNVERIFIED, blocks) — it
    is never silently treated as ``valid``.
    """
    return FormalBackendExecution(
        checker_id="apalache",
        command=list(APALACHE_S_AND_R_COMMAND),
        tool_version_command=["apalache-mc", "version"],
        artifact_dir=artifact_dir,
    )


class SystemConsistencyResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["0.1"] = SYSTEM_CHECKER_SCHEMA_VERSION
    requirement_id: str
    result: BackendResult
    counterexamples: list[Counterexample] = Field(default_factory=list)
    spec_ids: list[str] = Field(default_factory=list)


class RequirementSetConsistencyReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["0.1"] = SYSTEM_CHECKER_SCHEMA_VERSION
    result: Literal["valid", "contradiction"]
    contradictions: list[RequirementContradiction] = Field(default_factory=list)


def check_system_consistency_fixture(
    *,
    requirement: RequirementIRV2,
    lowered: LoweredFormalArtifact,
    registry: SystemSpecRegistry,
    impact: ImpactAnalysisArtifact,
    project_root: Path,
) -> SystemConsistencyResult:
    """Fixture-only S ∧ R check: decides by grepping the spec text for markers.

    This is NOT a real verification. ``valid`` is returned for any fresh, reviewed
    spec whose text lacks an ``NLREQ_COUNTEREXAMPLE:<id>``/``NLREQ_TIMEOUT`` marker —
    i.e. by string-absence, not by conjoining S. It exists only for offline tests
    that must not invoke a solver. The end-to-end gate uses
    ``check_solver_backed_system_consistency`` instead; do not wire this into any
    real decision path.
    """
    specs = specs_for_impact(registry, impact)
    registry_report = build_system_spec_registry_report(
        registry,
        project_root=project_root,
        module_ids=impact.affected_modules,
    )
    spec_ids = [spec.spec_id for spec in specs]
    if lowered.status != "lowered":
        return _system_result(
            requirement.requirement_id,
            "unsupported",
            spec_ids,
            {"reason": "lowered artifact is refused"},
        )
    bad_specs = [status for status in registry_report.statuses if status.status != "fresh"]
    if bad_specs:
        return _system_result(
            requirement.requirement_id,
            "unsupported",
            spec_ids,
            {
                "reason": "system specs are missing, stale, or unreviewed",
                "spec_statuses": [status.model_dump(mode="json", exclude_none=True) for status in bad_specs],
            },
        )

    for spec in specs:
        text = (project_root / spec.path).read_text()
        if "NLREQ_TIMEOUT" in text:
            return _system_result(
                requirement.requirement_id,
                "timeout",
                spec_ids,
                {"spec_id": spec.spec_id, "reason": "checker timeout marker"},
            )
        marker = f"NLREQ_COUNTEREXAMPLE:{requirement.requirement_id}"
        if marker in text:
            counterexample = Counterexample(
                counterexample_id=f"{spec.spec_id}:{requirement.requirement_id}",
                backend="system_checker",
                claim_id=requirement.requirement_id,
                description="system spec declares a counterexample marker for requirement",
                metadata={"spec_id": spec.spec_id, "marker": marker},
            )
            result = _system_result(
                requirement.requirement_id,
                "counterexample",
                spec_ids,
                {"spec_id": spec.spec_id, "marker": marker},
            )
            return result.model_copy(update={"counterexamples": [counterexample]})

    return _system_result(
        requirement.requirement_id,
        "valid",
        spec_ids,
        {"checked": "deterministic_s_and_r_boundary"},
    )


def check_solver_backed_system_consistency(
    *,
    requirement: RequirementIRV2,
    lowered: LoweredFormalArtifact,
    registry: SystemSpecRegistry,
    impact: ImpactAnalysisArtifact,
    project_root: Path,
    budget: FormalBackendBudget | None = None,
    execution: FormalBackendExecution | None = None,
) -> SystemConsistencyResult:
    specs = specs_for_impact(registry, impact)
    spec_ids = [spec.spec_id for spec in specs]
    registry_report = build_system_spec_registry_report(
        registry,
        project_root=project_root,
        module_ids=impact.affected_modules,
    )
    if lowered.status != "lowered" or lowered.content is None:
        return _solver_result(
            requirement.requirement_id,
            "unsupported",
            spec_ids,
            {"reason": "lowered artifact is refused", "mode": "solver_backed"},
        )
    bad_specs = [status for status in registry_report.statuses if status.status != "fresh"]
    if bad_specs:
        return _solver_result(
            requirement.requirement_id,
            "unsupported",
            spec_ids,
            {
                "mode": "solver_backed",
                "reason": "system specs are missing, stale, or unreviewed",
                "spec_statuses": [
                    status.model_dump(mode="json", exclude_none=True) for status in bad_specs
                ],
            },
        )

    execution = execution or FormalBackendExecution()
    spec_texts = [(spec.spec_id, (project_root / spec.path).read_text()) for spec in specs]
    pred_assignments = _extract_pred_assignments_from_specs(spec_texts)

    # Z3 in-process path: when checker_id == "z3", evaluate S∧R using Z3 without an
    # external binary.  S is given by Pred_*(a) == TRUE/FALSE definitions in spec files.
    # The check parses the Obligation line of the lowered module; a vacuous Obligation
    # (Obligation == TRUE) returns "unknown" — not a false "valid" — preserving honesty.
    if execution.checker_id == "z3":
        z3_outcome = _z3_check_obligation_under_s(lowered.content, pred_assignments)
        solver_status: Literal["valid", "counterexample", "timeout", "unsupported", "invalid"] = (
            z3_outcome if z3_outcome in {"valid", "counterexample"} else "unsupported"
        )
        # In-process Z3 is a propositional SMT check, not a bounded model checker.
        # Use SMT_CHECKED (not BOUNDED_CHECKED) to reflect the actual verification method.
        z3_evidence = EvidenceLevel.SMT_CHECKED if solver_status == "valid" else None
        return _solver_result(
            requirement.requirement_id,
            solver_status,
            spec_ids,
            {
                "mode": "solver_backed",
                "checker_id": "z3",
                "z3_outcome": z3_outcome,
                "obligation_pred_count": len(parse_obligation_predicates(lowered.content)),
                "s_pred_count": len(pred_assignments),
                "spec_hashes": {
                    spec_id: sha256_text(text) for spec_id, text in spec_texts
                },
            },
            evidence_level=z3_evidence,
        )

    # External-checker path: compose the reviewed system spec S into the lowered
    # requirement R and check S ∧ R with a real model checker (PB-1). The composition
    # binds S's concrete predicate definitions onto R's abstract premise predicates and
    # conjoins R's obligation with S's named invariants — replacing the prior
    # `SystemSpecAssumptions == TRUE` tautology. A composition that would be vacuous or
    # ill-formed refuses with a named reason instead of running a meaningless check.
    #
    # When S brings its own transition system, the composition narrows S: it needs the
    # requirement's obligation predicate to constrain S's reachable states, derived here from the
    # IR by claim class. An authorization_precondition yields the forbidden-outcome predicate
    # (``Pred_<action>``, negated into Inv); a state_postcondition yields the affirmed post-state
    # (``Pred_<state>(<value>)``). A malformed/unsupported shape leaves the obligation None, and the
    # stateful-S narrowing then refuses honestly rather than running a meaningless check.
    claim_class = requirement.semantic_ir.metadata.get("requirement_class")
    outcome_predicate = None
    post_state_obligation = None
    numeric_invariant_obligation = None
    if claim_class == "state_postcondition":
        post_state_obligation = _derive_post_state_obligation(requirement)
    elif claim_class == "numeric_invariant":
        # numeric_invariant yields a numeric invariant (``Premise => Obligation``) over a state
        # variable the reviewed S declares and evolves; the narrowing conjoins it into Inv as a
        # same-state property (no Pred_*, no ghost). See compose_s_and_r_module.
        numeric_invariant_obligation = _derive_numeric_invariant_obligation(requirement)
    else:
        outcome_predicate = _derive_outcome_predicate(requirement)
    module_name = _safe_tla_name(f"{requirement.requirement_id}_S_AND_R")
    composed = compose_s_and_r_module(
        module_name,
        lowered.content,
        _system_spec_contributions(specs, spec_texts),
        outcome_predicate=outcome_predicate,
        post_state_obligation=post_state_obligation,
        numeric_invariant_obligation=numeric_invariant_obligation,
    )
    if composed.status == "refused" or composed.module_text is None:
        return _solver_result(
            requirement.requirement_id,
            "unsupported",
            spec_ids,
            {
                "mode": "solver_backed",
                "checker_id": execution.checker_id,
                "reason": composed.refusal_reason
                or "S ∧ R composition refused",
                "refusal_kind": composed.refusal_kind,
                "s_pred_count": len(pred_assignments),
                "spec_count": len(spec_texts),
                "spec_hashes": {
                    spec_id: sha256_text(text) for spec_id, text in spec_texts
                },
            },
        )

    artifact_dir = _solver_artifact_dir(requirement, execution)
    artifact_dir.mkdir(parents=True, exist_ok=True)
    module_path = artifact_dir / f"{module_name}.tla"
    config_path = artifact_dir / f"{module_name}.cfg"
    module_path.write_text(composed.module_text)
    # The composed module's checkable operators (consumed by the checker via CLI flags or,
    # for TLC, this config): Init / Next as the transition system, Inv as the conjoined
    # S ∧ R state invariant, ConstInit pinning identifier constants.
    config_path.write_text("INIT Init\nNEXT Next\nINVARIANT Inv\n")

    # One effective budget is the single source of truth: its max_depth renders the command's
    # --length AND is recorded in bounds, so a run cannot claim a depth it did not search.
    runner_budget = _runner_budget(budget)
    command = _solver_checker_command(
        execution, module_path, config_path, module_name, max_depth=runner_budget.max_depth
    )
    runner_result = run_model_checker(
        ModelCheckerCommand(
            run_id=f"{requirement.requirement_id}:s-and-r",
            checker_id=execution.checker_id,
            command=command,
            cwd=artifact_dir.as_posix(),
            budget=runner_budget,
            expected_exit_code=execution.expected_exit_code,
            tool_version=execution.tool_version,
            tool_version_command=(
                execution.tool_version_command
                or _default_version_command(execution.checker_id)
            ),
            output_limit_bytes=execution.output_limit_bytes,
        )
    )
    status = _solver_status_for_runner(runner_result.outcome)
    counterexamples = _solver_counterexamples(requirement.requirement_id, runner_result)
    details = {
        "mode": "solver_backed",
        "checker_id": execution.checker_id,
        "runner_outcome": runner_result.outcome,
        "runner_result_hash": sha256_json(runner_result),
        "artifact_dir": artifact_dir.as_posix(),
        "module": module_path.name,
        "module_hash": sha256_text(module_path.read_text()),
        "config": config_path.name,
        "config_hash": sha256_text(config_path.read_text()),
        "command": command,
        "reproducibility": runner_result.reproducibility.model_dump(
            mode="json", exclude_none=True
        ),
        "bounds": runner_budget.model_dump(mode="json", exclude_none=True),
        "preserved_invariants": composed.preserved_invariants,
        "bound_predicates": composed.bound_predicates,
        "bound_state_invariants": composed.bound_state_invariants,
        "spec_hashes": {
            spec_id: sha256_text(text)
            for spec_id, text in spec_texts
        },
        "counterexamples": [
            item.model_dump(mode="json", exclude_none=True)
            for item in counterexamples
        ],
        "stdout": runner_result.stdout.model_dump(mode="json"),
        "stderr": runner_result.stderr.model_dump(mode="json"),
        "unsupported_markers": runner_result.unsupported_markers,
        "tool_error": runner_result.tool_error,
    }
    # Record the exact post-state value the narrowing checked so coverage can be value-EXACT: a
    # bounded verdict for one value (e.g. "accepted") must not be re-tagged as covering a post_state
    # fragment demanding a different value (e.g. "rejected") that shares the same Pred_<state>
    # operator. Only emitted for a state_postcondition (an auth result has no post-state value).
    if post_state_obligation is not None:
        details["bound_post_state_value"] = post_state_obligation.value_literal
    return _solver_result(
        requirement.requirement_id,
        status,
        spec_ids,
        details,
        counterexamples=counterexamples,
    )


def not_applicable_system_consistency(
    *,
    requirement: RequirementIRV2,
    registry: SystemSpecRegistry,
    impact: ImpactAnalysisArtifact,
) -> SystemConsistencyResult:
    """S ∧ R is not-applicable: no reviewed spec is relevant to the impacted modules, so
    there is no system spec ``S`` to conjoin and nothing to discharge.

    This is decided structurally from the registry — not from the absence of a marker in a
    spec file. The recorded BackendResult uses ``status="unsupported"`` (its status enum has
    no not-applicable value) and carries ``details["mode"] == "not_applicable"``; the gate
    reads that mode as a non-blocking stage, kept distinct from an ``unsupported`` produced
    because a real S could not be grounded (undefined predicate, stale spec) or because a
    relevant S declares no invariant (see
    :func:`unsupported_system_consistency_without_invariant`), both of which block.

    Distinct from "a relevant spec declares no invariant": a spec governing the impacted
    modules that asserts nothing checkable is a real S we refuse to silently accept (it
    blocks), whereas *no relevant spec at all* genuinely leaves S ∧ R with no obligation.
    """
    spec_ids = [spec.spec_id for spec in specs_for_impact(registry, impact)]
    return SystemConsistencyResult(
        requirement_id=requirement.requirement_id,
        spec_ids=spec_ids,
        result=BackendResult(
            backend="solver_system_checker",
            status="unsupported",
            evidence_level=None,
            details={
                "mode": "not_applicable",
                "reason": (
                    "no reviewed system spec is relevant to the impacted modules; there is "
                    "no S to conjoin, so S ∧ R has no obligation to discharge"
                ),
                "relevant_spec_ids": spec_ids,
            },
        ),
    )


def unsupported_system_consistency_without_invariant(
    *,
    requirement: RequirementIRV2,
    registry: SystemSpecRegistry,
    impact: ImpactAnalysisArtifact,
) -> SystemConsistencyResult:
    """A reviewed spec governs the impacted modules but declares no invariant, so no S ∧ R
    obligation can be formed from it — the requirement is refused, not silently accepted.

    This BLOCKS (``status="unsupported"``, ``evidence_level=None``). A reviewed spec relevant
    to the change that asserts nothing checkable cannot be passed: a reviewed S with no
    declared invariant cannot yield a valid S ∧ R, so a vacuous pass is refused. Carries
    ``details["mode"] == "relevant_spec_without_invariant"`` so the refusal reason is explicit.

    Kept distinct from :func:`not_applicable_system_consistency` (no reviewed spec is relevant
    at all — non-blocking) and from an ``unsupported`` produced because a grounded S could not
    be checked (stale spec, undefined predicate, solver refusal — also blocking, but for a
    spec that did declare an invariant).
    """
    spec_ids = [spec.spec_id for spec in specs_for_impact(registry, impact)]
    return SystemConsistencyResult(
        requirement_id=requirement.requirement_id,
        spec_ids=spec_ids,
        result=BackendResult(
            backend="solver_system_checker",
            status="unsupported",
            evidence_level=None,
            details={
                "mode": "relevant_spec_without_invariant",
                "reason": (
                    "a reviewed system spec governs the impacted modules but declares no "
                    "invariant; S ∧ R has no obligation to form, so the requirement cannot be "
                    "verified against the system and is refused (not silently accepted)"
                ),
                "relevant_spec_ids": spec_ids,
            },
        ),
    )


def check_requirement_set_consistency(
    requirements: list[RequirementIRV2],
) -> RequirementSetConsistencyReport:
    """Cross-requirement consistency decided over typed ``FormalClaim`` fragments.

    Each requirement is lowered to a ``FormalClaim`` and the deterministic taxonomy
    (:func:`nlreq.contradiction_taxonomy.detect_cross_requirement_contradictions`) compares the
    *obligations* of every pair of requirements whose premises provably co-occur on a shared scope.
    Opposite premises across requirements are the two halves of a complete specification, not a
    contradiction, so they are never flagged. A requirement that cannot be lowered is skipped here —
    its lowering refusal is surfaced by ``build_formal_claim`` itself — rather than silently treated
    as consistent with the rest.
    """
    # Local import: formal_claim's module transitively imports this one, so importing it at module
    # scope would close an initialization cycle. At call time every module is fully loaded.
    from .formal_claim import build_formal_claim

    claims = []
    for requirement in requirements:
        report = build_formal_claim(requirement)
        if report.result == "lowered" and report.formal_claim is not None:
            claims.append(report.formal_claim)
    contradictions = detect_cross_requirement_contradictions(claims)
    return RequirementSetConsistencyReport(
        result="contradiction" if contradictions else "valid",
        contradictions=contradictions,
    )


def _system_result(
    requirement_id: str,
    status: Literal["valid", "counterexample", "timeout", "unsupported"],
    spec_ids: list[str],
    details: dict[str, object],
) -> SystemConsistencyResult:
    return SystemConsistencyResult(
        requirement_id=requirement_id,
        spec_ids=spec_ids,
        result=BackendResult(
            backend="system_checker",
            status=status,
            evidence_level=EvidenceLevel.CONSISTENCY_CHECKED if status == "valid" else None,
            details=details,
        ),
    )


def _solver_result(
    requirement_id: str,
    status: Literal["valid", "counterexample", "timeout", "unsupported", "invalid"],
    spec_ids: list[str],
    details: dict[str, object],
    *,
    counterexamples: list[Counterexample] | None = None,
    evidence_level: EvidenceLevel | None = None,
) -> SystemConsistencyResult:
    # Default: BOUNDED_CHECKED for external model-checker runs (Apalache/TLC with depth), but
    # only when the run recorded its full bounded backing — the bounds it searched, the checker
    # command, and the version of the checker the run resolved (see
    # ``models.bounded_evidence_backing_complete``). A valid run that recorded no bounds, no
    # command, or no run version (a stub, or a tool that resolved no version) has no backing for
    # a bounded claim, so it self-gates to None/unverified rather than over-claim. The real
    # Apalache/TLC S ∧ R path records the command top-level and the version under
    # ``reproducibility``, so it stays BOUNDED_CHECKED. Callers that use an in-process SMT solver
    # (checker_id="z3") pass evidence_level=EvidenceLevel.SMT_CHECKED to avoid conflating
    # bounded-MC evidence with propositional satisfiability evidence.
    resolved_evidence = (
        evidence_level if evidence_level is not None
        else (
            EvidenceLevel.BOUNDED_CHECKED
            if status == "valid" and bounded_evidence_backing_complete(details)
            else None
        )
    )
    return SystemConsistencyResult(
        requirement_id=requirement_id,
        spec_ids=spec_ids,
        counterexamples=counterexamples or [],
        result=BackendResult(
            backend="solver_system_checker",
            status=status,
            evidence_level=resolved_evidence,
            details=details,
        ),
    )


def _solver_artifact_dir(
    requirement: RequirementIRV2, execution: FormalBackendExecution
) -> Path:
    if execution.artifact_dir is not None:
        return Path(execution.artifact_dir).resolve(strict=False)
    return (
        Path.cwd()
        / ".nlreq-formal-artifacts"
        / requirement.requirement_id
        / "solver-system-checker"
    ).resolve(strict=False)


def _extract_pred_assignments_from_specs(
    spec_texts: list[tuple[str, str]],
) -> dict[str, bool]:
    """Parse Pred_*(...) == TRUE/FALSE operator definitions from system spec files.

    Enables the Z3 gate path: when specs define predicate operators (e.g. from
    generate_minimal_discriminating_s_module), this function extracts the S assignments
    so _z3_check_obligation_under_s can encode the S∧R check in-process.

    Returns {pred_name: bool_value} for each found definition.  Duplicate definitions
    are last-writer-wins (same as TLA+ module import semantics).
    """
    import re
    pattern = re.compile(r"^\s*(Pred_\w+)\([^)]*\)\s*==\s*(TRUE|FALSE)", re.MULTILINE)
    assignments: dict[str, bool] = {}
    for _spec_id, text in spec_texts:
        for match in pattern.finditer(text):
            assignments[match.group(1)] = match.group(2) == "TRUE"
    return assignments


def _obligation_consequent_is_real(module_text: str) -> bool:
    return obligation_consequent_is_real(module_text)


def _next_has_steps(module_text: str) -> bool:
    return next_has_steps(module_text)


def _z3_check_obligation_under_s(
    lowered_content: str,
    pred_assignments: dict[str, bool],
) -> Literal["valid", "counterexample", "unknown"]:
    """Z3 in-process S∧R check: does the lowered obligation hold under system constraint S?

    SCOPE (structural template check — NOT PA-1 evidence):
    This function encodes Pred_* boolean assignments from S and checks whether the
    violation query (pred=TRUE AND reached_accepted=TRUE) is SAT under those assignments.
    It does NOT evaluate RequirementHolds, real action/state targets, or the full
    composed TLA+ transition system.  It is a structural discriminator useful for
    regression-catching on Pred_* assignments only.  Full bounded evidence comes from an
    Apalache run on the module built by compose_s_and_r_module; this in-process path is
    complementary, not a substitute.

    S is given by pred_assignments (Pred_name → bool).  The obligation predicates are
    parsed from the Obligation == line of the lowered module — not from CONSTANT declarations
    — so a regression that replaces Obligation with TRUE is caught (returns "unknown").

    Also validates structural integrity of the lowered module before encoding Z3 constraints:
      - Obligation must have a real state consequent (NLRState /=), not a vacuous => TRUE.
      - Next must include at least one Step_* action (not just UNCHANGED NLRState).
    Both checks return "unknown" on failure so no false-positive "valid" is emitted for
    a structurally defective module.

    Under S (pred = FALSE for R):
      Violation query: pred=TRUE AND reached=TRUE.
      S forces pred=FALSE; violation requires pred=TRUE → contradiction → UNSAT → "valid".

    Under S (pred = TRUE for ¬R):
      Violation query: pred=TRUE AND reached=TRUE.
      S has pred=TRUE (consistent with violation) and reached is unconstrained → SAT → "counterexample".

    Returns "unknown" when:
      - The Obligation line is absent or vacuous (Obligation == TRUE regression).
      - The obligation consequent is vacuous (=> TRUE mutation).
      - Next has no Step_* transitions (UNCHANGED-only regression).
      - Not all obligation predicates have assignments in pred_assignments.
    """
    from z3 import Bool, BoolVal, Solver, sat, unsat

    obligation_preds = parse_obligation_predicates(lowered_content)
    if not obligation_preds:
        return "unknown"

    if not _obligation_consequent_is_real(lowered_content):
        return "unknown"

    if not _next_has_steps(lowered_content):
        return "unknown"

    if not all(name in pred_assignments for name in obligation_preds):
        return "unknown"

    pred_bools = {name: Bool(name) for name in obligation_preds}
    reached = Bool("nlr_reached_accepted")
    s = Solver()

    for name, val in pred_assignments.items():
        if name in pred_bools:
            s.add(pred_bools[name] == BoolVal(val))

    for name in obligation_preds:
        s.add(pred_bools[name])
    s.add(reached)

    result = s.check()
    if result == unsat:
        return "valid"
    if result == sat:
        return "counterexample"
    return "unknown"


def _system_spec_contributions(specs, spec_texts: list[tuple[str, str]]):
    """Build the S ∧ R composition inputs from reviewed system spec entries.

    Pairs each spec entry with its file text and declared invariant operators so
    compose_s_and_r_module can inline the spec's predicate definitions and conjoin
    its invariants. Specs whose text was not read (e.g. missing file) are skipped;
    upstream freshness gating already refuses missing specs before this point.
    """
    text_by_id = dict(spec_texts)
    return [
        build_system_spec_contribution(
            spec.spec_id,
            text_by_id[spec.spec_id],
            spec.invariants,
            init_op=spec.init_op,
            next_op=spec.next_op,
        )
        for spec in specs
        if spec.spec_id in text_by_id
    ]


def _derive_outcome_predicate(requirement: RequirementIRV2) -> OutcomePredicate | None:
    """Derive the requirement's forbidden-outcome predicate, or None for an unsupported shape.

    The stateful-S narrowing needs ``Pred_<action>`` to constrain S's reachable states.
    A requirement whose obligation is not a supported authorization_precondition shape has
    no such predicate; returning None lets the narrowing refuse honestly rather than raise.
    """
    try:
        return derive_outcome_predicate(requirement.semantic_ir)
    except (ValueError, AttributeError):
        return None


def _derive_post_state_obligation(requirement: RequirementIRV2) -> PostStateObligation | None:
    """Derive the requirement's affirmed post-state obligation, or None for an unsupported shape.

    The stateful-S narrowing needs ``Pred_<state>(<value>)`` to constrain S's reachable states for a
    state_postcondition. A requirement whose obligation is not a supported post_state shape has no
    such predicate; returning None lets the narrowing refuse honestly rather than raise.
    """
    try:
        return derive_post_state_obligation(requirement.semantic_ir)
    except (ValueError, AttributeError):
        return None


def _derive_numeric_invariant_obligation(
    requirement: RequirementIRV2,
) -> NumericInvariantObligation | None:
    """Derive the requirement's numeric invariant (``Premise => Obligation``), or None for an
    unsupported shape.

    The stateful-S narrowing needs the obligation comparison over a state variable to constrain S's
    reachable states for a numeric_invariant. A requirement whose shape is not a supported numeric
    invariant has none; returning None lets the narrowing refuse honestly rather than raise. (On the
    solver path the lowering has already validated the shape, so this normally succeeds.)
    """
    if validate_numeric_invariant_shape(requirement.semantic_ir):
        return None
    try:
        return derive_numeric_invariant_obligation(requirement.semantic_ir)
    except (ValueError, AttributeError):
        return None


# Version commands for the pinned backends (docs/formal-backend-guide.md). The runner
# executes these to record the resolved tool version in the run's reproducibility metadata,
# so a bounded result always carries the exact checker it was produced by. Unknown checker
# ids (e.g. a test stub) get no default — their version stays whatever the caller supplied.
_DEFAULT_VERSION_COMMANDS: dict[str, list[str]] = {
    "apalache": ["apalache-mc", "version"],
}


def _default_version_command(checker_id: str) -> list[str] | None:
    """Return the pinned version command for a known checker, or None for an unknown one."""
    return _DEFAULT_VERSION_COMMANDS.get(checker_id)


def _solver_checker_command(
    execution: FormalBackendExecution,
    module_path: Path,
    config_path: Path,
    module_name: str,
    *,
    max_depth: int,
) -> list[str]:
    command = execution.command or ["tlc2.TLC", "-config", config_path.name, module_path.name]
    # ``{max_depth}`` renders the bounded-search depth from the *same* effective budget that is
    # recorded in ``bounds``, so the depth the checker searches (``--length``) can never disagree
    # with the depth the run claims. A custom command without the token simply ignores it.
    replacements = {
        "{module}": module_path.name,
        "{config}": config_path.name,
        "{module_name}": module_name,
        "{max_depth}": str(max_depth),
    }
    rendered: list[str] = []
    for part in command:
        value = part
        for token, replacement in replacements.items():
            value = value.replace(token, replacement)
        rendered.append(value)
    return rendered


def _runner_budget(budget: FormalBackendBudget | None) -> ModelCheckerBudget:
    # The effective S ∧ R budget. ``max_depth`` always resolves to a concrete value
    # (DEFAULT_S_AND_R_DEPTH when the caller supplies none) because it is the single source of
    # truth for both the rendered ``--length`` and the recorded ``bounds.max_depth``; leaving it
    # None would let the command's depth and the claimed depth drift apart.
    if budget is None:
        return ModelCheckerBudget(timeout_seconds=120, max_depth=DEFAULT_S_AND_R_DEPTH)
    return ModelCheckerBudget(
        timeout_seconds=budget.timeout_seconds or 120,
        max_depth=budget.max_depth or DEFAULT_S_AND_R_DEPTH,
        max_states=budget.max_states,
        memory_budget_mb=budget.memory_budget_mb,
        solver_options=budget.solver_options,
    )


def _solver_status_for_runner(outcome: str) -> Literal["valid", "counterexample", "timeout", "unsupported", "invalid"]:
    if outcome == "tool_error":
        return "invalid"
    if outcome in {"valid", "counterexample", "timeout", "unsupported"}:
        return outcome
    return "invalid"


def _solver_counterexamples(requirement_id: str, runner_result) -> list[Counterexample]:
    if runner_result.outcome != "counterexample":
        return []
    return [
        Counterexample(
            counterexample_id=f"{requirement_id}:solver:{index}",
            backend="solver_system_checker",
            claim_id=requirement_id,
            description="solver-backed S-and-R checker produced a counterexample",
            metadata=item.model_dump(mode="json", exclude_none=True),
        )
        for index, item in enumerate(runner_result.counterexamples, start=1)
    ]


def _safe_tla_name(value: str) -> str:
    cleaned = "".join(char if char.isalnum() else "_" for char in value)
    if not cleaned:
        return "Requirement"
    if cleaned[0].isdigit():
        return "_" + cleaned
    return cleaned
