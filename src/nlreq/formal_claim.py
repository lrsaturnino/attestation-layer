from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from .controlled_semantics import ClaimClass, build_controlled_requirement_semantics_reference
from .jsonutil import canonical_json, sha256_json
from .models import EvidenceLevel, RequirementIRV2, SemanticNode, SourceSpan, TemporalBound, ValueRef


FORMAL_CLAIM_SCHEMA_VERSION = "0.1"
FORMAL_CLAIM_TOOL_VERSION = "0.1"


FormalClaimRole = Literal["scope", "premise", "action", "obligation"]
FormalClaimFragmentKind = Literal[
    "scope",
    "predicate",
    "comparison",
    "membership",
    "action",
    "success",
    "rejection_order",
    "post_state",
    "event_emission",
    "state_invariant",
    "causal_transition",
]


class FormalClaimOperand(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal["identifier", "number", "string"]
    value: str | int | float


class FormalClaimTemporalBound(BaseModel):
    model_config = ConfigDict(extra="forbid")

    value: int | float
    unit: Literal["second", "minute", "hour", "day", "block"]


class FormalClaimFragment(BaseModel):
    model_config = ConfigDict(extra="forbid")

    fragment_id: str
    source_node_id: str
    role: FormalClaimRole
    kind: FormalClaimFragmentKind
    canonical: str
    predicate: str | None = None
    operator: Literal["eq", "neq", "lt", "lte", "gt", "gte", "in"] | None = None
    operands: list[FormalClaimOperand] = Field(default_factory=list)
    temporal_bound: FormalClaimTemporalBound | None = None
    source_spans: list[SourceSpan] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class FormalClaimUnsupportedFragment(BaseModel):
    model_config = ConfigDict(extra="forbid")

    node_id: str
    kind: str
    reason: str
    source_spans: list[SourceSpan] = Field(default_factory=list)
    next_actions: list[str] = Field(default_factory=list)


class FormalClaimSemanticsRule(BaseModel):
    model_config = ConfigDict(extra="forbid")

    rule_id: str
    claim_class: ClaimClass | None = None
    text: str


class FormalClaim(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["0.1"] = FORMAL_CLAIM_SCHEMA_VERSION
    claim_id: str
    requirement_id: str
    source_ir_version: Literal["0.2"]
    source_ir_hash: str
    claim_class: ClaimClass
    semantics_profile: str
    scope: list[FormalClaimFragment] = Field(default_factory=list)
    premises: list[FormalClaimFragment] = Field(default_factory=list)
    action: FormalClaimFragment
    obligations: list[FormalClaimFragment] = Field(default_factory=list)
    canonical_formula: str
    source_spans: list[SourceSpan] = Field(default_factory=list)
    node_map: dict[str, str] = Field(default_factory=dict)
    required_evidence: list[EvidenceLevel] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class FormalClaimLoweringReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["0.1"] = FORMAL_CLAIM_SCHEMA_VERSION
    requirement_id: str
    result: Literal["lowered", "refused", "needs_review"]
    source_ir_hash: str
    formal_claim: FormalClaim | None = None
    unsupported_fragments: list[FormalClaimUnsupportedFragment] = Field(default_factory=list)
    semantics_rules: list[FormalClaimSemanticsRule] = Field(default_factory=list)
    refusal_code: str | None = None
    input_hashes: dict[str, str] = Field(default_factory=dict)
    tool: str = "nlreq.formal_claim"
    tool_version: str = FORMAL_CLAIM_TOOL_VERSION


def build_formal_claim(requirement: RequirementIRV2) -> FormalClaimLoweringReport:
    source_ir_hash = sha256_json(requirement)
    claim_class = _claim_class(requirement)
    rules = _semantics_rules(claim_class)
    unsupported = _unsupported_fragments(requirement.semantic_ir)
    if claim_class is None:
        unsupported.append(
            FormalClaimUnsupportedFragment(
                node_id=requirement.semantic_ir.node_id,
                kind=requirement.semantic_ir.kind,
                reason="semantic root does not declare a supported requirement_class",
                source_spans=requirement.semantic_ir.source_spans,
                next_actions=["Use a supported DSL v3 requirement class."],
            )
        )
    if unsupported or claim_class is None:
        return FormalClaimLoweringReport(
            requirement_id=requirement.requirement_id,
            result="refused",
            source_ir_hash=source_ir_hash,
            unsupported_fragments=unsupported,
            semantics_rules=rules,
            refusal_code="NLR-SEMANTIC-UNSUPPORTED",
            input_hashes={"requirement_ir": source_ir_hash},
        )

    scope = [_scope_fragment(node) for node in requirement.semantic_ir.scope]
    premises = _premise_fragments(requirement.semantic_ir.premise)
    action = _action_fragment(requirement.semantic_ir.obligation.action)
    obligations = _obligation_fragments(requirement.semantic_ir.obligation.must)
    fragments = [*scope, *premises, action, *obligations]
    formula = _canonical_formula(scope, premises, action, obligations)
    claim = FormalClaim(
        claim_id=f"FC-{requirement.requirement_id}",
        requirement_id=requirement.requirement_id,
        source_ir_version=requirement.ir_version,
        source_ir_hash=source_ir_hash,
        claim_class=claim_class,
        semantics_profile=f"dsl-v3/{claim_class}",
        scope=scope,
        premises=premises,
        action=action,
        obligations=obligations,
        canonical_formula=formula,
        source_spans=requirement.semantic_ir.source_spans,
        node_map={fragment.source_node_id: fragment.fragment_id for fragment in fragments},
        required_evidence=_required_evidence_for_claim_class(claim_class),
        metadata={"canonical_signature_hash": sha256_json(_claim_signature_parts(scope, premises, action, obligations))},
    )
    return FormalClaimLoweringReport(
        requirement_id=requirement.requirement_id,
        result="lowered",
        source_ir_hash=source_ir_hash,
        formal_claim=claim,
        semantics_rules=rules,
        input_hashes={"requirement_ir": source_ir_hash, "formal_claim": sha256_json(claim)},
    )


def formal_claim_signature(
    claim: FormalClaim,
    *,
    alpha_identifiers: bool = False,
    commutative: bool = False,
) -> str:
    alpha_map: dict[str, str] = {}
    payload = {
        "claim_class": claim.claim_class,
        "scope": [
            _fragment_signature(fragment, alpha_map=alpha_map, alpha=alpha_identifiers)
            for fragment in claim.scope
        ],
        "premises": [
            _fragment_signature(fragment, alpha_map=alpha_map, alpha=alpha_identifiers)
            for fragment in claim.premises
        ],
        "action": _fragment_signature(claim.action, alpha_map=alpha_map, alpha=alpha_identifiers),
        "obligations": [
            _fragment_signature(fragment, alpha_map=alpha_map, alpha=alpha_identifiers)
            for fragment in claim.obligations
        ],
    }
    if commutative:
        payload["premises"] = sorted(payload["premises"], key=repr)
        payload["obligations"] = sorted(payload["obligations"], key=repr)
    return canonical_json(payload)


def _claim_class(requirement: RequirementIRV2) -> ClaimClass | None:
    raw = requirement.semantic_ir.metadata.get("requirement_class")
    supported = {item.claim_class for item in build_controlled_requirement_semantics_reference().claim_classes}
    return raw if raw in supported else None  # type: ignore[return-value]


def _semantics_rules(claim_class: ClaimClass | None) -> list[FormalClaimSemanticsRule]:
    reference = build_controlled_requirement_semantics_reference()
    rules = [
        FormalClaimSemanticsRule(
            rule_id="no-partial-unsupported-lowering",
            text="Unsupported semantic fragments produce refused formal-claim lowering.",
        ),
        FormalClaimSemanticsRule(
            rule_id="source-span-preservation",
            text="Every formal claim fragment retains source spans back to controlled text.",
        ),
    ]
    if claim_class is not None:
        claim_semantics = next(item for item in reference.claim_classes if item.claim_class == claim_class)
        rules.append(
            FormalClaimSemanticsRule(
                rule_id=f"claim-class.{claim_class}",
                claim_class=claim_class,
                text=claim_semantics.canonical_rule,
            )
        )
    return rules


def _required_evidence_for_claim_class(claim_class: ClaimClass) -> list[EvidenceLevel]:
    reference = build_controlled_requirement_semantics_reference()
    return next(item.required_evidence for item in reference.claim_classes if item.claim_class == claim_class)


def _unsupported_fragments(node: SemanticNode) -> list[FormalClaimUnsupportedFragment]:
    supported = {
        "rule",
        "forall",
        "and",
        "predicate",
        "membership",
        "eq",
        "neq",
        "lt",
        "lte",
        "gt",
        "gte",
        "action_obligation",
        "action",
        "before",
        "state_ref",
        "post_state",
        "within",
        "event",
        "transition",
    }
    result: list[FormalClaimUnsupportedFragment] = []
    for item in _walk_nodes(node):
        if item.kind not in supported:
            result.append(
                FormalClaimUnsupportedFragment(
                    node_id=item.node_id,
                    kind=item.kind,
                    reason="semantic node kind is not supported by formal claim IR lowering",
                    source_spans=item.source_spans,
                    next_actions=["Rewrite the requirement using a supported controlled construct."],
                )
            )
    return result


def _scope_fragment(node: SemanticNode) -> FormalClaimFragment:
    return FormalClaimFragment(
        fragment_id=f"formal.{node.node_id}",
        source_node_id=node.node_id,
        role="scope",
        kind="scope",
        canonical=f"forall({node.name}:{node.target})",
        operands=[FormalClaimOperand(kind="identifier", value=node.name or "")],
        source_spans=node.source_spans,
        metadata={"target": node.target} if node.target else {},
    )


def _premise_fragments(node: SemanticNode | None) -> list[FormalClaimFragment]:
    if node is None:
        return []
    if node.kind == "and":
        return [_premise_fragment(child) for child in node.children]
    return [_premise_fragment(node)]


def _premise_fragment(node: SemanticNode) -> FormalClaimFragment:
    if node.kind == "predicate":
        operands = [_operand(arg) for arg in node.args]
        return FormalClaimFragment(
            fragment_id=f"formal.{node.node_id}",
            source_node_id=node.node_id,
            role="premise",
            kind="predicate",
            canonical=f"{node.name}({_operands_canonical(operands)})",
            predicate=node.name,
            operands=operands,
            source_spans=node.source_spans,
        )
    if node.kind in {"eq", "neq", "lt", "lte", "gt", "gte"}:
        operands = [_operand(arg) for arg in node.args]
        return FormalClaimFragment(
            fragment_id=f"formal.{node.node_id}",
            source_node_id=node.node_id,
            role="premise",
            kind="comparison",
            canonical=f"{node.kind}({_operands_canonical(operands)})",
            operator=node.kind,  # type: ignore[arg-type]
            operands=operands,
            source_spans=node.source_spans,
        )
    if node.kind == "membership":
        operands = [_operand(arg) for arg in node.args]
        return FormalClaimFragment(
            fragment_id=f"formal.{node.node_id}",
            source_node_id=node.node_id,
            role="premise",
            kind="membership",
            canonical=f"in({_operands_canonical(operands)})",
            operator="in",
            operands=operands,
            source_spans=node.source_spans,
        )
    raise ValueError(f"unsupported premise node for formal claim lowering: {node.kind}")


def _action_fragment(node: SemanticNode | None) -> FormalClaimFragment:
    if node is None:
        raise ValueError("formal claim requires action node")
    return FormalClaimFragment(
        fragment_id=f"formal.{node.node_id}",
        source_node_id=node.node_id,
        role="action",
        kind="action",
        canonical=f"action({node.name})",
        operands=[FormalClaimOperand(kind="identifier", value=node.name or "")],
        source_spans=node.source_spans,
    )


def _obligation_fragments(node: SemanticNode | None) -> list[FormalClaimFragment]:
    if node is None:
        return []
    if node.kind == "and":
        return [_obligation_fragment(child) for child in node.children]
    return [_obligation_fragment(node)]


def _obligation_fragment(node: SemanticNode) -> FormalClaimFragment:
    if node.kind == "predicate" and node.name == "succeeds":
        operands = [_operand(arg) for arg in node.args]
        return FormalClaimFragment(
            fragment_id=f"formal.{node.node_id}",
            source_node_id=node.node_id,
            role="obligation",
            kind="success",
            canonical=f"succeeds({_operands_canonical(operands)})",
            predicate="succeeds",
            operands=operands,
            source_spans=node.source_spans,
        )
    if node.kind == "before":
        reject = node.children[0] if node.children else None
        before = node.children[1] if len(node.children) > 1 else None
        action = reject.args[0].value if reject is not None and reject.args else "unknown"
        state = before.name if before is not None else "unknown"
        return FormalClaimFragment(
            fragment_id=f"formal.{node.node_id}",
            source_node_id=node.node_id,
            role="obligation",
            kind="rejection_order",
            canonical=f"rejects_before({action},{state})",
            predicate="rejects_before",
            operands=[
                FormalClaimOperand(kind="identifier", value=str(action)),
                FormalClaimOperand(kind="identifier", value=str(state)),
            ],
            source_spans=node.source_spans,
        )
    if node.kind == "post_state":
        operand = _operand(node.value) if node.value is not None else FormalClaimOperand(kind="identifier", value="unknown")
        return FormalClaimFragment(
            fragment_id=f"formal.{node.node_id}",
            source_node_id=node.node_id,
            role="obligation",
            kind="post_state",
            canonical=f"post_state({node.name},{_operand_canonical(operand)})",
            predicate="post_state",
            operands=[FormalClaimOperand(kind="identifier", value=node.name or ""), operand],
            source_spans=node.source_spans,
        )
    if node.kind == "within":
        child = node.children[0] if node.children else None
        temporal_bound = _temporal_bound(node.temporal_bound)
        if child is not None and child.kind == "event":
            return FormalClaimFragment(
                fragment_id=f"formal.{node.node_id}",
                source_node_id=node.node_id,
                role="obligation",
                kind="event_emission",
                canonical=f"within(event({child.name}),{temporal_bound.value},{temporal_bound.unit})",
                predicate="within_event",
                operands=[FormalClaimOperand(kind="identifier", value=child.name or "")],
                temporal_bound=temporal_bound,
                source_spans=node.source_spans,
            )
        if child is not None and child.kind == "transition":
            source_module = str(child.metadata.get("source_module", "unknown"))
            target_module = str(child.metadata.get("target_module", "unknown"))
            return FormalClaimFragment(
                fragment_id=f"formal.{node.node_id}",
                source_node_id=node.node_id,
                role="obligation",
                kind="causal_transition",
                canonical=(
                    f"within(transition({source_module},{target_module},{child.name}),"
                    f"{temporal_bound.value},{temporal_bound.unit})"
                ),
                predicate="within_transition",
                operands=[
                    FormalClaimOperand(kind="identifier", value=source_module),
                    FormalClaimOperand(kind="identifier", value=target_module),
                    FormalClaimOperand(kind="identifier", value=child.name or ""),
                ],
                temporal_bound=temporal_bound,
                source_spans=node.source_spans,
            )
    if node.kind in {"eq", "neq", "lt", "lte", "gt", "gte"}:
        operands = [_operand(arg) for arg in node.args]
        return FormalClaimFragment(
            fragment_id=f"formal.{node.node_id}",
            source_node_id=node.node_id,
            role="obligation",
            kind="state_invariant",
            canonical=f"invariant({node.kind}({_operands_canonical(operands)}))",
            operator=node.kind,  # type: ignore[arg-type]
            operands=operands,
            source_spans=node.source_spans,
        )
    raise ValueError(f"unsupported obligation node for formal claim lowering: {node.kind}")


def _canonical_formula(
    scope: list[FormalClaimFragment],
    premises: list[FormalClaimFragment],
    action: FormalClaimFragment,
    obligations: list[FormalClaimFragment],
) -> str:
    scope_text = " and ".join(fragment.canonical for fragment in scope) or "true"
    premise_text = " and ".join(fragment.canonical for fragment in premises) or "true"
    obligation_text = " and ".join(fragment.canonical for fragment in obligations) or "true"
    return f"{scope_text}: ({premise_text}) => ({action.canonical} requires {obligation_text})"


def _claim_signature_parts(
    scope: list[FormalClaimFragment],
    premises: list[FormalClaimFragment],
    action: FormalClaimFragment,
    obligations: list[FormalClaimFragment],
) -> dict[str, Any]:
    return {
        "scope": [fragment.canonical for fragment in scope],
        "premises": [fragment.canonical for fragment in premises],
        "action": action.canonical,
        "obligations": [fragment.canonical for fragment in obligations],
    }


def _fragment_signature(
    fragment: FormalClaimFragment,
    *,
    alpha_map: dict[str, str],
    alpha: bool,
) -> dict[str, Any]:
    operands = [
        {"kind": operand.kind, "value": _alpha_value(str(operand.value), alpha_map) if alpha and operand.kind == "identifier" else operand.value}
        for operand in fragment.operands
    ]
    if fragment.operator in {"eq", "neq"}:
        operands = sorted(operands, key=repr)
    return {
        "role": fragment.role,
        "kind": fragment.kind,
        "predicate": fragment.predicate,
        "operator": fragment.operator,
        "operands": operands,
        "temporal_bound": fragment.temporal_bound.model_dump(mode="json") if fragment.temporal_bound else None,
        "metadata": fragment.metadata,
    }


def _alpha_value(value: str, alpha_map: dict[str, str]) -> str:
    if value not in alpha_map:
        alpha_map[value] = f"id{len(alpha_map) + 1}"
    return alpha_map[value]


def _operand(value: ValueRef | None) -> FormalClaimOperand:
    if value is None:
        return FormalClaimOperand(kind="identifier", value="unknown")
    return FormalClaimOperand(kind=value.kind, value=value.value)


def _temporal_bound(value: TemporalBound | None) -> FormalClaimTemporalBound:
    if value is None:
        raise ValueError("temporal formal claim fragment requires a temporal bound")
    return FormalClaimTemporalBound(value=value.value, unit=value.unit)


def _operands_canonical(operands: list[FormalClaimOperand]) -> str:
    return ",".join(_operand_canonical(operand) for operand in operands)


def _operand_canonical(operand: FormalClaimOperand) -> str:
    if operand.kind == "string":
        return repr(operand.value)
    return str(operand.value)


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

