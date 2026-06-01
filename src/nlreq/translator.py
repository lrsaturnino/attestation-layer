from __future__ import annotations

import difflib
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from .dsl_v2 import DslV2Parser
from .jsonutil import canonical_json, sha256_json, sha256_text
from .models import Approval, RequirementIRV2, SemanticNode, SourceSpan


DRAFT_SCHEMA_VERSION = "0.1"
LOWERING_SCHEMA_VERSION = "0.1"
TRANSLATOR_VERSION = "0.1"


class DraftingMetadata(BaseModel):
    model_config = ConfigDict(extra="forbid")

    method: Literal["manual", "llm"] = "manual"
    model: str | None = None
    prompt_hash: str | None = None
    prompt: str | None = None
    tool: str = "nlreq.translator"
    tool_version: str = TRANSLATOR_VERSION
    timestamp: str
    metadata: dict[str, str] = Field(default_factory=dict)


class ControlledDraft(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["0.1"] = DRAFT_SCHEMA_VERSION
    original_text: str
    suggested_text: str
    diff: str
    metadata: DraftingMetadata
    approval: Approval = Field(default_factory=lambda: Approval(status="needs_review"))


class LoweringDiagnostic(BaseModel):
    model_config = ConfigDict(extra="forbid")

    node_id: str
    kind: str
    reason: str
    source_spans: list[SourceSpan] = Field(default_factory=list)


class TemporalBoundRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    node_id: str
    value: int | float
    unit: str


class LoweredFormalArtifact(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["0.1"] = LOWERING_SCHEMA_VERSION
    requirement_id: str
    source_ir_version: Literal["0.2"]
    source_ir_hash: str
    target: Literal["tla"] = "tla"
    translator: str = "nlreq.translator.tla_skeleton"
    translator_version: str = TRANSLATOR_VERSION
    status: Literal["lowered", "refused"]
    content: str | None = None
    content_hash: str | None = None
    temporal_bounds: list[TemporalBoundRecord] = Field(default_factory=list)
    diagnostics: list[LoweringDiagnostic] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


def create_controlled_draft(
    *,
    original_text: str,
    suggested_text: str,
    timestamp: str,
    method: Literal["manual", "llm"] = "manual",
    model: str | None = None,
    prompt: str | None = None,
    metadata: dict[str, str] | None = None,
) -> ControlledDraft:
    return ControlledDraft(
        original_text=original_text,
        suggested_text=suggested_text,
        diff=_unified_diff(original_text, suggested_text),
        metadata=DraftingMetadata(
            method=method,
            model=model,
            prompt=prompt,
            prompt_hash=sha256_text(prompt) if prompt is not None else None,
            timestamp=timestamp,
            metadata=metadata or {},
        ),
    )


def approve_controlled_draft(
    draft: ControlledDraft,
    *,
    approved_by: str,
    approved_at: str,
) -> ControlledDraft:
    return draft.model_copy(
        update={
            "approval": Approval(
                status="approved",
                approved_by=approved_by,
                approved_at=approved_at,
            )
        }
    )


def parse_approved_draft_ir_v2(
    draft: ControlledDraft,
    *,
    requirement_id: str,
    title: str,
) -> RequirementIRV2:
    if draft.approval.status != "approved":
        raise ValueError("controlled draft must be approved before parsing")
    ir = DslV2Parser().parse_ir(
        draft.suggested_text,
        requirement_id=requirement_id,
        title=title,
    )
    return ir.model_copy(
        update={
            "source": ir.source.model_copy(
                update={
                    "original_text": draft.original_text,
                    "controlled_text_approval": draft.approval,
                }
            )
        }
    )


def lower_ir_v2_to_tla(ir: RequirementIRV2) -> LoweredFormalArtifact:
    diagnostics = _unsupported_nodes(ir.semantic_ir)
    temporal_bounds = _temporal_bounds(ir.semantic_ir)
    source_ir_hash = sha256_json(ir)
    if diagnostics:
        return LoweredFormalArtifact(
            requirement_id=ir.requirement_id,
            source_ir_version=ir.ir_version,
            source_ir_hash=source_ir_hash,
            status="refused",
            temporal_bounds=temporal_bounds,
            diagnostics=diagnostics,
        )

    content = _tla_skeleton(ir, temporal_bounds)
    return LoweredFormalArtifact(
        requirement_id=ir.requirement_id,
        source_ir_version=ir.ir_version,
        source_ir_hash=source_ir_hash,
        status="lowered",
        content=content,
        content_hash=sha256_text(content),
        temporal_bounds=temporal_bounds,
        metadata={"evidence": "not_checked"},
    )


def _unified_diff(original: str, suggested: str) -> str:
    return "".join(
        difflib.unified_diff(
            original.splitlines(keepends=True),
            suggested.splitlines(keepends=True),
            fromfile="original",
            tofile="suggested",
        )
    )


def _unsupported_nodes(node: SemanticNode) -> list[LoweringDiagnostic]:
    supported = {
        "rule",
        "forall",
        "and",
        "predicate",
        "lte",
        "gte",
        "action_obligation",
        "action",
        "within",
        "event",
    }
    diagnostics: list[LoweringDiagnostic] = []
    for item in _walk_nodes(node):
        if item.kind not in supported:
            diagnostics.append(
                LoweringDiagnostic(
                    node_id=item.node_id,
                    kind=item.kind,
                    reason="node kind is not supported by TLA skeleton lowering",
                    source_spans=item.source_spans,
                )
            )
    return diagnostics


def _temporal_bounds(node: SemanticNode) -> list[TemporalBoundRecord]:
    bounds: list[TemporalBoundRecord] = []
    for item in _walk_nodes(node):
        if item.kind == "within" and item.temporal_bound is not None:
            bounds.append(
                TemporalBoundRecord(
                    node_id=item.node_id,
                    value=item.temporal_bound.value,
                    unit=item.temporal_bound.unit,
                )
            )
    return bounds


def _tla_skeleton(ir: RequirementIRV2, temporal_bounds: list[TemporalBoundRecord]) -> str:
    root = ir.semantic_ir
    module_name = _module_name(ir.requirement_id)
    premises = _node_expr(root.premise) if root.premise else "TRUE"
    obligation = _node_expr(root.obligation) if root.obligation else "TRUE"
    bounds = canonical_json([bound.model_dump(mode="json") for bound in temporal_bounds]).strip()
    return (
        f"---- MODULE {module_name} ----\n"
        "EXTENDS Naturals, TLC\n\n"
        f"\\* Generated by nlreq translator {TRANSLATOR_VERSION}; not model-checked evidence.\n"
        f"\\* Requirement: {ir.requirement_id}\n"
        f"\\* Temporal bounds: {bounds}\n\n"
        f"Premise == {premises}\n\n"
        f"Obligation == {obligation}\n\n"
        "RequirementHolds == Premise => Obligation\n\n"
        "====\n"
    )


def _node_expr(node: SemanticNode | None) -> str:
    if node is None:
        return "TRUE"
    if node.kind == "and":
        if not node.children:
            return "TRUE"
        return " /\\ ".join(f"({_node_expr(child)})" for child in node.children)
    if node.kind == "predicate":
        args = ", ".join(str(arg.value) for arg in node.args)
        return f"{_safe_name(node.name or 'predicate')}({args})"
    if node.kind in {"lte", "gte"}:
        if len(node.args) < 2:
            return "FALSE"
        operator = "<=" if node.kind == "lte" else ">="
        return f"{node.args[0].value} {operator} {node.args[1].value}"
    if node.kind == "action_obligation":
        return _node_expr(node.must)
    if node.kind == "within":
        event = _node_expr(node.children[0]) if node.children else "TRUE"
        if node.temporal_bound is None:
            return event
        return (
            f"Within({event}, {node.temporal_bound.value}, "
            f"\"{node.temporal_bound.unit}\")"
        )
    if node.kind == "event":
        return f"Event_{_safe_name(node.name or 'event')}"
    return f"Unsupported_{_safe_name(node.kind)}"


def _module_name(requirement_id: str) -> str:
    return "Req_" + _safe_name(requirement_id)


def _safe_name(value: str) -> str:
    cleaned = "".join(char if char.isalnum() else "_" for char in value)
    if not cleaned:
        return "Unnamed"
    if cleaned[0].isdigit():
        return "_" + cleaned
    return cleaned


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
