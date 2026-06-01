from __future__ import annotations

import json
from typing import Any

from .jsonutil import sha256_json
from .models import (
    IR_V1_VERSION,
    IR_V2_VERSION,
    Claim,
    ExpectedResult,
    MigrationDiffEntry,
    Predicate,
    RequirementIR,
    RequirementIRMigrationRecord,
    RequirementIRV2,
    SemanticNode,
    SemanticProvenance,
    SourceSpan,
    ValueRef,
)


MIGRATION_TOOL = "nlreq.phase19.flat-to-compositional"
DEFAULT_MIGRATION_TOOL_VERSION = "0.1"
DEFAULT_MIGRATION_TIMESTAMP = "2026-06-01T00:00:00Z"


RequirementIRDocument = RequirementIR | RequirementIRV2


def validate_requirement_ir_json(text: str) -> RequirementIRDocument:
    return validate_requirement_ir_data(json.loads(text))


def validate_requirement_ir_data(data: Any) -> RequirementIRDocument:
    if not isinstance(data, dict):
        raise ValueError("IR document must be a JSON object")
    version = data.get("ir_version", IR_V1_VERSION)
    if version == IR_V1_VERSION:
        return RequirementIR.model_validate(data)
    if version == IR_V2_VERSION:
        return RequirementIRV2.model_validate(data)
    raise ValueError(f"unsupported ir_version: {version}")


def migrate_requirement_ir_v1_to_v2(
    ir: RequirementIR,
    *,
    tool_version: str = DEFAULT_MIGRATION_TOOL_VERSION,
    timestamp: str = DEFAULT_MIGRATION_TIMESTAMP,
) -> tuple[RequirementIRV2, RequirementIRMigrationRecord]:
    source_ir_hash = sha256_json(ir)
    semantic_ir = _rule_node(ir, tool_version=tool_version, timestamp=timestamp)
    migrated = RequirementIRV2(
        requirement_id=ir.requirement_id,
        title=ir.title,
        source=ir.source,
        semantic_ir=semantic_ir,
        bindings=ir.bindings,
        assumptions=ir.assumptions,
        required_evidence=ir.required_evidence,
    )
    target_ir_hash = sha256_json(migrated)
    record = RequirementIRMigrationRecord(
        migration_id=f"MIGRATE-{ir.requirement_id}-0.1-to-0.2",
        source_ir_version=IR_V1_VERSION,
        target_ir_version=IR_V2_VERSION,
        source_ir_hash=source_ir_hash,
        target_ir_hash=target_ir_hash,
        tool=MIGRATION_TOOL,
        tool_version=tool_version,
        timestamp=timestamp,
        diff=[
            MigrationDiffEntry(
                path="/claim/forall",
                change="moved",
                detail="flat forall bindings migrated to semantic_ir.scope nodes",
            ),
            MigrationDiffEntry(
                path="/claim/condition",
                change="moved",
                detail="flat condition list migrated to semantic_ir.premise",
            ),
            MigrationDiffEntry(
                path="/claim/action",
                change="moved",
                detail="flat action migrated to semantic_ir.obligation.action",
            ),
            MigrationDiffEntry(
                path="/claim/expected",
                change="moved",
                detail="flat expected result migrated to semantic_ir.obligation.must",
            ),
            MigrationDiffEntry(
                path="/semantic_ir",
                change="added",
                detail="compositional semantic tree added as the authoritative 0.2 IR spine",
            ),
        ],
    )
    return migrated, record


def legacy_projection_from_v2(ir: RequirementIRV2) -> RequirementIR:
    rule = ir.semantic_ir
    if rule.kind != "rule":
        raise ValueError("legacy projection requires rule root")
    claim_kind = rule.metadata.get("legacy_claim_kind")
    if not isinstance(claim_kind, str):
        raise ValueError("legacy projection requires legacy_claim_kind metadata")
    forall = _project_scope(rule.scope)
    condition = _project_premise(rule.premise)
    action, expected = _project_obligation(rule.obligation)
    return RequirementIR(
        requirement_id=ir.requirement_id,
        title=ir.title,
        source=ir.source,
        claim=Claim(
            kind=claim_kind,  # type: ignore[arg-type]
            forall=forall,
            condition=condition,
            action=action,
            expected=expected,
        ),
        bindings=ir.bindings,
        assumptions=ir.assumptions,
        required_evidence=ir.required_evidence,
    )


def _rule_node(ir: RequirementIR, *, tool_version: str, timestamp: str) -> SemanticNode:
    return SemanticNode(
        node_id="rule.root",
        kind="rule",
        provenance=_provenance("claim", tool_version=tool_version, timestamp=timestamp),
        confidence="migration_inferred",
        metadata={"legacy_claim_kind": ir.claim.kind},
        scope=[
            _scope_node(item, index, tool_version=tool_version, timestamp=timestamp)
            for index, item in enumerate(ir.claim.forall)
        ],
        premise=_premise_node(
            ir.claim.condition,
            tool_version=tool_version,
            timestamp=timestamp,
        ),
        obligation=_obligation_node(
            ir,
            tool_version=tool_version,
            timestamp=timestamp,
        ),
    )


def _scope_node(
    item: dict[str, str],
    index: int,
    *,
    tool_version: str,
    timestamp: str,
) -> SemanticNode:
    return SemanticNode(
        node_id=f"scope.{index}",
        kind="forall",
        provenance=_provenance(
            f"claim.forall[{index}]",
            tool_version=tool_version,
            timestamp=timestamp,
        ),
        confidence="migration_inferred",
        name=item["name"],
        target=item.get("type"),
    )


def _premise_node(
    predicates: list[Predicate],
    *,
    tool_version: str,
    timestamp: str,
) -> SemanticNode:
    return SemanticNode(
        node_id="premise.root",
        kind="and",
        provenance=_provenance("claim.condition", tool_version=tool_version, timestamp=timestamp),
        confidence="migration_inferred",
        children=[
            _predicate_node(
                predicate,
                index,
                tool_version=tool_version,
                timestamp=timestamp,
            )
            for index, predicate in enumerate(predicates)
        ],
    )


def _predicate_node(
    predicate: Predicate,
    index: int,
    *,
    tool_version: str,
    timestamp: str,
) -> SemanticNode:
    return SemanticNode(
        node_id=f"premise.{index}",
        kind="predicate",
        source_spans=[predicate.source_span],
        provenance=_provenance(
            f"claim.condition[{index}]",
            tool_version=tool_version,
            timestamp=timestamp,
        ),
        confidence="migration_inferred",
        name=predicate.op,
        args=predicate.args,
    )


def _obligation_node(
    ir: RequirementIR,
    *,
    tool_version: str,
    timestamp: str,
) -> SemanticNode:
    return SemanticNode(
        node_id="obligation.root",
        kind="action_obligation",
        source_spans=_action_spans(ir),
        provenance=_provenance("claim", tool_version=tool_version, timestamp=timestamp),
        confidence="migration_inferred",
        action=SemanticNode(
            node_id="obligation.action",
            kind="action",
            source_spans=_action_spans(ir),
            provenance=_provenance(
                "claim.action",
                tool_version=tool_version,
                timestamp=timestamp,
            ),
            confidence="migration_inferred",
            name=ir.claim.action,
        ),
        must=_expected_node(
            ir.claim.expected,
            tool_version=tool_version,
            timestamp=timestamp,
        ),
    )


def _expected_node(
    expected: ExpectedResult,
    *,
    tool_version: str,
    timestamp: str,
) -> SemanticNode:
    common = {
        "source_spans": [expected.source_span],
        "provenance": _provenance(
            "claim.expected",
            tool_version=tool_version,
            timestamp=timestamp,
        ),
        "confidence": "migration_inferred",
    }
    if expected.kind == "rejected_before":
        if expected.target is None:
            raise ValueError("rejected_before migration requires target")
        return SemanticNode(
            node_id="obligation.must",
            kind="before",
            **common,
            children=[
                SemanticNode(
                    node_id="obligation.must.rejected",
                    kind="predicate",
                    **common,
                    name="rejected",
                ),
                SemanticNode(
                    node_id="obligation.must.before",
                    kind="transition",
                    **common,
                    name=expected.target,
                ),
            ],
        )
    if expected.kind in {"rejected", "succeed"}:
        return SemanticNode(
            node_id="obligation.must",
            kind="predicate",
            **common,
            name=expected.kind,
        )
    if expected.kind == "emit":
        if expected.target is None:
            raise ValueError("emit migration requires target")
        return SemanticNode(
            node_id="obligation.must",
            kind="event",
            **common,
            name=expected.target,
        )
    if expected.kind == "not_change":
        if expected.target is None:
            raise ValueError("not_change migration requires target")
        return SemanticNode(
            node_id="obligation.must",
            kind="invariant",
            **common,
            name="not_change",
            target=expected.target,
        )
    if expected.kind in {"set", "increase", "decrease"}:
        if expected.target is None:
            raise ValueError(f"{expected.kind} migration requires target")
        return SemanticNode(
            node_id="obligation.must",
            kind="state_delta",
            **common,
            name=expected.kind,
            target=expected.target,
            value=expected.value,
        )
    raise ValueError(f"unsupported expected result for migration: {expected.kind}")


def _provenance(
    derived_from: str,
    *,
    tool_version: str,
    timestamp: str,
) -> SemanticProvenance:
    return SemanticProvenance(
        source_document="controlled_requirement",
        derived_from=[derived_from],
        method="migration",
        tool=MIGRATION_TOOL,
        tool_version=tool_version,
        timestamp=timestamp,
    )


def _action_spans(ir: RequirementIR) -> list[SourceSpan]:
    needle = f"then {ir.claim.action} must"
    start = ir.source.controlled_text.find(needle)
    if start < 0:
        return []
    start_char = start + len("then ")
    end_char = start_char + len(ir.claim.action)
    return [
        SourceSpan(
            document="controlled_requirement",
            start_char=start_char,
            end_char=end_char,
            text=ir.source.controlled_text[start_char:end_char],
        )
    ]


def _project_scope(scope: list[SemanticNode]) -> list[dict[str, str]]:
    projected: list[dict[str, str]] = []
    for node in scope:
        if node.kind != "forall" or not node.name or not node.target:
            raise ValueError("legacy projection supports only forall scope nodes")
        projected.append({"name": node.name, "type": node.target})
    return projected


def _project_premise(premise: SemanticNode | None) -> list[Predicate]:
    if premise is None or premise.kind != "and":
        raise ValueError("legacy projection requires an and premise")
    return [_project_predicate(child) for child in premise.children]


def _project_predicate(node: SemanticNode) -> Predicate:
    if node.kind != "predicate" or not node.name:
        raise ValueError("legacy projection supports only predicate premise children")
    return Predicate(
        op=node.name,  # type: ignore[arg-type]
        args=node.args,
        source_span=_single_source_span(node),
    )


def _project_obligation(obligation: SemanticNode | None) -> tuple[str, ExpectedResult]:
    if obligation is None or obligation.kind != "action_obligation":
        raise ValueError("legacy projection requires an action_obligation")
    if obligation.action is None or obligation.action.kind != "action" or not obligation.action.name:
        raise ValueError("legacy projection requires an action node")
    if obligation.must is None:
        raise ValueError("legacy projection requires a must node")
    return obligation.action.name, _project_expected(obligation.must)


def _project_expected(node: SemanticNode) -> ExpectedResult:
    source_span = _single_source_span(node)
    if node.kind == "before":
        if len(node.children) != 2:
            raise ValueError("legacy rejected_before projection requires two before children")
        rejected, transition = node.children
        if rejected.kind != "predicate" or rejected.name != "rejected":
            raise ValueError("legacy rejected_before projection requires rejected predicate")
        if transition.kind != "transition" or not transition.name:
            raise ValueError("legacy rejected_before projection requires transition target")
        return ExpectedResult(
            kind="rejected_before",
            target=transition.name,
            source_span=source_span,
        )
    if node.kind == "predicate" and node.name in {"rejected", "succeed"}:
        return ExpectedResult(
            kind=node.name,  # type: ignore[arg-type]
            source_span=source_span,
        )
    if node.kind == "event" and node.name:
        return ExpectedResult(kind="emit", target=node.name, source_span=source_span)
    if node.kind == "invariant" and node.name == "not_change" and node.target:
        return ExpectedResult(kind="not_change", target=node.target, source_span=source_span)
    if node.kind == "state_delta" and node.name in {"set", "increase", "decrease"} and node.target:
        return ExpectedResult(
            kind=node.name,  # type: ignore[arg-type]
            target=node.target,
            value=node.value,
            source_span=source_span,
        )
    raise ValueError(f"cannot project {node.kind} node to legacy expected result")


def _single_source_span(node: SemanticNode) -> SourceSpan:
    if len(node.source_spans) != 1:
        raise ValueError("legacy projection requires exactly one source span per projected node")
    return node.source_spans[0]
