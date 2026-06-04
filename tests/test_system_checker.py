import json
import shutil
import sys
from pathlib import Path

import pytest

from nlreq.cli import main
from nlreq.dsl_v2 import DslV2Parser
from nlreq.formal_backend import FormalBackendBudget, FormalBackendExecution
from nlreq.formal_lowering import build_system_spec_contribution, compose_s_and_r_module
from nlreq.impact import ImpactAnalysisArtifact
from nlreq.models import RequirementIR
from nlreq.parser import RequirementParser
from nlreq.system_checker import (
    check_requirement_set_consistency,
    check_solver_backed_system_consistency,
    check_system_consistency,
)
from nlreq.system_spec import SystemSpecRegistry
from nlreq.translator import LoweredFormalArtifact, lower_ir_v2_to_tla


DSL = (
    "For every redemption:\n"
    "when wallet is authorized\n"
    "and requested_amount <= spendable_balance\n"
    "then finalize_redemption must emit redemption_finalized within 6 hours.\n"
)


def test_system_consistency_returns_valid_for_fresh_specs_and_lowered_requirement(
    tmp_path: Path,
) -> None:
    result = check_system_consistency(
        requirement=_ir(),
        lowered=lower_ir_v2_to_tla(_ir()),
        registry=_registry(tmp_path),
        impact=_impact(),
        project_root=tmp_path,
    )

    assert result.result.status == "valid"
    assert result.result.evidence_level == "CONSISTENCY_CHECKED"


def test_system_consistency_returns_counterexample_marker(tmp_path: Path) -> None:
    result = check_system_consistency(
        requirement=_ir(),
        lowered=lower_ir_v2_to_tla(_ir()),
        registry=_registry(tmp_path, marker="\\* NLREQ_COUNTEREXAMPLE:REQ-SYS-001\n"),
        impact=_impact(),
        project_root=tmp_path,
    )

    assert result.result.status == "counterexample"
    assert result.counterexamples[0].metadata["spec_id"] == "spec:redemption"


def test_system_consistency_returns_timeout_marker(tmp_path: Path) -> None:
    result = check_system_consistency(
        requirement=_ir(),
        lowered=lower_ir_v2_to_tla(_ir()),
        registry=_registry(tmp_path, marker="\\* NLREQ_TIMEOUT\n"),
        impact=_impact(),
        project_root=tmp_path,
    )

    assert result.result.status == "timeout"


def test_system_consistency_returns_unsupported_for_stale_spec(tmp_path: Path) -> None:
    registry = _registry(tmp_path)
    data = registry.model_dump(mode="json")
    data["specs"][0]["freshness"] = "stale"

    result = check_system_consistency(
        requirement=_ir(),
        lowered=lower_ir_v2_to_tla(_ir()),
        registry=SystemSpecRegistry.model_validate(data),
        impact=_impact(),
        project_root=tmp_path,
    )

    assert result.result.status == "unsupported"


def test_system_consistency_returns_unsupported_for_refused_lowering(tmp_path: Path) -> None:
    lowered = lower_ir_v2_to_tla(_ir())
    refused = LoweredFormalArtifact.model_validate(
        lowered.model_copy(update={"status": "refused", "content": None, "content_hash": None})
        .model_dump(mode="json", exclude_none=True)
    )

    result = check_system_consistency(
        requirement=_ir(),
        lowered=refused,
        registry=_registry(tmp_path),
        impact=_impact(),
        project_root=tmp_path,
    )

    assert result.result.status == "unsupported"


def test_requirement_set_consistency_detects_opposite_predicates() -> None:
    parser = RequirementParser()
    approved = parser.parse_ir(
        "For every operation request:\n"
        "if actor is approved\n"
        "then operation must succeed.\n",
        requirement_id="REQ-APPROVED",
        title="Approved",
        claim_kind="state_precondition",
    )
    not_approved = parser.parse_ir(
        "For every operation request:\n"
        "if actor is not approved\n"
        "then operation must be rejected.\n",
        requirement_id="REQ-NOT-APPROVED",
        title="Not approved",
        claim_kind="state_precondition",
    )

    report = check_requirement_set_consistency([approved, not_approved])

    assert report.result == "contradiction"
    assert report.contradictions[0].contradiction_type == "opposite_predicate"


# ---------------------------------------------------------------------------
# PB-1 solver-backed S ∧ R: a real reviewed spec S is composed into the lowered
# requirement R and a real model checker verifies S ∧ R. The reviewed S pins the
# authorization predicates R leaves abstract (the shared-predicate coupling that
# makes the check non-vacuous) and declares a named system invariant.
# ---------------------------------------------------------------------------

APALACHE = shutil.which("apalache-mc")

_APALACHE_COMMAND = [
    "apalache-mc",
    "check",
    "--cinit=ConstInit",
    "--init=Init",
    "--next=Next",
    "--inv=Inv",
    "--length=6",
    "{module}",
]


def _reviewed_s_spec_text() -> str:
    """Reviewed system spec S: interprets both authorization predicates and declares
    a named system invariant, so the composed S ∧ R is grounded and non-vacuous."""
    return (
        "---- MODULE RedemptionSystem ----\n"
        "\\* @type: (Str) => Bool;\n"
        "Pred_authorized(a) == FALSE\n"
        "\\* @type: (Str) => Bool;\n"
        "Pred_not_authorized(a) == TRUE\n"
        "\\* System invariant: authorization defaults closed.\n"
        'SystemDefaultsClosed == Pred_authorized("wallet") = FALSE\n'
        "====\n"
    )


def _reviewed_s_registry(
    tmp_path: Path,
    *,
    spec_text: str | None = None,
    invariants: tuple[str, ...] = ("SystemDefaultsClosed",),
) -> SystemSpecRegistry:
    specs = tmp_path / "specs"
    specs.mkdir(exist_ok=True)
    (specs / "RedemptionSystem.tla").write_text(
        spec_text if spec_text is not None else _reviewed_s_spec_text()
    )
    return SystemSpecRegistry.model_validate(
        {
            "schema_version": "0.1",
            "specs": [
                {
                    "spec_id": "spec:redemption",
                    "module_ids": ["redemption"],
                    "formalism": "tla",
                    "path": "specs/RedemptionSystem.tla",
                    "version": "1",
                    "review_status": "reviewed",
                    "freshness": "fresh",
                    "invariants": list(invariants),
                }
            ],
        }
    )


@pytest.mark.skipif(APALACHE is None, reason="apalache-mc binary not installed")
def test_solver_backed_s_and_r_compatible_requirement_is_valid(tmp_path: Path) -> None:
    """SP2-B: a requirement compatible with S yields a real Apalache 'valid'.

    R's premise is Pred_authorized, which S pins FALSE; the obligation is vacuously
    satisfied, so no reachable state violates the conjoined invariant.
    """
    ir = _authz_ir()
    result = check_solver_backed_system_consistency(
        requirement=ir,
        lowered=lower_ir_v2_to_tla(ir),
        registry=_reviewed_s_registry(tmp_path),
        impact=_authz_impact(),
        project_root=tmp_path,
        budget=FormalBackendBudget(timeout_seconds=60, max_depth=6),
        execution=FormalBackendExecution(
            checker_id="apalache",
            command=_APALACHE_COMMAND,
            artifact_dir=(tmp_path / "artifacts").as_posix(),
        ),
    )

    assert result.result.status == "valid", result.result.details
    assert result.result.backend == "solver_system_checker"
    assert result.result.evidence_level.value == "BOUNDED_CHECKED"
    assert "RequirementHolds" in result.result.details["preserved_invariants"]
    assert "SystemDefaultsClosed" in result.result.details["preserved_invariants"]
    assert result.result.details["bound_predicates"] == ["Pred_authorized"]


@pytest.mark.skipif(APALACHE is None, reason="apalache-mc binary not installed")
def test_solver_backed_s_and_r_contradicting_requirement_is_counterexample(
    tmp_path: Path,
) -> None:
    """SP2-B: a requirement that contradicts S yields a real Apalache counterexample.

    ¬R's premise is Pred_not_authorized, which S pins TRUE; the obligation fires and
    the transition system reaches "accepted", violating the conjoined invariant.
    Same S as the compatible-sibling test — the only change is the requirement.
    """
    ir = _negation_ir()
    result = check_solver_backed_system_consistency(
        requirement=ir,
        lowered=lower_ir_v2_to_tla(ir),
        registry=_reviewed_s_registry(tmp_path),
        impact=_authz_impact(),
        project_root=tmp_path,
        budget=FormalBackendBudget(timeout_seconds=60, max_depth=6),
        execution=FormalBackendExecution(
            checker_id="apalache",
            command=_APALACHE_COMMAND,
            artifact_dir=(tmp_path / "artifacts").as_posix(),
        ),
    )

    assert result.result.status == "counterexample", result.result.details
    assert result.counterexamples
    assert result.counterexamples[0].backend == "solver_system_checker"


def test_solver_backed_refuses_spec_without_declared_invariant(tmp_path: Path) -> None:
    """A reviewed S that declares no invariant cannot make S ∧ R non-trivial — refuse.

    Replaces the prior PB-4 guard: the refusal is now grounded in the composition
    (no system invariant to preserve), not a 'pending implementation' marker.
    """
    ir = _authz_ir()
    result = check_solver_backed_system_consistency(
        requirement=ir,
        lowered=lower_ir_v2_to_tla(ir),
        registry=_reviewed_s_registry(tmp_path, invariants=()),
        impact=_authz_impact(),
        project_root=tmp_path,
        execution=FormalBackendExecution(
            checker_id="custom",
            command=[sys.executable, "-c", "print('verification successful')"],
            artifact_dir=(tmp_path / "artifacts").as_posix(),
        ),
    )

    assert result.result.status == "unsupported"
    assert result.result.details["refusal_kind"] == "no_system_invariant"
    # Refusal happens before composition runs the checker — no artifacts written.
    assert not (tmp_path / "artifacts").exists()


def test_solver_backed_refuses_when_spec_omits_required_predicate(tmp_path: Path) -> None:
    """S declares an invariant but does not interpret the predicate R depends on — refuse.

    Without a concrete Pred_authorized definition the composed module has an undefined
    operator; the composition refuses rather than emit an unrunnable module.
    """
    ir = _authz_ir()
    spec_text = (
        "---- MODULE RedemptionSystem ----\n"
        "SystemSafety == TRUE\n"
        "====\n"
    )
    result = check_solver_backed_system_consistency(
        requirement=ir,
        lowered=lower_ir_v2_to_tla(ir),
        registry=_reviewed_s_registry(
            tmp_path, spec_text=spec_text, invariants=("SystemSafety",)
        ),
        impact=_authz_impact(),
        project_root=tmp_path,
        execution=FormalBackendExecution(
            checker_id="custom",
            command=[sys.executable, "-c", "print('verification successful')"],
            artifact_dir=(tmp_path / "artifacts").as_posix(),
        ),
    )

    assert result.result.status == "unsupported"
    assert result.result.details["refusal_kind"] == "undefined_predicate"
    assert not (tmp_path / "artifacts").exists()


def test_solver_backed_refuses_operator_name_collision(tmp_path: Path) -> None:
    """S declares an operator whose name shadows a requirement operator — refuse.

    Honors the namespacing rule: the requirement projection's operators are not
    silently overridden by a system spec that reuses their names.
    """
    ir = _authz_ir()
    spec_text = (
        "---- MODULE RedemptionSystem ----\n"
        "\\* @type: (Str) => Bool;\n"
        "Pred_authorized(a) == FALSE\n"
        "Obligation == TRUE\n"
        'SystemDefaultsClosed == Pred_authorized("wallet") = FALSE\n'
        "====\n"
    )
    result = check_solver_backed_system_consistency(
        requirement=ir,
        lowered=lower_ir_v2_to_tla(ir),
        registry=_reviewed_s_registry(
            tmp_path, spec_text=spec_text, invariants=("SystemDefaultsClosed",)
        ),
        impact=_authz_impact(),
        project_root=tmp_path,
        execution=FormalBackendExecution(
            checker_id="custom",
            command=[sys.executable, "-c", "print('verification successful')"],
            artifact_dir=(tmp_path / "artifacts").as_posix(),
        ),
    )

    assert result.result.status == "unsupported"
    assert result.result.details["refusal_kind"] == "operator_name_collision"
    assert not (tmp_path / "artifacts").exists()


def test_solver_backed_runs_checker_over_composed_module(tmp_path: Path) -> None:
    """The composed S ∧ R module is written and the checker subprocess runs over it.

    Uses a stub checker (deterministic, tool-free) to exercise the subprocess plumbing
    and artifact recording; the composed module text asserts the tautology is gone.
    """
    ir = _authz_ir()
    result = check_solver_backed_system_consistency(
        requirement=ir,
        lowered=lower_ir_v2_to_tla(ir),
        registry=_reviewed_s_registry(tmp_path),
        impact=_authz_impact(),
        project_root=tmp_path,
        execution=FormalBackendExecution(
            checker_id="custom",
            command=[sys.executable, "-c", "print('verification successful')"],
            artifact_dir=(tmp_path / "artifacts").as_posix(),
        ),
    )

    assert result.result.status == "valid"
    assert result.result.details["mode"] == "solver_backed"
    module_path = tmp_path / "artifacts" / "REQ_SYS_AUTHZ_S_AND_R.tla"
    assert module_path.is_file()
    composed = module_path.read_text()
    assert "Inv == RequirementHolds /\\ SystemDefaultsClosed" in composed
    assert "SystemSpecAssumptions" not in composed
    assert "Pred_authorized(a) == FALSE" in composed


def test_solver_backed_parses_counterexample_from_checker_output(tmp_path: Path) -> None:
    """A counterexample marker in the checker subprocess output maps to a counterexample."""
    ir = _authz_ir()
    result = check_solver_backed_system_consistency(
        requirement=ir,
        lowered=lower_ir_v2_to_tla(ir),
        registry=_reviewed_s_registry(tmp_path),
        impact=_authz_impact(),
        project_root=tmp_path,
        execution=FormalBackendExecution(
            checker_id="custom",
            command=[sys.executable, "-c", "print('Counterexample: state 2 violates property')"],
            artifact_dir=(tmp_path / "artifacts").as_posix(),
        ),
    )

    assert result.result.status == "counterexample"
    assert result.counterexamples[0].backend == "solver_system_checker"
    assert result.counterexamples[0].metadata["marker"] == "counterexample"


def test_solver_backed_system_consistency_blocks_stale_specs_before_execution(
    tmp_path: Path,
) -> None:
    registry = _registry(tmp_path)
    data = registry.model_dump(mode="json")
    data["specs"][0]["freshness"] = "stale"
    artifact_dir = tmp_path / "artifacts"

    result = check_solver_backed_system_consistency(
        requirement=_ir(),
        lowered=lower_ir_v2_to_tla(_ir()),
        registry=SystemSpecRegistry.model_validate(data),
        impact=_impact(),
        project_root=tmp_path,
        execution=FormalBackendExecution(
            checker_id="custom",
            command=[sys.executable, "-c", "raise SystemExit(99)"],
            artifact_dir=artifact_dir.as_posix(),
        ),
    )

    assert result.result.status == "unsupported"
    assert result.result.details["reason"] == "system specs are missing, stale, or unreviewed"
    assert not artifact_dir.exists()


def test_system_consistency_cli(tmp_path: Path, capsys) -> None:
    ir = _ir()
    lowered = lower_ir_v2_to_tla(ir)
    registry = _registry(tmp_path)
    impact = _impact()
    ir_path = tmp_path / "requirement.ir.json"
    lowered_path = tmp_path / "lowered.json"
    registry_path = tmp_path / "registry.json"
    impact_path = tmp_path / "impact.json"
    out = tmp_path / "system-result.json"
    ir_path.write_text(json.dumps(ir.model_dump(mode="json"), indent=2))
    lowered_path.write_text(json.dumps(lowered.model_dump(mode="json", exclude_none=True), indent=2))
    registry_path.write_text(json.dumps(registry.model_dump(mode="json"), indent=2))
    impact_path.write_text(json.dumps(impact.model_dump(mode="json"), indent=2))

    exit_code = main(
        [
            "system-consistency-check",
            "--requirement-ir",
            str(ir_path),
            "--lowered",
            str(lowered_path),
            "--registry",
            str(registry_path),
            "--impact",
            str(impact_path),
            "--project-root",
            str(tmp_path),
            "--out",
            str(out),
        ]
    )

    output = capsys.readouterr().out

    assert exit_code == 0
    assert "System consistency result:" in output
    assert json.loads(out.read_text())["result"]["status"] == "valid"


def test_solver_backed_system_consistency_cli(tmp_path: Path, capsys) -> None:
    ir = _authz_ir()
    lowered = lower_ir_v2_to_tla(ir)
    # A reviewed spec S is composed into R; the stub checker exercises the CLI plumbing
    # over the real composed S ∧ R module.
    registry = _reviewed_s_registry(tmp_path)
    impact = _authz_impact()
    ir_path = tmp_path / "requirement.ir.json"
    lowered_path = tmp_path / "lowered.json"
    registry_path = tmp_path / "registry.json"
    impact_path = tmp_path / "impact.json"
    out = tmp_path / "solver-system-result.json"
    artifacts = tmp_path / "artifacts"
    ir_path.write_text(json.dumps(ir.model_dump(mode="json"), indent=2))
    lowered_path.write_text(json.dumps(lowered.model_dump(mode="json", exclude_none=True), indent=2))
    registry_path.write_text(json.dumps(registry.model_dump(mode="json"), indent=2))
    impact_path.write_text(json.dumps(impact.model_dump(mode="json"), indent=2))

    exit_code = main(
        [
            "solver-system-consistency-check",
            "--requirement-ir",
            str(ir_path),
            "--lowered",
            str(lowered_path),
            "--registry",
            str(registry_path),
            "--impact",
            str(impact_path),
            "--project-root",
            str(tmp_path),
            "--artifact-dir",
            str(artifacts),
            "--checker-id",
            "custom",
            "--out",
            str(out),
            "--checker-command",
            sys.executable,
            "-c",
            "print('verification successful')",
        ]
    )

    output = capsys.readouterr().out

    assert exit_code == 0
    assert "Solver-backed system consistency result:" in output
    assert json.loads(out.read_text())["result"]["status"] == "valid"


def _ir():
    return DslV2Parser().parse_ir(DSL, requirement_id="REQ-SYS-001", title="System check")


def _impact() -> ImpactAnalysisArtifact:
    return ImpactAnalysisArtifact(
        adapter_id="python-source",
        language="python",
        input_symbols=["finalize_redemption"],
        affected_modules=["redemption"],
    )


def _registry(tmp_path: Path, *, marker: str = "") -> SystemSpecRegistry:
    specs = tmp_path / "specs"
    specs.mkdir(exist_ok=True)
    (specs / "Redemption.tla").write_text(
        "---- MODULE Redemption ----\nRedemptionInvariant == TRUE\n" + marker + "====\n"
    )
    return SystemSpecRegistry.model_validate(
        {
            "schema_version": "0.1",
            "specs": [
                {
                    "spec_id": "spec:redemption",
                    "module_ids": ["redemption"],
                    "formalism": "tla",
                    "path": "specs/Redemption.tla",
                    "version": "1",
                    "review_status": "reviewed",
                    "freshness": "fresh",
                }
            ],
        }
    )


# ---------------------------------------------------------------------------
# Z3 in-process S∧R gate tests (PA-1)
# ---------------------------------------------------------------------------

def _authz_ir():
    """DSL v3 authorization_precondition IR: wallet is authorized."""
    from nlreq.dsl_v3 import DslV3Parser
    return DslV3Parser().parse_ir(
        "requirement authorization_precondition: scope redemption "
        "when wallet is authorized then finalize_redemption must reject before rejected.",
        requirement_id="REQ-SYS-AUTHZ",
        title="Authorization precondition",
    )


def _negation_ir():
    """DSL v3 authorization_precondition IR: wallet is not authorized (negation of _authz_ir).

    Predicate name is 'not_authorized' (DSL tokenizes "not authorized" → Pred_not_authorized).
    """
    from nlreq.dsl_v3 import DslV3Parser
    return DslV3Parser().parse_ir(
        "requirement authorization_precondition: scope redemption "
        "when wallet is not authorized then finalize_redemption must reject before rejected.",
        requirement_id="REQ-SYS-AUTHZ-NEG",
        title="Authorization precondition negation",
    )


def _z3_registry(tmp_path: Path, *, spec_content: str) -> SystemSpecRegistry:
    """Registry with a single spec whose content defines Pred_* assignments for Z3 gate."""
    specs = tmp_path / "specs"
    specs.mkdir(exist_ok=True)
    (specs / "SystemConstraint.tla").write_text(spec_content)
    return SystemSpecRegistry.model_validate(
        {
            "schema_version": "0.1",
            "specs": [
                {
                    "spec_id": "spec:z3-constraint",
                    "module_ids": ["redemption"],
                    "formalism": "tla",
                    "path": "specs/SystemConstraint.tla",
                    "version": "1",
                    "review_status": "reviewed",
                    "freshness": "fresh",
                }
            ],
        }
    )


def _authz_impact() -> ImpactAnalysisArtifact:
    return ImpactAnalysisArtifact(
        adapter_id="python-source",
        language="python",
        input_symbols=["finalize_redemption"],
        affected_modules=["redemption"],
    )


def test_z3_gate_r_plus_s_returns_valid(tmp_path: Path) -> None:
    """R + S(pred=FALSE) → Z3 UNSAT → valid.

    S assigns Pred_authorized(a) = FALSE.  Under S, the violation query
    (Pred_authorized=TRUE ∧ reached=TRUE) contradicts S → UNSAT → "valid".
    This is the PA-1 gate-path evidence: R holds under the system constraint.
    """
    from nlreq.formal_lowering import lower_authorization_precondition_tla
    ir = _authz_ir()
    lowered = lower_ir_v2_to_tla(ir)
    assert lowered.status == "lowered", f"IR must lower successfully, got: {lowered}"

    # S: Pred_authorized(a) == FALSE — R holds vacuously under this constraint.
    s_spec = (
        "---- MODULE SystemConstraint ----\n"
        "CONSTANT a\n"
        "\\* @type: (Str) => Bool;\n"
        "Pred_authorized(a) == FALSE\n"
        "====\n"
    )
    registry = _z3_registry(tmp_path, spec_content=s_spec)
    result = check_solver_backed_system_consistency(
        requirement=ir,
        lowered=lowered,
        registry=registry,
        impact=_authz_impact(),
        project_root=tmp_path,
        execution=FormalBackendExecution(checker_id="z3"),
    )

    assert result.result.status == "valid", (
        f"R+S must return 'valid' (UNSAT under conservative S), got {result.result.status!r}"
    )
    assert result.result.backend == "solver_system_checker"
    # Z3 in-process is a propositional SMT check, not a bounded model checker.
    assert result.result.evidence_level.value == "SMT_CHECKED"
    assert result.result.details["checker_id"] == "z3"
    assert result.result.details["z3_outcome"] == "valid"


def test_z3_gate_neg_r_plus_s_returns_counterexample(tmp_path: Path) -> None:
    """¬R + S(pred=TRUE) → Z3 SAT → counterexample.

    S assigns Pred_not_authorized(a) = TRUE.  Under S, the violation query
    (Pred_not_authorized=TRUE ∧ reached=TRUE) is consistent with S → SAT → "counterexample".
    This discriminates R from ¬R: R holds under S while ¬R fails.
    """
    ir = _negation_ir()
    lowered = lower_ir_v2_to_tla(ir)
    assert lowered.status == "lowered", f"Negation IR must lower successfully, got: {lowered}"

    # S: Pred_not_authorized(a) == TRUE — ¬R's obligation fires, violation is reachable.
    s_spec = (
        "---- MODULE SystemConstraint ----\n"
        "CONSTANT a\n"
        "\\* @type: (Str) => Bool;\n"
        "Pred_not_authorized(a) == TRUE\n"
        "====\n"
    )
    registry = _z3_registry(tmp_path, spec_content=s_spec)
    result = check_solver_backed_system_consistency(
        requirement=ir,
        lowered=lowered,
        registry=registry,
        impact=_authz_impact(),
        project_root=tmp_path,
        execution=FormalBackendExecution(checker_id="z3"),
    )

    assert result.result.status == "counterexample", (
        f"¬R+S must return 'counterexample' (SAT: ¬R fails under S), got {result.result.status!r}"
    )
    assert result.result.details["z3_outcome"] == "counterexample"


def test_z3_gate_obligation_vacuous_breaks_discrimination(tmp_path: Path) -> None:
    """Mutation: Obligation == TRUE → Z3 gate returns 'unsupported' for ¬R (no discrimination).

    When the lowered module's Obligation is replaced with TRUE (vacuous regression),
    parse_obligation_predicates returns [] and _z3_check_obligation_under_s returns
    "unknown".  The gate must NOT return "counterexample" — proving it is anchored to
    the actual Obligation line, not to CONSTANT declarations.
    """
    import re
    from nlreq.translator import LoweredFormalArtifact as LFA
    from nlreq.jsonutil import sha256_text

    ir = _negation_ir()
    normal_lowered = lower_ir_v2_to_tla(ir)
    assert normal_lowered.status == "lowered"

    # Mutate: replace "Obligation == ..." with "Obligation == TRUE"
    vacuous_content = re.sub(
        r"^Obligation == .*$",
        "Obligation == TRUE",
        normal_lowered.content,
        flags=re.MULTILINE,
    )
    vacuous_lowered = LFA.model_validate(
        normal_lowered.model_copy(
            update={"content": vacuous_content, "content_hash": sha256_text(vacuous_content)}
        ).model_dump(mode="json", exclude_none=True)
    )

    # S assigns ¬R's predicates = TRUE — would normally produce "counterexample".
    s_spec = (
        "---- MODULE SystemConstraint ----\n"
        "CONSTANT a\n"
        "\\* @type: (Str) => Bool;\n"
        "Pred_not_authorized(a) == TRUE\n"
        "====\n"
    )
    registry = _z3_registry(tmp_path, spec_content=s_spec)
    result = check_solver_backed_system_consistency(
        requirement=ir,
        lowered=vacuous_lowered,
        registry=registry,
        impact=_authz_impact(),
        project_root=tmp_path,
        execution=FormalBackendExecution(checker_id="z3"),
    )

    assert result.result.status != "counterexample", (
        "Vacuous obligation (Obligation == TRUE) must NOT produce 'counterexample' — "
        "the Z3 gate is not anchored to CONSTANT declarations alone, only the Obligation line. "
        f"Got status: {result.result.status!r}"
    )
    assert result.result.status == "unsupported", (
        f"Vacuous obligation must return 'unsupported' (unknown Z3 outcome), "
        f"got {result.result.status!r}"
    )


def test_z3_gate_vacuous_consequent_returns_unsupported(tmp_path: Path) -> None:
    """Mutation: Obligation == Pred_foo(a) => TRUE (vacuous consequent).

    The check must return 'unsupported' (unknown Z3 outcome), NOT 'counterexample'.
    _obligation_consequent_is_real detects the absent NLRState /= constraint and
    returns unknown before encoding any Z3 formulas — anchoring the check to the
    actual obligation consequent, not just the predicate name.
    """
    import re
    from nlreq.translator import LoweredFormalArtifact as LFA
    from nlreq.jsonutil import sha256_text

    ir = _negation_ir()
    normal_lowered = lower_ir_v2_to_tla(ir)
    assert normal_lowered.status == "lowered"

    # Mutate: replace real consequent with => TRUE (vacuous, obligation never fires)
    vacuous_content = re.sub(
        r"(^Obligation == .* => )NLRState /= \"accepted\"",
        r"\1TRUE",
        normal_lowered.content,
        flags=re.MULTILINE,
    )
    assert "=> TRUE" in vacuous_content, "Mutation must insert => TRUE consequent"
    vacuous_lowered = LFA.model_validate(
        normal_lowered.model_copy(
            update={"content": vacuous_content, "content_hash": sha256_text(vacuous_content)}
        ).model_dump(mode="json", exclude_none=True)
    )

    s_spec = (
        "---- MODULE SystemConstraint ----\n"
        "CONSTANT a\n"
        "\\* @type: (Str) => Bool;\n"
        "Pred_not_authorized(a) == TRUE\n"
        "====\n"
    )
    registry = _z3_registry(tmp_path, spec_content=s_spec)
    result = check_solver_backed_system_consistency(
        requirement=ir,
        lowered=vacuous_lowered,
        registry=registry,
        impact=_authz_impact(),
        project_root=tmp_path,
        execution=FormalBackendExecution(checker_id="z3"),
    )

    assert result.result.status == "unsupported", (
        f"Vacuous consequent (=> TRUE) must return 'unsupported', "
        f"got {result.result.status!r}"
    )


def test_z3_gate_no_step_transitions_returns_unsupported(tmp_path: Path) -> None:
    """Mutation: Next == UNCHANGED NLRState (no real transitions).

    When the Next definition has no Step_* actions, the obligation is trivially
    satisfied because NLRState never changes from 'idle'. The check must return
    'unsupported' so this structural defect does not produce a false 'valid'.
    _next_has_steps detects the absent Step_* references before encoding Z3.
    """
    import re
    from nlreq.translator import LoweredFormalArtifact as LFA
    from nlreq.jsonutil import sha256_text

    ir = _authz_ir()
    normal_lowered = lower_ir_v2_to_tla(ir)
    assert normal_lowered.status == "lowered"

    # Mutate: remove all Step_* references from Next, leaving only UNCHANGED
    stub_content = re.sub(
        r"^Next == .*$",
        "Next == UNCHANGED NLRState",
        normal_lowered.content,
        flags=re.MULTILINE,
    )
    assert "UNCHANGED NLRState" in stub_content
    stub_lowered = LFA.model_validate(
        normal_lowered.model_copy(
            update={"content": stub_content, "content_hash": sha256_text(stub_content)}
        ).model_dump(mode="json", exclude_none=True)
    )

    s_spec = (
        "---- MODULE SystemConstraint ----\n"
        "CONSTANT a\n"
        "\\* @type: (Str) => Bool;\n"
        "Pred_authorized(a) == FALSE\n"
        "====\n"
    )
    registry = _z3_registry(tmp_path, spec_content=s_spec)
    result = check_solver_backed_system_consistency(
        requirement=ir,
        lowered=stub_lowered,
        registry=registry,
        impact=_authz_impact(),
        project_root=tmp_path,
        execution=FormalBackendExecution(checker_id="z3"),
    )

    assert result.result.status == "unsupported", (
        f"No-step Next definition must return 'unsupported', got {result.result.status!r}"
    )



# ---------------------------------------------------------------------------
# compose_s_and_r_module: byte-stable composition + refusal unit tests (PB-1)
# ---------------------------------------------------------------------------

_GOLDEN_LOWERED = (
    "---- MODULE Req_GOLDEN ----\n"
    "EXTENDS Naturals, TLC\n\n"
    "\\* @type: Str;\n"
    "CONSTANT wallet\n\n"
    "\\* @type: (Str) => Bool;\n"
    "CONSTANT Pred_authorized(_)\n\n"
    "\\* @type: Str;\n"
    "VARIABLE NLRState\n\n"
    'Init == NLRState = "idle"\n\n'
    "Step_act ==\n"
    '  /\\ NLRState = "idle"\n'
    '  /\\ NLRState\' \\in {"rejected", "accepted"}\n\n'
    "Next == Step_act \\/ UNCHANGED NLRState\n\n"
    "Premise == Pred_authorized(wallet)\n\n"
    'Obligation == Pred_authorized(wallet) => NLRState /= "accepted"\n\n'
    "RequirementHolds == Premise => Obligation\n\n"
    "====\n"
)

_GOLDEN_SPEC = (
    "---- MODULE Sys ----\n"
    "\\* @type: (Str) => Bool;\n"
    "Pred_authorized(a) == FALSE\n"
    'SystemDefaultsClosed == Pred_authorized("wallet") = FALSE\n'
    "====\n"
)

_GOLDEN_COMPOSED = (
    "---- MODULE Req_GOLDEN_S_AND_R ----\n"
    "EXTENDS Naturals, TLC\n\n"
    "CONSTANT\n"
    "  \\* @type: Str;\n"
    "  wallet\n\n"
    "\\* ===== Reviewed system spec S (inlined; operators keep their names) =====\n"
    "\\* @type: (Str) => Bool;\n"
    "Pred_authorized(a) == FALSE\n"
    'SystemDefaultsClosed == Pred_authorized("wallet") = FALSE\n\n'
    "VARIABLE\n"
    "  \\* @type: Str;\n"
    "  NLRState\n\n"
    "\\* ===== Requirement projection R (transition system + obligation) =====\n"
    'Init == NLRState = "idle"\n\n'
    "Step_act ==\n"
    '  /\\ NLRState = "idle"\n'
    '  /\\ NLRState\' \\in {"rejected", "accepted"}\n\n'
    "Next == Step_act \\/ UNCHANGED NLRState\n\n"
    "Premise == Pred_authorized(wallet)\n\n"
    'Obligation == Pred_authorized(wallet) => NLRState /= "accepted"\n\n'
    "RequirementHolds == Premise => Obligation\n\n"
    "\\* ===== S ∧ R: requirement obligation conjoined with system invariants =====\n"
    "Inv == RequirementHolds /\\ SystemDefaultsClosed\n"
    'ConstInit == wallet = "wallet"\n'
    "====\n"
)


def test_compose_s_and_r_module_is_byte_stable() -> None:
    """The composed S ∧ R module is byte-for-byte stable and inlines the real spec
    invariant operator — not a hash comment or a SystemSpecAssumptions tautology."""
    contribution = build_system_spec_contribution(
        "spec:sys", _GOLDEN_SPEC, ["SystemDefaultsClosed"]
    )
    composed = compose_s_and_r_module("Req_GOLDEN_S_AND_R", _GOLDEN_LOWERED, [contribution])

    assert composed.status == "composed"
    assert composed.module_text == _GOLDEN_COMPOSED
    # The spec's invariant operator is textually present (acceptance: not just a hash).
    assert "SystemDefaultsClosed == " in composed.module_text
    assert "SystemSpecAssumptions" not in composed.module_text
    assert composed.preserved_invariants == ["RequirementHolds", "SystemDefaultsClosed"]
    assert composed.bound_predicates == ["Pred_authorized"]


def test_compose_s_and_r_module_refuses_without_invariant() -> None:
    """A spec with no declared invariant cannot yield a non-vacuous S ∧ R — refuse."""
    contribution = build_system_spec_contribution("spec:sys", _GOLDEN_SPEC, [])
    composed = compose_s_and_r_module("Req_GOLDEN_S_AND_R", _GOLDEN_LOWERED, [contribution])

    assert composed.status == "refused"
    assert composed.module_text is None
    assert composed.refusal_kind == "no_system_invariant"


def test_compose_s_and_r_module_refuses_operator_name_collision() -> None:
    """A spec operator that shadows a requirement operator is refused, not overridden."""
    colliding_spec = (
        "---- MODULE Sys ----\n"
        "\\* @type: (Str) => Bool;\n"
        "Pred_authorized(a) == FALSE\n"
        "RequirementHolds == TRUE\n"
        "====\n"
    )
    contribution = build_system_spec_contribution(
        "spec:sys", colliding_spec, ["RequirementHolds"]
    )
    composed = compose_s_and_r_module("Req_GOLDEN_S_AND_R", _GOLDEN_LOWERED, [contribution])

    assert composed.status == "refused"
    assert composed.refusal_kind == "operator_name_collision"
