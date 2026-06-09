from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .backend_agreement import BackendAgreementReport
from .coverage_alignment import SpecCoverageReport, TraceAlignmentReport
from .formal_backend import FormalBackendResponse
from .jsonutil import sha256_json
from .models import (
    BackendResult,
    EvidenceLevel,
    RequirementIRV2,
    SemanticNode,
    _has_command_metadata as _details_has_command,
    _has_recorded_bounds as _details_has_bounds,
    _recorded_tool_version as _details_recorded_tool_version,
)
from .system_checker import SystemConsistencyResult


PROOF_CLOSURE_SCHEMA_VERSION = "0.1"
PROOF_CLOSURE_TOOL_VERSION = "0.1"
HIGH_ASSURANCE_LEVELS = {EvidenceLevel.BOUNDED_CHECKED, EvidenceLevel.PROVEN_INDUCTIVE}


class EvidenceProducer(BaseModel):
    model_config = ConfigDict(extra="forbid")

    producer_id: str
    producer_kind: Literal[
        "formal_backend",
        "model_checker",
        "proof_assistant",
        "smt_solver",
        "system_checker",
        "trace_validator",
        "test_runner",
        "review",
        "coverage_checker",
        "formal_boundary",
        "other",
    ]
    real_producer: bool = True
    allowed_evidence_levels: list[EvidenceLevel] = Field(default_factory=list)
    tool: str
    tool_version: str | None = None
    command: str | None = None
    reproducibility: dict[str, str] = Field(default_factory=dict)


class EvidenceProducerMapping(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["0.1"] = PROOF_CLOSURE_SCHEMA_VERSION
    producers: list[EvidenceProducer] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_unique_producers(self) -> EvidenceProducerMapping:
        producer_ids = [producer.producer_id for producer in self.producers]
        if len(producer_ids) != len(set(producer_ids)):
            raise ValueError("producer_id values must be unique")
        return self


class ProofPremiseRoute(BaseModel):
    model_config = ConfigDict(extra="forbid")

    premise_id: str
    node_id: str
    node_kind: str
    role: Literal["premise", "obligation"]
    backend_id: str
    required_evidence: EvidenceLevel
    reason: str
    routing_mode: Literal["formal_claim", "semantic_node"] = "semantic_node"


class ProofDispatchPlan(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["0.1"] = PROOF_CLOSURE_SCHEMA_VERSION
    policy_id: str
    routes: list[ProofPremiseRoute] = Field(default_factory=list)


class ProofPremise(BaseModel):
    model_config = ConfigDict(extra="forbid")

    premise_id: str
    node_id: str
    node_kind: str
    role: Literal["premise", "obligation"]
    required_evidence: EvidenceLevel
    routed_backend: str
    status: Literal["discharged", "open", "blocked"]
    achieved_evidence: EvidenceLevel | None = None
    producer_id: str | None = None
    backend_status: str | None = None
    reason: str | None = None


class ProofClosureBlocker(BaseModel):
    model_config = ConfigDict(extra="forbid")

    category: Literal[
        "missing_context",
        "coverage",
        "trace_alignment",
        "producer_mapping",
        "backend_result",
        "backend_agreement",
        "premise",
    ]
    message: str
    premise_id: str | None = None
    backend: str | None = None
    evidence_level: EvidenceLevel | None = None


class ProofReproducibility(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tool: str = "nlreq.proof_closure"
    tool_version: str = PROOF_CLOSURE_TOOL_VERSION
    input_hashes: dict[str, str] = Field(default_factory=dict)


class ProofObject(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["0.1"] = PROOF_CLOSURE_SCHEMA_VERSION
    proof_id: str
    requirement_id: str
    requirement_ir_hash: str
    status: Literal["closed", "open", "blocked"]
    dispatch: ProofDispatchPlan
    premises: list[ProofPremise] = Field(default_factory=list)
    backend_results: list[BackendResult] = Field(default_factory=list)
    backend_agreement: BackendAgreementReport | None = None
    producer_mapping: EvidenceProducerMapping
    coverage_result: Literal["passed", "blocked", "missing"]
    trace_alignment_result: Literal["passed", "blocked", "missing"]
    blockers: list[ProofClosureBlocker] = Field(default_factory=list)
    reproducibility: ProofReproducibility


class ClosureGateReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["0.1"] = PROOF_CLOSURE_SCHEMA_VERSION
    result: Literal["passed", "blocked"]
    downstream_action: str
    proof_id: str
    requirement_id: str
    proof_status: Literal["closed", "open", "blocked"]
    blockers: list[ProofClosureBlocker] = Field(default_factory=list)


def default_evidence_producer_mapping() -> EvidenceProducerMapping:
    return EvidenceProducerMapping(
        producers=[
            EvidenceProducer(
                producer_id="system_checker",
                producer_kind="system_checker",
                allowed_evidence_levels=[EvidenceLevel.CONSISTENCY_CHECKED],
                tool="nlreq.system_checker",
                tool_version="0.1",
            ),
            EvidenceProducer(
                producer_id="solver_system_checker",
                producer_kind="system_checker",
                # SMT_CHECKED for checker_id="z3" (in-process propositional Z3);
                # BOUNDED_CHECKED for external model checkers (Apalache, TLC with depth).
                allowed_evidence_levels=[EvidenceLevel.SMT_CHECKED, EvidenceLevel.BOUNDED_CHECKED],
                tool="nlreq.system_checker.check_solver_backed_system_consistency",
                tool_version="0.1",
            ),
            EvidenceProducer(
                producer_id="core_smt",
                producer_kind="smt_solver",
                allowed_evidence_levels=[EvidenceLevel.SMT_CHECKED],
                tool="nlreq.smt",
                tool_version="0.1",
            ),
            EvidenceProducer(
                producer_id="smt-theories",
                producer_kind="smt_solver",
                # The theory-aware FormalClaim SMT producer (PB-6/PB-7): z3 with Int/Real linear
                # arithmetic and an uninterpreted member sort (formal_claim_smt), distinct from the
                # propositional core_smt above. Comparison premises route here and are discharged at
                # SMT_CHECKED by the joint premise-consistency query — the discharge core_smt's
                # propositional encoder cannot perform (it drops those ops). Set-literal-membership
                # premises route to the cvc5 producer below, not here (see _SMT_THEORY_DISCHARGED_KINDS
                # in formal_claim): formal_claim_smt can co-encode a membership in its joint query, but
                # the routed discharge for membership is cvc5's native finite-set theory. Naming this
                # as its own producer is what keeps a theory-checked premise from being tagged with the
                # propositional producer that never encoded it.
                allowed_evidence_levels=[EvidenceLevel.SMT_CHECKED],
                tool="nlreq.formal_claim_smt",
                tool_version="0.1",
            ),
            EvidenceProducer(
                producer_id="cvc5",
                producer_kind="smt_solver",
                # The second SMT backend (PB-6.T2): an independent cvc5 projection of the same
                # FormalClaim premise-consistency question core_smt checks with z3. SMT_CHECKED only;
                # tool_version is None here and recorded per-run from the installed cvc5 (it is an
                # optional dependency that degrades to "unsupported"/no-level when absent).
                allowed_evidence_levels=[EvidenceLevel.SMT_CHECKED],
                tool="cvc5",
                tool_version=None,
            ),
            EvidenceProducer(
                producer_id="tla",
                producer_kind="model_checker",
                allowed_evidence_levels=[EvidenceLevel.BOUNDED_CHECKED],
                tool="nlreq.tla_adapter",
                tool_version="0.1",
            ),
            EvidenceProducer(
                producer_id="tla-runner",
                producer_kind="model_checker",
                allowed_evidence_levels=[EvidenceLevel.BOUNDED_CHECKED],
                tool="nlreq.formal_backend.TlaRunnerBackend",
                tool_version="0.1",
            ),
            EvidenceProducer(
                producer_id="apalache",
                producer_kind="model_checker",
                allowed_evidence_levels=[EvidenceLevel.BOUNDED_CHECKED],
                tool="nlreq.formal_backend.ApalacheBackend",
                tool_version="0.1",
            ),
            EvidenceProducer(
                producer_id="tlc",
                producer_kind="model_checker",
                allowed_evidence_levels=[EvidenceLevel.BOUNDED_CHECKED],
                tool="nlreq.formal_backend.TlcProductionBackend",
                tool_version="0.1",
            ),
            EvidenceProducer(
                producer_id="tlaps",
                producer_kind="proof_assistant",
                allowed_evidence_levels=[EvidenceLevel.PROVEN_INDUCTIVE],
                tool="tlapm",
                tool_version=None,
            ),
            EvidenceProducer(
                producer_id="tla-boundary",
                producer_kind="formal_boundary",
                real_producer=False,
                allowed_evidence_levels=[],
                tool="nlreq.formal_backend.TlaBoundaryBackend",
                tool_version="0.1",
            ),
            EvidenceProducer(
                producer_id="trace_validation",
                producer_kind="trace_validator",
                allowed_evidence_levels=[EvidenceLevel.TRACE_VALIDATED],
                tool="nlreq.trace_validation",
                tool_version="0.1",
            ),
            EvidenceProducer(
                producer_id="command",
                producer_kind="test_runner",
                allowed_evidence_levels=[EvidenceLevel.TEST_VALIDATED],
                tool="nlreq.command_adapter",
                tool_version="0.1",
            ),
            EvidenceProducer(
                producer_id="human_review",
                producer_kind="review",
                allowed_evidence_levels=[EvidenceLevel.REVIEWED],
                tool="human_review",
            ),
            EvidenceProducer(
                producer_id="coverage_alignment",
                producer_kind="coverage_checker",
                allowed_evidence_levels=[],
                tool="nlreq.coverage_alignment",
                tool_version="0.1",
            ),
        ]
    )


# Per-premise backend routing table over generic SemanticNode kinds. Encoded as data + a pure
# function so the routing decision is executable and tested. This is the routing used for a
# requirement that does NOT lower to a FormalClaim: ``build_proof_object``'s no-dispatch default,
# the gate's refused-claim fallback, and the CLI's non-lowered fallback all build it via
# ``build_proof_dispatch_plan`` (its only routing — the legacy single-backend plan is the separate
# ``build_single_backend_dispatch_plan``). The AUTHORITATIVE routing for a LOWERED claim
# is ``formal_claim._backend_for_fragment_kind``, which routes the FormalClaim fragments the gate
# actually dispatches. This coarse generic router aligns its THEORY-routed kinds with that policy:
# comparison -> smt-theories and set-membership -> cvc5 on both surfaces, so a theory premise never
# routes to two different backends across the two APIs. It deliberately does NOT mirror
# predicate/rejection_order, which the authoritative router discharges via the S ∧ R model check
# (solver_system_checker) — a discharge concept this kind-only router does not model; here they fall
# to the core SMT checker. Membership in particular routes to cvc5's native finite-set theory, never
# the linear-arithmetic ``smt-theories`` backend that cannot encode a set literal.
_ROUTE_BACKEND_CORE_SMT = "core_smt"
_ROUTE_BACKEND_SMT_THEORIES = "smt-theories"
_ROUTE_BACKEND_CVC5 = "cvc5"
_ROUTE_BACKEND_APALACHE = "apalache"
_ROUTE_BACKEND_TRACE = "trace_validation"

# Numeric and comparison fragments → SMT with Int/Real theories (smt-theories).
_SMT_THEORY_NODE_KINDS = frozenset(
    {"comparison", "eq", "neq", "lt", "lte", "gt", "gte", "increase", "decrease"}
)
# Set-membership fragments → cvc5's native finite-set theory, matching the authoritative FormalClaim
# routing (``membership`` -> cvc5). The linear-arithmetic smt-theories backend cannot encode a
# set-literal membership, so routing it there would name a producer that never discharges it. This is
# the kind-only decision (correct for the v2 dispatch path, where a v3 set-literal membership really
# discharges on cvc5); the generic v1 adapter OVERRIDES it to the ``unsupported`` open sentinel for its
# always-opaque memberships (the v1 grammar has no set literal) — see ``adapter._generic_premise_backend``.
_SET_MEMBERSHIP_NODE_KINDS = frozenset({"membership"})
# State and temporal fragments → the Apalache S ∧ R model check.
_STATE_TEMPORAL_NODE_KINDS = frozenset(
    {
        "transition",
        "pre_state",
        "post_state",
        "invariant",
        "state_delta",
        "state_ref",
        "always",
        "eventually",
        "until",
        "before",
        "within",
    }
)
# Fragments grounded in observed execution → trace validation.
_TRACE_NODE_KINDS = frozenset({"trace_ref"})


def backend_for_proof_node(role: str, node_kind: str) -> str:
    """The backend that can discharge a proof premise of ``node_kind`` (per-premise routing decision).

    Numeric/comparison route to SMT with theories (smt-theories), set-membership to cvc5, state and
    temporal fragments to the Apalache S ∧ R model check, trace-grounded fragments to trace
    validation, and everything else (authorization and propositional structure) to the core SMT
    consistency checker. The comparison → smt-theories and membership → cvc5 choices align with the
    authoritative FormalClaim routing (``formal_claim._backend_for_fragment_kind``); predicate and
    rejection_order intentionally differ — the authoritative router discharges them via the S ∧ R
    model check (solver_system_checker), a concept this coarse kind-only router does not model.
    ``role`` ("premise"/"obligation") is accepted for future role-sensitive routing; today routing is
    by kind alone. This is the routing *decision* only — discharging a route still requires the
    matching producer to be registered and to have produced a result.
    """
    if node_kind in _SMT_THEORY_NODE_KINDS:
        return _ROUTE_BACKEND_SMT_THEORIES
    if node_kind in _SET_MEMBERSHIP_NODE_KINDS:
        return _ROUTE_BACKEND_CVC5
    if node_kind in _STATE_TEMPORAL_NODE_KINDS:
        return _ROUTE_BACKEND_APALACHE
    if node_kind in _TRACE_NODE_KINDS:
        return _ROUTE_BACKEND_TRACE
    return _ROUTE_BACKEND_CORE_SMT


# The evidence level each kind-routed backend discharges a premise at. A kind-routed plan must ask
# each route for exactly the level its routed backend emits: ``_evaluate_premise`` requires the
# achieved evidence to EQUAL ``route.required_evidence`` — it never widens, because equality is what
# keeps a BOUNDED_CHECKED result from silently satisfying an SMT_CHECKED obligation (the evidence-level
# non-conflation discipline). A kind-routed route left at the flat CONSISTENCY_CHECKED default could
# therefore never be discharged: none of these producers emit CONSISTENCY_CHECKED. Each level here is
# the routed backend's SOLE allowed level in ``default_evidence_producer_mapping`` —
# ``test_route_by_kind_routes_dischargeable_by_routed_producers`` pins this table to that registry so
# the two cannot drift (the same "must stay in sync" contract ``formal_claim._backend_for_evidence``
# carries). CONSISTENCY_CHECKED is intentionally absent: only the legacy single-backend
# ``system_checker`` plan requires it, and the kind-routed plan never routes there.
_REQUIRED_EVIDENCE_FOR_BACKEND: dict[str, EvidenceLevel] = {
    _ROUTE_BACKEND_CORE_SMT: EvidenceLevel.SMT_CHECKED,
    _ROUTE_BACKEND_SMT_THEORIES: EvidenceLevel.SMT_CHECKED,
    _ROUTE_BACKEND_CVC5: EvidenceLevel.SMT_CHECKED,
    _ROUTE_BACKEND_APALACHE: EvidenceLevel.BOUNDED_CHECKED,
    _ROUTE_BACKEND_TRACE: EvidenceLevel.TRACE_VALIDATED,
}


def required_evidence_for_proof_node(role: str, node_kind: str) -> EvidenceLevel:
    """The evidence level a kind-routed premise of ``node_kind`` must reach to discharge.

    Derived from the backend its kind routes to (:func:`backend_for_proof_node`): each kind-routed
    backend discharges at a single level (its sole entry in :func:`default_evidence_producer_mapping`),
    and the exact-match evidence gate in :func:`_evaluate_premise` requires the route to ask for
    exactly that level. Comparison/numeric and authorization/propositional premises route to SMT
    backends (SMT_CHECKED), set-membership to cvc5 (SMT_CHECKED), state/temporal to the Apalache
    S ∧ R model check (BOUNDED_CHECKED), and trace-grounded fragments to trace validation
    (TRACE_VALIDATED). This is the evidence *requirement* a kind-routed premise carries — discharging
    it still needs the routed producer to have produced a matching valid result; it does not itself
    run any backend.
    """
    return _REQUIRED_EVIDENCE_FOR_BACKEND.get(
        backend_for_proof_node(role, node_kind), EvidenceLevel.CONSISTENCY_CHECKED
    )


def build_proof_dispatch_plan(
    requirement: RequirementIRV2,
    *,
    policy_id: str = "default-system-consistency",
) -> ProofDispatchPlan:
    """Build the per-premise dispatch plan: each premise routes to the backend its kind needs.

    Each premise routes to :func:`backend_for_proof_node` and requires the evidence level that
    backend discharges at (:func:`required_evidence_for_proof_node`). Deriving the per-route evidence
    is what makes the plan dischargeable: the closure evidence gate is exact-match, so a route left at
    a flat default would block on a valid routed result (e.g. ``smt-theories`` emits SMT_CHECKED, not
    the old CONSISTENCY_CHECKED default). This is the closure default :func:`build_proof_object` builds
    when no explicit dispatch is given, and the plan the gate's refused-claim fallback and the CLI's
    non-lowered fallback use. The legacy single-backend plan — every premise on one backend — is
    :func:`build_single_backend_dispatch_plan`, which must be named explicitly so a lone verdict
    cannot silently close a multi-premise proof.
    """
    routes = [
        ProofPremiseRoute(
            premise_id=f"{requirement.requirement_id}:{role}:{node.node_id}",
            node_id=node.node_id,
            node_kind=node.kind,
            role=role,
            backend_id=backend_for_proof_node(role, node.kind),
            required_evidence=required_evidence_for_proof_node(role, node.kind),
            reason=f"routed by fragment kind '{node.kind}'",
        )
        for role, node in _proof_nodes(requirement.semantic_ir)
    ]
    return ProofDispatchPlan(policy_id=policy_id, routes=routes)


def build_single_backend_dispatch_plan(
    requirement: RequirementIRV2,
    *,
    backend_id: str = "system_checker",
    required_evidence: EvidenceLevel = EvidenceLevel.CONSISTENCY_CHECKED,
    policy_id: str = "default-system-consistency",
) -> ProofDispatchPlan:
    """The legacy single-backend plan: every premise routes to ``backend_id`` at ``required_evidence``.

    Explicitly named rather than a flag on :func:`build_proof_dispatch_plan`, so a single-backend plan
    is never the silent default — a lone verdict cannot close a multi-premise proof unless a caller
    asks for this plan by name. Used by fixtures that close on one ``system_checker`` verdict, by the
    high-assurance producer-mapping test (a custom ``backend_id``/``required_evidence``), and by
    cross-language / certification / backend-agreement helpers whose intent is closure, not premise
    routing.
    """
    routes = [
        ProofPremiseRoute(
            premise_id=f"{requirement.requirement_id}:{role}:{node.node_id}",
            node_id=node.node_id,
            node_kind=node.kind,
            role=role,
            backend_id=backend_id,
            required_evidence=required_evidence,
            reason="single-backend route for compositional proof fragment",
        )
        for role, node in _proof_nodes(requirement.semantic_ir)
    ]
    return ProofDispatchPlan(policy_id=policy_id, routes=routes)


def build_cross_language_dispatch_plan(
    requirement: RequirementIRV2,
    *,
    backend_id: str = "solver_system_checker",
    required_evidence: EvidenceLevel = EvidenceLevel.BOUNDED_CHECKED,
    policy_id: str = "cross-language-s-and-r",
) -> ProofDispatchPlan:
    """Route one proof premise per language to the per-language ``S ∧ R`` model check (PC-13).

    A cross-language requirement's obligation is an ``and`` of one *guard* per language (each a real
    :class:`SemanticNode` with its own ``node_id`` and a ``vertical_*`` metadata binding —
    see :func:`cross_language_guard_nodes`). This plan emits one route per guard, each routed to the
    solver-backed ``S ∧ R`` producer (``solver_system_checker``) at ``BOUNDED_CHECKED`` — the level a
    real Apalache ``S ∧ R`` run discharges. Each premise_id follows the same
    ``f"{req_id}:{role}:{node_id}"`` convention :func:`build_proof_dispatch_plan` uses, pointing at the
    parent requirement's REAL nodes, so the aggregated :class:`ProofObject`'s premises ARE the
    requirement's per-language guards — not invented labels.

    Routing mode is ``formal_claim`` (not ``semantic_node``) so the plan FAILS CLOSED: a guard is
    discharged only by a result that explicitly declares the guard's premise_id in its
    ``covered_fragment_ids``. Both per-language runs share the same backend id
    (``solver_system_checker``); under ``semantic_node`` matching an untagged Go result could silently
    discharge the Solidity guard. ``formal_claim`` makes that non-interchangeability structural — each
    guard is discharged ONLY by its own language's ``S ∧ R`` result, tagged with that guard's
    premise_id (see :mod:`nlreq.cross_language`).
    """
    routes = [
        ProofPremiseRoute(
            premise_id=f"{requirement.requirement_id}:{role}:{node.node_id}",
            node_id=node.node_id,
            node_kind=node.kind,
            role=role,
            backend_id=backend_id,
            required_evidence=required_evidence,
            reason=f"per-language S ∧ R premise for guard '{node.name or node.node_id}'",
            routing_mode="formal_claim",
        )
        for role, node in cross_language_guard_nodes(requirement.semantic_ir)
    ]
    return ProofDispatchPlan(policy_id=policy_id, routes=routes)


def cross_language_guard_nodes(
    root: SemanticNode,
) -> list[tuple[Literal["premise", "obligation"], SemanticNode]]:
    """The per-language guard nodes of a cross-language requirement's obligation.

    A cross-language requirement conjoins one guard per language under an ``and`` obligation; each
    conjunct is one proof premise discharged by ITS language's ``S ∧ R``. Returns one
    ``("obligation", guard)`` per conjunct. Falls back to the obligation as a single node when it is
    not an ``and`` (a degenerate single-language requirement), and to :func:`_proof_nodes` when there
    is no obligation at all — so the function is total over any rule node.
    """
    obligation = root.obligation
    if obligation is None:
        return _proof_nodes(root)
    if obligation.kind == "and" and obligation.children:
        return [("obligation", child) for child in obligation.children]
    return [("obligation", obligation)]


def build_proof_object(
    *,
    requirement: RequirementIRV2,
    backend_results: list[BackendResult],
    coverage: SpecCoverageReport | None = None,
    trace_alignment: TraceAlignmentReport | None = None,
    backend_agreement: BackendAgreementReport | None = None,
    producer_mapping: EvidenceProducerMapping | None = None,
    dispatch: ProofDispatchPlan | None = None,
) -> ProofObject:
    mapping = producer_mapping or default_evidence_producer_mapping()
    # With no explicit dispatch, route each premise to the backend its kind needs, never collapse
    # them onto the single system_checker default. A lone system-consistency verdict then discharges
    # only the premises that route to it, so it cannot close a multi-premise proof whose
    # comparison/membership/state premises need their own producer. Callers that genuinely want the
    # legacy single-backend plan (e.g. a fixture closing on one system_checker result) request it
    # explicitly via build_single_backend_dispatch_plan(requirement).
    plan = dispatch or build_proof_dispatch_plan(requirement)
    blockers: list[ProofClosureBlocker] = []

    coverage_result = _coverage_result(coverage, blockers)
    trace_result = _trace_alignment_result(trace_alignment, blockers)
    _backend_agreement_result(backend_agreement, blockers)
    blockers.extend(_producer_blockers(backend_results, mapping))

    premises = [
        _evaluate_premise(route, backend_results, mapping, blockers)
        for route in plan.routes
    ]
    blockers.extend(
        ProofClosureBlocker(
            category="premise",
            premise_id=premise.premise_id,
            backend=premise.routed_backend,
            evidence_level=premise.required_evidence,
            message=premise.reason or "premise is not discharged",
        )
        for premise in premises
        if premise.status != "discharged"
    )

    if blockers:
        status: Literal["closed", "open", "blocked"] = "blocked"
    elif all(premise.status == "discharged" for premise in premises):
        status = "closed"
    else:
        status = "open"

    input_hashes = {
        "requirement_ir": sha256_json(requirement),
        "dispatch": sha256_json(plan),
        "producer_mapping": sha256_json(mapping),
        "backend_results": sha256_json(backend_results),
    }
    if coverage is not None:
        input_hashes["spec_coverage"] = sha256_json(coverage)
    if trace_alignment is not None:
        input_hashes["trace_alignment"] = sha256_json(trace_alignment)
    if backend_agreement is not None:
        input_hashes["backend_agreement"] = sha256_json(backend_agreement)

    requirement_hash = sha256_json(requirement)
    return ProofObject(
        proof_id=f"proof:{requirement.requirement_id}",
        requirement_id=requirement.requirement_id,
        requirement_ir_hash=requirement_hash,
        status=status,
        dispatch=plan,
        premises=premises,
        backend_results=backend_results,
        backend_agreement=backend_agreement,
        producer_mapping=mapping,
        coverage_result=coverage_result,
        trace_alignment_result=trace_result,
        blockers=blockers,
        reproducibility=ProofReproducibility(input_hashes=input_hashes),
    )


def evaluate_closure_gate(
    proof: ProofObject,
    *,
    downstream_action: str = "merge",
) -> ClosureGateReport:
    blockers = list(proof.blockers)
    if proof.status != "closed":
        blockers.append(
            ProofClosureBlocker(
                category="premise",
                message="downstream action requires a closed proof object",
            )
        )
    return ClosureGateReport(
        result="blocked" if blockers else "passed",
        downstream_action=downstream_action,
        proof_id=proof.proof_id,
        requirement_id=proof.requirement_id,
        proof_status=proof.status,
        blockers=blockers,
    )


def backend_results_from_system_consistency(
    result: SystemConsistencyResult,
) -> list[BackendResult]:
    return [result.result]


def backend_results_from_formal_response(response: FormalBackendResponse) -> list[BackendResult]:
    return [response.result]


def _coverage_result(
    coverage: SpecCoverageReport | None,
    blockers: list[ProofClosureBlocker],
) -> Literal["passed", "blocked", "missing"]:
    if coverage is None:
        blockers.append(
            ProofClosureBlocker(
                category="missing_context",
                message="spec coverage report is required for proof closure",
            )
        )
        return "missing"
    if coverage.result != "passed":
        blockers.append(
            ProofClosureBlocker(
                category="coverage",
                message="spec coverage report did not pass",
            )
        )
    return coverage.result


def _backend_agreement_result(
    backend_agreement: BackendAgreementReport | None,
    blockers: list[ProofClosureBlocker],
) -> None:
    """Gate proof closure on a cross-backend agreement report, honoring its ``closure_effect``.

    The report's ``closure_effect`` is authoritative: ``build_backend_agreement_report`` sets it to
    ``"block"`` only for a real ``disagreed`` report — two backends reaching opposite conclusions on
    the same question (the same overlap_key), a genuine encoder divergence — under the ``blocking``
    policy. The non-blocking statuses already carry ``closure_effect="allow"`` at the source, so they
    never reach the block branch here:

      - ``non_overlap`` — the backends share no comparable question. A requirement that poses no
        cross-backend question (e.g. one with no comparison/membership premise, so its overlap_key is
        None) has nothing to disagree about and must not be refused for it.
      - ``needs_review`` — fewer than two backends decided (e.g. cvc5 is not installed), so there is
        no second opinion to cross-check. The single backend's per-premise results still flow through
        normal closure; the absent cross-check is additive, not a missing discharge.

    Honoring ``closure_effect`` (rather than re-deriving the blocking statuses here) means a
    ``report_only`` policy also never blocks: a disagreement under it yields
    ``closure_effect="report_only"``, not ``"block"``.
    """
    if backend_agreement is None:
        return
    if backend_agreement.closure_effect != "block":
        return
    messages = backend_agreement.blockers or ["backend agreement report blocked closure"]
    for message in messages:
        blockers.append(
            ProofClosureBlocker(
                category="backend_agreement",
                message=message,
            )
        )


def _trace_alignment_result(
    trace_alignment: TraceAlignmentReport | None,
    blockers: list[ProofClosureBlocker],
) -> Literal["passed", "blocked", "missing"]:
    if trace_alignment is None:
        blockers.append(
            ProofClosureBlocker(
                category="missing_context",
                message="trace alignment report is required for proof closure",
            )
        )
        return "missing"
    if trace_alignment.result != "passed":
        blockers.append(
            ProofClosureBlocker(
                category="trace_alignment",
                message="trace alignment report did not pass",
            )
        )
    return trace_alignment.result


def _evaluate_premise(
    route: ProofPremiseRoute,
    backend_results: list[BackendResult],
    mapping: EvidenceProducerMapping,
    blockers: list[ProofClosureBlocker],
) -> ProofPremise:
    # FormalClaim routes require explicit covered_fragment_ids — a result without the
    # field cannot discharge a formal_claim route. Semantic-node routes retain
    # backward-compatible backend-only matching for legacy paths.
    if route.routing_mode == "formal_claim":
        matching = [
            result
            for result in backend_results
            if result.backend == route.backend_id
            and "covered_fragment_ids" in result.details
            and route.premise_id in result.details["covered_fragment_ids"]
        ]
    else:
        matching = [
            result
            for result in backend_results
            if result.backend == route.backend_id
            and (
                "covered_fragment_ids" not in result.details
                or route.premise_id in result.details["covered_fragment_ids"]
            )
        ]
    if not matching:
        return _premise_from_route(
            route,
            status="open",
            reason="no backend result was supplied for routed premise",
        )

    result = next((item for item in matching if item.status == "valid"), matching[0])
    if result.status != "valid":
        status: Literal["open", "blocked"] = (
            "open" if result.status == "needs_review" else "blocked"
        )
        return _premise_from_route(
            route,
            status=status,
            backend_status=result.status,
            producer_id=result.backend,
            achieved_evidence=result.evidence_level,
            reason=f"backend result status is {result.status}",
        )
    if result.evidence_level is None:
        return _premise_from_route(
            route,
            status="open",
            backend_status=result.status,
            producer_id=result.backend,
            reason="backend result did not declare an evidence level",
        )
    if result.evidence_level != route.required_evidence:
        return _premise_from_route(
            route,
            status="blocked",
            backend_status=result.status,
            producer_id=result.backend,
            achieved_evidence=result.evidence_level,
            reason=(
                f"backend result evidence {result.evidence_level.value} "
                f"does not satisfy required {route.required_evidence.value}"
            ),
        )
    producer = _producer_by_id(mapping).get(result.backend)
    if producer is None:
        return _premise_from_route(
            route,
            status="blocked",
            backend_status=result.status,
            producer_id=result.backend,
            achieved_evidence=result.evidence_level,
            reason="backend result producer is not registered",
        )
    if result.evidence_level not in producer.allowed_evidence_levels:
        return _premise_from_route(
            route,
            status="blocked",
            backend_status=result.status,
            producer_id=result.backend,
            achieved_evidence=result.evidence_level,
            reason="producer is not allowed to emit this evidence level",
        )
    if result.evidence_level in HIGH_ASSURANCE_LEVELS and not producer.real_producer:
        blockers.append(
            ProofClosureBlocker(
                category="producer_mapping",
                backend=result.backend,
                evidence_level=result.evidence_level,
                message="high-assurance evidence requires a real producer",
            )
        )
        return _premise_from_route(
            route,
            status="blocked",
            backend_status=result.status,
            producer_id=result.backend,
            achieved_evidence=result.evidence_level,
            reason="high-assurance evidence requires a real producer",
        )
    backing = bounded_backing_problems(result)
    if backing:
        return _premise_from_route(
            route,
            status="blocked",
            backend_status=result.status,
            producer_id=result.backend,
            achieved_evidence=result.evidence_level,
            reason=f"bounded evidence is not backed: {'; '.join(backing)}",
        )

    return _premise_from_route(
        route,
        status="discharged",
        backend_status=result.status,
        producer_id=result.backend,
        achieved_evidence=result.evidence_level,
    )


def _premise_from_route(
    route: ProofPremiseRoute,
    *,
    status: Literal["discharged", "open", "blocked"],
    achieved_evidence: EvidenceLevel | None = None,
    producer_id: str | None = None,
    backend_status: str | None = None,
    reason: str | None = None,
) -> ProofPremise:
    return ProofPremise(
        premise_id=route.premise_id,
        node_id=route.node_id,
        node_kind=route.node_kind,
        role=route.role,
        required_evidence=route.required_evidence,
        routed_backend=route.backend_id,
        status=status,
        achieved_evidence=achieved_evidence,
        producer_id=producer_id,
        backend_status=backend_status,
        reason=reason,
    )


def _producer_blockers(
    backend_results: list[BackendResult],
    mapping: EvidenceProducerMapping,
) -> list[ProofClosureBlocker]:
    producers = _producer_by_id(mapping)
    blockers: list[ProofClosureBlocker] = []
    for result in backend_results:
        if result.evidence_level is None:
            continue
        producer = producers.get(result.backend)
        if producer is None:
            blockers.append(
                ProofClosureBlocker(
                    category="producer_mapping",
                    backend=result.backend,
                    evidence_level=result.evidence_level,
                    message="backend result producer is not registered",
                )
            )
            continue
        if result.evidence_level not in producer.allowed_evidence_levels:
            blockers.append(
                ProofClosureBlocker(
                    category="producer_mapping",
                    backend=result.backend,
                    evidence_level=result.evidence_level,
                    message="producer is not allowed to emit this evidence level",
                )
            )
        if result.evidence_level in HIGH_ASSURANCE_LEVELS and not producer.real_producer:
            blockers.append(
                ProofClosureBlocker(
                    category="producer_mapping",
                    backend=result.backend,
                    evidence_level=result.evidence_level,
                    message="high-assurance evidence requires a real producer",
                )
            )
        for problem in bounded_backing_problems(result):
            blockers.append(
                ProofClosureBlocker(
                    category="producer_mapping",
                    backend=result.backend,
                    evidence_level=result.evidence_level,
                    message=f"bounded evidence is not backed: {problem}",
                )
            )
    return blockers


def _producer_by_id(mapping: EvidenceProducerMapping) -> dict[str, EvidenceProducer]:
    return {producer.producer_id: producer for producer in mapping.producers}


def bounded_backing_problems(result: BackendResult) -> list[str]:
    """Reasons a BOUNDED_CHECKED result is not backed by a real bounded model check.

    BOUNDED_CHECKED asserts a bounded checker actually searched the model to a recorded depth.
    The honest backing for that claim is: recorded bounds, the checker command, and a tool
    version recorded *from the run that produced it* (not a producer's static placeholder). A
    stub or custom command that emits BOUNDED_CHECKED without these did not produce bounded
    evidence and must not discharge or be accepted into a proof — this is the single definition
    of "backed" shared by the closure gate and the evidence-producer validator. Returns the
    empty list for any non-BOUNDED_CHECKED result (it makes no claim about other levels).
    """
    if result.evidence_level != EvidenceLevel.BOUNDED_CHECKED:
        return []
    problems: list[str] = []
    if not _has_bounds(result):
        problems.append("recorded bounds are missing")
    if not _has_command_metadata(result):
        problems.append("command metadata is missing")
    if _recorded_tool_version(result) is None:
        problems.append("tool version is missing")
    return problems


# The granular reasons reuse the canonical, ``details``-based bounded-backing predicates in
# ``models`` so this closure-layer check and the producers' self-gating (and the BackendResult
# construction guard) cannot drift from one definition of "backed". ``bounded_backing_problems``
# is the message-producing sibling of ``models.bounded_evidence_backing_complete``: it returns no
# problems exactly when that predicate is True.
def _has_bounds(result: BackendResult) -> bool:
    return _details_has_bounds(result.details)


def _has_command_metadata(result: BackendResult) -> bool:
    return _details_has_command(result.details)


def _recorded_tool_version(result: BackendResult) -> str | None:
    return _details_recorded_tool_version(result.details)


def _proof_nodes(root: SemanticNode) -> list[tuple[Literal["premise", "obligation"], SemanticNode]]:
    nodes: list[tuple[Literal["premise", "obligation"], SemanticNode]] = []
    if root.premise is not None:
        if root.premise.kind == "and" and root.premise.children:
            nodes.extend(("premise", child) for child in root.premise.children)
        else:
            nodes.append(("premise", root.premise))
    if root.obligation is not None:
        nodes.append(("obligation", root.obligation))
    if not nodes:
        nodes.append(("obligation", root))
    return nodes
