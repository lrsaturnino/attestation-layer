from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .backend_agreement import BackendAgreementReport
from .coverage_alignment import SpecCoverageReport, TraceAlignmentReport
from .formal_backend import FormalBackendResponse
from .jsonutil import sha256_json
from .models import BackendResult, EvidenceLevel, RequirementIRV2, SemanticNode
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
                allowed_evidence_levels=[EvidenceLevel.BOUNDED_CHECKED],
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


def build_proof_dispatch_plan(
    requirement: RequirementIRV2,
    *,
    backend_id: str = "system_checker",
    required_evidence: EvidenceLevel = EvidenceLevel.CONSISTENCY_CHECKED,
    policy_id: str = "default-system-consistency",
) -> ProofDispatchPlan:
    routes = [
        ProofPremiseRoute(
            premise_id=f"{requirement.requirement_id}:{role}:{node.node_id}",
            node_id=node.node_id,
            node_kind=node.kind,
            role=role,
            backend_id=backend_id,
            required_evidence=required_evidence,
            reason="default route for compositional proof fragment",
        )
        for role, node in _proof_nodes(requirement.semantic_ir)
    ]
    return ProofDispatchPlan(policy_id=policy_id, routes=routes)


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
    matching = [result for result in backend_results if result.backend == route.backend_id]
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
    return blockers


def _producer_by_id(mapping: EvidenceProducerMapping) -> dict[str, EvidenceProducer]:
    return {producer.producer_id: producer for producer in mapping.producers}


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
