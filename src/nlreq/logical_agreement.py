from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from .jsonutil import sha256_json
from .models import RequirementIRV2, SemanticNode, ValueRef
from .translator_agreement import TranslationCandidate


LOGICAL_AGREEMENT_SCHEMA_VERSION = "0.1"


class LogicalAgreementComparison(BaseModel):
    model_config = ConfigDict(extra="forbid")

    left_translator_id: str
    right_translator_id: str
    status: Literal["agreed", "conflict", "needs_review"]
    method: Literal[
        "normalized_ir_equality",
        "alpha_renaming",
        "commutative_predicate_equivalence",
        "smt_simple_predicate_equivalence",
        "bounded_trace_equivalence",
        "unsupported",
    ]
    message: str


class LogicalTranslationAgreementReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["0.1"] = LOGICAL_AGREEMENT_SCHEMA_VERSION
    requirement_id: str
    status: Literal["agreed", "conflict", "needs_review"]
    candidate_hashes: dict[str, str]
    comparisons: list[LogicalAgreementComparison] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)


def build_logical_translation_agreement_report(
    candidates: list[TranslationCandidate],
) -> LogicalTranslationAgreementReport:
    if not candidates:
        raise ValueError("logical agreement requires at least one candidate")
    requirement_id = candidates[0].requirement.requirement_id
    comparisons: list[LogicalAgreementComparison] = []
    for candidate in candidates[1:]:
        comparisons.append(_compare(candidates[0], candidate))
    if any(item.status == "conflict" for item in comparisons):
        status: Literal["agreed", "conflict", "needs_review"] = "conflict"
    elif any(item.status == "needs_review" for item in comparisons):
        status = "needs_review"
    else:
        status = "agreed"
    return LogicalTranslationAgreementReport(
        requirement_id=requirement_id,
        status=status,
        candidate_hashes={candidate.translator_id: sha256_json(candidate.requirement) for candidate in candidates},
        comparisons=comparisons,
        limitations=[
            "SMT equivalence is limited to simple predicate/comparison fragments.",
            "Bounded trace equivalence remains needs_review until trace witnesses are supplied.",
        ],
    )


def _compare(left: TranslationCandidate, right: TranslationCandidate) -> LogicalAgreementComparison:
    methods = [
        ("normalized_ir_equality", _normalized_signature),
        ("alpha_renaming", _alpha_signature),
        ("commutative_predicate_equivalence", _commutative_signature),
        ("smt_simple_predicate_equivalence", _commutative_signature),
    ]
    for method, signature in methods:
        if signature(left.requirement) == signature(right.requirement):
            return LogicalAgreementComparison(
                left_translator_id=left.translator_id,
                right_translator_id=right.translator_id,
                status="agreed",
                method=method,  # type: ignore[arg-type]
                message=f"candidates are equivalent by {method}",
            )
    if _contains_temporal(left.requirement.semantic_ir) or _contains_temporal(right.requirement.semantic_ir):
        return LogicalAgreementComparison(
            left_translator_id=left.translator_id,
            right_translator_id=right.translator_id,
            status="needs_review",
            method="bounded_trace_equivalence",
            message="temporal fragments require bounded trace equivalence witnesses",
        )
    return LogicalAgreementComparison(
        left_translator_id=left.translator_id,
        right_translator_id=right.translator_id,
        status="conflict",
        method="unsupported",
        message="no supported equivalence method proved agreement",
    )


def _normalized_signature(requirement: RequirementIRV2) -> Any:
    return _node_signature(requirement.semantic_ir, alpha=False, commutative=False, alpha_map={})


def _alpha_signature(requirement: RequirementIRV2) -> Any:
    return _node_signature(requirement.semantic_ir, alpha=True, commutative=False, alpha_map={})


def _commutative_signature(requirement: RequirementIRV2) -> Any:
    return _node_signature(requirement.semantic_ir, alpha=True, commutative=True, alpha_map={})


def _node_signature(
    node: SemanticNode,
    *,
    alpha: bool,
    commutative: bool,
    alpha_map: dict[str, str],
) -> dict[str, Any]:
    name = _node_name(node, alpha=alpha, alpha_map=alpha_map)
    target = _node_target(node, alpha=alpha, alpha_map=alpha_map)
    children = [
        _node_signature(child, alpha=alpha, commutative=commutative, alpha_map=alpha_map)
        for child in node.children
    ]
    if commutative and node.kind == "and":
        children = sorted(children, key=repr)
    args = [_value_signature(arg, alpha=alpha, alpha_map=alpha_map) for arg in node.args]
    if commutative and node.kind in {"eq", "neq"}:
        args = sorted(args, key=repr)
    return {
        "kind": node.kind,
        "name": name,
        "target": target,
        "args": args,
        "temporal_bound": node.temporal_bound.model_dump(mode="json") if node.temporal_bound else None,
        "scope": [_node_signature(child, alpha=alpha, commutative=commutative, alpha_map=alpha_map) for child in node.scope],
        "premise": _node_signature(node.premise, alpha=alpha, commutative=commutative, alpha_map=alpha_map) if node.premise else None,
        "obligation": _node_signature(node.obligation, alpha=alpha, commutative=commutative, alpha_map=alpha_map) if node.obligation else None,
        "action": _node_signature(node.action, alpha=alpha, commutative=commutative, alpha_map=alpha_map) if node.action else None,
        "must": _node_signature(node.must, alpha=alpha, commutative=commutative, alpha_map=alpha_map) if node.must else None,
        "children": children,
    }


def _node_name(node: SemanticNode, *, alpha: bool, alpha_map: dict[str, str]) -> str | None:
    if not alpha or node.name is None:
        return node.name
    if node.kind in {"forall", "exists", "entity_scope", "module_scope"}:
        return _alpha_identifier(node.name, alpha_map)
    if node.name in alpha_map and node.kind in {"action", "call", "state_ref", "transition"}:
        return alpha_map[node.name]
    return node.name


def _node_target(node: SemanticNode, *, alpha: bool, alpha_map: dict[str, str]) -> str | None:
    if not alpha or node.target is None:
        return node.target
    if node.kind in {"forall", "exists", "entity_scope", "module_scope"}:
        return _alpha_identifier(node.target, alpha_map)
    return alpha_map.get(node.target, node.target)


def _value_signature(value: ValueRef, *, alpha: bool, alpha_map: dict[str, str]) -> dict[str, Any]:
    if alpha and value.kind == "identifier":
        return {"kind": value.kind, "value": alpha_map.get(str(value.value), str(value.value))}
    return {"kind": value.kind, "value": value.value}


def _alpha_identifier(value: str, alpha_map: dict[str, str]) -> str:
    if value not in alpha_map:
        alpha_map[value] = f"id{len(alpha_map) + 1}"
    return alpha_map[value]


def _contains_temporal(node: SemanticNode) -> bool:
    if node.kind in {"within", "always", "eventually", "until", "before"}:
        return True
    return any(_contains_temporal(child) for child in [*node.scope, *node.children]) or any(
        _contains_temporal(child)
        for child in [node.premise, node.obligation, node.action, node.must]
        if child is not None
    )
