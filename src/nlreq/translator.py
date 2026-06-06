from __future__ import annotations

import difflib
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from .dsl_v2 import DslV2Parser
from .formal_lowering import (
    FORMAL_LOWERING_VERSION,
    lower_authorization_precondition_tla,
    lower_state_postcondition_tla,
    validate_authorization_precondition_shape,
    validate_state_postcondition_shape,
)
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


# Claim classes whose obligation is a numeric/state invariant the legacy skeleton can only lower
# vacuously, so they must refuse at translation rather than emit a misleading status="lowered"
# artifact. The skeleton stubs every identifier to ``name == 0`` and renders the obligation
# comparison over those stubs (e.g. ``keep collateral >= 100`` becomes a check of the constant 0,
# not the system's ``collateral``), so a model check of the skeleton answers a question about
# nothing. A faithful S ∧ R lowering needs a reviewed system spec that DECLARES the state variable
# for the invariant to bind against (PB-4); ``numeric_invariant``'s ``gte``/``lte`` obligation is in
# the skeleton's supported set, so it needs this explicit claim-class guard until that faithful
# lowering exists. The companion state-obligation class ``state_postcondition`` now HAS such a
# lowering — ``_lower_state_postcondition`` emits a non-vacuous module the stateful-S narrowing
# binds against ``Pred_<state>`` — so it is no longer refused here. Comparison/membership PREMISES
# are unaffected — they are discharged by the theory-aware SMT backends on the FormalClaim path,
# never this lowering.
_UNGROUNDED_STATE_INVARIANT_CLAIM_CLASSES = frozenset({"numeric_invariant"})


def lower_ir_v2_to_tla(ir: RequirementIRV2) -> LoweredFormalArtifact:
    claim_class = ir.semantic_ir.metadata.get("requirement_class")
    if claim_class == "authorization_precondition":
        return _lower_non_vacuous(ir, claim_class)
    if claim_class == "state_postcondition":
        return _lower_state_postcondition(ir, claim_class)
    if claim_class in _UNGROUNDED_STATE_INVARIANT_CLAIM_CLASSES:
        return _refuse_ungrounded_state_invariant(ir, claim_class)
    return _lower_skeleton(ir)


def _refuse_ungrounded_state_invariant(
    ir: RequirementIRV2, claim_class: str
) -> LoweredFormalArtifact:
    """Refuse a numeric/state-invariant claim the skeleton can only lower vacuously.

    See ``_UNGROUNDED_STATE_INVARIANT_CLAIM_CLASSES``: the skeleton would stub the invariant's
    identifiers to 0 and check the obligation comparison over those stubs, so the lowered module
    would not be S ∧ R evidence. Refuse with a source-spanned diagnostic anchored on the obligation
    invariant rather than emit a misleading ``status="lowered"`` artifact. The downstream backend
    and system-checker callers already branch on ``status != "lowered"`` and surface these
    diagnostics as ``unsupported``, so the refusal flows through the gate without a false discharge.
    """
    obligation = ir.semantic_ir.obligation
    anchor = (obligation.must or obligation) if obligation is not None else ir.semantic_ir
    return LoweredFormalArtifact(
        requirement_id=ir.requirement_id,
        source_ir_version=ir.ir_version,
        source_ir_hash=sha256_json(ir),
        status="refused",
        temporal_bounds=_temporal_bounds(ir.semantic_ir),
        diagnostics=[
            LoweringDiagnostic(
                node_id=anchor.node_id,
                kind=anchor.kind,
                reason=(
                    f"{claim_class} obligation is a state invariant over identifiers the TLA "
                    "skeleton can only stub to 0; a faithful S ∧ R lowering requires a reviewed "
                    "system spec that declares the state variable. Refused rather than emit a "
                    "vacuous lowered module (comparison and membership premises are discharged by "
                    "the SMT backends, not this lowering)."
                ),
                source_spans=anchor.source_spans,
            )
        ],
        metadata={
            "refusal_code": "NLR-LOWERING-UNGROUNDED-STATE-INVARIANT",
            "claim_class": claim_class,
        },
    )


def _lower_non_vacuous(ir: RequirementIRV2, claim_class: str) -> LoweredFormalArtifact:
    """Non-vacuous lowering for supported claim kinds (authorization_precondition)."""
    shape_problems = validate_authorization_precondition_shape(ir.semantic_ir)
    if shape_problems:
        return LoweredFormalArtifact(
            requirement_id=ir.requirement_id,
            source_ir_version=ir.ir_version,
            source_ir_hash=sha256_json(ir),
            status="refused",
            temporal_bounds=_temporal_bounds(ir.semantic_ir),
            diagnostics=[
                LoweringDiagnostic(
                    node_id=offending.node_id if offending is not None else ir.semantic_ir.node_id,
                    kind=kind,
                    reason=reason,
                    source_spans=offending.source_spans if offending is not None else ir.semantic_ir.source_spans,
                )
                for kind, reason, offending in shape_problems
            ],
            metadata={"refusal_code": "NLR-LOWERING-UNSUPPORTED-SHAPE"},
        )
    temporal_bounds = _temporal_bounds(ir.semantic_ir)
    source_ir_hash = sha256_json(ir)
    bounds_json = canonical_json([b.model_dump(mode="json") for b in temporal_bounds]).strip()
    content = lower_authorization_precondition_tla(ir, bounds_json=bounds_json)
    return LoweredFormalArtifact(
        requirement_id=ir.requirement_id,
        source_ir_version=ir.ir_version,
        source_ir_hash=source_ir_hash,
        translator="nlreq.formal_lowering.authorization_precondition",
        translator_version=FORMAL_LOWERING_VERSION,
        status="lowered",
        content=content,
        content_hash=sha256_text(content),
        temporal_bounds=temporal_bounds,
        metadata={"evidence": "lowered", "semantics": "non_vacuous", "claim_class": claim_class},
    )


def _lower_state_postcondition(ir: RequirementIRV2, claim_class: str) -> LoweredFormalArtifact:
    """Non-vacuous lowering for state_postcondition.

    The post_state obligation is the affirmed twin of the authorization forbidden outcome: the
    module's premise predicates are abstract operators a reviewed S interprets, and the stateful-S
    narrowing checks ``Pred_<state>(<value>)`` as a NEXT-STEP transition obligation over S's own
    Init/Next (a ghost history bit records the premise in the pre-state). A malformed shape refuses
    with source-spanned diagnostics rather than emit a misleading ``status="lowered"`` artifact;
    the downstream checker callers branch on ``status != "lowered"`` and surface the refusal as
    ``unsupported`` without a false discharge.
    """
    shape_problems = validate_state_postcondition_shape(ir.semantic_ir)
    if shape_problems:
        return LoweredFormalArtifact(
            requirement_id=ir.requirement_id,
            source_ir_version=ir.ir_version,
            source_ir_hash=sha256_json(ir),
            status="refused",
            temporal_bounds=_temporal_bounds(ir.semantic_ir),
            diagnostics=[
                LoweringDiagnostic(
                    node_id=offending.node_id if offending is not None else ir.semantic_ir.node_id,
                    kind=kind,
                    reason=reason,
                    source_spans=offending.source_spans if offending is not None else ir.semantic_ir.source_spans,
                )
                for kind, reason, offending in shape_problems
            ],
            metadata={"refusal_code": "NLR-LOWERING-UNSUPPORTED-SHAPE"},
        )
    temporal_bounds = _temporal_bounds(ir.semantic_ir)
    source_ir_hash = sha256_json(ir)
    bounds_json = canonical_json([b.model_dump(mode="json") for b in temporal_bounds]).strip()
    content = lower_state_postcondition_tla(ir, bounds_json=bounds_json)
    return LoweredFormalArtifact(
        requirement_id=ir.requirement_id,
        source_ir_version=ir.ir_version,
        source_ir_hash=source_ir_hash,
        translator="nlreq.formal_lowering.state_postcondition",
        translator_version=FORMAL_LOWERING_VERSION,
        status="lowered",
        content=content,
        content_hash=sha256_text(content),
        temporal_bounds=temporal_bounds,
        metadata={"evidence": "lowered", "semantics": "non_vacuous", "claim_class": claim_class},
    )


def _lower_skeleton(ir: RequirementIRV2) -> LoweredFormalArtifact:
    """Legacy vacuous skeleton lowering (deprecated for claim kinds with non-vacuous support)."""
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
    identifier_defs = "\n".join(
        f"{name} == 0" for name in sorted(_identifiers(root))
    )
    predicate_defs = "\n".join(
        f"{name}(arg) == TRUE" for name in sorted(_predicates(root))
    )
    event_defs = "\n".join(
        f"Event_{name} == TRUE" for name in sorted(_events(root))
    )
    helper_blocks = "\n\n".join(
        block
        for block in [
            "VARIABLE NLRState\n\nInit == NLRState = 0\nNext == UNCHANGED NLRState",
            "Within(event, amount, unit) == event",
            identifier_defs,
            predicate_defs,
            event_defs,
        ]
        if block
    )
    return (
        f"---- MODULE {module_name} ----\n"
        "EXTENDS Naturals, TLC\n\n"
        f"\\* Generated by nlreq translator {TRANSLATOR_VERSION}; runnable MVP fragment.\n"
        f"\\* Requirement: {ir.requirement_id}\n"
        f"\\* Temporal bounds: {bounds}\n\n"
        f"{helper_blocks}\n\n"
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


def _identifiers(node: SemanticNode) -> set[str]:
    names: set[str] = set()
    for item in _walk_nodes(node):
        for arg in item.args:
            if arg.kind == "identifier":
                names.add(_safe_name(str(arg.value)))
    return names


def _predicates(node: SemanticNode) -> set[str]:
    return {
        _safe_name(item.name or "predicate")
        for item in _walk_nodes(node)
        if item.kind == "predicate"
    }


def _events(node: SemanticNode) -> set[str]:
    return {
        _safe_name(item.name or "event")
        for item in _walk_nodes(node)
        if item.kind == "event"
    }


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
