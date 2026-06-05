import json
import shutil
import sys
from pathlib import Path

import pytest

from nlreq.cli import main
from nlreq.dsl_v2 import DslV2Parser
from nlreq.formal_backend import FormalBackendBudget, FormalBackendExecution
from nlreq.formal_lowering import (
    OutcomePredicate,
    build_system_spec_contribution,
    compose_s_and_r_module,
)
from nlreq.impact import ImpactAnalysisArtifact
from nlreq.models import EvidenceLevel, RequirementIR
from nlreq.parser import RequirementParser
from nlreq.system_checker import (
    APALACHE_S_AND_R_COMMAND,
    DEFAULT_S_AND_R_DEPTH,
    _solver_result,
    check_requirement_set_consistency,
    check_solver_backed_system_consistency,
    check_system_consistency_fixture,
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
    result = check_system_consistency_fixture(
        requirement=_ir(),
        lowered=lower_ir_v2_to_tla(_ir()),
        registry=_registry(tmp_path),
        impact=_impact(),
        project_root=tmp_path,
    )

    assert result.result.status == "valid"
    assert result.result.evidence_level == "CONSISTENCY_CHECKED"


def test_system_consistency_returns_counterexample_marker(tmp_path: Path) -> None:
    result = check_system_consistency_fixture(
        requirement=_ir(),
        lowered=lower_ir_v2_to_tla(_ir()),
        registry=_registry(tmp_path, marker="\\* NLREQ_COUNTEREXAMPLE:REQ-SYS-001\n"),
        impact=_impact(),
        project_root=tmp_path,
    )

    assert result.result.status == "counterexample"
    assert result.counterexamples[0].metadata["spec_id"] == "spec:redemption"


def test_system_consistency_returns_timeout_marker(tmp_path: Path) -> None:
    result = check_system_consistency_fixture(
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

    result = check_system_consistency_fixture(
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

    result = check_system_consistency_fixture(
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

# The S ∧ R command is owned by system_checker (single source of truth); these tests check
# the same command the default gate and the retained benchmark corpus run.
_APALACHE_COMMAND = list(APALACHE_S_AND_R_COMMAND)


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
    init_op: str | None = None,
    next_op: str | None = None,
) -> SystemSpecRegistry:
    specs = tmp_path / "specs"
    specs.mkdir(exist_ok=True)
    (specs / "RedemptionSystem.tla").write_text(
        spec_text if spec_text is not None else _reviewed_s_spec_text()
    )
    entry: dict[str, object] = {
        "spec_id": "spec:redemption",
        "module_ids": ["redemption"],
        "formalism": "tla",
        "path": "specs/RedemptionSystem.tla",
        "version": "1",
        "review_status": "reviewed",
        "freshness": "fresh",
        "invariants": list(invariants),
    }
    if init_op is not None:
        entry["init_op"] = init_op
    if next_op is not None:
        entry["next_op"] = next_op
    return SystemSpecRegistry.model_validate(
        {
            "schema_version": "0.1",
            "specs": [entry],
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


def test_solver_backed_command_depth_matches_recorded_bounds(tmp_path: Path) -> None:
    """The executed ``--length`` is rendered from the same budget recorded in ``bounds``.

    Regression for the depth-provenance gap: the S ∧ R command used to hardcode ``--length=6``
    while ``bounds`` recorded the caller's ``max_depth`` separately, so a run could claim one
    depth in metadata while the checker searched another. With a non-default depth (9), the
    rendered command and the recorded bounds must agree, and the ``{max_depth}`` token must be
    substituted (never executed raw). Tool-free: composition succeeds and the command/bounds are
    recorded regardless of the (deliberately absent) checker binary, so this needs no Apalache.
    """
    ir = _authz_ir()
    result = check_solver_backed_system_consistency(
        requirement=ir,
        lowered=lower_ir_v2_to_tla(ir),
        registry=_reviewed_s_registry(tmp_path),
        impact=_authz_impact(),
        project_root=tmp_path,
        budget=FormalBackendBudget(timeout_seconds=60, max_depth=9),
        execution=FormalBackendExecution(
            checker_id="apalache",
            command=["apalache-mc-not-installed", *list(APALACHE_S_AND_R_COMMAND)[1:]],
            artifact_dir=(tmp_path / "artifacts").as_posix(),
        ),
    )

    command = result.result.details["command"]
    assert "--length=9" in command, command
    assert "--length={max_depth}" not in command, command
    assert result.result.details["bounds"]["max_depth"] == 9


def test_solver_backed_default_depth_is_recorded_when_budget_omits_it(tmp_path: Path) -> None:
    """With no caller depth, the rendered ``--length`` and recorded ``bounds`` both fall back to
    the same DEFAULT_S_AND_R_DEPTH — never a silent depth the run does not claim."""
    ir = _authz_ir()
    result = check_solver_backed_system_consistency(
        requirement=ir,
        lowered=lower_ir_v2_to_tla(ir),
        registry=_reviewed_s_registry(tmp_path),
        impact=_authz_impact(),
        project_root=tmp_path,
        execution=FormalBackendExecution(
            checker_id="apalache",
            command=["apalache-mc-not-installed", *list(APALACHE_S_AND_R_COMMAND)[1:]],
            artifact_dir=(tmp_path / "artifacts").as_posix(),
        ),
    )

    assert f"--length={DEFAULT_S_AND_R_DEPTH}" in result.result.details["command"]
    assert result.result.details["bounds"]["max_depth"] == DEFAULT_S_AND_R_DEPTH


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


def _stateful_s_registry(tmp_path: Path) -> SystemSpecRegistry:
    """Registry with the reviewed stateful S (Case B: its own SInit/SNext)."""
    return _reviewed_s_registry(
        tmp_path,
        spec_text=_STATEFUL_SPEC,
        invariants=("AuthorizationDefaultsClosed",),
        init_op="SInit",
        next_op="SNext",
    )


def test_solver_backed_narrowing_path_writes_narrowing_module(tmp_path: Path) -> None:
    """A reviewed S that brings its own transition system composes end-to-end as a NARROWING
    (Case B) — it is no longer refused. The artifact on disk uses S's own Init/Next as the
    sole state machine and conjoins R's obligation as a state invariant; R contributes no
    transitions and no harness variable."""
    ir = _authz_ir()
    result = check_solver_backed_system_consistency(
        requirement=ir,
        lowered=lower_ir_v2_to_tla(ir),
        registry=_stateful_s_registry(tmp_path),
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
    # S's own transitions are the only state machine; R adds none and the harness is gone.
    assert "Init == SInit\n" in composed
    assert "Next == SNext\n" in composed
    assert "Inv == AuthorizationDefaultsClosed /\\ R_Requirement\n" in composed
    assert "R_Requirement == Pred_authorized(wallet) => ~Pred_finalize_redemption(wallet)" in composed
    assert "NLRState" not in composed
    assert "SystemSpecAssumptions" not in composed


def _itf_traces_under(artifact_dir: Path) -> list[dict]:
    """Load every Apalache ITF counterexample trace written under an artifact dir."""
    traces = []
    for path in sorted(artifact_dir.glob("**/violation*.itf.json")):
        traces.append(json.loads(path.read_text()))
    return traces


@pytest.mark.skipif(APALACHE is None, reason="apalache-mc binary not installed")
def test_solver_backed_narrowing_compatible_requirement_is_valid(tmp_path: Path) -> None:
    """SP2-B (stateful S): a requirement compatible with a reviewed S that has its own
    transition system yields a real Apalache 'valid'. S's premise predicate (Pred_authorized)
    stays FALSE, so the narrowing obligation Premise => ~Pred_finalize_redemption is
    vacuously satisfied even though S does reach the 'finalized' outcome."""
    ir = _authz_ir()
    result = check_solver_backed_system_consistency(
        requirement=ir,
        lowered=lower_ir_v2_to_tla(ir),
        registry=_stateful_s_registry(tmp_path),
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
    assert result.result.evidence_level.value == "BOUNDED_CHECKED"
    assert "AuthorizationDefaultsClosed" in result.result.details["preserved_invariants"]
    assert "R_Requirement" in result.result.details["preserved_invariants"]
    # PB-3: a bounded result records the resolved checker and its real version. The version
    # command defaults to the pinned `apalache-mc version` even though the caller did not set
    # tool_version_command, so reproducibility metadata is never blank for a real run.
    repro = result.result.details["reproducibility"]
    assert repro["tool_version_command"] == ["apalache-mc", "version"]
    assert repro["tool_version"], "expected a non-null resolved Apalache version"
    assert repro["executable_resolved"], "expected the resolved apalache-mc path"


@pytest.mark.skipif(APALACHE is None, reason="apalache-mc binary not installed")
def test_solver_backed_narrowing_contradicting_counterexample_shows_system_step(
    tmp_path: Path,
) -> None:
    """SP2-B (stateful S): the contradicting sibling yields a real Apalache counterexample
    whose trace shows S TAKING ITS OWN TRANSITIONS to the forbidden outcome — authPhase
    walks init→denied→finalized, so Pred_finalize_redemption fires while Pred_not_authorized
    holds. The violation is a real S behavior reachable only because S's Next steps to
    'finalized'; nothing but S's transition relation produces it. Same S as the compatible
    test."""
    ir = _negation_ir()
    artifact_dir = tmp_path / "artifacts"
    result = check_solver_backed_system_consistency(
        requirement=ir,
        lowered=lower_ir_v2_to_tla(ir),
        registry=_stateful_s_registry(tmp_path),
        impact=_authz_impact(),
        project_root=tmp_path,
        budget=FormalBackendBudget(timeout_seconds=60, max_depth=6),
        execution=FormalBackendExecution(
            checker_id="apalache",
            command=_APALACHE_COMMAND,
            artifact_dir=artifact_dir.as_posix(),
        ),
    )

    assert result.result.status == "counterexample", result.result.details
    assert result.counterexamples

    traces = _itf_traces_under(artifact_dir)
    assert traces, "expected a retained Apalache ITF counterexample trace"
    states = traces[0]["states"]
    phases = [state.get("authPhase") for state in states]
    # The violation is a real S behavior: S must step all the way to "finalized" (where it
    # executes the action while still unauthorized), not sit at the initial state.
    assert phases[0] == "init"
    assert "finalized" in phases[1:], f"S did not reach the forbidden outcome; authPhase was {phases!r}"


@pytest.mark.skipif(APALACHE is None, reason="apalache-mc binary not installed")
def test_solver_backed_narrowing_no_spurious_counterexample_when_outcome_unreachable(
    tmp_path: Path,
) -> None:
    """Regression for the product-vs-narrowing bug: a reviewed S that becomes unauthorized
    but has NO transition that executes the action (Pred_finalize_redemption is never true)
    yields a real Apalache 'valid'. The premise fires (S steps to 'denied'), yet the
    obligation holds because S cannot reach the forbidden outcome. The discarded synchronous
    product reported a SPURIOUS counterexample here, because R's harness reached 'accepted'
    on its own — independent of S's transitions. The narrowing must not."""
    ir = _negation_ir()
    artifact_dir = tmp_path / "artifacts"
    result = check_solver_backed_system_consistency(
        requirement=ir,
        lowered=lower_ir_v2_to_tla(ir),
        registry=_reviewed_s_registry(
            tmp_path,
            spec_text=_REGRESSION_SPEC,
            invariants=("AuthorizationDefaultsClosed",),
            init_op="SInit",
            next_op="SNext",
        ),
        impact=_authz_impact(),
        project_root=tmp_path,
        budget=FormalBackendBudget(timeout_seconds=60, max_depth=6),
        execution=FormalBackendExecution(
            checker_id="apalache",
            command=_APALACHE_COMMAND,
            artifact_dir=artifact_dir.as_posix(),
        ),
    )

    assert result.result.status == "valid", result.result.details
    assert not result.counterexamples


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


def test_system_consistency_fixture_cli(tmp_path: Path, capsys) -> None:
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
            "system-consistency-check-fixture",
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


# A reviewed S that brings its OWN transition system (Case B). authPhase walks
# "init" -> "denied" (unauthorized) -> "finalized" (the redemption is executed while
# still unauthorized — the bug the requirement forbids). Pred_authorized stays FALSE;
# Pred_not_authorized latches once denied; Pred_finalize_redemption marks the
# accepted/executed outcome. R narrows S as a state invariant, so a counterexample is
# only reachable because S actually steps to "finalized" — a real S behavior, never a
# requirement harness moving its own variable.
_STATEFUL_SPEC = (
    "---- MODULE RedemptionAuthorization ----\n"
    "EXTENDS Naturals, TLC\n\n"
    "\\* @type: Str;\n"
    "VARIABLE authPhase\n\n"
    "\\* @type: (Str) => Bool;\n"
    "Pred_authorized(a) == FALSE\n"
    "\\* @type: (Str) => Bool;\n"
    'Pred_not_authorized(a) == authPhase \\in {"denied", "finalized"}\n'
    "\\* @type: (Str) => Bool;\n"
    'Pred_finalize_redemption(a) == authPhase = "finalized"\n'
    "\\* System invariant: authorization defaults closed.\n"
    'AuthorizationDefaultsClosed == Pred_authorized("wallet") = FALSE\n'
    'SInit == authPhase = "init"\n'
    'SNext == \\/ (authPhase = "init" /\\ authPhase\' = "denied")\n'
    '         \\/ (authPhase = "denied" /\\ authPhase\' = "finalized")\n'
    '         \\/ UNCHANGED authPhase\n'
    "====\n"
)

# A reviewed S that becomes unauthorized but has NO transition that finalizes the
# redemption (Pred_finalize_redemption is never true). The narrowing yields 'valid':
# S cannot reach the forbidden outcome, so the obligation holds even though the premise
# fires. The discarded synchronous product reported a SPURIOUS counterexample here — its
# requirement harness reached "accepted" on its own, independent of S — which is exactly
# the product-vs-narrowing bug this fixture pins (see the regression test below).
_REGRESSION_SPEC = (
    "---- MODULE RedemptionAuthorization ----\n"
    "EXTENDS Naturals, TLC\n\n"
    "\\* @type: Str;\n"
    "VARIABLE authPhase\n\n"
    "\\* @type: (Str) => Bool;\n"
    "Pred_authorized(a) == FALSE\n"
    "\\* @type: (Str) => Bool;\n"
    'Pred_not_authorized(a) == authPhase = "denied"\n'
    "\\* @type: (Str) => Bool;\n"
    "Pred_finalize_redemption(a) == FALSE\n"
    "\\* System invariant: authorization defaults closed.\n"
    'AuthorizationDefaultsClosed == Pred_authorized("wallet") = FALSE\n'
    'SInit == authPhase = "init"\n'
    'SNext == (authPhase = "init" /\\ authPhase\' = "denied") \\/ UNCHANGED authPhase\n'
    "====\n"
)

# The forbidden-outcome predicate the narrowing conjoins for the authorization_precondition
# requirements below: Pred_<action>(subject) == Pred_finalize_redemption(wallet).
_OUTCOME_FINALIZE = OutcomePredicate("Pred_finalize_redemption", ("wallet",))

# Byte-stable Case B *narrowing* of _GOLDEN_LOWERED with _STATEFUL_SPEC: S's own Init/Next
# are the only state machine and R contributes a single state invariant R_Requirement ==
# Premise => ~Pred_finalize_redemption(wallet). No R harness variable, no R_Init/R_Next.
# Validated against apalache-mc 0.58.0.
_GOLDEN_NARROWING_COMPOSED = (
    "---- MODULE Req_GOLDEN_S_AND_R ----\n"
    "EXTENDS Naturals, TLC\n\n"
    "CONSTANT\n"
    "  \\* @type: Str;\n"
    "  wallet\n\n"
    "VARIABLE\n"
    "  \\* @type: Str;\n"
    "  authPhase\n\n"
    "\\* ===== Reviewed system spec S (inlined; operators keep their names) =====\n"
    "\\* @type: (Str) => Bool;\n"
    "Pred_authorized(a) == FALSE\n"
    "\\* @type: (Str) => Bool;\n"
    'Pred_not_authorized(a) == authPhase \\in {"denied", "finalized"}\n'
    "\\* @type: (Str) => Bool;\n"
    'Pred_finalize_redemption(a) == authPhase = "finalized"\n'
    "\\* System invariant: authorization defaults closed.\n"
    'AuthorizationDefaultsClosed == Pred_authorized("wallet") = FALSE\n'
    'SInit == authPhase = "init"\n'
    'SNext == \\/ (authPhase = "init" /\\ authPhase\' = "denied")\n'
    '         \\/ (authPhase = "denied" /\\ authPhase\' = "finalized")\n'
    '         \\/ UNCHANGED authPhase\n\n'
    "\\* ===== Requirement R narrows S: a state invariant over S's own variables. R adds\n"
    "\\* no transitions and no variable — S's Init/Next are the only state machine. The\n"
    "\\* obligation forbids S reaching the accepted/executed outcome (Pred_finalize_redemption)\n"
    "\\* while the premise holds, so a counterexample is a real S behavior — not an artifact\n"
    "\\* of a requirement harness stepping its own state. =====\n"
    "R_Requirement == Pred_authorized(wallet) => ~Pred_finalize_redemption(wallet)\n\n"
    "\\* ===== S ∧ R: S's reachable states must preserve S's invariants and R's obligation =====\n"
    "Init == SInit\n"
    "Next == SNext\n"
    "Inv == AuthorizationDefaultsClosed /\\ R_Requirement\n"
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


def test_compose_s_and_r_narrowing_module_is_byte_stable() -> None:
    """A reviewed spec that brings its own transition system (init_op/next_op) composes as
    a NARROWING: S's own Init/Next are the sole state machine and R contributes a single
    state invariant R_Requirement == Premise => ~Pred_<action>. No R harness variable, no
    R_Init/R_Next. Byte-stable; not a refusal."""
    contribution = build_system_spec_contribution(
        "spec:sys", _STATEFUL_SPEC, ["AuthorizationDefaultsClosed"],
        init_op="SInit", next_op="SNext",
    )
    composed = compose_s_and_r_module(
        "Req_GOLDEN_S_AND_R", _GOLDEN_LOWERED, [contribution],
        outcome_predicate=_OUTCOME_FINALIZE,
    )

    assert composed.status == "composed"
    assert composed.module_text == _GOLDEN_NARROWING_COMPOSED
    # The narrowing preserves S's named invariant and the obligation invariant.
    assert composed.preserved_invariants == ["AuthorizationDefaultsClosed", "R_Requirement"]
    assert composed.bound_predicates == ["Pred_authorized", "Pred_finalize_redemption"]
    # S's own transitions are the only state machine — R adds none, and the harness is gone.
    assert "Init == SInit\n" in composed.module_text
    assert "Next == SNext\n" in composed.module_text
    assert "NLRState" not in composed.module_text
    assert "R_Init" not in composed.module_text
    assert "R_Next" not in composed.module_text


def test_compose_s_and_r_narrowing_refuses_incomplete_transition_operators() -> None:
    """A spec that declares only one of init_op/next_op has an ill-formed transition
    system — refuse rather than narrow against half a state machine."""
    contribution = build_system_spec_contribution(
        "spec:sys", _STATEFUL_SPEC, ["AuthorizationDefaultsClosed"], next_op="SNext"
    )
    composed = compose_s_and_r_module(
        "Req_GOLDEN_S_AND_R", _GOLDEN_LOWERED, [contribution],
        outcome_predicate=_OUTCOME_FINALIZE,
    )

    assert composed.status == "refused"
    assert composed.refusal_kind == "incomplete_transition_operators"


def test_compose_s_and_r_narrowing_refuses_undefined_transition_operator() -> None:
    """init_op/next_op naming operators the spec body does not define is refused, so a
    typo'd transition name cannot silently fall back to a vacuous machine."""
    contribution = build_system_spec_contribution(
        "spec:sys", _STATEFUL_SPEC, ["AuthorizationDefaultsClosed"],
        init_op="SInit", next_op="NoSuchNext",
    )
    composed = compose_s_and_r_module(
        "Req_GOLDEN_S_AND_R", _GOLDEN_LOWERED, [contribution],
        outcome_predicate=_OUTCOME_FINALIZE,
    )

    assert composed.status == "refused"
    assert composed.refusal_kind == "undefined_transition_operator"


def test_compose_s_and_r_narrowing_refuses_spec_constant() -> None:
    """A stateful spec that declares its own CONSTANT is refused: the composition cannot pin
    it in ConstInit, so it declines rather than leave it unconstrained."""
    spec_with_constant = (
        "---- MODULE Sys ----\n"
        "EXTENDS Naturals, TLC\n\n"
        "\\* @type: Str;\n"
        "CONSTANT threshold\n\n"
        "\\* @type: Str;\n"
        "VARIABLE authPhase\n\n"
        "\\* @type: (Str) => Bool;\n"
        "Pred_authorized(a) == FALSE\n"
        "\\* @type: (Str) => Bool;\n"
        'Pred_finalize_redemption(a) == FALSE\n'
        'SystemClosed == Pred_authorized("wallet") = FALSE\n'
        'SInit == authPhase = "init"\n'
        "SNext == UNCHANGED authPhase\n"
        "====\n"
    )
    contribution = build_system_spec_contribution(
        "spec:sys", spec_with_constant, ["SystemClosed"], init_op="SInit", next_op="SNext"
    )
    composed = compose_s_and_r_module(
        "Req_GOLDEN_S_AND_R", _GOLDEN_LOWERED, [contribution],
        outcome_predicate=_OUTCOME_FINALIZE,
    )

    assert composed.status == "refused"
    assert composed.refusal_kind == "unsupported_spec_constant"


def test_compose_s_and_r_narrowing_refuses_variable_name_collision() -> None:
    """Two reviewed specs that declare the SAME variable are refused: the composed state
    would conflate two machines into one variable. (R no longer contributes a harness
    variable, so the collision is now strictly between system specs.)"""
    spec_a = (
        "---- MODULE SysA ----\n"
        "EXTENDS Naturals, TLC\n\n"
        "\\* @type: Str;\n"
        "VARIABLE sharedPhase\n\n"
        "\\* @type: (Str) => Bool;\n"
        "Pred_authorized(a) == FALSE\n"
        "\\* @type: (Str) => Bool;\n"
        'Pred_finalize_redemption(a) == FALSE\n'
        'SystemClosedA == Pred_authorized("wallet") = FALSE\n'
        'SInitA == sharedPhase = "init"\n'
        "SNextA == UNCHANGED sharedPhase\n"
        "====\n"
    )
    spec_b = (
        "---- MODULE SysB ----\n"
        "EXTENDS Naturals, TLC\n\n"
        "\\* @type: Str;\n"
        "VARIABLE sharedPhase\n\n"
        'SystemClosedB == TRUE\n'
        'SInitB == sharedPhase = "init"\n'
        "SNextB == UNCHANGED sharedPhase\n"
        "====\n"
    )
    contributions = [
        build_system_spec_contribution(
            "spec:a", spec_a, ["SystemClosedA"], init_op="SInitA", next_op="SNextA"
        ),
        build_system_spec_contribution(
            "spec:b", spec_b, ["SystemClosedB"], init_op="SInitB", next_op="SNextB"
        ),
    ]
    composed = compose_s_and_r_module(
        "Req_GOLDEN_S_AND_R", _GOLDEN_LOWERED, contributions,
        outcome_predicate=_OUTCOME_FINALIZE,
    )

    assert composed.status == "refused"
    assert composed.refusal_kind == "variable_name_collision"


def test_compose_s_and_r_narrowing_refuses_undefined_outcome_predicate() -> None:
    """If the reviewed S does not interpret the forbidden-outcome predicate Pred_<action>,
    the narrowing cannot tell whether S reaches the outcome the requirement forbids, so it
    refuses rather than emit a module whose obligation references an undefined operator."""
    spec_without_outcome = (
        "---- MODULE Sys ----\n"
        "EXTENDS Naturals, TLC\n\n"
        "\\* @type: Str;\n"
        "VARIABLE authPhase\n\n"
        "\\* @type: (Str) => Bool;\n"
        "Pred_authorized(a) == FALSE\n"
        'SystemClosed == Pred_authorized("wallet") = FALSE\n'
        'SInit == authPhase = "init"\n'
        "SNext == UNCHANGED authPhase\n"
        "====\n"
    )
    contribution = build_system_spec_contribution(
        "spec:sys", spec_without_outcome, ["SystemClosed"], init_op="SInit", next_op="SNext"
    )
    composed = compose_s_and_r_module(
        "Req_GOLDEN_S_AND_R", _GOLDEN_LOWERED, [contribution],
        outcome_predicate=_OUTCOME_FINALIZE,
    )

    assert composed.status == "refused"
    assert composed.refusal_kind == "undefined_outcome_predicate"


def test_compose_s_and_r_narrowing_refuses_missing_outcome_predicate() -> None:
    """A stateful S narrowing needs the requirement's forbidden-outcome predicate. Without
    it (the requirement shape did not yield one), the composition refuses rather than emit a
    module that constrains nothing."""
    contribution = build_system_spec_contribution(
        "spec:sys", _STATEFUL_SPEC, ["AuthorizationDefaultsClosed"],
        init_op="SInit", next_op="SNext",
    )
    composed = compose_s_and_r_module("Req_GOLDEN_S_AND_R", _GOLDEN_LOWERED, [contribution])

    assert composed.status == "refused"
    assert composed.refusal_kind == "missing_outcome_predicate"


def test_solver_result_labels_valid_run_bounded_only_with_full_backing() -> None:
    """A valid solver run defaults to BOUNDED_CHECKED only when it recorded its full bounded
    backing — the bounds it searched, the checker command, and the version of the checker the run
    resolved. A run missing any of the three has no backing for a bounded claim, so the level
    degrades to None/unverified rather than over-claim (and rather than crash the BackendResult
    guard). The real Apalache/TLC S ∧ R path records all three — the command top-level, the
    version under reproducibility — so it stays BOUNDED_CHECKED."""
    no_bounds = _solver_result("REQ-1", "valid", ["spec:sys"], {"mode": "solver_backed"})
    bounds_only = _solver_result(
        "REQ-1", "valid", ["spec:sys"], {"mode": "solver_backed", "bounds": {"max_depth": 8}}
    )
    backed = _solver_result(
        "REQ-1",
        "valid",
        ["spec:sys"],
        {
            "mode": "solver_backed",
            "bounds": {"max_depth": 8},
            "command": ["apalache-mc", "check", "Module.tla"],
            "reproducibility": {"tool_version": "apalache 0.58.0"},
        },
    )

    assert no_bounds.result.evidence_level is None
    assert bounds_only.result.evidence_level is None
    assert backed.result.evidence_level == EvidenceLevel.BOUNDED_CHECKED
