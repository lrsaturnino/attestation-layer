from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from .formal_backend import (
    FormalBackendBudget,
    FormalBackendExecution,
    FormalBackendResponse,
    UnsupportedConstruct,
    build_formal_backend_request,
    check_formal_backend,
)
from .jsonutil import sha256_json
from .models import BackendResult, EvidenceLevel, RequirementIRV2, SemanticNode, SourceSpan, ValueRef


REQUIREMENT_SELF_CONSISTENCY_SCHEMA_VERSION = "0.1"


class RequirementSelfContradiction(BaseModel):
    model_config = ConfigDict(extra="forbid")

    contradiction_type: Literal[
        "opposite_fragment",
        "direct_opposite_predicates",
        "impossible_comparison",
        "mutually_exclusive_states",
        "overlapping_opposite_obligations",
        "temporal_impossibility",
        "numeric_bound_conflict",
        "duplicate_obligation_conflict",
        "backend_counterexample",
    ]
    code: str | None = None
    node_ids: list[str] = Field(default_factory=list)
    message: str
    source_spans: list[SourceSpan] = Field(default_factory=list)


class RequirementSelfConsistencyResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["0.1"] = REQUIREMENT_SELF_CONSISTENCY_SCHEMA_VERSION
    requirement_id: str
    status: Literal["valid", "contradiction", "unsupported", "timeout", "tool_error"]
    result: BackendResult
    contradictions: list[RequirementSelfContradiction] = Field(default_factory=list)
    unsupported_constructs: list[UnsupportedConstruct] = Field(default_factory=list)
    formal_backend_response: FormalBackendResponse | None = None


def check_requirement_self_consistency(
    requirement: RequirementIRV2,
    *,
    backend_id: str = "tla-runner",
    budget: FormalBackendBudget | None = None,
    execution: FormalBackendExecution | None = None,
) -> RequirementSelfConsistencyResult:
    contradictions = _deterministic_contradictions(requirement.semantic_ir)
    if contradictions:
        return RequirementSelfConsistencyResult(
            requirement_id=requirement.requirement_id,
            status="contradiction",
            result=BackendResult(
                backend="requirement_self_consistency",
                status="invalid",
                evidence_level=None,
                details={
                    "checker": "deterministic_precheck",
                    "contradictions": [
                        item.model_dump(mode="json", exclude_none=True)
                        for item in contradictions
                    ],
                },
            ),
            contradictions=contradictions,
        )

    response = check_formal_backend(
        build_formal_backend_request(
            requirement,
            backend_id=backend_id,
            budget=budget,
            execution=execution,
        )
    )
    status = _result_status(response)
    backend_counterexamples = _counterexamples_from_backend(response) if status == "contradiction" else []
    return RequirementSelfConsistencyResult(
        requirement_id=requirement.requirement_id,
        status=status,
        result=BackendResult(
            backend="requirement_self_consistency",
            status=_backend_result_status(status),
            evidence_level=EvidenceLevel.BOUNDED_CHECKED if status == "valid" else None,
            details={
                "checker": backend_id,
                "formal_backend_status": response.result.status,
                "formal_backend_response_hash": sha256_json(response),
                "backend_details": response.result.details,
            },
        ),
        contradictions=backend_counterexamples,
        unsupported_constructs=response.unsupported_constructs,
        formal_backend_response=response,
    )


def _result_status(response: FormalBackendResponse) -> str:
    status = response.result.status
    if status == "valid":
        return "valid"
    if status == "counterexample":
        return "contradiction"
    if status in {"timeout", "unsupported", "tool_error"}:
        return status
    if status == "invalid" and response.result.details.get("runner_outcome") == "tool_error":
        return "tool_error"
    return "unsupported"


def _backend_result_status(status: str) -> str:
    if status == "valid":
        return "valid"
    if status == "timeout":
        return "timeout"
    if status == "unsupported":
        return "unsupported"
    return "invalid"


def _counterexamples_from_backend(
    response: FormalBackendResponse,
) -> list[RequirementSelfContradiction]:
    counterexamples = response.result.details.get("counterexamples", [])
    if not isinstance(counterexamples, list):
        counterexamples = []
    return [
        RequirementSelfContradiction(
            contradiction_type="backend_counterexample",
            message="formal backend found a counterexample for R checked alone",
            node_ids=[],
            source_spans=[],
        )
    ] if counterexamples or response.result.status == "counterexample" else []


def _deterministic_contradictions(root: SemanticNode) -> list[RequirementSelfContradiction]:
    contradictions: list[RequirementSelfContradiction] = []
    for node in _walk_nodes(root):
        if node.kind == "and":
            contradictions.extend(_opposite_fragment_contradictions(node.children))
            contradictions.extend(_numeric_bound_conflicts(node.children))
            contradictions.extend(_duplicate_obligation_conflicts(node.children))
        if node.kind in {"eq", "neq", "lt", "lte", "gt", "gte"}:
            contradiction = _impossible_comparison(node)
            if contradiction is not None:
                contradictions.append(contradiction)
        if node.kind == "within":
            contradiction = _temporal_impossibility(node)
            if contradiction is not None:
                contradictions.append(contradiction)
    return contradictions


def _opposite_fragment_contradictions(
    children: list[SemanticNode],
) -> list[RequirementSelfContradiction]:
    contradictions: list[RequirementSelfContradiction] = []
    seen: dict[tuple[str, tuple[str, ...]], SemanticNode] = {}
    for child in children:
        signature = _fragment_signature(child)
        if signature is None:
            continue
        opposite = _opposite_signature(signature)
        if opposite in seen:
            other = seen[opposite]
            contradictions.append(
                RequirementSelfContradiction(
                    contradiction_type=_opposite_contradiction_type(other, child),
                    code=_opposite_contradiction_code(other, child),
                    node_ids=[other.node_id, child.node_id],
                    message="requirement contains mutually exclusive fragments",
                    source_spans=[*other.source_spans, *child.source_spans],
                )
            )
        seen[signature] = child
    return contradictions


def _fragment_signature(node: SemanticNode) -> tuple[str, tuple[str, ...]] | None:
    if node.kind == "predicate":
        return (f"predicate:{node.name}", tuple(_value_text(arg) for arg in node.args))
    if node.kind == "not" and node.children and node.children[0].kind == "predicate":
        child = node.children[0]
        return (f"not_predicate:{child.name}", tuple(_value_text(arg) for arg in child.args))
    if node.kind in {"eq", "neq", "lt", "lte", "gt", "gte"}:
        return (node.kind, tuple(_value_text(arg) for arg in _node_args(node)))
    return None


def _opposite_contradiction_type(
    left: SemanticNode, right: SemanticNode
) -> str:
    if left.kind == "predicate" or right.kind == "predicate":
        return "direct_opposite_predicates"
    if left.kind in {"eq", "neq"} and right.kind in {"eq", "neq"}:
        return "mutually_exclusive_states" if _state_like(left, right) else "opposite_fragment"
    return "overlapping_opposite_obligations" if _obligation_like(left, right) else "opposite_fragment"


def _opposite_contradiction_code(left: SemanticNode, right: SemanticNode) -> str:
    category = _opposite_contradiction_type(left, right)
    return {
        "direct_opposite_predicates": "CONTRADICTION_DIRECT_OPPOSITE_PREDICATES",
        "mutually_exclusive_states": "CONTRADICTION_MUTUALLY_EXCLUSIVE_STATES",
        "overlapping_opposite_obligations": "CONTRADICTION_OVERLAPPING_OPPOSITE_OBLIGATIONS",
    }.get(category, "CONTRADICTION_OPPOSITE_FRAGMENT")


def _state_like(left: SemanticNode, right: SemanticNode) -> bool:
    return left.metadata.get("predicate") == "state_is" or right.metadata.get("predicate") == "state_is"


def _obligation_like(left: SemanticNode, right: SemanticNode) -> bool:
    return left.node_id.startswith("obligation.") or right.node_id.startswith("obligation.")


def _opposite_signature(signature: tuple[str, tuple[str, ...]]) -> tuple[str, tuple[str, ...]]:
    kind, args = signature
    opposites = {
        "eq": "neq",
        "neq": "eq",
        "lt": "gte",
        "lte": "gt",
        "gt": "lte",
        "gte": "lt",
    }
    if kind.startswith("predicate:"):
        return (kind.replace("predicate:", "not_predicate:", 1), args)
    if kind.startswith("not_predicate:"):
        return (kind.replace("not_predicate:", "predicate:", 1), args)
    return (opposites.get(kind, ""), args)


def _impossible_comparison(node: SemanticNode) -> RequirementSelfContradiction | None:
    args = _node_args(node)
    if len(args) < 2 or args[0].kind != "number" or args[1].kind != "number":
        return None
    left = float(args[0].value)
    right = float(args[1].value)
    valid = {
        "eq": left == right,
        "neq": left != right,
        "lt": left < right,
        "lte": left <= right,
        "gt": left > right,
        "gte": left >= right,
    }[node.kind]
    if valid:
        return None
    return RequirementSelfContradiction(
        contradiction_type="impossible_comparison",
        code="CONTRADICTION_IMPOSSIBLE_COMPARISON",
        node_ids=[node.node_id],
        message=f"comparison {left:g} {node.kind} {right:g} is unsatisfiable",
        source_spans=node.source_spans,
    )


def _numeric_bound_conflicts(
    children: list[SemanticNode],
) -> list[RequirementSelfContradiction]:
    comparisons: dict[str, list[SemanticNode]] = {}
    for child in children:
        args = _node_args(child)
        if child.kind in {"lt", "lte", "gt", "gte"} and len(args) >= 2:
            comparisons.setdefault(_value_text(args[0]), []).append(child)
    contradictions: list[RequirementSelfContradiction] = []
    for nodes in comparisons.values():
        lower_bounds = [_bound_value(node) for node in nodes if node.kind in {"gt", "gte"}]
        upper_bounds = [_bound_value(node) for node in nodes if node.kind in {"lt", "lte"}]
        lower_bounds = [item for item in lower_bounds if item is not None]
        upper_bounds = [item for item in upper_bounds if item is not None]
        if lower_bounds and upper_bounds and max(lower_bounds) > min(upper_bounds):
            involved = nodes[:]
            contradictions.append(
                RequirementSelfContradiction(
                    contradiction_type="numeric_bound_conflict",
                    code="CONTRADICTION_NUMERIC_BOUND_CONFLICT",
                    node_ids=[node.node_id for node in involved],
                    message="numeric lower bound exceeds upper bound",
                    source_spans=[span for node in involved for span in node.source_spans],
                )
            )
    return contradictions


def _duplicate_obligation_conflicts(
    children: list[SemanticNode],
) -> list[RequirementSelfContradiction]:
    seen: dict[tuple[str, tuple[str, ...]], SemanticNode] = {}
    contradictions: list[RequirementSelfContradiction] = []
    for child in children:
        signature = _fragment_signature(child)
        if signature is None:
            continue
        if signature in seen and _obligation_like(seen[signature], child):
            other = seen[signature]
            contradictions.append(
                RequirementSelfContradiction(
                    contradiction_type="duplicate_obligation_conflict",
                    code="CONTRADICTION_DUPLICATE_OBLIGATION_CONFLICT",
                    node_ids=[other.node_id, child.node_id],
                    message="duplicate obligation appears in the same obligation set",
                    source_spans=[*other.source_spans, *child.source_spans],
                )
            )
        seen[signature] = child
    return contradictions


def _temporal_impossibility(node: SemanticNode) -> RequirementSelfContradiction | None:
    if node.temporal_bound is None:
        return None
    if float(node.temporal_bound.value) >= 0:
        return None
    return RequirementSelfContradiction(
        contradiction_type="temporal_impossibility",
        code="CONTRADICTION_TEMPORAL_IMPOSSIBILITY",
        node_ids=[node.node_id],
        message="temporal bound cannot be negative",
        source_spans=node.source_spans,
    )


def _bound_value(node: SemanticNode) -> float | None:
    args = _node_args(node)
    if len(args) < 2 or args[1].kind != "number":
        return None
    return float(args[1].value)


def _node_args(node: SemanticNode) -> list[ValueRef]:
    if node.args:
        return node.args
    values: list[ValueRef] = []
    if isinstance(node.left, ValueRef):
        values.append(node.left)
    if isinstance(node.right, ValueRef):
        values.append(node.right)
    return values


def _value_text(value: ValueRef) -> str:
    return f"{value.kind}:{value.value}"


def _walk_nodes(node: SemanticNode):
    yield node
    for child in node.scope:
        yield from _walk_nodes(child)
    if node.premise is not None:
        yield from _walk_nodes(node.premise)
    if node.obligation is not None:
        yield from _walk_nodes(node.obligation)
    if node.action is not None:
        yield from _walk_nodes(node.action)
    if node.must is not None:
        yield from _walk_nodes(node.must)
    for child in node.children:
        yield from _walk_nodes(child)
    if isinstance(node.left, SemanticNode):
        yield from _walk_nodes(node.left)
    if isinstance(node.right, SemanticNode):
        yield from _walk_nodes(node.right)
