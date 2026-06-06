import json
import shutil
import sys
from pathlib import Path

import pytest

from nlreq.cli import main
from nlreq.coverage_alignment import SpecCoverageReport, TraceAlignmentReport
from nlreq.cvc5_backend import cvc5_available, cvc5_check_formal_claim_premises
from nlreq.dsl_v3 import DslV3Parser
from nlreq.end_to_end_gate import (
    _cover_s_and_r_fragments,
    build_proof_with_formal_claim_dispatch,
    run_end_to_end_requirement_gate,
)
from nlreq.formal_backend import FormalBackendExecution
from nlreq.formal_claim import build_formal_claim
from nlreq.formal_claim_smt import smt_check_formal_claim_premise_consistency
from nlreq.impact import analyze_source_impact
from nlreq.system_checker import (
    APALACHE_S_AND_R_COMMAND,
    check_solver_backed_system_consistency,
    default_apalache_s_and_r_execution,
)
from nlreq.translator import lower_ir_v2_to_tla

APALACHE = shutil.which("apalache-mc")
from nlreq.jsonutil import read_json
from nlreq.python_source_adapter import PythonSourceLanguageAdapter
from nlreq.source_adapter import SourceManifest
from nlreq.system_spec import SystemSpecRegistry
from nlreq.translator_agreement import TranslationAgreementInput, TranslationCandidate

FIXTURES = Path(__file__).parent / "fixtures" / "requirements"

requires_cvc5 = pytest.mark.skipif(
    not cvc5_available(),
    reason="cvc5 optional dependency not installed (run under `uv run --extra formal`)",
)


DSL = (
    "For every redemption:\n"
    "when wallet is authorized\n"
    "and requested_amount <= spendable_balance\n"
    "then finalize_redemption must emit redemption_finalized within 6 hours.\n"
)


def _run_reviewed_s_gate(
    tmp_path: Path, *, solver_execution: FormalBackendExecution | None = None
):
    """Run the end-to-end gate over the reviewed-S fixture and return the report.

    The fixture's reviewed S pins ``Pred_authorized`` FALSE and declares the real invariant
    ``SystemDefaultsClosed``, so the v3 authorization_precondition requirement composes into a
    grounded, non-vacuous S ∧ R. Two agreeing deterministic translation candidates keep the
    ensemble "agreed" — a single provided IR would be "needs_review" and mask the S ∧ R verdict.
    ``solver_execution=None`` exercises the gate's default (real Apalache); callers pass an
    explicit execution to test the Z3 fixture path or checker-absence degradation.
    """
    manifest, registry = _project(tmp_path, reviewed_invariant=True)
    controlled_text = (
        "requirement authorization_precondition: scope redemption "
        "when wallet is authorized then finalize_redemption must reject before rejected."
    )
    requirement_ir = DslV3Parser().parse_ir(
        controlled_text, requirement_id="REQ-GATE-001", title="Requirement gate"
    )
    agreement = TranslationAgreementInput(
        candidates=[
            TranslationCandidate(translator_id="primary", method="deterministic",
                                 requirement=requirement_ir, provenance={"source": "test"}),
            TranslationCandidate(translator_id="replica", method="deterministic",
                                 requirement=requirement_ir, provenance={"source": "test"}),
        ]
    )
    return run_end_to_end_requirement_gate(
        controlled_text=controlled_text,
        requirement_id="REQ-GATE-001",
        title="Requirement gate",
        source_adapter=PythonSourceLanguageAdapter(project_root=tmp_path),
        source_manifest=manifest,
        symbols=["finalize_redemption"],
        registry=registry,
        project_root=tmp_path,
        artifact_dir=tmp_path / "gate-artifacts",
        execution=_execution(tmp_path),
        solver_execution=solver_execution,
        requirement_ir=requirement_ir,
        translation_agreement=agreement,
    )


def _run_narrowing_s_gate(tmp_path: Path, *, counterexample: bool = False):
    """Run the end-to-end gate over the stateful-S (Case B narrowing) fixture and return the report.

    The negation requirement ("when wallet is *not* authorized ...") has premise
    Pred_not_authorized, which fires under S's reachable states. The reviewed S binds both that
    predicate and the forbidden-outcome Pred_finalize_redemption, so a real Apalache S ∧ R
    resolves BOTH formal-claim premises through the same routing+coverage code. With
    ``counterexample=False`` the outcome is unreachable → valid → both premises discharge and
    the proof closes; with ``counterexample=True`` the outcome is reachable while the premise
    holds → Apalache returns a counterexample → both premises block and the gate refuses.
    ``solver_execution`` is left unset so the gate runs the real checker.
    """
    manifest, registry = _project(
        tmp_path, narrowing=not counterexample, narrowing_counterexample=counterexample
    )
    controlled_text = (
        "requirement authorization_precondition: scope redemption "
        "when wallet is not authorized then finalize_redemption must reject before rejected."
    )
    requirement_ir = DslV3Parser().parse_ir(
        controlled_text, requirement_id="REQ-GATE-NARROW", title="Narrowing gate"
    )
    agreement = TranslationAgreementInput(
        candidates=[
            TranslationCandidate(translator_id="primary", method="deterministic",
                                 requirement=requirement_ir, provenance={"source": "test"}),
            TranslationCandidate(translator_id="replica", method="deterministic",
                                 requirement=requirement_ir, provenance={"source": "test"}),
        ]
    )
    return run_end_to_end_requirement_gate(
        controlled_text=controlled_text,
        requirement_id="REQ-GATE-NARROW",
        title="Narrowing gate",
        source_adapter=PythonSourceLanguageAdapter(project_root=tmp_path),
        source_manifest=manifest,
        symbols=["finalize_redemption"],
        registry=registry,
        project_root=tmp_path,
        artifact_dir=tmp_path / "gate-artifacts",
        execution=_execution(tmp_path),
        requirement_ir=requirement_ir,
        translation_agreement=agreement,
    )


@pytest.mark.skipif(APALACHE is None, reason="apalache-mc binary not installed")
def test_end_to_end_gate_composes_real_s_and_r_valid(tmp_path: Path) -> None:
    """A real, solver-backed S ∧ R reaches `valid` end-to-end against a reviewed S.

    This exercises the gate's *default* checker — no `solver_execution` is passed, so the gate
    runs a real Apalache check of the composed S ∧ R module, not the in-process Z3 fixture path.
    This is the genuine successor to the old "accepts closed requirement" test. That test closed
    the gate via the vacuous not_applicable floor baseline that no longer exists (a reviewed spec
    that asserts nothing no longer produces a passing S ∧ R). Here a reviewed *stateless* S pins
    `Pred_authorized` FALSE and declares a real invariant, and a v3 authorization_precondition
    requirement lowers to a `Pred_authorized` obligation that S discharges — so a bounded model
    check of the composed module genuinely returns `valid` (BOUNDED_CHECKED), with the resolved
    tool version recorded. spec_coverage passes (S covers the module) and the FormalClaim lowers.

    What it deliberately does NOT assert is `decision == accepted`. The predicate premise now
    DOES discharge — the solver-backed S ∧ R verdict covers `Pred_authorized` because S bound it
    into the checked module. But this stateless S binds only the premise predicate, not the
    forbidden-outcome `Pred_finalize_redemption`, so the rejection-order obligation premise has
    no bound operator to discharge against and stays open — closure does not pass. Reaching
    `accepted` needs a stateful S that narrows its own transitions and binds the forbidden
    outcome too; that genuine accepted path is covered by
    test_end_to_end_gate_narrowing_s_and_r_closes_and_accepts. The split is the honest
    consequence of anchoring discharge to what the module actually bound, never faking it.
    """
    report = _run_reviewed_s_gate(tmp_path)

    # The real S ∧ R composition verified the requirement against a reviewed S.
    assert report.statuses["system_consistency"] == "valid", (
        report.statuses, [(b.stage, b.status) for b in report.blockers]
    )
    # The default ran a real Apalache bounded check (not the Z3 fixture path): a non-null tool
    # version proves a real binary resolved, and the evidence level is bounded-MC, not SMT.
    system_consistency = read_json(
        Path(next(a.path for a in report.artifacts if a.name == "system_consistency"))
    )
    assert system_consistency["result"]["details"]["checker_id"] == "apalache"
    assert system_consistency["result"]["evidence_level"] == "BOUNDED_CHECKED"
    assert system_consistency["result"]["details"]["reproducibility"]["tool_version"]
    # The real bounded result carries its backing (bounds + command + a run-recorded version
    # nested under reproducibility), so the closure gate must accept it — no premise or producer
    # blocker may flag it as unbacked bounded evidence (PB-9). A regression in the nested-version
    # extraction would surface here as a spurious "not backed" blocker on a genuinely real run.
    proof_object = read_json(
        Path(next(a.path for a in report.artifacts if a.name == "proof_object"))
    )
    assert not any(
        "not backed" in blocker["message"] for blocker in proof_object["blockers"]
    ), proof_object["blockers"]
    assert report.statuses["spec_coverage"] == "passed"
    assert report.statuses["translation_agreement"] == "agreed"
    assert report.statuses["formal_claim"] == "lowered"
    # The full pipeline still ran and recorded every artifact, even though closure is deferred.
    assert {artifact.name for artifact in report.artifacts} >= {
        "requirement_ir",
        "translation_agreement",
        "requirement_self_consistency",
        "source_impact",
        "spec_coverage",
        "trace_replay",
        "system_consistency",
        "delta_report",
        "proof_object",
        "closure_gate",
    }
    assert all(Path(artifact.path).is_file() for artifact in report.artifacts)


@pytest.mark.skipif(APALACHE is None, reason="apalache-mc binary not installed")
def test_end_to_end_gate_narrowing_s_and_r_closes_and_accepts(tmp_path: Path) -> None:
    """A reviewed stateful S that narrows R closes the proof end-to-end: accepted/closed/passed.

    This is the per-premise discharge slice (PB-7/PB-8) — the first genuine accepted path for a
    requirement checked against a reviewed S. The reviewed S brings its own transition system
    and interprets both the premise predicate (Pred_not_authorized, which fires once authPhase
    reaches "denied") and the forbidden outcome (Pred_finalize_redemption, pinned unreachable),
    so a real Apalache bounded check verifies S never reaches the forbidden outcome while the
    premise holds — a NON-vacuous obligation discharge, not a premise that can never fire.

    Because both Pred_* operators are bound into the checked module (recorded in the result's
    bound_predicates), the solver-backed S ∧ R verdict discharges BOTH formal-claim premises —
    the predicate and the rejection-order obligation — at BOUNDED_CHECKED. So the ProofObject
    closes and the gate accepts downstream action. The discharge is anchored to what the module
    actually bound: a stateless S that binds only the premise, or a counterexample/timeout,
    would leave the obligation premise undischarged. Only a real, bound, valid S ∧ R reaches
    this accepted path — the honest successor to the deferred-closure state above.
    """
    report = _run_narrowing_s_gate(tmp_path)

    assert report.statuses["system_consistency"] == "valid", (
        report.statuses, [(b.stage, b.status) for b in report.blockers]
    )
    assert report.decision == "accepted", (
        report.statuses, [(b.stage, b.status) for b in report.blockers]
    )
    assert report.proof_status == "closed"
    assert report.closure_result == "passed"
    assert report.downstream_action_allowed is True

    # Closure rests on a real bounded model check that bound BOTH predicates — not a vacuous
    # pass and not faked high-assurance evidence. Every formal-claim premise (predicate and
    # rejection_order) is discharged by the solver-backed S ∧ R at BOUNDED_CHECKED.
    proof = read_json(
        Path(next(a.path for a in report.artifacts if a.name == "proof_object"))
    )
    assert proof["status"] == "closed"
    assert {p["node_kind"] for p in proof["premises"]} == {"predicate", "rejection_order"}
    for premise in proof["premises"]:
        assert premise["status"] == "discharged", premise
        assert premise["routed_backend"] == "solver_system_checker"
        assert premise["achieved_evidence"] == "BOUNDED_CHECKED"
    assert not proof["blockers"], proof["blockers"]

    # The discharging verdict came from a real Apalache run (recorded tool version), and it
    # bound both the premise predicate and the forbidden-outcome predicate — the coupling that
    # makes the discharge a genuine narrowing of S, not a fragment-level shortcut.
    system_consistency = read_json(
        Path(next(a.path for a in report.artifacts if a.name == "system_consistency"))
    )
    assert system_consistency["result"]["details"]["checker_id"] == "apalache"
    assert system_consistency["result"]["evidence_level"] == "BOUNDED_CHECKED"
    assert system_consistency["result"]["details"]["reproducibility"]["tool_version"]
    assert set(system_consistency["result"]["details"]["bound_predicates"]) == {
        "Pred_not_authorized",
        "Pred_finalize_redemption",
    }


@pytest.mark.skipif(APALACHE is None, reason="apalache-mc binary not installed")
def test_end_to_end_gate_narrowing_s_and_r_counterexample_refuses(tmp_path: Path) -> None:
    """The same routing+coverage path REFUSES on a real S ∧ R counterexample — it never falsely
    accepts.

    This is the negative twin of the accepted-path test, and the property that matters most: the
    mechanism that now discharges premises from a `valid` verdict must block them on a real
    counterexample. Here the reviewed stateful S can reach the forbidden outcome while the
    premise holds (authPhase reaches "finalized", where Pred_not_authorized AND
    Pred_finalize_redemption both hold), so the composed Inv (Premise => ~outcome) is violated
    and a real Apalache run returns a counterexample.

    Both Pred_* operators are still bound into the checked module, so both formal-claim premises
    are *covered* by the solver result — but because its status is `counterexample`, not `valid`,
    _evaluate_premise marks them `blocked` (named on the real verdict), not silently `open` and
    never `discharged`. The ProofObject does not close and the gate refuses downstream action.
    Coverage matching the verdict is exactly what keeps a real counterexample from being read as
    an accept.
    """
    report = _run_narrowing_s_gate(tmp_path, counterexample=True)

    assert report.statuses["system_consistency"] == "counterexample", (
        report.statuses, [(b.stage, b.status) for b in report.blockers]
    )
    assert report.decision == "refused"
    assert report.proof_status != "closed"
    assert report.closure_result != "passed"
    assert report.downstream_action_allowed is False

    proof = read_json(
        Path(next(a.path for a in report.artifacts if a.name == "proof_object"))
    )
    assert proof["status"] != "closed"
    formal_premises = [
        p for p in proof["premises"] if p["node_kind"] in {"predicate", "rejection_order"}
    ]
    assert {p["node_kind"] for p in formal_premises} == {"predicate", "rejection_order"}
    # Both premises must be BLOCKED — covered by the solver result (so the route matched) but
    # refused because the verdict is a counterexample. "open" would mean coverage was wrongly
    # withheld; "discharged" would be a false accept.
    for premise in formal_premises:
        assert premise["status"] == "blocked", premise
        assert premise["routed_backend"] == "solver_system_checker"

    # The blocking verdict came from a real Apalache run that produced a counterexample.
    system_consistency = read_json(
        Path(next(a.path for a in report.artifacts if a.name == "system_consistency"))
    )
    assert system_consistency["result"]["details"]["checker_id"] == "apalache"
    assert system_consistency["result"]["details"]["reproducibility"]["tool_version"]
    assert system_consistency["counterexamples"]


# The two faces of one requirement used by the multi-backend tests below: the full requirement
# carries an authorization premise, a numeric comparison premise, a set-membership premise, and a
# rejection-order obligation; the auth projection keeps only the authorization premise. Both lower
# to the SAME TLA+ module — the authorization_precondition lowering projects the comparison/
# membership premises out of S ∧ R (they are discharged by smt-theories / cvc5; PB-4) — binding the
# Pred_not_authorized / Pred_finalize_redemption operators the auth premise and rejection
# obligation map to. The dispatch-builder test assembles backend results by hand; the full-gate
# test closes the same requirement end to end.
_MULTI_BACKEND_REQUIREMENT = (
    "requirement authorization_precondition: scope redemption "
    "when wallet is not authorized and requested_amount <= spendable_balance "
    "and tier is in {gold, silver} "
    "then finalize_redemption must reject before rejected."
)
_MULTI_BACKEND_AUTH_PROJECTION = (
    "requirement authorization_precondition: scope redemption "
    "when wallet is not authorized then finalize_redemption must reject before rejected."
)
# Same auth premise + rejection obligation as the capstone (so its S ∧ R auth slice is VALID against
# the same reviewed S), but the comparison premises are jointly UNSATISFIABLE (requested_amount <= 5
# AND requested_amount >= 10). The projection routes those comparisons to smt-theories, which finds
# the contradictory antecedent — so they must block closure even though S ∧ R is valid. No membership
# premise, so no cvc5 dependency: the blocked SMT premise is isolated as the sole reason to refuse.
_MULTI_BACKEND_CONTRADICTORY_COMPARISON = (
    "requirement authorization_precondition: scope redemption "
    "when wallet is not authorized and requested_amount <= 5 and requested_amount >= 10 "
    "then finalize_redemption must reject before rejected."
)


def test_gate_dispatch_routes_mixed_requirement_across_distinct_backends() -> None:
    """The production evidence path routes per-fragment, never via the single-backend default.

    ``build_proof_with_formal_claim_dispatch`` is the gate's entry point. For a mixed requirement it
    builds the ProofObject's dispatch from the FormalClaim per-fragment router, so the proof that
    gates action carries the distinct backends each premise kind needs — and never the single-backend
    ``system_checker`` default that ``build_proof_dispatch_plan`` falls back to. This asserts the
    ROUTING alone (no backend results, so it runs without any solver installed);
    ``test_multi_backend_proof_closes_across_distinct_producers`` covers the real cross-producer
    discharge under installed Apalache + cvc5.
    """
    requirement = DslV3Parser().parse_ir(
        _MULTI_BACKEND_REQUIREMENT, requirement_id="REQ-MB-ROUTE", title="mixed routing"
    )

    proof, report = build_proof_with_formal_claim_dispatch(requirement=requirement, backend_results=[])

    assert report.result == "lowered"
    backends = {route.backend_id for route in proof.dispatch.routes}
    assert backends == {"solver_system_checker", "smt-theories", "cvc5"}
    assert "system_checker" not in backends
    assert {route.routing_mode for route in proof.dispatch.routes} == {"formal_claim"}


@pytest.mark.skipif(APALACHE is None, reason="apalache-mc binary not installed")
@requires_cvc5
def test_multi_backend_proof_closes_across_distinct_producers(tmp_path: Path) -> None:
    """PB-7 acceptance: one requirement's premises close across THREE distinct real producers.

    The production dispatch builder (``build_proof_with_formal_claim_dispatch``) routes each premise
    of a four-fragment requirement to the backend its kind needs, and each is discharged by a
    *different* real verification engine:

      - the authorization predicate and the rejection-order obligation -> ``solver_system_checker``,
        a real Apalache bounded S ∧ R check (BOUNDED_CHECKED);
      - the numeric comparison premise -> ``smt-theories``, a real z3 Int/Real query (SMT_CHECKED);
      - the set-membership premise -> ``cvc5``, a real cvc5 finite-set query (SMT_CHECKED).

    No premise is funneled to the propositional ``core_smt`` that drops comparison/membership ops —
    the conflation this closes. The S ∧ R verdict comes from the requirement's *auth projection* —
    identical to the full requirement's own lowering, which projects the comparison/membership
    premises out of S ∧ R (PB-4) — binding exactly the Pred_not_authorized /
    Pred_finalize_redemption operators the full claim's auth premise and rejection obligation map to.
    The decomposition is sound: S never reaches the forbidden outcome while ``not_authorized`` holds,
    so the obligation holds a fortiori under the stronger antecedent that also requires the numeric
    and membership conditions; z3 and cvc5 in turn confirm those added antecedent conditions are
    realizable. Every premise rests on a real solver result — not a fixture.
    """
    from nlreq.models import EvidenceLevel

    manifest, registry = _project(tmp_path, narrowing=True)
    impact = analyze_source_impact(
        PythonSourceLanguageAdapter(project_root=tmp_path), manifest, symbols=["finalize_redemption"]
    )

    # Real Apalache S ∧ R over the auth projection: valid, BOUNDED_CHECKED, binding both predicates.
    auth_projection = DslV3Parser().parse_ir(
        _MULTI_BACKEND_AUTH_PROJECTION, requirement_id="REQ-MB-AUTH", title="auth projection"
    )
    system_consistency = check_solver_backed_system_consistency(
        requirement=auth_projection,
        lowered=lower_ir_v2_to_tla(auth_projection),
        registry=registry,
        impact=impact,
        project_root=tmp_path,
        execution=default_apalache_s_and_r_execution(
            artifact_dir=(tmp_path / "s-and-r").as_posix()
        ),
    )
    assert system_consistency.result.status == "valid"
    assert system_consistency.result.details["checker_id"] == "apalache"
    assert set(system_consistency.result.details["bound_predicates"]) == {
        "Pred_not_authorized",
        "Pred_finalize_redemption",
    }

    # The full four-fragment requirement and its real z3 / cvc5 premise-consistency results.
    requirement = DslV3Parser().parse_ir(
        _MULTI_BACKEND_REQUIREMENT, requirement_id="REQ-MB-3P", title="multi-backend"
    )
    claim = build_formal_claim(requirement).formal_claim
    assert claim is not None
    covered_s_and_r = _cover_s_and_r_fragments(system_consistency.result, claim)
    backend_results = [
        covered_s_and_r,
        *smt_check_formal_claim_premise_consistency(claim),
        *cvc5_check_formal_claim_premises(claim),
    ]

    proof, _ = build_proof_with_formal_claim_dispatch(
        requirement=requirement,
        backend_results=backend_results,
        coverage=SpecCoverageReport(
            result="passed", threshold=0.0, covered_modules=0, total_modules=0,
            coverage_ratio=1.0, modules=[],
        ),
        trace_alignment=TraceAlignmentReport(result="passed", alignments=[]),
    )

    assert proof.status == "closed", [b.message for b in proof.blockers]
    assert not proof.blockers

    # Every premise discharged, each tagged with the distinct producer its kind routed to.
    by_kind = {premise.node_kind: premise for premise in proof.premises}
    assert all(premise.status == "discharged" for premise in proof.premises), proof.premises
    assert by_kind["predicate"].producer_id == "solver_system_checker"
    assert by_kind["predicate"].achieved_evidence == EvidenceLevel.BOUNDED_CHECKED
    assert by_kind["rejection_order"].producer_id == "solver_system_checker"
    assert by_kind["comparison"].producer_id == "smt-theories"
    assert by_kind["comparison"].achieved_evidence == EvidenceLevel.SMT_CHECKED
    assert by_kind["membership"].producer_id == "cvc5"
    assert by_kind["membership"].achieved_evidence == EvidenceLevel.SMT_CHECKED

    # The headline property: three genuinely distinct producers discharged this one requirement.
    discharging_producers = {
        premise.producer_id for premise in proof.premises if premise.status == "discharged"
    }
    assert discharging_producers == {"solver_system_checker", "smt-theories", "cvc5"}


@pytest.mark.skipif(APALACHE is None, reason="apalache-mc binary not installed")
@requires_cvc5
def test_end_to_end_gate_closes_mixed_requirement_across_distinct_producers(tmp_path: Path) -> None:
    """The full gate closes one mixed requirement across THREE distinct real producers (PB-4 capstone).

    This runs the *full* production gate (not the dispatch builder in isolation) on the
    four-fragment requirement and reads the proof_object artifact it writes. Every premise is
    discharged by the real verification engine its kind routes to, and three genuinely distinct
    engines close this one requirement:

      - the authorization predicate and the rejection-order obligation -> ``solver_system_checker``,
        a real Apalache bounded S ∧ R check (BOUNDED_CHECKED);
      - the numeric comparison premise -> ``smt-theories`` (z3 Int/Real, SMT_CHECKED);
      - the set-membership premise -> ``cvc5`` (native finite-set theory, SMT_CHECKED).

    Before PB-4 the gate's S ∧ R stage was ``unsupported`` here: the translator refused any TLA+
    lowering that mixed a comparison/membership premise, so the predicate/rejection premises stayed
    open and the gate could not accept. The authorization_precondition lowering now PROJECTS the
    comparison/membership premises out of the obligation (they are discharged independently by the
    SMT backends above) and lowers the auth obligation, so the same reviewed stateful S that closes
    the pure-auth requirement (test_end_to_end_gate_narrowing_s_and_r_closes_and_accepts) now closes
    this mixed one. No premise is funneled to the propositional ``core_smt`` that drops
    comparison/membership ops — the conflation this closes. Every premise rests on a real solver
    result, not a fixture.
    """
    manifest, registry = _project(tmp_path, narrowing=True)
    requirement = DslV3Parser().parse_ir(
        _MULTI_BACKEND_REQUIREMENT, requirement_id="REQ-MB-GATE", title="multi-backend gate"
    )
    agreement = TranslationAgreementInput(
        candidates=[
            TranslationCandidate(translator_id="primary", method="deterministic",
                                 requirement=requirement, provenance={"source": "test"}),
            TranslationCandidate(translator_id="replica", method="deterministic",
                                 requirement=requirement, provenance={"source": "test"}),
        ]
    )
    report = run_end_to_end_requirement_gate(
        controlled_text=_MULTI_BACKEND_REQUIREMENT,
        requirement_id="REQ-MB-GATE",
        title="multi-backend gate",
        source_adapter=PythonSourceLanguageAdapter(project_root=tmp_path),
        source_manifest=manifest,
        symbols=["finalize_redemption"],
        registry=registry,
        project_root=tmp_path,
        artifact_dir=tmp_path / "gate-artifacts",
        execution=_execution(tmp_path),
        requirement_ir=requirement,
        translation_agreement=agreement,
    )

    # S ∧ R now runs (the mixed requirement lowers) and the gate accepts end to end.
    assert report.statuses["system_consistency"] == "valid", (
        report.statuses, [(b.stage, b.status) for b in report.blockers]
    )
    assert report.decision == "accepted", (
        report.statuses, [(b.stage, b.status) for b in report.blockers]
    )
    assert report.proof_status == "closed"
    assert report.closure_result == "passed"
    assert report.downstream_action_allowed is True

    proof = read_json(Path(next(a.path for a in report.artifacts if a.name == "proof_object")))
    assert proof["status"] == "closed"
    by_kind = {premise["node_kind"]: premise for premise in proof["premises"]}
    assert all(premise["status"] == "discharged" for premise in proof["premises"]), proof["premises"]
    # Auth predicate + rejection-order obligation: real Apalache S ∧ R, BOUNDED_CHECKED.
    assert by_kind["predicate"]["producer_id"] == "solver_system_checker"
    assert by_kind["predicate"]["achieved_evidence"] == "BOUNDED_CHECKED"
    assert by_kind["rejection_order"]["producer_id"] == "solver_system_checker"
    # The two SMT premises are discharged by distinct theory producers — the de-conflation.
    assert by_kind["comparison"]["producer_id"] == "smt-theories"
    assert by_kind["comparison"]["achieved_evidence"] == "SMT_CHECKED"
    assert by_kind["membership"]["producer_id"] == "cvc5"
    assert by_kind["membership"]["achieved_evidence"] == "SMT_CHECKED"
    # The headline property: three genuinely distinct producers closed this one requirement.
    assert {p["producer_id"] for p in proof["premises"]} == {
        "solver_system_checker", "smt-theories", "cvc5",
    }


@pytest.mark.skipif(APALACHE is None, reason="apalache-mc binary not installed")
@requires_cvc5
def test_end_to_end_gate_mixed_requirement_refuses_on_s_and_r_counterexample(tmp_path: Path) -> None:
    """SMT-discharged premises must NOT mask a blocked S ∧ R — the mixed false-accept guard.

    The negative twin of the capstone above, and the property that matters most for PB-4: when the
    reviewed stateful S CAN reach the forbidden outcome while the premise holds, the auth predicate
    and rejection-order obligation BLOCK on a real Apalache counterexample — even though the
    comparison and set-membership premises are independently discharged by smt-theories / cvc5. The
    projection routes those SMT premises away from S ∧ R, so a naive reading could let two green SMT
    verdicts mask the blocked model check. They do not: closure requires EVERY premise discharged,
    so the blocked predicate/rejection premises keep the proof open and the gate refuses. This is
    the same false-accept this codebase guards everywhere — never trust generic closure logic for
    the refuse direction; prove it against a real counterexample.
    """
    manifest, registry = _project(tmp_path, narrowing_counterexample=True)
    requirement = DslV3Parser().parse_ir(
        _MULTI_BACKEND_REQUIREMENT, requirement_id="REQ-MB-GATE-CE", title="multi-backend ce"
    )
    agreement = TranslationAgreementInput(
        candidates=[
            TranslationCandidate(translator_id="primary", method="deterministic",
                                 requirement=requirement, provenance={"source": "test"}),
            TranslationCandidate(translator_id="replica", method="deterministic",
                                 requirement=requirement, provenance={"source": "test"}),
        ]
    )
    report = run_end_to_end_requirement_gate(
        controlled_text=_MULTI_BACKEND_REQUIREMENT,
        requirement_id="REQ-MB-GATE-CE",
        title="multi-backend ce",
        source_adapter=PythonSourceLanguageAdapter(project_root=tmp_path),
        source_manifest=manifest,
        symbols=["finalize_redemption"],
        registry=registry,
        project_root=tmp_path,
        artifact_dir=tmp_path / "gate-artifacts",
        execution=_execution(tmp_path),
        requirement_ir=requirement,
        translation_agreement=agreement,
    )

    assert report.statuses["system_consistency"] == "counterexample", (
        report.statuses, [(b.stage, b.status) for b in report.blockers]
    )
    assert report.decision == "refused"
    assert report.proof_status != "closed"
    assert report.closure_result != "passed"
    assert report.downstream_action_allowed is False

    proof = read_json(Path(next(a.path for a in report.artifacts if a.name == "proof_object")))
    assert proof["status"] != "closed"
    by_kind = {premise["node_kind"]: premise for premise in proof["premises"]}
    # Auth predicate + rejection-order BLOCKED on the real Apalache counterexample (covered by the
    # S ∧ R result, so the route matched, but refused because the verdict is a counterexample).
    assert by_kind["predicate"]["status"] == "blocked", by_kind["predicate"]
    assert by_kind["predicate"]["routed_backend"] == "solver_system_checker"
    assert by_kind["rejection_order"]["status"] == "blocked", by_kind["rejection_order"]
    # The SMT premises ARE discharged — yet cannot rescue closure while S ∧ R is blocked.
    assert by_kind["comparison"]["status"] == "discharged"
    assert by_kind["comparison"]["producer_id"] == "smt-theories"
    assert by_kind["membership"]["status"] == "discharged"
    assert by_kind["membership"]["producer_id"] == "cvc5"


@pytest.mark.skipif(APALACHE is None, reason="apalache-mc binary not installed")
def test_end_to_end_gate_refuses_when_projected_smt_premise_blocks_despite_valid_s_and_r(
    tmp_path: Path,
) -> None:
    """A valid S ∧ R auth slice must NOT close a requirement whose projected SMT premise blocks.

    The complement of the S ∧ R-counterexample twin above: there S ∧ R blocked while the SMT premises
    were green; here S ∧ R is VALID while a projected SMT premise blocks. The projection routes the
    comparison premises away from S ∧ R to smt-theories, so a naive reading could let one green model
    check mask a contradictory antecedent. It must not: the comparisons are jointly unsatisfiable
    (requested_amount <= 5 AND requested_amount >= 10), so smt-theories returns ``invalid`` for them,
    those premises stay blocked, and closure — which requires EVERY premise discharged — keeps the
    proof open and the gate refuses. This proves projection cannot become a false close from the SMT
    side. Needs Apalache for the real valid S ∧ R, but no cvc5: there is no membership premise, so the
    blocked comparison is the sole, isolated reason the gate refuses.
    """
    manifest, registry = _project(tmp_path, narrowing=True)
    requirement = DslV3Parser().parse_ir(
        _MULTI_BACKEND_CONTRADICTORY_COMPARISON,
        requirement_id="REQ-MB-GATE-CONTRA",
        title="multi-backend contradictory comparison",
    )
    agreement = TranslationAgreementInput(
        candidates=[
            TranslationCandidate(translator_id="primary", method="deterministic",
                                 requirement=requirement, provenance={"source": "test"}),
            TranslationCandidate(translator_id="replica", method="deterministic",
                                 requirement=requirement, provenance={"source": "test"}),
        ]
    )
    report = run_end_to_end_requirement_gate(
        controlled_text=_MULTI_BACKEND_CONTRADICTORY_COMPARISON,
        requirement_id="REQ-MB-GATE-CONTRA",
        title="multi-backend contradictory comparison",
        source_adapter=PythonSourceLanguageAdapter(project_root=tmp_path),
        source_manifest=manifest,
        symbols=["finalize_redemption"],
        registry=registry,
        project_root=tmp_path,
        artifact_dir=tmp_path / "gate-artifacts",
        execution=_execution(tmp_path),
        requirement_ir=requirement,
        translation_agreement=agreement,
    )

    # S ∧ R itself is VALID (the auth slice is identical to the capstone's) — the refusal is NOT
    # an S ∧ R block.
    assert report.statuses["system_consistency"] == "valid", (
        report.statuses, [(b.stage, b.status) for b in report.blockers]
    )
    # ...yet the gate REFUSES, because the projected SMT premise did not discharge.
    assert report.decision == "refused"
    assert report.proof_status != "closed"
    assert report.closure_result != "passed"
    assert report.downstream_action_allowed is False

    proof = read_json(Path(next(a.path for a in report.artifacts if a.name == "proof_object")))
    assert proof["status"] != "closed"
    by_kind = {premise["node_kind"]: premise for premise in proof["premises"]}
    # The comparison premise is BLOCKED by its real smt-theories verdict (contradictory antecedent),
    # and the proof names it as the open premise — projection did not silently close it.
    assert by_kind["comparison"]["status"] == "blocked", by_kind["comparison"]
    assert by_kind["comparison"]["routed_backend"] == "smt-theories"
    # The auth predicate + rejection-order obligation DID discharge on the valid S ∧ R — proving the
    # refusal is caused by the SMT premise alone, not a blocked model check.
    assert by_kind["predicate"]["status"] == "discharged"
    assert by_kind["predicate"]["producer_id"] == "solver_system_checker"
    assert by_kind["rejection_order"]["status"] == "discharged"


def test_end_to_end_gate_s_and_r_blocks_when_checker_absent(tmp_path: Path) -> None:
    """When the S ∧ R checker binary is absent, the gate refuses — it never silently passes.

    This is the PB-3 honesty tripwire at the gate level. The composition succeeds (a real,
    grounded S ∧ R module is written), but the checker subprocess cannot launch, so the run
    degrades to ``tool_error`` → ``invalid`` (UNVERIFIED), the system_consistency stage records
    no evidence level, and the gate decision is ``refused`` with a system_consistency blocker.
    A missing model checker must never be read as ``valid``. Hermetic: the bogus binary name is
    absent on every machine, so this needs no installed checker.
    """
    absent_checker = FormalBackendExecution(
        checker_id="apalache",
        command=["apalache-mc-not-installed", *list(APALACHE_S_AND_R_COMMAND)[1:]],
        artifact_dir=(tmp_path / "s-and-r-absent").as_posix(),
    )
    report = _run_reviewed_s_gate(tmp_path, solver_execution=absent_checker)

    assert report.statuses["system_consistency"] == "invalid", (
        report.statuses, [(b.stage, b.status) for b in report.blockers]
    )
    system_consistency = read_json(
        Path(next(a.path for a in report.artifacts if a.name == "system_consistency"))
    )
    assert system_consistency["result"].get("evidence_level") is None
    assert system_consistency["result"]["details"]["tool_error"]
    assert report.decision == "refused"
    assert any(b.stage == "system_consistency" for b in report.blockers)


def test_end_to_end_gate_s_and_r_z3_is_explicit_fixture_mode(tmp_path: Path) -> None:
    """The in-process Z3 path is reachable only as an explicit opt-in, and is labeled SMT — not
    bounded — evidence.

    Z3 is the development/fixture checker: it parses the lowered obligation under S's predicate
    assignments without ever evaluating S's Init/Next, so it is not a substitute for a bounded
    model check of the composed transition system. It must be reached only when a caller asks
    for it by name, and its verdict must carry ``SMT_CHECKED``, never ``BOUNDED_CHECKED`` — so
    it can never be mistaken for real S ∧ R evidence. Hermetic: no external binary.
    """
    report = _run_reviewed_s_gate(
        tmp_path, solver_execution=FormalBackendExecution(checker_id="z3")
    )

    assert report.statuses["system_consistency"] == "valid", (
        report.statuses, [(b.stage, b.status) for b in report.blockers]
    )
    system_consistency = read_json(
        Path(next(a.path for a in report.artifacts if a.name == "system_consistency"))
    )
    assert system_consistency["result"]["details"]["checker_id"] == "z3"
    assert system_consistency["result"]["evidence_level"] == "SMT_CHECKED"


def test_build_proof_with_formal_claim_dispatch_uses_fragment_ids_for_classed_ir() -> None:
    """build_proof_with_formal_claim_dispatch must carry FormalClaim fragment IDs into the ProofObject.

    This tests the production entry point — not a manually-constructed dispatch plan — so the
    assertion that ProofObject.premises contain formal fragment IDs is not test-only wiring.
    With no backend results all premises are open; the test only verifies the IDs are present.
    """
    ir = DslV3Parser().parse_ir(
        FIXTURES.joinpath("authorization_precondition_v3.nlreq").read_text(),
        requirement_id="AUTH-FC-GATE",
        title="Authorization precondition (gate test)",
    )

    proof, formal_claim_report = build_proof_with_formal_claim_dispatch(
        requirement=ir,
        backend_results=[],
    )

    assert formal_claim_report.result == "lowered"
    assert formal_claim_report.formal_claim is not None
    premise_ids = {p.premise_id for p in proof.premises}
    for fragment in [*formal_claim_report.formal_claim.premises, *formal_claim_report.formal_claim.obligations]:
        assert fragment.fragment_id in premise_ids, (
            f"fragment {fragment.fragment_id} ({fragment.kind}) missing from ProofObject.premises"
        )
    # All premises open — no backend results were supplied
    assert all(p.status == "open" for p in proof.premises)


def test_end_to_end_gate_records_formal_claim_artifact(tmp_path: Path) -> None:
    """FormalClaim artifact must be recorded by the gate regardless of claim class support.

    DSL-v2 text without a supported requirement_class produces a 'refused' formal claim;
    the artifact is still recorded so downstream tooling can inspect why dispatch fell back
    to the default system-consistency plan.
    """
    manifest, registry = _project(tmp_path)

    report = run_end_to_end_requirement_gate(
        controlled_text=DSL,
        requirement_id="REQ-GATE-FC-001",
        title="Formal claim artifact test",
        source_adapter=PythonSourceLanguageAdapter(project_root=tmp_path),
        source_manifest=manifest,
        symbols=["finalize_redemption"],
        registry=registry,
        project_root=tmp_path,
        artifact_dir=tmp_path / "gate-artifacts",
        execution=_execution(tmp_path),
    )

    assert "formal_claim_artifact" in {artifact.name for artifact in report.artifacts}
    assert "formal_claim" in report.statuses
    # DSL-v2 text has no requirement_class annotation — the formal claim is refused and the
    # gate falls back to the default system-consistency dispatch. The artifact is recorded
    # regardless, which is what this test guards.
    assert report.statuses["formal_claim"] == "refused"
    # The overall decision is intentionally NOT asserted accepted here. This fixture's reviewed
    # spec covers the module but declares no invariant, so the S ∧ R stage is `unsupported` and
    # the gate blocks (no vacuous floor pass). That blocking is unrelated to formal-claim
    # recording; the dedicated coverage is
    # test_end_to_end_gate_blocks_relevant_spec_without_invariant.


def test_end_to_end_gate_blocks_relevant_spec_without_invariant(tmp_path: Path) -> None:
    """A reviewed spec that covers the impacted module but declares no invariant must BLOCK.

    This is the positive guard against a vacuous S ∧ R floor: a reviewed spec relevant to the
    change that asserts nothing checkable cannot be silently accepted. It is distinct from
    "no reviewed spec is relevant at all" (genuinely not_applicable, passing).
    The default _project fixture registers exactly this case — spec:redemption covers the
    redemption module, is reviewed and fresh, but declares no invariant — so the S ∧ R stage is
    `unsupported` with mode `relevant_spec_without_invariant`, the gate does not accept, and
    downstream action is refused.
    """
    manifest, registry = _project(tmp_path)

    report = run_end_to_end_requirement_gate(
        controlled_text=DSL,
        requirement_id="REQ-GATE-NOINV-001",
        title="Relevant spec without invariant blocks",
        source_adapter=PythonSourceLanguageAdapter(project_root=tmp_path),
        source_manifest=manifest,
        symbols=["finalize_redemption"],
        registry=registry,
        project_root=tmp_path,
        artifact_dir=tmp_path / "gate-artifacts",
        execution=_execution(tmp_path),
    )

    # The S ∧ R stage refuses to form an obligation from an assertionless reviewed spec.
    assert report.statuses["system_consistency"] == "unsupported"
    assert report.decision != "accepted"
    assert report.downstream_action_allowed is False
    # The refusal is structural (read from the registry), not a marker grep: its recorded mode
    # names exactly why, and names the relevant spec.
    sysc_path = Path(next(a.path for a in report.artifacts if a.name == "system_consistency"))
    details = read_json(sysc_path)["result"]["details"]
    assert details["mode"] == "relevant_spec_without_invariant"
    assert "spec:redemption" in details["relevant_spec_ids"]
    # The block surfaces as a system_consistency blocker (inconclusive — we could not form an
    # S ∧ R obligation), kept distinct from a definitive counterexample refusal.
    sysc_blocker = next(
        (b for b in report.blockers if b.stage == "system_consistency"), None
    )
    assert sysc_blocker is not None
    assert sysc_blocker.status == "unknown"


def test_end_to_end_gate_with_v3_requirement_has_formal_claim_fragment_ids(tmp_path: Path) -> None:
    """Full gate with a DSL v3 requirement carries FormalClaim fragment IDs into the ProofObject.

    This exercises the production code path: run_end_to_end_requirement_gate → FormalClaim
    dispatch → ProofObject. It is NOT the helper-only path from
    test_build_proof_with_formal_claim_dispatch_uses_fragment_ids_for_classed_ir.

    Predicate and rejection_order premises stay UNDISCHARGED here. They route to the
    solver-backed S ∧ R (BOUNDED_CHECKED), which discharges them only against a reviewed S that
    binds their predicates into a composed module. This project uses the default empty spec
    (no declared invariant), so the S ∧ R composition refuses and binds nothing — the premises
    have no bound operator to discharge against and remain open. A reviewed, stateful S that
    binds the predicates is what closes them (see the narrowing accepted-path test).
    """
    manifest, registry = _project(tmp_path)
    ir = DslV3Parser().parse_ir(
        FIXTURES.joinpath("authorization_precondition_v3.nlreq").read_text(),
        requirement_id="AUTH-GATE-V3-001",
        title="Authorization precondition (v3 gate test)",
    )

    report = run_end_to_end_requirement_gate(
        controlled_text="when actor is not authorized then operation must reject before state_change.",
        requirement_id="AUTH-GATE-V3-001",
        title="Authorization precondition (v3 gate test)",
        source_adapter=PythonSourceLanguageAdapter(project_root=tmp_path),
        source_manifest=manifest,
        symbols=["operation"],
        registry=registry,
        project_root=tmp_path,
        artifact_dir=tmp_path / "gate-artifacts-v3",
        execution=_execution(tmp_path),
        requirement_ir=ir,
    )

    assert "formal_claim_artifact" in {artifact.name for artifact in report.artifacts}
    assert report.statuses["formal_claim"] == "lowered"

    # ProofObject must contain FormalClaim fragment IDs from the normal gate flow
    proof_path = Path(next(a.path for a in report.artifacts if a.name == "proof_object"))
    from nlreq.proof_closure import ProofObject
    from nlreq.jsonutil import read_json
    proof = ProofObject.model_validate(read_json(proof_path))
    premise_ids = {p.premise_id for p in proof.premises}
    # All premise IDs must be formal fragment IDs (start with "formal.")
    assert all(pid.startswith("formal.") for pid in premise_ids), (
        f"Expected formal fragment IDs in ProofObject but found: {premise_ids}"
    )

    # Predicate and rejection_order premises must NOT be discharged: the default empty spec
    # declares no invariant, so the solver-backed S ∧ R composition refuses and binds no
    # predicate — there is no bound operator to discharge these formal premises against.
    predicate_premises = [p for p in proof.premises if p.node_kind == "predicate"]
    rejection_order = [p for p in proof.premises if p.node_kind == "rejection_order"]
    assert predicate_premises and rejection_order
    assert all(p.status != "discharged" for p in predicate_premises), (
        f"Predicate premises must not be discharged without a reviewed S that binds them: "
        f"{predicate_premises}"
    )
    assert all(p.status != "discharged" for p in rejection_order), (
        f"rejection_order premises must not be discharged without a reviewed S that binds them: "
        f"{rejection_order}"
    )

    # No producer-mapping blockers from intentionally-unsupported fragments.
    # Unsupported BackendResults must carry evidence_level=None so _producer_blockers
    # skips them, rather than emitting spurious "producer is not allowed to emit this
    # evidence level" blockers for core_smt / apalache backends.
    producer_mapping_blockers = [
        b for b in proof.blockers if b.category == "producer_mapping"
    ]
    assert not producer_mapping_blockers, (
        f"No producer-mapping blockers expected for intentionally-unsupported fragments, "
        f"got: {producer_mapping_blockers}"
    )


@requires_cvc5
def test_end_to_end_gate_wires_premise_consistency_agreement(tmp_path: Path) -> None:
    """The gate computes the cross-backend premise-consistency agreement on the lowered FormalClaim
    and carries it into the production ProofObject (PB-6.T3 production wiring).

    A numeric_invariant requirement whose premises are jointly satisfiable (collateral in [10, 50])
    is decided 'valid' by both independent SMT encoders — z3 as core_smt and cvc5 — so the agreement
    is 'agreed'. The assertions are scoped to the agreement, not the overall gate decision: the
    default project's reviewed spec declares no invariant, so the S ∧ R stage blocks for that
    unrelated reason. The point here is that the agreement is computed, persisted as its own
    artifact, and embedded in the ProofObject — not that the requirement is accepted.
    """
    manifest, registry = _project(tmp_path)
    ir = DslV3Parser().parse_ir(
        "requirement numeric_invariant:\n"
        "scope reserve\n"
        "when collateral >= 10 and collateral <= 50\n"
        "then keep collateral >= 1\n",
        requirement_id="REQ-AGREE-E2E-001",
        title="Premise consistency agreement (e2e)",
    )

    report = run_end_to_end_requirement_gate(
        controlled_text="when collateral >= 10 and collateral <= 50 then keep collateral >= 1.",
        requirement_id="REQ-AGREE-E2E-001",
        title="Premise consistency agreement (e2e)",
        source_adapter=PythonSourceLanguageAdapter(project_root=tmp_path),
        source_manifest=manifest,
        symbols=["operation"],
        registry=registry,
        project_root=tmp_path,
        artifact_dir=tmp_path / "gate-artifacts-agree",
        execution=_execution(tmp_path),
        requirement_ir=ir,
    )

    # The agreement report is persisted as its own gate artifact.
    assert "backend_agreement" in {artifact.name for artifact in report.artifacts}

    # The agreement is carried into the production ProofObject, with the two independent SMT
    # encoders agreeing on the satisfiable premise set.
    from nlreq.proof_closure import ProofObject

    proof_path = Path(next(a.path for a in report.artifacts if a.name == "proof_object"))
    proof = ProofObject.model_validate(read_json(proof_path))
    assert proof.backend_agreement is not None
    assert proof.backend_agreement.status == "agreed"
    # An agreement is additive: it never adds a backend_agreement blocker — only a real
    # opposite-verdict divergence (status "disagreed") would gate closure.
    assert not any(b.category == "backend_agreement" for b in proof.blockers)


def test_end_to_end_gate_refuses_on_premise_consistency_disagreement(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A real opposite-verdict divergence between the two SMT encoders refuses the production gate.

    The mirror of test_end_to_end_gate_wires_premise_consistency_agreement: there the encoders agree
    and the agreement adds no blocker; here build_premise_consistency_agreement is forced to return a
    "disagreed" report (two backends reaching opposite verdicts on the same overlap_key), and the
    refusal must propagate through every layer — the ProofObject blocks with a backend_agreement
    blocker, the closure gate blocks, and the final decision refuses. Forcing the report lets this run
    without cvc5: it proves the wiring refuses on disagreement, not that cvc5 produces one."""
    from nlreq.backend_agreement import build_backend_agreement_report
    from nlreq.models import BackendResult, EvidenceLevel
    from nlreq.proof_closure import ProofObject

    def _forced_disagreement(_claim, **_kwargs):
        opposite_verdicts = [
            BackendResult(
                backend="core_smt",
                status="valid",
                evidence_level=EvidenceLevel.SMT_CHECKED,
                details={"overlap_key": "planted-question", "agreement_compare": "verdict"},
            ),
            BackendResult(
                backend="cvc5",
                status="invalid",
                evidence_level=EvidenceLevel.SMT_CHECKED,
                details={"overlap_key": "planted-question", "agreement_compare": "verdict"},
            ),
        ]
        return build_backend_agreement_report(opposite_verdicts, mode="verdict")

    monkeypatch.setattr(
        "nlreq.end_to_end_gate.build_premise_consistency_agreement", _forced_disagreement
    )

    manifest, registry = _project(tmp_path)
    ir = DslV3Parser().parse_ir(
        "requirement numeric_invariant:\n"
        "scope reserve\n"
        "when collateral >= 10 and collateral <= 50\n"
        "then keep collateral >= 1\n",
        requirement_id="REQ-DISAGREE-E2E-001",
        title="Premise consistency disagreement (e2e)",
    )

    report = run_end_to_end_requirement_gate(
        controlled_text="when collateral >= 10 and collateral <= 50 then keep collateral >= 1.",
        requirement_id="REQ-DISAGREE-E2E-001",
        title="Premise consistency disagreement (e2e)",
        source_adapter=PythonSourceLanguageAdapter(project_root=tmp_path),
        source_manifest=manifest,
        symbols=["operation"],
        registry=registry,
        project_root=tmp_path,
        artifact_dir=tmp_path / "gate-artifacts-disagree",
        execution=_execution(tmp_path),
        requirement_ir=ir,
    )

    # The disagreement reaches the ProofObject and blocks it with a backend_agreement blocker.
    proof_path = Path(next(a.path for a in report.artifacts if a.name == "proof_object"))
    proof = ProofObject.model_validate(read_json(proof_path))
    assert proof.backend_agreement is not None
    assert proof.backend_agreement.status == "disagreed"
    assert proof.status == "blocked"
    assert any(b.category == "backend_agreement" for b in proof.blockers)

    # The closure gate and the final decision both refuse on the back of that block.
    assert report.closure_result == "blocked"
    assert report.decision == "refused"
    assert report.downstream_action_allowed is False


def test_end_to_end_gate_refuses_trace_replay_violation(tmp_path: Path) -> None:
    manifest, registry = _project(tmp_path, trace_actions=["finalize_redemption"])

    report = run_end_to_end_requirement_gate(
        controlled_text=DSL,
        requirement_id="REQ-GATE-002",
        title="Requirement gate refusal",
        source_adapter=PythonSourceLanguageAdapter(project_root=tmp_path),
        source_manifest=manifest,
        symbols=["finalize_redemption"],
        registry=registry,
        project_root=tmp_path,
        artifact_dir=tmp_path / "gate-artifacts",
        execution=_execution(tmp_path),
    )

    assert report.decision == "refused"
    assert report.downstream_action_allowed is False
    assert any(blocker.stage == "trace_replay" for blocker in report.blockers)


def test_end_to_end_requirement_gate_cli_writes_report(tmp_path: Path, capsys) -> None:
    manifest, registry = _project(tmp_path)
    requirement_path = tmp_path / "requirement.nlreq2"
    manifest_path = tmp_path / "source-manifest.json"
    registry_path = tmp_path / "registry.json"
    out = tmp_path / "gate-report.json"
    requirement_path.write_text(DSL)
    manifest_path.write_text(json.dumps(manifest.model_dump(mode="json"), indent=2))
    registry_path.write_text(json.dumps(registry.model_dump(mode="json"), indent=2))

    exit_code = main(
        [
            "requirement-gate",
            str(requirement_path),
            "--requirement-id",
            "REQ-GATE-003",
            "--title",
            "Requirement gate CLI",
            "--source-manifest",
            str(manifest_path),
            "--source-language",
            "python",
            "--symbol",
            "finalize_redemption",
            "--registry",
            str(registry_path),
            "--project-root",
            str(tmp_path),
            "--artifact-dir",
            str(tmp_path / "gate-artifacts"),
            "--out",
            str(out),
            "--checker-id",
            "custom",
            "--checker-command",
            sys.executable,
            "-c",
            "print('verification successful')",
        ]
    )

    output = capsys.readouterr().out

    assert exit_code == 0
    assert "Requirement gate report:" in output
    # This test guards that the CLI runs the gate and writes a well-formed report. The decision
    # is not asserted accepted: the fixture's reviewed spec covers the module but declares no
    # invariant, so S ∧ R is `unsupported` and the gate blocks rather than
    # passing on a vacuous floor. (Dedicated coverage of that block:
    # test_end_to_end_gate_blocks_relevant_spec_without_invariant.)
    report_json = read_json(out)
    assert report_json["decision"] in {"accepted", "refused", "unknown"}
    assert report_json["statuses"]["system_consistency"] == "unsupported"
    assert report_json["artifacts"]


def test_gate_single_source_ir_yields_needs_review_not_agreed(tmp_path: Path) -> None:
    """When a single pre-parsed IR is supplied, translation agreement must be needs_review.

    The old implementation fabricated two identical candidates so the agreement was
    trivially 'agreed'. A single source cannot produce ensemble agreement — it should
    be 'needs_review' instead.
    """
    manifest, registry = _project(tmp_path)
    ir = DslV3Parser().parse_ir(
        FIXTURES.joinpath("authorization_precondition_v3.nlreq").read_text(),
        requirement_id="GATE-SINGLE-001",
        title="Single source gate test",
    )

    report = run_end_to_end_requirement_gate(
        controlled_text="when actor is not authorized then operation must reject before state_change.",
        requirement_id="GATE-SINGLE-001",
        title="Single source gate test",
        source_adapter=PythonSourceLanguageAdapter(project_root=tmp_path),
        source_manifest=manifest,
        symbols=["operation"],
        registry=registry,
        project_root=tmp_path,
        artifact_dir=tmp_path / "gate-single-artifacts",
        execution=_execution(tmp_path),
        requirement_ir=ir,
    )

    # Locate the translation_agreement artifact and assert it is needs_review.
    agreement_artifact = next(
        (a for a in report.artifacts if a.name == "translation_agreement"), None
    )
    assert agreement_artifact is not None, "translation_agreement artifact must be recorded"
    from nlreq.translator_agreement import TranslationAgreementReport

    agreement = TranslationAgreementReport.model_validate(read_json(Path(agreement_artifact.path)))
    assert agreement.status == "needs_review", (
        f"Single-source IR must yield needs_review, not {agreement.status!r}"
    )


def test_gate_refuses_on_disagreeing_translation_agreement_input(tmp_path: Path) -> None:
    """When a TranslationAgreementInput with genuinely different candidates is supplied,
    the gate must produce decision='refused' (not 'unknown' or 'accepted') and record
    a translation_refusal artifact with NLR-REFUSED-AMBIGUOUS.

    This exercises the full refuse_ambiguous_ensemble wiring: the gate calls it on
    disagreement and the decision propagates as a blocker.
    """
    from nlreq.dsl_v3 import DslV3Parser
    from nlreq.translator_agreement import TranslationAgreementInput, TranslationCandidate

    manifest, registry = _project(tmp_path)

    auth_req = DslV3Parser().parse_ir(
        FIXTURES.joinpath("authorization_precondition_v3.nlreq").read_text(),
        requirement_id="GATE-DISAGREE-001",
        title="Auth candidate",
    )
    # A structurally distinct requirement (numeric_invariant has different claim_class).
    numeric_req = DslV3Parser().parse_ir(
        "requirement numeric_invariant:\nscope reserve\nwhen reserve is confirmed\nthen keep collateral >= 100\n",
        requirement_id="GATE-DISAGREE-001",
        title="Numeric candidate",
    )
    disagreeing_input = TranslationAgreementInput(
        candidates=[
            TranslationCandidate(
                translator_id="candidate-auth",
                method="deterministic",
                requirement=auth_req,
                provenance={"source": "test"},
            ),
            TranslationCandidate(
                translator_id="candidate-numeric",
                method="deterministic",
                requirement=numeric_req,
                provenance={"source": "test"},
            ),
        ]
    )

    report = run_end_to_end_requirement_gate(
        controlled_text="when actor is not authorized then operation must reject before state_change.",
        requirement_id="GATE-DISAGREE-001",
        title="Disagree gate test",
        source_adapter=PythonSourceLanguageAdapter(project_root=tmp_path),
        source_manifest=manifest,
        symbols=["operation"],
        registry=registry,
        project_root=tmp_path,
        artifact_dir=tmp_path / "gate-disagree-artifacts",
        execution=_execution(tmp_path),
        requirement_ir=auth_req,
        translation_agreement=disagreeing_input,
    )

    # Gate must be refused, not unknown or accepted.
    assert report.decision == "refused", (
        f"Disagreeing translation must produce refused decision, got {report.decision!r}"
    )
    assert report.downstream_action_allowed is False

    # A translation_refusal artifact with NLR-REFUSED-AMBIGUOUS must be recorded.
    refusal_artifact = next(
        (a for a in report.artifacts if a.name == "translation_refusal"), None
    )
    assert refusal_artifact is not None, "translation_refusal artifact must be recorded on disagreement"
    from nlreq.semantic_translation import SemanticTranslationReport

    refusal = SemanticTranslationReport.model_validate(read_json(Path(refusal_artifact.path)))
    assert refusal.refusal_code == "NLR-REFUSED-AMBIGUOUS", (
        f"Expected NLR-REFUSED-AMBIGUOUS, got {refusal.refusal_code!r}"
    )
    assert len(refusal.clarification_questions) >= 1

    # Provenance: gate must set a gate-scoped translation_id and carry input hashes.
    assert refusal.translation_id == "gate-translation-GATE-DISAGREE-001", (
        f"Gate refusal must carry gate-scoped translation_id, got {refusal.translation_id!r}"
    )
    assert "controlled_text" in refusal.input_hashes, (
        "Gate refusal must carry controlled_text hash in input_hashes"
    )
    assert "requirement_ir" in refusal.input_hashes, (
        "Gate refusal must carry requirement_ir hash in input_hashes"
    )

    # Fail-fast: no downstream artifacts must be produced after a disagreed translation.
    artifact_names = {a.name for a in report.artifacts}
    for downstream in ("formal_claim_artifact", "proof_object", "closure_gate", "lowered_formal"):
        assert downstream not in artifact_names, (
            f"Downstream artifact '{downstream}' must not be produced when translation disagreed"
        )


def test_gate_z3_neg_r_plus_s_refuses_on_counterexample(tmp_path: Path) -> None:
    """Z3 gate refusal: ¬R + S(pred=TRUE) → counterexample → gate refused.

    Mirrors test_z3_gate_neg_r_plus_s_returns_counterexample but drives the full
    run_end_to_end_requirement_gate.  ¬R has Pred_not_authorized; S assigns it TRUE.
    Z3 returns counterexample → system_consistency blocker → decision 'refused'.

    The translation_agreement supplies two matching candidates so the agreement is
    'agreed' and the solver refusal is the sole blocker (not masked as 'unknown').
    """
    from nlreq.translator_agreement import TranslationAgreementInput, TranslationCandidate

    src = tmp_path / "src"
    specs = tmp_path / "specs"
    src.mkdir()
    specs.mkdir()
    (src / "redemption.py").write_text(
        "def finalize_redemption(wallet):\n    return 'rejected'\n"
    )
    # S: Pred_not_authorized(a) == TRUE — ¬R's obligation predicate is TRUE, Z3 → counterexample.
    # SafetyInvariant makes S declare an invariant so the gate treats S ∧ R as applicable and
    # runs the solver; the Z3 in-process path decides from the Pred_* assignment, not the
    # invariant body.
    (specs / "SystemConstraint.tla").write_text(
        "---- MODULE SystemConstraint ----\n"
        "CONSTANT a\n"
        "\\* @type: (Str) => Bool;\n"
        "Pred_not_authorized(a) == TRUE\n"
        "SafetyInvariant == TRUE\n"
        "====\n"
    )
    trace_path = tmp_path / "traces.json"
    trace_path.write_text(json.dumps([{
        "trace_id": "T1",
        "adapter_id": "raw-python",
        "source_hash": "sha256:x",
        "events": [
            {"event_id": "e1", "timestamp": "2026-06-01T00:00:01Z",
             "action": "finalize_redemption", "post_state": {}},
        ],
    }]))
    manifest = SourceManifest.model_validate({
        "schema_version": "0.1",
        "adapter": "python-source",
        "language": "python",
        "runtime": "cpython",
        "modules": [{
            "module_id": "redemption",
            "path": "src/redemption.py",
            "symbols": ["finalize_redemption"],
            "trace_sources": ["traces.json"],
        }],
    })
    registry = SystemSpecRegistry.model_validate({
        "schema_version": "0.1",
        "specs": [{
            "spec_id": "spec:redemption",
            "module_ids": ["redemption"],
            "formalism": "tla",
            "path": "specs/SystemConstraint.tla",
            "version": "1",
            "review_status": "reviewed",
            "freshness": "fresh",
            "invariants": ["SafetyInvariant"],
        }],
    })
    neg_r_ir = DslV3Parser().parse_ir(
        "requirement authorization_precondition: scope redemption "
        "when wallet is not authorized then finalize_redemption must reject before rejected.",
        requirement_id="GATE-Z3-NEG-001",
        title="Negation gate Z3 test",
    )
    # Two matching candidates so translation_agreement status is 'agreed', not 'needs_review'.
    agreement = TranslationAgreementInput(
        candidates=[
            TranslationCandidate(
                translator_id="neg-r-primary",
                method="deterministic",
                requirement=neg_r_ir,
                provenance={"source": "test"},
            ),
            TranslationCandidate(
                translator_id="neg-r-reparse",
                method="deterministic",
                requirement=neg_r_ir,
                provenance={"source": "test"},
            ),
        ]
    )

    # execution=None so self-consistency uses the default unsupported path (no TLA binary);
    # solver_execution="z3" drives the solver-backed S∧R check in-process via Z3.
    report = run_end_to_end_requirement_gate(
        controlled_text="when wallet is not authorized then finalize_redemption must reject before rejected.",
        requirement_id="GATE-Z3-NEG-001",
        title="Negation gate Z3 test",
        source_adapter=PythonSourceLanguageAdapter(project_root=tmp_path),
        source_manifest=manifest,
        symbols=["finalize_redemption"],
        registry=registry,
        project_root=tmp_path,
        artifact_dir=tmp_path / "gate-z3-neg-artifacts",
        solver_execution=FormalBackendExecution(checker_id="z3"),
        requirement_ir=neg_r_ir,
        translation_agreement=agreement,
    )

    assert report.decision == "refused", (
        f"¬R + Z3 S(pred=TRUE) must refuse; got decision={report.decision!r}, "
        f"blockers={[b.model_dump() for b in report.blockers]}"
    )
    system_blockers = [b for b in report.blockers if b.stage == "system_consistency"]
    assert system_blockers, (
        "Gate refusal must carry a system_consistency blocker"
    )
    assert system_blockers[0].status == "refused"


def test_gate_z3_execution_adds_smt_checked_solver_result_to_proof_object(tmp_path: Path) -> None:
    """Gate with Z3 positive path: solver returns valid/SMT_CHECKED and ProofObject carries it.

    Mirrors test_z3_gate_r_plus_s_returns_valid through the full gate.  The authorization_
    precondition IR has Pred_authorized; S assigns Pred_authorized(a) == FALSE (conservative
    constraint).  Z3 returns "valid" → evidence_level=SMT_CHECKED (in-process propositional
    check, not bounded model checking).  The result must appear in ProofObject.backend_results.
    """
    from nlreq.formal_backend import FormalBackendExecution
    from nlreq.proof_closure import ProofObject
    from nlreq.models import EvidenceLevel
    from nlreq.translator_agreement import TranslationAgreementInput, TranslationCandidate

    src = tmp_path / "src"
    specs = tmp_path / "specs"
    src.mkdir()
    specs.mkdir()
    (src / "operation.py").write_text(
        "def operation(actor):\n    return 'rejected'\n"
    )
    # Fixture: "when actor is not authorized then operation must reject" → predicate is
    # Pred_not_authorized.  S assigns Pred_not_authorized(a) == FALSE so the obligation
    # antecedent is never triggered → no violation reachable → Z3 UNSAT → "valid".
    # SafetyInvariant makes S declare an invariant so the gate runs the solver; the Z3
    # in-process path decides from the Pred_* assignment, not the invariant body.
    (specs / "SystemConstraint.tla").write_text(
        "---- MODULE SystemConstraint ----\n"
        "CONSTANT a\n"
        "\\* @type: (Str) => Bool;\n"
        "Pred_not_authorized(a) == FALSE\n"
        "SafetyInvariant == TRUE\n"
        "====\n"
    )
    trace_path = tmp_path / "traces.json"
    trace_path.write_text(json.dumps([{
        "trace_id": "T1", "adapter_id": "raw-python", "source_hash": "sha256:x",
        "events": [{"event_id": "e1", "timestamp": "2026-06-01T00:00:01Z",
                    "action": "operation", "post_state": {}}],
    }]))
    manifest = SourceManifest.model_validate({
        "schema_version": "0.1", "adapter": "python-source",
        "language": "python", "runtime": "cpython",
        "modules": [{"module_id": "redemption", "path": "src/operation.py",
                     "symbols": ["operation"], "trace_sources": ["traces.json"]}],
    })
    registry = SystemSpecRegistry.model_validate({
        "schema_version": "0.1",
        "specs": [{"spec_id": "spec:redemption", "module_ids": ["redemption"],
                   "formalism": "tla", "path": "specs/SystemConstraint.tla",
                   "version": "1", "review_status": "reviewed", "freshness": "fresh",
                   "invariants": ["SafetyInvariant"]}],
    })
    ir = DslV3Parser().parse_ir(
        FIXTURES.joinpath("authorization_precondition_v3.nlreq").read_text(),
        requirement_id="GATE-Z3-POS-001",
        title="Z3 positive gate test",
    )
    agreement = TranslationAgreementInput(
        candidates=[
            TranslationCandidate(translator_id="z3-pos-p", method="deterministic",
                                 requirement=ir, provenance={"source": "test"}),
            TranslationCandidate(translator_id="z3-pos-r", method="deterministic",
                                 requirement=ir, provenance={"source": "test"}),
        ]
    )

    report = run_end_to_end_requirement_gate(
        controlled_text=(FIXTURES / "authorization_precondition_v3.nlreq").read_text(),
        requirement_id="GATE-Z3-POS-001",
        title="Z3 positive gate test",
        source_adapter=PythonSourceLanguageAdapter(project_root=tmp_path),
        source_manifest=manifest,
        symbols=["operation"],
        registry=registry,
        project_root=tmp_path,
        artifact_dir=tmp_path / "gate-z3-pos-artifacts",
        solver_execution=FormalBackendExecution(checker_id="z3"),
        requirement_ir=ir,
        translation_agreement=agreement,
    )

    # The consolidated, solver-backed system-consistency artifact must be recorded.
    artifact_names = {a.name for a in report.artifacts}
    assert "system_consistency" in artifact_names, (
        "system_consistency artifact must be recorded (solver-backed when solver_execution='z3')"
    )

    # ProofObject must contain a valid solver_system_checker result with SMT_CHECKED.
    proof_path = Path(next(a.path for a in report.artifacts if a.name == "proof_object"))
    proof = ProofObject.model_validate(read_json(proof_path))
    solver_results = [r for r in proof.backend_results if r.backend == "solver_system_checker"]
    assert solver_results, (
        "ProofObject must carry at least one solver_system_checker backend result"
    )
    valid_solver = [r for r in solver_results if r.status == "valid"]
    assert valid_solver, (
        f"solver_system_checker result must be 'valid' for R + S(pred=FALSE); "
        f"got {[r.status for r in solver_results]}"
    )
    # Z3 in-process is propositional SMT — SMT_CHECKED, not BOUNDED_CHECKED.
    assert all(r.evidence_level == EvidenceLevel.SMT_CHECKED for r in valid_solver), (
        f"Valid solver results must carry SMT_CHECKED: {valid_solver}"
    )


def test_solver_status_recorded_in_gate_statuses(tmp_path: Path) -> None:
    """Solver status is recorded in report.statuses['system_consistency'].

    System consistency is solver-backed by default, so the base gate records the solver
    result status under the consolidated 'system_consistency' key (not a separate
    'solver_system_consistency' key) so the extended gate and callers can read it directly.
    """
    from nlreq.dsl_v3 import DslV3Parser
    from nlreq.translator_agreement import TranslationAgreementInput, TranslationCandidate

    src = tmp_path / "src"
    specs = tmp_path / "specs"
    src.mkdir()
    specs.mkdir()
    (src / "operation.py").write_text("def operation(actor):\n    return 'rejected'\n")
    (specs / "SystemConstraint.tla").write_text(
        "---- MODULE SystemConstraint ----\n"
        "CONSTANT a\n"
        "\\* @type: (Str) => Bool;\n"
        "Pred_authorized(a) == FALSE\n"
        "====\n"
    )
    trace_path = tmp_path / "traces.json"
    trace_path.write_text(json.dumps([{
        "trace_id": "T1", "adapter_id": "raw-python", "source_hash": "sha256:x",
        "events": [{"event_id": "e1", "timestamp": "2026-06-01T00:00:01Z",
                    "action": "operation", "post_state": {}}],
    }]))
    manifest = SourceManifest.model_validate({
        "schema_version": "0.1", "adapter": "python-source",
        "language": "python", "runtime": "cpython",
        "modules": [{"module_id": "redemption", "path": "src/operation.py",
                     "symbols": ["operation"], "trace_sources": ["traces.json"]}],
    })
    registry = SystemSpecRegistry.model_validate({
        "schema_version": "0.1",
        "specs": [{"spec_id": "spec:redemption", "module_ids": ["redemption"],
                   "formalism": "tla", "path": "specs/SystemConstraint.tla",
                   "version": "1", "review_status": "reviewed", "freshness": "fresh",
                   "invariants": ["SafetyInvariant"]}],
    })
    # SafetyInvariant makes S declare an invariant so the gate treats S ∧ R as applicable and
    # runs the solver; with no Pred_* assignment for R's obligation predicate, the Z3 path
    # reports 'unsupported' — a recognized solver outcome recorded in report.statuses.
    ir = DslV3Parser().parse_ir(
        FIXTURES.joinpath("authorization_precondition_v3.nlreq").read_text(),
        requirement_id="GATE-STATUS-001",
        title="Solver status recording test",
    )
    agreement = TranslationAgreementInput(
        candidates=[
            TranslationCandidate(translator_id="p", method="deterministic",
                                 requirement=ir, provenance={"source": "test"}),
            TranslationCandidate(translator_id="r", method="deterministic",
                                 requirement=ir, provenance={"source": "test"}),
        ]
    )

    report = run_end_to_end_requirement_gate(
        controlled_text=FIXTURES.joinpath("authorization_precondition_v3.nlreq").read_text(),
        requirement_id="GATE-STATUS-001",
        title="Solver status recording test",
        source_adapter=__import__("nlreq.python_source_adapter", fromlist=["PythonSourceLanguageAdapter"]).PythonSourceLanguageAdapter(project_root=tmp_path),
        source_manifest=manifest,
        symbols=["operation"],
        registry=registry,
        project_root=tmp_path,
        artifact_dir=tmp_path / "gate-status-artifacts",
        solver_execution=FormalBackendExecution(checker_id="z3"),
        requirement_ir=ir,
        translation_agreement=agreement,
    )

    assert "system_consistency" in report.statuses, (
        "report.statuses must contain 'system_consistency' (solver-backed by default)"
    )
    assert report.statuses["system_consistency"] in {"valid", "counterexample", "unsupported", "timeout", "not_applicable"}, (
        f"system_consistency must be a recognized solver outcome, "
        f"got {report.statuses['system_consistency']!r}"
    )


def test_solver_unsupported_produces_unknown_decision(tmp_path: Path) -> None:
    """Solver returning 'unsupported' produces an 'unknown' gate decision, not 'accepted'.

    An inconclusive solver run must NOT silently pass through to acceptance.
    The gate decision is 'unknown' so downstream consumers know checking was inconclusive
    and cannot treat the requirement as cleared.
    """
    from nlreq.dsl_v3 import DslV3Parser
    from nlreq.translator_agreement import TranslationAgreementInput, TranslationCandidate

    src = tmp_path / "src"
    specs = tmp_path / "specs"
    src.mkdir()
    specs.mkdir()
    (src / "operation.py").write_text("def operation(actor):\n    return 'rejected'\n")
    # S declares the InvariantHolds invariant (so the gate treats S ∧ R as applicable and
    # runs the solver) but defines no Pred_*(...) assignment for the Z3 in-process path to
    # ground R's obligation predicate on — so the Z3 checker returns 'unsupported'.
    (specs / "SystemConstraint.tla").write_text(
        "---- MODULE SystemConstraint ----\n"
        "InvariantHolds == TRUE\n"
        "====\n"
    )
    trace_path = tmp_path / "traces.json"
    trace_path.write_text(json.dumps([{
        "trace_id": "T1", "adapter_id": "raw-python", "source_hash": "sha256:x",
        "events": [{"event_id": "e1", "timestamp": "2026-06-01T00:00:01Z",
                    "action": "operation", "post_state": {}}],
    }]))
    manifest = SourceManifest.model_validate({
        "schema_version": "0.1", "adapter": "python-source",
        "language": "python", "runtime": "cpython",
        "modules": [{"module_id": "redemption", "path": "src/operation.py",
                     "symbols": ["operation"], "trace_sources": ["traces.json"]}],
    })
    registry = SystemSpecRegistry.model_validate({
        "schema_version": "0.1",
        "specs": [{"spec_id": "spec:redemption", "module_ids": ["redemption"],
                   "formalism": "tla", "path": "specs/SystemConstraint.tla",
                   "version": "1", "review_status": "reviewed", "freshness": "fresh",
                   "invariants": ["InvariantHolds"]}],
    })
    ir = DslV3Parser().parse_ir(
        FIXTURES.joinpath("authorization_precondition_v3.nlreq").read_text(),
        requirement_id="GATE-UNKNOWN-001",
        title="Solver unsupported → unknown decision",
    )
    agreement = TranslationAgreementInput(
        candidates=[
            TranslationCandidate(translator_id="p", method="deterministic",
                                 requirement=ir, provenance={"source": "test"}),
            TranslationCandidate(translator_id="r", method="deterministic",
                                 requirement=ir, provenance={"source": "test"}),
        ]
    )

    report = run_end_to_end_requirement_gate(
        controlled_text=FIXTURES.joinpath("authorization_precondition_v3.nlreq").read_text(),
        requirement_id="GATE-UNKNOWN-001",
        title="Solver unsupported → unknown decision",
        source_adapter=__import__("nlreq.python_source_adapter", fromlist=["PythonSourceLanguageAdapter"]).PythonSourceLanguageAdapter(project_root=tmp_path),
        source_manifest=manifest,
        symbols=["operation"],
        registry=registry,
        project_root=tmp_path,
        artifact_dir=tmp_path / "gate-unknown-artifacts",
        solver_execution=FormalBackendExecution(checker_id="z3"),
        requirement_ir=ir,
        translation_agreement=agreement,
    )

    system_status = report.statuses.get("system_consistency")
    # The spec has no Pred_* assignments → Z3 gate returns unsupported (predicates not assigned).
    assert system_status == "unsupported", (
        f"Expected system_consistency='unsupported' for spec without Pred_* assignments; "
        f"got {system_status!r}"
    )
    assert report.decision == "unknown", (
        f"Gate must be 'unknown' when solver returns 'unsupported'; got {report.decision!r}"
    )
    assert report.downstream_action_allowed is False, (
        "downstream_action_allowed must be False when gate is unknown"
    )
    unknown_blocker = next(
        (b for b in report.blockers if b.stage == "system_consistency"), None
    )
    assert unknown_blocker is not None, "Must have a system_consistency blocker"
    assert unknown_blocker.status == "unknown", (
        f"system_consistency blocker must be 'unknown'; got {unknown_blocker.status!r}"
    )


def test_extended_gate_s_and_r_composition_reads_solver_backed_system_consistency(
    tmp_path: Path,
) -> None:
    """_extended_gate_default_statuses maps s_and_r_composition from the consolidated,
    solver-backed system_consistency status.

    System consistency is solver-backed by default — there is no separate marker vs solver
    split to reconcile. The extended gate therefore reads s_and_r_composition directly from
    the single system_consistency status, surfacing whatever the solver produced
    (valid / counterexample / unsupported / timeout / not_applicable). No weaker marker
    result can mask a real solver outcome.
    """
    from nlreq.end_to_end_gate import (
        EndToEndRequirementGateReport,
        _extended_gate_default_statuses,
    )

    def _gate(system_consistency: str, *, decision: str) -> EndToEndRequirementGateReport:
        return EndToEndRequirementGateReport(
            requirement_id=f"TEST-{system_consistency.upper()}",
            decision=decision,
            downstream_action="merge",
            downstream_action_allowed=decision == "accepted",
            proof_status="closed" if decision == "accepted" else "blocked",
            closure_result="passed" if decision == "accepted" else "blocked",
            statuses={
                "system_consistency": system_consistency,
                "translation_agreement": "agreed",
                "requirement_self_consistency": "valid",
            },
        )

    # A solver counterexample is surfaced verbatim — never masked by a weaker result.
    assert (
        _extended_gate_default_statuses(_gate("counterexample", decision="refused"))[
            "s_and_r_composition"
        ]
        == "counterexample"
    )
    # An inconclusive run (unsupported) is surfaced as-is, not silently passed.
    assert (
        _extended_gate_default_statuses(_gate("unsupported", decision="unknown"))[
            "s_and_r_composition"
        ]
        == "unsupported"
    )
    # A verified 'valid' is surfaced as valid.
    assert (
        _extended_gate_default_statuses(_gate("valid", decision="accepted"))[
            "s_and_r_composition"
        ]
        == "valid"
    )
    # 'not_applicable' (no reviewed S relevant to the impact declares an invariant) is
    # surfaced as-is — a passing, non-blocking outcome distinct from a verified 'valid'.
    assert (
        _extended_gate_default_statuses(_gate("not_applicable", decision="accepted"))[
            "s_and_r_composition"
        ]
        == "not_applicable"
    )


def test_build_proof_with_formal_claim_dispatch_routes_unclassed_ir_by_kind() -> None:
    """A requirement that does NOT lower to a FormalClaim routes its premises BY KIND through the
    production gate helper — never collapsed onto the single system_checker default (PB-7.T3).

    DSL-v2 text declares no requirement_class, so build_formal_claim refuses and there is no
    per-fragment routing. The gate helper must then dispatch route_by_kind=True (mirroring the
    public proof-object CLI fallback), so the comparison premise routes to smt-theories and no
    premise routes to system_checker. With only a lone system_checker verdict supplied, none of
    the kind-routed premises discharge, so the proof blocks honestly rather than over-closing on
    one coarse pass. This is the regression guarding the asymmetric None fallback the gate helper
    used to share with the retired single-backend default.
    """
    from nlreq.dsl_v2 import DslV2Parser
    from nlreq.models import BackendResult, EvidenceLevel

    ir = DslV2Parser().parse_ir(
        DSL, requirement_id="REQ-GATE-UNCLASSED", title="Unclassed gate dispatch"
    )

    proof, formal_claim_report = build_proof_with_formal_claim_dispatch(
        requirement=ir,
        backend_results=[
            BackendResult(
                backend="system_checker",
                status="valid",
                evidence_level=EvidenceLevel.CONSISTENCY_CHECKED,
            )
        ],
    )

    assert formal_claim_report.result == "refused"
    routed = {premise.routed_backend for premise in proof.premises}
    assert "system_checker" not in routed
    assert "smt-theories" in routed
    # A lone system_checker verdict discharges none of the kind-routed premises.
    assert proof.status != "closed"
    assert all(premise.status != "discharged" for premise in proof.premises)


def test_z3_fixture_solver_result_cannot_discharge_formal_premises(tmp_path: Path) -> None:
    """The in-process Z3 fixture cannot discharge formal-claim premises — only a real bounded
    S ∧ R can.

    The predicate and rejection_order premises route to solver_system_checker at
    BOUNDED_CHECKED: an uninterpreted predicate and a rejection-order obligation are discharged
    only by the requirement-level S ∧ R model check that binds them into a composed module. The
    Z3 fixture path (checker_id='z3') parses the lowered obligation propositionally WITHOUT
    composing or binding any module — it records no bound_predicates and emits SMT_CHECKED,
    never BOUNDED_CHECKED — so it covers no formal fragment. The premises therefore stay
    undischarged and the proof cannot close on the fixture path. This is the honesty tripwire:
    SMT-level fixture evidence must never close a bounded-model-check obligation.
    """
    from nlreq.dsl_v3 import DslV3Parser
    from nlreq.models import EvidenceLevel
    from nlreq.proof_closure import ProofObject
    from nlreq.jsonutil import read_json
    from nlreq.translator_agreement import TranslationAgreementInput, TranslationCandidate
    from nlreq.python_source_adapter import PythonSourceLanguageAdapter

    src = tmp_path / "src"
    specs = tmp_path / "specs"
    src.mkdir()
    specs.mkdir()
    (src / "operation.py").write_text("def operation(actor):\n    return 'rejected'\n")
    (specs / "SystemConstraint.tla").write_text(
        "---- MODULE SystemConstraint ----\n"
        "CONSTANT a\n"
        "\\* @type: (Str) => Bool;\n"
        "Pred_authorized(a) == FALSE\n"
        "====\n"
    )
    trace_path = tmp_path / "traces.json"
    trace_path.write_text(json.dumps([{
        "trace_id": "T1", "adapter_id": "raw-python", "source_hash": "sha256:x",
        "events": [{"event_id": "e1", "timestamp": "2026-06-01T00:00:01Z",
                    "action": "operation", "post_state": {}}],
    }]))
    manifest = SourceManifest.model_validate({
        "schema_version": "0.1", "adapter": "python-source",
        "language": "python", "runtime": "cpython",
        "modules": [{"module_id": "redemption", "path": "src/operation.py",
                     "symbols": ["operation"], "trace_sources": ["traces.json"]}],
    })
    registry = SystemSpecRegistry.model_validate({
        "schema_version": "0.1",
        "specs": [{"spec_id": "spec:redemption", "module_ids": ["redemption"],
                   "formalism": "tla", "path": "specs/SystemConstraint.tla",
                   "version": "1", "review_status": "reviewed", "freshness": "fresh"}],
    })
    ir = DslV3Parser().parse_ir(
        FIXTURES.joinpath("authorization_precondition_v3.nlreq").read_text(),
        requirement_id="GATE-FRAG-001",
        title="Fragment binding test",
    )
    agreement = TranslationAgreementInput(
        candidates=[
            TranslationCandidate(translator_id="p", method="deterministic",
                                 requirement=ir, provenance={"source": "test"}),
            TranslationCandidate(translator_id="r", method="deterministic",
                                 requirement=ir, provenance={"source": "test"}),
        ]
    )

    report = run_end_to_end_requirement_gate(
        controlled_text=FIXTURES.joinpath("authorization_precondition_v3.nlreq").read_text(),
        requirement_id="GATE-FRAG-001",
        title="Fragment binding test",
        source_adapter=PythonSourceLanguageAdapter(project_root=tmp_path),
        source_manifest=manifest,
        symbols=["operation"],
        registry=registry,
        project_root=tmp_path,
        artifact_dir=tmp_path / "gate-frag-artifacts",
        solver_execution=FormalBackendExecution(checker_id="z3"),
        requirement_ir=ir,
        translation_agreement=agreement,
    )

    proof_path = Path(next(a.path for a in report.artifacts if a.name == "proof_object"))
    proof = ProofObject.model_validate(read_json(proof_path))

    # The Z3 fixture result is SMT-level and composes no module, so it binds no predicate and
    # covers no fragment — it can never satisfy a BOUNDED_CHECKED formal-claim route.
    solver_results = [r for r in proof.backend_results if r.backend == "solver_system_checker"]
    assert solver_results, "ProofObject must carry solver_system_checker backend result"
    for result in solver_results:
        assert result.evidence_level != EvidenceLevel.BOUNDED_CHECKED, (
            "the Z3 fixture must not emit bounded-MC evidence; it is an SMT-level check"
        )
        assert "covered_fragment_ids" not in result.details, (
            "the Z3 fixture composes no module (no bound_predicates), so it covers no fragment"
        )

    # Predicate and rejection_order premises stay undischarged — the fixture cannot close them.
    formal_premises = [
        p for p in proof.premises
        if p.node_kind in {"predicate", "rejection_order"}
    ]
    assert formal_premises, "the authorization_precondition claim must yield formal premises"
    for premise in formal_premises:
        assert premise.status != "discharged", (
            f"premise {premise.premise_id!r} must NOT be discharged by the Z3 fixture; "
            f"got {premise.status!r}. Only a real bounded S ∧ R that binds the predicates "
            "into a composed module may discharge a formal-claim premise."
        )
    assert report.decision != "accepted"


def _project(
    tmp_path: Path,
    *,
    trace_actions: list[str] | None = None,
    reviewed_invariant: bool = False,
    narrowing: bool = False,
    narrowing_counterexample: bool = False,
) -> tuple[SourceManifest, SystemSpecRegistry]:
    src = tmp_path / "src"
    specs = tmp_path / "specs"
    src.mkdir()
    specs.mkdir()
    (src / "redemption.py").write_text(
        "def finalize_redemption(wallet):\n"
        "    if wallet.authorized:\n"
        "        return 'redemption_finalized'\n"
        "    return 'rejected'\n"
    )
    if narrowing or narrowing_counterexample:
        # A reviewed *stateful* S (Case B narrowing): S brings its own transition system
        # (SInit/SNext over authPhase) and interprets both the premise predicate
        # Pred_not_authorized — which FIRES once authPhase reaches "denied" — and the
        # forbidden-outcome Pred_finalize_redemption. The composition narrows S: a bounded
        # check verifies whether S can reach the forbidden outcome while the premise holds.
        # Both Pred_* operators are bound into the checked module, so the S ∧ R verdict
        # discharges (valid) or blocks (counterexample) both formal-claim premises.
        if narrowing_counterexample:
            # The forbidden outcome IS reachable while the premise holds: authPhase can reach
            # "finalized", where Pred_not_authorized AND Pred_finalize_redemption both hold, so
            # R_Requirement (Premise => ~outcome) is violated and a real Apalache run returns a
            # counterexample. This is the benchmark's RedemptionAuthorization.tla shape.
            (specs / "Redemption.tla").write_text(
                "---- MODULE Redemption ----\n"
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
                "         \\/ UNCHANGED authPhase\n"
                "====\n"
            )
        else:
            # The forbidden outcome is pinned unreachable (Pred_finalize_redemption == FALSE)
            # while the premise still fires (authPhase reaches "denied"): S never reaches the
            # forbidden outcome, so a real Apalache run returns valid — a non-vacuous discharge.
            (specs / "Redemption.tla").write_text(
                "---- MODULE Redemption ----\n"
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
                "SNext == (authPhase = \"init\" /\\ authPhase' = \"denied\") \\/ UNCHANGED authPhase\n"
                "====\n"
            )
    elif reviewed_invariant:
        # A reviewed S that pins the authorization predicate FALSE and declares a real system
        # invariant. A v3 authorization_precondition requirement ("when wallet is authorized")
        # lowers to a Pred_authorized obligation that this S discharges (premise pinned FALSE →
        # obligation vacuously satisfied → S ∧ R valid). This is the genuine closed-S ∧ R fixture;
        # the empty-module spec below cannot close S ∧ R (no invariant → refused).
        (specs / "Redemption.tla").write_text(
            "---- MODULE Redemption ----\n"
            "\\* @type: (Str) => Bool;\n"
            "Pred_authorized(a) == FALSE\n"
            "\\* @type: (Str) => Bool;\n"
            "Pred_not_authorized(a) == TRUE\n"
            "\\* System invariant: authorization defaults closed.\n"
            'SystemDefaultsClosed == Pred_authorized("wallet") = FALSE\n'
            "====\n"
        )
    else:
        (specs / "Redemption.tla").write_text("---- MODULE Redemption ----\n====\n")
    trace_path = tmp_path / "traces.json"
    trace_path.write_text(json.dumps(_trace_payload(trace_actions or [
        "finalize_redemption",
        "redemption_finalized",
    ])))
    manifest = SourceManifest.model_validate(
        {
            "schema_version": "0.1",
            "adapter": "python-source",
            "language": "python",
            "runtime": "cpython",
            "modules": [
                {
                    "module_id": "redemption",
                    "path": "src/redemption.py",
                    "symbols": ["finalize_redemption"],
                    "trace_sources": ["traces.json"],
                }
            ],
        }
    )
    spec_entry: dict[str, object] = {
        "spec_id": "spec:redemption",
        "module_ids": ["redemption"],
        "formalism": "tla",
        "path": "specs/Redemption.tla",
        "version": "1",
        "review_status": "reviewed",
        "freshness": "fresh",
    }
    if narrowing or narrowing_counterexample:
        spec_entry["init_op"] = "SInit"
        spec_entry["next_op"] = "SNext"
        spec_entry["invariants"] = ["AuthorizationDefaultsClosed"]
    elif reviewed_invariant:
        spec_entry["invariants"] = ["SystemDefaultsClosed"]
    registry = SystemSpecRegistry.model_validate(
        {
            "schema_version": "0.1",
            "specs": [spec_entry],
        }
    )
    return manifest, registry


def _trace_payload(actions: list[str]) -> list[dict[str, object]]:
    return [
        {
            "trace_id": "TRACE-GATE-001",
            "adapter_id": "raw-python",
            "source_hash": "sha256:source",
            "events": [
                {
                    "event_id": f"evt-{index}",
                    "timestamp": f"2026-06-01T00:00:0{index}Z",
                    "action": action,
                    "post_state": (
                        {"collateral": 150, "reserve_floor": 100}
                        if action == "redemption_finalized"
                        else {}
                    ),
                }
                for index, action in enumerate(actions, start=1)
            ],
        }
    ]


def _execution(tmp_path: Path) -> FormalBackendExecution:
    return FormalBackendExecution(
        checker_id="custom",
        command=[sys.executable, "-c", "print('verification successful')"],
        artifact_dir=(tmp_path / "formal-self-check").as_posix(),
    )
