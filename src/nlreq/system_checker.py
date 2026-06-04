from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from .formal_backend import FormalBackendBudget, FormalBackendExecution
from .formal_lowering import (
    obligation_consequent_is_real,
    next_has_steps,
    parse_obligation_predicates,
)
from .jsonutil import sha256_json, sha256_text
from .model_checker_runner import (
    ModelCheckerBudget,
    ModelCheckerCommand,
    run_model_checker,
)
from .models import BackendResult, Counterexample, EvidenceLevel, Predicate, RequirementIR, RequirementIRV2, SourceSpan
from .system_spec import SystemSpecRegistry, build_system_spec_registry_report, specs_for_impact
from .impact import ImpactAnalysisArtifact
from .translator import LoweredFormalArtifact


SYSTEM_CHECKER_SCHEMA_VERSION = "0.1"


class SystemConsistencyResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["0.1"] = SYSTEM_CHECKER_SCHEMA_VERSION
    requirement_id: str
    result: BackendResult
    counterexamples: list[Counterexample] = Field(default_factory=list)
    spec_ids: list[str] = Field(default_factory=list)


class RequirementContradiction(BaseModel):
    model_config = ConfigDict(extra="forbid")

    contradiction_type: Literal["opposite_predicate"]
    requirement_ids: list[str]
    fragments: list[str]
    source_spans: list[SourceSpan] = Field(default_factory=list)


class RequirementSetConsistencyReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["0.1"] = SYSTEM_CHECKER_SCHEMA_VERSION
    result: Literal["valid", "contradiction"]
    contradictions: list[RequirementContradiction] = Field(default_factory=list)


def check_system_consistency(
    *,
    requirement: RequirementIRV2,
    lowered: LoweredFormalArtifact,
    registry: SystemSpecRegistry,
    impact: ImpactAnalysisArtifact,
    project_root: Path,
) -> SystemConsistencyResult:
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

    # External-checker path: real S∧R composition requires inlining S operator definitions
    # into the composed module.  Until PB-4 implements proper composition, refuse whenever
    # relevant system spec files exist — not only when they happen to define the simple
    # Pred_*(...) == TRUE/FALSE pattern.  Any other TLA+ constraint in a spec file would
    # still be composed with SystemSpecAssumptions == TRUE (a tautology that proves nothing).
    if spec_texts:
        return _solver_result(
            requirement.requirement_id,
            "unsupported",
            spec_ids,
            {
                "mode": "solver_backed",
                "checker_id": execution.checker_id,
                "reason": (
                    "system spec files cannot be inlined into the composed TLA+ module; "
                    "real S∧R composition is pending PB-4"
                ),
                "s_pred_count": len(pred_assignments),
                "spec_count": len(spec_texts),
                "spec_hashes": {
                    spec_id: sha256_text(text) for spec_id, text in spec_texts
                },
            },
        )

    artifact_dir = _solver_artifact_dir(requirement, execution)
    artifact_dir.mkdir(parents=True, exist_ok=True)
    module_name = _safe_tla_name(f"{requirement.requirement_id}_S_AND_R")
    module_path = artifact_dir / f"{module_name}.tla"
    config_path = artifact_dir / f"{module_name}.cfg"
    module_path.write_text(_composed_tla_module(module_name, lowered, spec_texts))
    config_path.write_text("INIT Init\nNEXT Next\nPROPERTY SystemAndRequirement\n")

    command = _solver_checker_command(execution, module_path, config_path, module_name)
    runner_result = run_model_checker(
        ModelCheckerCommand(
            run_id=f"{requirement.requirement_id}:s-and-r",
            checker_id=execution.checker_id,
            command=command,
            cwd=artifact_dir.as_posix(),
            budget=_runner_budget(budget),
            expected_exit_code=execution.expected_exit_code,
            tool_version=execution.tool_version,
            tool_version_command=execution.tool_version_command,
            output_limit_bytes=execution.output_limit_bytes,
        )
    )
    status = _solver_status_for_runner(runner_result.outcome)
    counterexamples = _solver_counterexamples(requirement.requirement_id, runner_result)
    return _solver_result(
        requirement.requirement_id,
        status,
        spec_ids,
        {
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
            "bounds": _budget_details(budget),
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
        },
        counterexamples=counterexamples,
    )


def check_requirement_set_consistency(requirements: list[RequirementIR]) -> RequirementSetConsistencyReport:
    contradictions: list[RequirementContradiction] = []
    seen: dict[tuple[str, tuple[str, ...]], tuple[str, Predicate]] = {}
    opposites = {
        "authorized": "not_authorized",
        "not_authorized": "authorized",
        "approved": "not_approved",
        "not_approved": "approved",
        "eq": "neq",
        "neq": "eq",
    }
    for ir in requirements:
        for predicate in ir.claim.condition:
            args = tuple(str(arg.value) for arg in predicate.args)
            opposite = (opposites.get(predicate.op, ""), args)
            if opposite in seen:
                other_id, other_predicate = seen[opposite]
                contradictions.append(
                    RequirementContradiction(
                        contradiction_type="opposite_predicate",
                        requirement_ids=[other_id, ir.requirement_id],
                        fragments=[other_predicate.source_span.text, predicate.source_span.text],
                        source_spans=[other_predicate.source_span, predicate.source_span],
                    )
                )
            seen[(predicate.op, args)] = (ir.requirement_id, predicate)
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
    # Default: BOUNDED_CHECKED for external model-checker runs (Apalache/TLC with depth).
    # Callers that use an in-process SMT solver (checker_id="z3") should pass
    # evidence_level=EvidenceLevel.SMT_CHECKED to avoid conflating bounded-MC evidence
    # with propositional satisfiability evidence.
    resolved_evidence = (
        evidence_level if evidence_level is not None
        else (EvidenceLevel.BOUNDED_CHECKED if status == "valid" else None)
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


def _composed_tla_module(
    module_name: str,
    lowered: LoweredFormalArtifact,
    spec_texts: list[tuple[str, str]],
) -> str:
    body = _strip_tla_module_wrapper(lowered.content or "")
    spec_hashes = "\n".join(
        f"\\* System spec {spec_id}: {sha256_text(text)}" for spec_id, text in spec_texts
    )
    # Document the S predicate assignments (if any) from spec files.
    # The Z3 gate path uses these to run S∧R in-process; TLC/Apalache paths
    # use them as documentation — the full inline composition requires PB-4.
    pred_assignments = _extract_pred_assignments_from_specs(spec_texts)
    if pred_assignments:
        s_comment_lines = "\n".join(
            f"\\*   {name}(a) == {'TRUE' if val else 'FALSE'}"
            for name, val in sorted(pred_assignments.items())
        )
        s_block = f"\\* System constraint S from spec files:\n{s_comment_lines}\n"
    else:
        s_block = ""
    return (
        f"---- MODULE {module_name} ----\n"
        f"{spec_hashes}\n"
        f"{s_block}\n"
        f"{body}\n\n"
        "SystemSpecAssumptions == TRUE\n"
        "SystemAndRequirement == SystemSpecAssumptions => RequirementHolds\n\n"
        "====\n"
    )


def _strip_tla_module_wrapper(content: str) -> str:
    lines = content.splitlines()
    if lines and lines[0].startswith("---- MODULE "):
        lines = lines[1:]
    if lines and lines[-1] == "====":
        lines = lines[:-1]
    return "\n".join(lines).strip()


def _solver_checker_command(
    execution: FormalBackendExecution,
    module_path: Path,
    config_path: Path,
    module_name: str,
) -> list[str]:
    command = execution.command or ["tlc2.TLC", "-config", config_path.name, module_path.name]
    replacements = {
        "{module}": module_path.name,
        "{config}": config_path.name,
        "{module_name}": module_name,
    }
    rendered: list[str] = []
    for part in command:
        value = part
        for token, replacement in replacements.items():
            value = value.replace(token, replacement)
        rendered.append(value)
    return rendered


def _runner_budget(budget: FormalBackendBudget | None) -> ModelCheckerBudget:
    if budget is None:
        return ModelCheckerBudget(timeout_seconds=120)
    return ModelCheckerBudget(
        timeout_seconds=budget.timeout_seconds or 120,
        max_depth=budget.max_depth,
        max_states=budget.max_states,
        memory_budget_mb=budget.memory_budget_mb,
        solver_options=budget.solver_options,
    )


def _budget_details(budget: FormalBackendBudget | None) -> dict[str, object]:
    return _runner_budget(budget).model_dump(mode="json", exclude_none=True)


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
