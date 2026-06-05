from __future__ import annotations

from fractions import Fraction
from typing import Any, Literal

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
from .numeric_literal import exact_fraction


REQUIREMENT_SELF_CONSISTENCY_SCHEMA_VERSION = "0.1"
REQUIREMENT_CONTRADICTION_TAXONOMY_VERSION = "alice-style-0.1"


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


class RequirementContradictionTaxonomyEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    contradiction_type: str
    code: str
    description: str
    deterministic: bool
    blocks_closure: bool


class RequirementContradictionTaxonomy(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["0.1"] = REQUIREMENT_SELF_CONSISTENCY_SCHEMA_VERSION
    taxonomy_version: Literal["alice-style-0.1"] = REQUIREMENT_CONTRADICTION_TAXONOMY_VERSION
    entries: list[RequirementContradictionTaxonomyEntry]


class UntrustedContradictionSuggestion(BaseModel):
    model_config = ConfigDict(extra="forbid")

    suggestion_id: str
    suggested_type: str
    message: str
    source_spans: list[SourceSpan] = Field(default_factory=list)
    producer: str = "untrusted"


class RequirementSelfConsistencyResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["0.1"] = REQUIREMENT_SELF_CONSISTENCY_SCHEMA_VERSION
    requirement_id: str
    status: Literal["valid", "contradiction", "unsupported", "timeout", "tool_error"]
    result: BackendResult
    taxonomy_version: Literal["alice-style-0.1"] = REQUIREMENT_CONTRADICTION_TAXONOMY_VERSION
    checked_taxonomy_codes: list[str] = Field(default_factory=list)
    contradictions: list[RequirementSelfContradiction] = Field(default_factory=list)
    untrusted_suggestions: list[UntrustedContradictionSuggestion] = Field(default_factory=list)
    unsupported_constructs: list[UnsupportedConstruct] = Field(default_factory=list)
    formal_backend_response: FormalBackendResponse | None = None


def build_requirement_contradiction_taxonomy() -> RequirementContradictionTaxonomy:
    return RequirementContradictionTaxonomy(
        entries=[
            RequirementContradictionTaxonomyEntry(
                contradiction_type="direct_opposite_predicates",
                code="CONTRADICTION_DIRECT_OPPOSITE_PREDICATES",
                description="A predicate and its direct negation are both required under the same conjunction.",
                deterministic=True,
                blocks_closure=True,
            ),
            RequirementContradictionTaxonomyEntry(
                contradiction_type="impossible_comparison",
                code="CONTRADICTION_IMPOSSIBLE_COMPARISON",
                description="A literal numeric or equality comparison is unsatisfiable.",
                deterministic=True,
                blocks_closure=True,
            ),
            RequirementContradictionTaxonomyEntry(
                contradiction_type="mutually_exclusive_states",
                code="CONTRADICTION_MUTUALLY_EXCLUSIVE_STATES",
                description="The same state reference is constrained to incompatible values.",
                deterministic=True,
                blocks_closure=True,
            ),
            RequirementContradictionTaxonomyEntry(
                contradiction_type="overlapping_opposite_obligations",
                code="CONTRADICTION_OVERLAPPING_OPPOSITE_OBLIGATIONS",
                description="Obligations in the same set require incompatible outcomes.",
                deterministic=True,
                blocks_closure=True,
            ),
            RequirementContradictionTaxonomyEntry(
                contradiction_type="temporal_impossibility",
                code="CONTRADICTION_TEMPORAL_IMPOSSIBILITY",
                description="A temporal bound cannot be satisfied.",
                deterministic=True,
                blocks_closure=True,
            ),
            RequirementContradictionTaxonomyEntry(
                contradiction_type="numeric_bound_conflict",
                code="CONTRADICTION_NUMERIC_BOUND_CONFLICT",
                description="Numeric lower and upper bounds have no overlap.",
                deterministic=True,
                blocks_closure=True,
            ),
            RequirementContradictionTaxonomyEntry(
                contradiction_type="duplicate_obligation_conflict",
                code="CONTRADICTION_DUPLICATE_OBLIGATION_CONFLICT",
                description="A duplicated obligation requires human review because it may hide a modeling error.",
                deterministic=True,
                blocks_closure=True,
            ),
            RequirementContradictionTaxonomyEntry(
                contradiction_type="backend_counterexample",
                code="CONTRADICTION_BACKEND_COUNTEREXAMPLE",
                description="A formal backend found a counterexample when checking the requirement against itself.",
                deterministic=False,
                blocks_closure=True,
            ),
        ]
    )


def check_requirement_self_consistency(
    requirement: RequirementIRV2,
    *,
    backend_id: str = "tla-runner",
    budget: FormalBackendBudget | None = None,
    execution: FormalBackendExecution | None = None,
    untrusted_suggestions: list[UntrustedContradictionSuggestion] | None = None,
) -> RequirementSelfConsistencyResult:
    contradictions = _deterministic_contradictions(requirement.semantic_ir)
    checked_codes = _taxonomy_codes()
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
            checked_taxonomy_codes=checked_codes,
            contradictions=contradictions,
            untrusted_suggestions=untrusted_suggestions or [],
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
    # Surface the bounds the inner bounded check ran under at the top level so a BOUNDED_CHECKED
    # claim carries its backing where the construction guard reads it. A bounded result is honest
    # only when a bounded check actually recorded a bound, so the level is claimed only then.
    backend_details = response.result.details
    inner_bounds = backend_details.get("bounds") if isinstance(backend_details, dict) else None
    has_bounds = isinstance(inner_bounds, dict) and len(inner_bounds) > 0
    self_consistency_details: dict[str, Any] = {
        "checker": backend_id,
        "formal_backend_status": response.result.status,
        "formal_backend_response_hash": sha256_json(response),
        "backend_details": backend_details,
    }
    if has_bounds:
        self_consistency_details["bounds"] = inner_bounds
    return RequirementSelfConsistencyResult(
        requirement_id=requirement.requirement_id,
        status=status,
        result=BackendResult(
            backend="requirement_self_consistency",
            status=_backend_result_status(status),
            evidence_level=(
                EvidenceLevel.BOUNDED_CHECKED if status == "valid" and has_bounds else None
            ),
            details=self_consistency_details,
        ),
        checked_taxonomy_codes=checked_codes,
        contradictions=backend_counterexamples,
        untrusted_suggestions=untrusted_suggestions or [],
        unsupported_constructs=response.unsupported_constructs,
        formal_backend_response=response,
    )


def _taxonomy_codes() -> list[str]:
    return [entry.code for entry in build_requirement_contradiction_taxonomy().entries]


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
            contradictions.extend(_mutually_exclusive_state_conflicts(node.children))
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
        "predicate:authorized": "predicate:not_authorized",
        "predicate:not_authorized": "predicate:authorized",
        "predicate:approved": "predicate:not_approved",
        "predicate:not_approved": "predicate:approved",
        "eq": "neq",
        "neq": "eq",
        "lt": "gte",
        "lte": "gt",
        "gt": "lte",
        "gte": "lt",
    }
    if kind in opposites:
        return (opposites[kind], args)
    if kind.startswith("predicate:"):
        return (kind.replace("predicate:", "not_predicate:", 1), args)
    if kind.startswith("not_predicate:"):
        return (kind.replace("not_predicate:", "predicate:", 1), args)
    return (opposites.get(kind, ""), args)


def _mutually_exclusive_state_conflicts(
    children: list[SemanticNode],
) -> list[RequirementSelfContradiction]:
    states: dict[str, SemanticNode] = {}
    contradictions: list[RequirementSelfContradiction] = []
    for child in children:
        if child.kind != "eq" or child.metadata.get("predicate") != "state_is":
            continue
        args = _node_args(child)
        if len(args) < 2:
            continue
        state_key = _value_text(args[0])
        if state_key in states and _value_text(_node_args(states[state_key])[1]) != _value_text(args[1]):
            other = states[state_key]
            contradictions.append(
                RequirementSelfContradiction(
                    contradiction_type="mutually_exclusive_states",
                    code="CONTRADICTION_MUTUALLY_EXCLUSIVE_STATES",
                    node_ids=[other.node_id, child.node_id],
                    message="state predicate requires two different values under the same condition",
                    source_spans=[*other.source_spans, *child.source_spans],
                )
            )
        states[state_key] = child
    return contradictions


def _impossible_comparison(node: SemanticNode) -> RequirementSelfContradiction | None:
    args = _node_args(node)
    if len(args) < 2 or args[0].kind != "number" or args[1].kind != "number":
        return None
    # Decide the comparison over exact rationals, not float(): a constant comparison of large
    # integers (9007199254740993 lte 9007199254740992) rounds to equal under float and the real
    # contradiction would silently vanish. A non-finite literal is not decidable -> leave it alone.
    left = exact_fraction(args[0].value)
    right = exact_fraction(args[1].value)
    if left is None or right is None:
        return None
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
        message=f"comparison {args[0].value} {node.kind} {args[1].value} is unsatisfiable",
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
        lower_bounds = [
            _bound(node) for node in nodes if node.kind in {"gt", "gte"}
        ]
        upper_bounds = [
            _bound(node) for node in nodes if node.kind in {"lt", "lte"}
        ]
        lower_bounds = [item for item in lower_bounds if item is not None]
        upper_bounds = [item for item in upper_bounds if item is not None]
        if lower_bounds and upper_bounds and _bounds_conflict(lower_bounds, upper_bounds):
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
    bound = exact_fraction(node.temporal_bound.value)
    if bound is None or bound >= 0:
        return None
    return RequirementSelfContradiction(
        contradiction_type="temporal_impossibility",
        code="CONTRADICTION_TEMPORAL_IMPOSSIBILITY",
        node_ids=[node.node_id],
        message="temporal bound cannot be negative",
        source_spans=node.source_spans,
    )


def _bound_value(node: SemanticNode) -> Fraction | None:
    args = _node_args(node)
    if len(args) < 2 or args[1].kind != "number":
        return None
    # Exact, so a lower/upper bound conflict between large-integer bounds is not lost to float
    # rounding (9007199254740993 as a lower bound vs 9007199254740992 as an upper bound).
    return exact_fraction(args[1].value)


def _bound(node: SemanticNode) -> tuple[Fraction, bool] | None:
    value = _bound_value(node)
    if value is None:
        return None
    return (value, node.kind in {"gte", "lte"})


def _bounds_conflict(
    lower_bounds: list[tuple[Fraction, bool]],
    upper_bounds: list[tuple[Fraction, bool]],
) -> bool:
    strongest_lower = max(lower_bounds, key=lambda item: (item[0], not item[1]))
    strongest_upper = min(upper_bounds, key=lambda item: (item[0], item[1]))
    if strongest_lower[0] > strongest_upper[0]:
        return True
    if strongest_lower[0] == strongest_upper[0] and (
        not strongest_lower[1] or not strongest_upper[1]
    ):
        return True
    return False


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
