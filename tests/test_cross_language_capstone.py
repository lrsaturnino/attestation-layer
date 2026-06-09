"""PC-13 — the cross-language capstone (SP3): one requirement whose per-language guards are
discharged by REAL per-language S ∧ R runs (real Apalache over a Solidity reviewed S and a Go
reviewed S) and aggregated into ONE ProofObject whose closure gates a downstream action.

The Solidity contract (the Foundry redemption vault) and the Go coordinator (the redemption sweep
coordinator) together realize ONE requirement: a redemption is authorized on-chain before it is
finalized AND authorized off-chain before it is swept. tBTC-style domain language lives only here,
above the adapter line; the agnostic core stays domain-free.

- The tool-free tests pin the dispatch + aggregation structure and the non-interchangeability of the
  two per-language guards (a Go S ∧ R result cannot discharge the Solidity guard) without a checker.
- The real-tool tests run real per-language S ∧ R + real trace extraction; they skip with a recorded
  reason when apalache-mc / forge / go is absent (never a silent pass), exactly like the PB-5 / PC-4 /
  PC-7 real-run tests.
"""

from __future__ import annotations

import dataclasses
import json
import shutil
from pathlib import Path

import pytest

from nlreq import foundry_client, go_client
from nlreq.cross_language import (
    CrossLanguageVertical,
    close_cross_language_proof,
)
from nlreq.dsl_v3 import DslV3Parser
from nlreq.impact import ImpactAnalysisArtifact, analyze_source_impact
from nlreq.models import (
    BackendResult,
    EvidenceLevel,
    NormalizedTraceArtifact,
    RequirementIRV2,
    SymbolRef,
)
from nlreq.proof_closure import build_cross_language_dispatch_plan, build_proof_object
from nlreq.coverage_alignment import SpecCoverageReport, TraceAlignmentReport
from nlreq.production_source_adapters import GoSourceAdapter, SoliditySourceAdapter
from nlreq.source_adapter import SourceManifest
from nlreq.system_spec import SpecTraceContract, SpecTraceExpectation, SystemSpecRegistry


FIXTURE_ROOT = Path(__file__).parent / "fixtures" / "cross_language"
# Dedicated cross-language source fixtures that REALIZE the requirement's named actions: the Solidity
# vault's finalize_redemption require()s authorization, and the Go coordinator's execute_sweep refuses
# an unauthorized sweep. Symbol resolution + call-graph impact + traces all come from these (PC-13).
SOL_ROOT = FIXTURE_ROOT / "solidity"
GO_ROOT = FIXTURE_ROOT / "go"

REQUIREMENT = RequirementIRV2.model_validate(
    json.loads((FIXTURE_ROOT / "requirement.json").read_text())
)

requires_capstone_tools = pytest.mark.skipif(
    shutil.which("apalache-mc") is None
    or not foundry_client.foundry_available()
    or not go_client.go_trace_tools_available(),
    reason=(
        "the cross-language capstone needs apalache-mc + forge + go on PATH to run real "
        "per-language S ∧ R and extract real traces"
    ),
)


# --- Per-vertical builders -----------------------------------------------------------------------


def _registry(project_root: Path, *, module_id, spec_id, spec_file, invariant) -> SystemSpecRegistry:
    """Write the reviewed S into a per-vertical project root and register it fresh + reviewed."""
    specs = project_root / "specs"
    specs.mkdir(parents=True, exist_ok=True)
    (specs / spec_file).write_text((FIXTURE_ROOT / spec_file).read_text())
    return SystemSpecRegistry.model_validate(
        {
            "schema_version": "0.1",
            "specs": [
                {
                    "spec_id": spec_id,
                    "module_ids": [module_id],
                    "formalism": "tla",
                    "path": f"specs/{spec_file}",
                    "version": "1",
                    "review_status": "reviewed",
                    "freshness": "fresh",
                    "invariants": [invariant],
                    "init_op": "SInit",
                    "next_op": "SNext",
                }
            ],
        }
    )


def _solidity_manifest() -> SourceManifest:
    return SourceManifest.model_validate(
        {
            "schema_version": "0.1",
            "adapter": "solidity-source",
            "language": "solidity",
            "runtime": "evm",
            "modules": [
                {
                    "module_id": "vault",
                    "path": "src/RedemptionVault.sol",
                    "symbols": [
                        "RedemptionVault",
                        "authorize",
                        "finalize_redemption",
                        "RedemptionAuthorized",
                        "RedemptionFinalized",
                        "finalizedTotal",
                    ],
                }
            ],
        }
    )


def _go_manifest() -> SourceManifest:
    return SourceManifest.model_validate(
        {
            "schema_version": "0.1",
            "adapter": "go-source",
            "language": "go",
            "runtime": "go",
            "modules": [
                {
                    "module_id": "coordinator",
                    "path": "coordinator/coordinator.go",
                    "symbols": ["execute_sweep", "Authorizer", "Sweeper", "Guard", "Total"],
                }
            ],
        }
    )


def _solidity_real_impact() -> ImpactAnalysisArtifact:
    """Resolve finalize_redemption and build impact from the REAL Slither call graph (PC-3/PC-9).

    Asserts the requirement's named action resolves to a real source symbol first, so the impact is
    tied to source (a resolved symbol + call-graph-reachable modules), not a hand-written stand-in.
    Real-tool only: Slither must be drivable (guarded by ``requires_capstone_tools`` at the call site).
    """
    adapter = SoliditySourceAdapter(project_root=SOL_ROOT)
    manifest = _solidity_manifest()
    resolution = adapter.resolve_symbol(SymbolRef(name="finalize_redemption"), manifest)
    assert resolution.status == "resolved", resolution.reason
    return analyze_source_impact(adapter, manifest, symbols=["finalize_redemption"])


def _go_real_impact() -> ImpactAnalysisArtifact:
    """Resolve execute_sweep and build impact from the REAL CHA call graph (PC-6/PC-9)."""
    adapter = GoSourceAdapter(project_root=GO_ROOT)
    manifest = _go_manifest()
    resolution = adapter.resolve_symbol(SymbolRef(name="execute_sweep"), manifest)
    assert resolution.status == "resolved", resolution.reason
    return analyze_source_impact(adapter, manifest, symbols=["execute_sweep"])


def _placeholder_impact(adapter_id, language, module_id, symbol) -> ImpactAnalysisArtifact:
    """A minimal impact for the TOOL-FREE binding tests only.

    Binding validation refuses a misconfigured vertical BEFORE any S ∧ R or coverage step ever reads
    the impact, so those tests need a well-formed artifact, not a real Slither/CHA analysis (which
    would require the tools). The real-tool tests use :func:`_solidity_real_impact` / :func:`_go_real_impact`.
    """
    return ImpactAnalysisArtifact.model_validate(
        {
            "schema_version": "0.1",
            "adapter_id": adapter_id,
            "language": language,
            "input_symbols": [symbol],
            "affected_modules": [module_id],
            "call_graph_edges": [],
            "metadata": {},
        }
    )


def _solidity_vertical(
    project_root: Path,
    traces: NormalizedTraceArtifact,
    impact: ImpactAnalysisArtifact,
    *,
    safe: bool,
):
    # The sub-claim is ALWAYS the parent's unauthorized-rejection slice: when NOT authorized, the
    # action must be rejected (the guard the requirement declares). ``safe`` selects the reviewed S,
    # NOT the requirement — the SAFE S discharges it (forbidden outcome unreachable, premise still
    # reachable → real valid, non-vacuous), the UNSAFE S yields a real counterexample over the SAME R.
    sub_claim = DslV3Parser().parse_ir(
        "requirement authorization_precondition: scope redemption when wallet is "
        "not authorized then finalize_redemption must reject before rejected.",
        requirement_id="REQ-XLANG-REDEMPTION-001-SOL",
        title="On-chain redemption authorization",
    )
    return CrossLanguageVertical(
        language="solidity",
        adapter_id="solidity-source",
        guard_node_id="obligation.solidity_authorization_guard",
        sub_claim=sub_claim,
        registry=_registry(
            project_root,
            module_id="vault",
            spec_id="spec:vault",
            spec_file="RedemptionVault.tla" if safe else "RedemptionVaultUnsafe.tla",
            invariant="VaultFinalizeAuthorized" if safe else "VaultAuthorizationClosed",
        ),
        impact=impact,
        project_root=project_root,
        traces=traces,
        # The reviewed S's trace-observable projection over the vault's REAL Foundry traces: the
        # authorize + finalize events, the finalizedTotal read reaching 5, AND the unauthorized
        # finalize reverting with the contract's reason — so S is validated against the contract's
        # real authorization behavior, not just incidental events.
        spec_trace_contract=SpecTraceContract(
            spec_id="spec:vault",
            module_ids=["vault"],
            expectations=[
                SpecTraceExpectation(
                    expectation_id="vault-authorized",
                    kind="event_emitted",
                    target="RedemptionAuthorized",
                ),
                SpecTraceExpectation(
                    expectation_id="vault-finalized",
                    kind="event_emitted",
                    target="RedemptionFinalized",
                ),
                SpecTraceExpectation(
                    expectation_id="vault-total",
                    kind="state_value_reached",
                    target="finalizedTotal",
                    value="5",
                ),
                SpecTraceExpectation(
                    expectation_id="vault-unauthorized-reverts",
                    kind="action_reverts",
                    target="finalize_redemption",
                    value="redemption not authorized",
                ),
            ],
        ),
    )


def _go_vertical(
    project_root: Path,
    traces: NormalizedTraceArtifact,
    impact: ImpactAnalysisArtifact,
    *,
    safe: bool,
):
    # As in _solidity_vertical: the sub-claim is ALWAYS the parent's "when NOT authorized, reject"
    # slice; ``safe`` selects the reviewed S (SAFE discharges it, UNSAFE counterexamples).
    sub_claim = DslV3Parser().parse_ir(
        "requirement authorization_precondition: scope sweep when operator is "
        "not authorized then execute_sweep must reject before rejected.",
        requirement_id="REQ-XLANG-REDEMPTION-001-GO",
        title="Off-chain sweep authorization",
    )
    return CrossLanguageVertical(
        language="go",
        adapter_id="go-source",
        guard_node_id="obligation.go_authorization_guard",
        sub_claim=sub_claim,
        registry=_registry(
            project_root,
            module_id="coordinator",
            spec_id="spec:coordinator",
            spec_file="RedemptionCoordinator.tla" if safe else "RedemptionCoordinatorUnsafe.tla",
            invariant="CoordinatorSweepAuthorized" if safe else "CoordinatorAuthorizationClosed",
        ),
        impact=impact,
        project_root=project_root,
        traces=traces,
        # The reviewed S's trace-observable projection over the coordinator's REAL `go test -trace`
        # runtime trace: the authorize stage then the guarded sweep stage. Go has no revert, so the
        # off-chain rejection is a return value, not a trace event — the guard is carried by S and
        # checked by S ∧ R; the trace grounds the happy-path stages the spec models.
        spec_trace_contract=SpecTraceContract(
            spec_id="spec:coordinator",
            module_ids=["coordinator"],
            expectations=[
                SpecTraceExpectation(
                    expectation_id="coord-authorize", kind="event_emitted", target="authorize"
                ),
                SpecTraceExpectation(
                    expectation_id="coord-sweep", kind="event_emitted", target="sweep"
                ),
            ],
        ),
    )


def _solidity_traces() -> NormalizedTraceArtifact:
    return SoliditySourceAdapter(project_root=SOL_ROOT).extract_traces(_solidity_manifest())


def _go_traces() -> NormalizedTraceArtifact:
    return GoSourceAdapter(project_root=GO_ROOT).extract_traces(_go_manifest())


# --- Tool-free structure + non-interchangeability -------------------------------------------------


def test_dispatch_plan_routes_one_solver_premise_per_language_guard() -> None:
    plan = build_cross_language_dispatch_plan(REQUIREMENT)

    assert [route.node_id for route in plan.routes] == [
        "obligation.solidity_authorization_guard",
        "obligation.go_authorization_guard",
    ]
    for route in plan.routes:
        # Each guard routes to the solver-backed S ∧ R producer at the level a real Apalache run
        # discharges, and FAILS CLOSED (formal_claim): only a result tagged with this guard's
        # premise_id can discharge it.
        assert route.backend_id == "solver_system_checker"
        assert route.required_evidence == EvidenceLevel.BOUNDED_CHECKED
        assert route.routing_mode == "formal_claim"
        # The premise_id points at the requirement's REAL node, not an invented label.
        assert route.premise_id == f"{REQUIREMENT.requirement_id}:obligation:{route.node_id}"


def _backed_solver_result(*, covered: list[str], status: str = "valid") -> BackendResult:
    """A solver S ∧ R result with full BOUNDED_CHECKED backing, tagged with the guards it covers."""
    return BackendResult(
        backend="solver_system_checker",
        status=status,  # type: ignore[arg-type]
        evidence_level=EvidenceLevel.BOUNDED_CHECKED if status == "valid" else None,
        details={
            "mode": "solver_backed",
            "checker_id": "apalache",
            "bounds": {"max_depth": 6, "timeout_seconds": 60},
            "command": ["apalache-mc", "check", "Module.tla"],
            "reproducibility": {"tool_version": "0.47.2"},
            "covered_fragment_ids": covered,
        },
    )


def _passed_reports() -> tuple[SpecCoverageReport, TraceAlignmentReport]:
    coverage = SpecCoverageReport(
        result="passed", threshold=1.0, covered_modules=2, total_modules=2, coverage_ratio=1.0
    )
    return coverage, TraceAlignmentReport(result="passed")


def test_each_guard_is_discharged_only_by_its_own_language_result() -> None:
    """Non-interchangeability: under formal_claim routing a Go S ∧ R result tagged with the Go
    guard cannot discharge the Solidity guard, even though both share the solver_system_checker
    backend. Correctly-tagged results close the proof; a swapped tag leaves a guard open."""
    plan = build_cross_language_dispatch_plan(REQUIREMENT)
    sol_pid = f"{REQUIREMENT.requirement_id}:obligation:obligation.solidity_authorization_guard"
    go_pid = f"{REQUIREMENT.requirement_id}:obligation:obligation.go_authorization_guard"
    coverage, trace = _passed_reports()

    closed = build_proof_object(
        requirement=REQUIREMENT,
        backend_results=[
            _backed_solver_result(covered=[sol_pid]),
            _backed_solver_result(covered=[go_pid]),
        ],
        coverage=coverage,
        trace_alignment=trace,
        dispatch=plan,
    )
    assert closed.status == "closed"
    assert {p.node_id: p.status for p in closed.premises} == {
        "obligation.solidity_authorization_guard": "discharged",
        "obligation.go_authorization_guard": "discharged",
    }

    # Both real results exist and are valid, but BOTH are tagged with the Go guard only. The
    # Solidity guard has no result naming its premise_id, so it stays open — a Go verdict cannot
    # stand in for the Solidity guard.
    mistagged = build_proof_object(
        requirement=REQUIREMENT,
        backend_results=[
            _backed_solver_result(covered=[go_pid]),
            _backed_solver_result(covered=[go_pid]),
        ],
        coverage=coverage,
        trace_alignment=trace,
        dispatch=plan,
    )
    assert mistagged.status != "closed"
    sol_premise = next(
        p for p in mistagged.premises if p.node_id == "obligation.solidity_authorization_guard"
    )
    assert sol_premise.status == "open"


def _empty_traces() -> NormalizedTraceArtifact:
    """A trace artifact with no traces. Binding validation runs before any S ∧ R or trace use, so a
    tool-free binding test needs only a well-formed (empty) artifact, never a real extraction."""
    return NormalizedTraceArtifact.model_validate([])


def test_close_refuses_a_misconfigured_vertical_binding(tmp_path) -> None:
    """``close_cross_language_proof`` derives each S ∧ R result's discharge tag from the vertical's
    ``guard_node_id`` (``route_by_node[guard_node_id].premise_id``), so the binding is the ONLY
    caller-controlled lever deciding which guard a run discharges. A misbinding is refused UP FRONT —
    before any Apalache run — so a wrong-language S ∧ R can never be tagged onto a guard it does not
    belong to. Validation is tool-free; these cases run without apalache/forge/go.
    """
    sol = _solidity_vertical(
        tmp_path / "sol",
        _empty_traces(),
        _placeholder_impact("solidity-source", "solidity", "vault", "finalize_redemption"),
        safe=True,
    )
    go = _go_vertical(
        tmp_path / "go",
        _empty_traces(),
        _placeholder_impact("go-source", "go", "coordinator", "execute_sweep"),
        safe=True,
    )

    # (1) Unknown guard: a vertical bound to a node that is not a per-language guard of the requirement.
    with pytest.raises(ValueError, match="not a per-language guard"):
        close_cross_language_proof(
            requirement=REQUIREMENT,
            verticals=[dataclasses.replace(sol, guard_node_id="obligation.does_not_exist")],
        )

    # (2) Duplicate guard: two verticals claim the same guard, so one guard would carry two S ∧ R runs.
    with pytest.raises(ValueError, match="claimed by more than one"):
        close_cross_language_proof(
            requirement=REQUIREMENT,
            verticals=[sol, dataclasses.replace(sol, project_root=tmp_path / "sol_dup")],
        )

    # (3) Wrong language: a Go vertical bound to the Solidity guard. The guard declares
    # vertical_language="solidity"; a Go S ∧ R cannot stand in for the on-chain guard, so the binding
    # is refused rather than silently tagging a Go run onto the Solidity premise_id.
    with pytest.raises(ValueError, match="vertical_language"):
        close_cross_language_proof(
            requirement=REQUIREMENT,
            verticals=[
                dataclasses.replace(go, guard_node_id="obligation.solidity_authorization_guard")
            ],
        )

    # (4) Mismatched precondition: the RIGHT-language Solidity vertical, but carrying a sub-claim whose
    # premise is "authorized" (not "not authorized"). Over a reviewed S that leaves Pred_authorized
    # always-false this would close VACUOUSLY — discharging the Solidity guard without proving the
    # parent's stated unauthorized-rejection slice. The guard declares
    # guard_premise_predicate="not_authorized", so the binding is refused UP FRONT: a valid-but-wrong
    # S ∧ R can never be tagged onto the guard.
    vacuous_sub_claim = DslV3Parser().parse_ir(
        "requirement authorization_precondition: scope redemption when wallet is "
        "authorized then finalize_redemption must reject before rejected.",
        requirement_id="REQ-XLANG-REDEMPTION-001-SOL",
        title="On-chain redemption authorization",
    )
    with pytest.raises(ValueError, match="guard_premise_predicate"):
        close_cross_language_proof(
            requirement=REQUIREMENT,
            verticals=[dataclasses.replace(sol, sub_claim=vacuous_sub_claim)],
        )

    # (5) Mismatched action: a sub-claim naming a DIFFERENT action than the guard declares is refused
    # on guard_action, so a vertical cannot prove a guard about one action with a run about another.
    wrong_action_sub_claim = DslV3Parser().parse_ir(
        "requirement authorization_precondition: scope redemption when wallet is "
        "not authorized then request_redemption must reject before rejected.",
        requirement_id="REQ-XLANG-REDEMPTION-001-SOL",
        title="On-chain redemption authorization",
    )
    with pytest.raises(ValueError, match="guard_action"):
        close_cross_language_proof(
            requirement=REQUIREMENT,
            verticals=[dataclasses.replace(sol, sub_claim=wrong_action_sub_claim)],
        )


# --- Real per-language S ∧ R end-to-end (the SP3 loop) --------------------------------------------


@requires_capstone_tools
def test_cross_language_requirement_closes_one_proof_and_gates_the_action(tmp_path_factory) -> None:
    """The loop closes: both per-language guards are discharged by their OWN language's real Apalache
    S ∧ R (BOUNDED_CHECKED), the single ProofObject closes, and the closure gate passes the action.

    Closure is NON-VACUOUS and proves the parent's stated slice. Both sub-claims are the requirement's
    own "when NOT authorized, the action must be rejected" guard; each reviewed SAFE S leaves the
    not-authorized premise REACHABLE (init/denied) while making the forbidden outcome — the action
    firing while not-authorized — UNREACHABLE. So the premise fires and the obligation still holds: a
    real ``valid`` that witnesses the guard, not a vacuous one where the premise is always false. The
    companion counterexample tests run the SAME requirement against an UNSAFE S to show the contrast.

    The per-vertical project roots come from ``tmp_path_factory`` (session base), NOT ``tmp_path``,
    so the Apalache working-directory path carries only the clean label — never the test name. The
    model-checker runner classifies a counterexample by scanning the checker's combined output, which
    echoes that working-directory path; a path containing a marker word (e.g. a test named
    ``...counterexample...``) would misclassify a VALID run. Using a clean label keeps the path inert.
    """
    sol_traces = _solidity_traces()
    go_traces = _go_traces()
    # Impact for each vertical is built from REAL symbol resolution + the REAL call graph of the
    # source that realizes the action (Slither for finalize_redemption, CHA for execute_sweep) — not a
    # hand-written stand-in. Each carries call-graph edges out of the named action.
    sol_impact = _solidity_real_impact()
    go_impact = _go_real_impact()
    assert any("finalize_redemption" in edge["caller"] for edge in sol_impact.call_graph_edges)
    assert any("execute_sweep" in edge["caller"] for edge in go_impact.call_graph_edges)

    result = close_cross_language_proof(
        requirement=REQUIREMENT,
        verticals=[
            _solidity_vertical(tmp_path_factory.mktemp("xlang_sol"), sol_traces, sol_impact, safe=True),
            _go_vertical(tmp_path_factory.mktemp("xlang_go"), go_traces, go_impact, safe=True),
        ],
        downstream_action="merge",
    )

    # ONE ProofObject for the cross-language requirement, closed.
    assert result.proof.requirement_id == "REQ-XLANG-REDEMPTION-001"
    assert result.proof.status == "closed"

    # Each guard is discharged by its OWN language's BOUNDED_CHECKED S ∧ R result.
    premises = {p.node_id: p for p in result.proof.premises}
    assert set(premises) == {
        "obligation.solidity_authorization_guard",
        "obligation.go_authorization_guard",
    }
    for premise in premises.values():
        assert premise.status == "discharged"
        assert premise.routed_backend == "solver_system_checker"
        assert premise.producer_id == "solver_system_checker"
        assert premise.achieved_evidence == EvidenceLevel.BOUNDED_CHECKED

    # Both verticals: real Apalache valid + reviewed S reproduces the real traces (PC-11).
    by_lang = {v.language: v for v in result.verticals}
    assert by_lang["solidity"].s_and_r_status == "valid"
    assert by_lang["go"].s_and_r_status == "valid"
    assert by_lang["solidity"].evidence_level == EvidenceLevel.BOUNDED_CHECKED
    assert by_lang["go"].evidence_level == EvidenceLevel.BOUNDED_CHECKED
    assert by_lang["solidity"].trace_alignment == "satisfies"
    assert by_lang["go"].trace_alignment == "satisfies"

    # The aggregate supporting reports are REAL and pass over both languages.
    assert result.coverage.result == "passed"
    assert result.coverage.total_modules == 2
    assert result.trace_alignment.result == "passed"
    assert result.composition.result == "valid"
    assert sorted(result.composition.languages) == ["go", "solidity"]

    # The closure gates the downstream action.
    assert result.gate.result == "passed"
    assert result.gate.downstream_action == "merge"
    assert result.gate.proof_status == "closed"


@requires_capstone_tools
def test_counterexample_in_one_language_blocks_the_action(tmp_path_factory) -> None:
    """A real Apalache counterexample in ONE vertical (the Solidity guard, where S can reach a
    finalize while not-authorized) leaves that guard undischarged; the single ProofObject does not
    close and the closure gate blocks the action — even though the Go guard discharges normally.

    Project roots come from ``tmp_path_factory`` (clean label), not ``tmp_path``, so the Apalache
    working-directory path the runner scans does not carry this test's name (which contains the
    marker word ``counterexample``) — see the closing test above for why that matters.
    """
    sol_traces = _solidity_traces()
    go_traces = _go_traces()

    result = close_cross_language_proof(
        requirement=REQUIREMENT,
        verticals=[
            _solidity_vertical(
                tmp_path_factory.mktemp("xlang_sol"), sol_traces, _solidity_real_impact(), safe=False
            ),
            _go_vertical(
                tmp_path_factory.mktemp("xlang_go"), go_traces, _go_real_impact(), safe=True
            ),
        ],
        downstream_action="merge",
    )

    assert result.proof.status != "closed"
    premises = {p.node_id: p for p in result.proof.premises}
    # The Solidity guard is blocked by its real counterexample; the Go guard still discharges.
    assert premises["obligation.solidity_authorization_guard"].status == "blocked"
    assert premises["obligation.go_authorization_guard"].status == "discharged"

    by_lang = {v.language: v for v in result.verticals}
    assert by_lang["solidity"].s_and_r_status == "counterexample"
    assert by_lang["go"].s_and_r_status == "valid"

    # The per-language S ∧ R aggregate and the closure gate both block the downstream action.
    assert result.composition.result == "blocked"
    assert any("solidity" in blocker for blocker in result.composition.blockers)
    assert result.gate.result == "blocked"


@requires_capstone_tools
def test_counterexample_in_the_go_vertical_blocks_the_action(tmp_path_factory) -> None:
    """Symmetric to the Solidity counterexample: a real Apalache counterexample in the GO vertical
    (the off-chain coordinator's UNSAFE S can reach a sweep while not-authorized) leaves the Go guard
    undischarged, so the single ProofObject does not close and the gate blocks the action — even
    though the Solidity guard discharges normally. EITHER language's real failure blocks the action;
    the cross-language closure is not satisfied by the on-chain proof alone.

    Project roots come from ``tmp_path_factory`` (clean label), not ``tmp_path``, so the Apalache
    working-directory path the runner scans does not carry this test's name — see the closing test.
    """
    sol_traces = _solidity_traces()
    go_traces = _go_traces()

    result = close_cross_language_proof(
        requirement=REQUIREMENT,
        verticals=[
            _solidity_vertical(
                tmp_path_factory.mktemp("xlang_sol"), sol_traces, _solidity_real_impact(), safe=True
            ),
            _go_vertical(
                tmp_path_factory.mktemp("xlang_go"), go_traces, _go_real_impact(), safe=False
            ),
        ],
        downstream_action="merge",
    )

    assert result.proof.status != "closed"
    premises = {p.node_id: p for p in result.proof.premises}
    # The Go guard is blocked by its real counterexample; the Solidity guard still discharges.
    assert premises["obligation.go_authorization_guard"].status == "blocked"
    assert premises["obligation.solidity_authorization_guard"].status == "discharged"

    by_lang = {v.language: v for v in result.verticals}
    assert by_lang["go"].s_and_r_status == "counterexample"
    assert by_lang["solidity"].s_and_r_status == "valid"

    # The per-language S ∧ R aggregate and the closure gate both block the downstream action.
    assert result.composition.result == "blocked"
    assert any("go" in blocker for blocker in result.composition.blockers)
    assert result.gate.result == "blocked"
