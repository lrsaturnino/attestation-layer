from __future__ import annotations

import difflib
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from .dsl_v2 import DslV2Parser
from .formal_lowering import (
    FORMAL_LOWERING_VERSION,
    lower_authorization_precondition_tla,
    lower_bounded_temporal_tla,
    lower_cross_module_causal_tla,
    lower_numeric_invariant_tla,
    lower_state_postcondition_tla,
    lower_state_precondition_tla,
    validate_authorization_precondition_shape,
    validate_bounded_temporal_shape,
    validate_cross_module_causal_shape,
    validate_numeric_invariant_shape,
    validate_state_postcondition_shape,
    validate_state_precondition_shape,
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


def lower_ir_v2_to_tla(
    ir: RequirementIRV2, *, legacy_skeleton: bool = False
) -> LoweredFormalArtifact:
    """Lower a requirement IR to a TLA+ artifact for the formal backends.

    Every supported DSL v3 ``requirement_class`` lowers to a NON-VACUOUS module (real typed
    relations/constraints, never ``TRUE``/``0``) or REFUSES with source-spanned diagnostics on a
    malformed shape — no supported claim kind silently returns the legacy ``not_checked`` skeleton.

    Class dispatch on the live path (``legacy_skeleton=False``):
      - supported class -> non-vacuous lowering (or refuse on a bad shape);
      - a requirement_class that is PRESENT but unsupported -> REFUSE (a genuine error — the v3
        parser never emits such a class, so it can only come from a hand-built IR);
      - an ABSENT requirement_class -> the legacy DSL v2 skeleton. This is preserved deliberately:
        the production ``end_to_end_gate`` default-parses controlled text with ``DslV2Parser``, which
        carries no class metadata, so refusing absent-class would break production with no DoD gain
        (all supported KINDS already lower non-vacuously). The ``Within(...) == event`` passthrough is
        therefore confined to this legacy v2 branch; its ``evidence=not_checked`` keeps it honest
        (unchecked, never a false pass).

    ``legacy_skeleton=True`` forces the deprecated vacuous skeleton regardless of class (predicates ->
    ``TRUE``, identifiers -> ``== 0``, the ``Within`` passthrough) — the explicit opt-in HELPER PA-1.T3
    calls for, used by the back-compat golden tests that pin that historical shape.
    """
    if legacy_skeleton:
        return _lower_skeleton(ir)
    claim_class = ir.semantic_ir.metadata.get("requirement_class")
    if claim_class == "authorization_precondition":
        return _lower_non_vacuous(ir, claim_class)
    if claim_class == "state_postcondition":
        return _lower_state_postcondition(ir, claim_class)
    if claim_class == "state_precondition":
        return _lower_state_precondition(ir, claim_class)
    if claim_class == "numeric_invariant":
        return _lower_numeric_invariant(ir, claim_class)
    if claim_class in {"bounded_temporal", "event_state_correspondence"}:
        return _lower_bounded_temporal(ir, claim_class)
    if claim_class == "cross_module_causal_obligation":
        return _lower_cross_module_causal(ir, claim_class)
    if claim_class is not None:
        # A present-but-unsupported requirement_class is a genuine error, not legacy input: refuse
        # rather than emit a meaningless skeleton.
        return _lower_refused_unsupported_class(ir, claim_class)
    # Absent class: the legacy DSL v2 path (see docstring) — back-compat skeleton, not the live
    # non-vacuous path.
    return _lower_skeleton(ir)


def _lower_numeric_invariant(ir: RequirementIRV2, claim_class: str) -> LoweredFormalArtifact:
    """Non-vacuous lowering for numeric_invariant.

    The obligation is a numeric invariant ``Premise => Obligation`` over a state variable. Where the
    legacy skeleton could only stub that variable to a constant ``0`` (a check of nothing), the
    stateful-S narrowing (compose_s_and_r_module) now binds it to a reviewed S that DECLARES and
    evolves the variable and checks the invariant as a SAME-STATE property over S's own Init/Next —
    so a counterexample is a reachable S state inside the premise bounds that violates the kept
    obligation. A malformed shape refuses with source-spanned diagnostics rather than emit a
    misleading ``status="lowered"`` artifact; the downstream checker callers branch on
    ``status != "lowered"`` and surface the refusal as ``unsupported`` without a false discharge.
    Comparison premises are ALSO discharged independently by the theory-aware SMT backends on the
    FormalClaim path (PB-7 routing); this lowering carries the obligation invariant to the S ∧ R model
    check.
    """
    shape_problems = validate_numeric_invariant_shape(ir.semantic_ir)
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
    content = lower_numeric_invariant_tla(ir, bounds_json=bounds_json)
    return LoweredFormalArtifact(
        requirement_id=ir.requirement_id,
        source_ir_version=ir.ir_version,
        source_ir_hash=source_ir_hash,
        translator="nlreq.formal_lowering.numeric_invariant",
        translator_version=FORMAL_LOWERING_VERSION,
        status="lowered",
        content=content,
        content_hash=sha256_text(content),
        temporal_bounds=temporal_bounds,
        metadata={"evidence": "lowered", "semantics": "non_vacuous", "claim_class": claim_class},
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


def _lower_state_precondition(ir: RequirementIRV2, claim_class: str) -> LoweredFormalArtifact:
    """Non-vacuous lowering for state_precondition.

    The affirmative dual of authorization_precondition: ``when <predicate> then <action> must
    succeed`` lowers to a harness whose obligation is the SAME-STATE safety invariant ``Premise =>
    NLRState /= "failed"`` over a reviewed S that interprets the premise predicate (the stateless-S
    Case A product of compose_s_and_r_module). A malformed shape refuses with source-spanned
    diagnostics rather than emit a misleading ``status="lowered"`` artifact; the downstream checker
    callers branch on ``status != "lowered"`` and surface the refusal as ``unsupported`` without a
    false discharge.
    """
    shape_problems = validate_state_precondition_shape(ir.semantic_ir)
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
    content = lower_state_precondition_tla(ir, bounds_json=bounds_json)
    return LoweredFormalArtifact(
        requirement_id=ir.requirement_id,
        source_ir_version=ir.ir_version,
        source_ir_hash=source_ir_hash,
        translator="nlreq.formal_lowering.state_precondition",
        translator_version=FORMAL_LOWERING_VERSION,
        status="lowered",
        content=content,
        content_hash=sha256_text(content),
        temporal_bounds=temporal_bounds,
        metadata={"evidence": "lowered", "semantics": "non_vacuous", "claim_class": claim_class},
    )


def _lower_bounded_temporal(ir: RequirementIRV2, claim_class: str) -> LoweredFormalArtifact:
    """Non-vacuous bounded-temporal lowering for bounded_temporal / event_state_correspondence.

    Replaces the legacy ``Within(event, amount, unit) == event`` skeleton passthrough on the live
    v3 path. The obligation ``emit <event> within <k> <unit>`` lowers to a step-counter encoding of
    the bounded-response property — the standalone harness models a worst-case (unbounded-latency)
    system, and the real S ∧ R evidence comes from the stateful-S narrowing (compose_s_and_r_module),
    which counts S's own steps against the deadline. A malformed shape (e.g. a cross-module
    transition response, or a predicate-free premise) refuses with source-spanned diagnostics rather
    than emit a misleading ``status="lowered"`` artifact.
    """
    shape_problems = validate_bounded_temporal_shape(ir.semantic_ir)
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
    content = lower_bounded_temporal_tla(ir, bounds_json=bounds_json)
    return LoweredFormalArtifact(
        requirement_id=ir.requirement_id,
        source_ir_version=ir.ir_version,
        source_ir_hash=source_ir_hash,
        translator="nlreq.formal_lowering.bounded_temporal",
        translator_version=FORMAL_LOWERING_VERSION,
        status="lowered",
        content=content,
        content_hash=sha256_text(content),
        temporal_bounds=temporal_bounds,
        metadata={"evidence": "lowered", "semantics": "non_vacuous", "claim_class": claim_class},
    )


def _lower_cross_module_causal(ir: RequirementIRV2, claim_class: str) -> LoweredFormalArtifact:
    """Non-vacuous bounded-response lowering for cross_module_causal_obligation.

    ``when <predicate> then module A causes module B to <action> within <k> <unit>`` is the cross-
    module sibling of bounded_temporal: the response is "module B performs <action>" (interpreted by
    the target module's reviewed S as ``Pred_<action>``) rather than an emitted event. It reuses the
    same pending-deadline narrowing (compose_s_and_r_module), so the obligation is genuinely checked,
    never a not_checked skeleton. A malformed shape (e.g. an emitted-event response, or a
    predicate-free premise) refuses with source-spanned diagnostics rather than emit a misleading
    ``status="lowered"`` artifact.
    """
    shape_problems = validate_cross_module_causal_shape(ir.semantic_ir)
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
    content = lower_cross_module_causal_tla(ir, bounds_json=bounds_json)
    return LoweredFormalArtifact(
        requirement_id=ir.requirement_id,
        source_ir_version=ir.ir_version,
        source_ir_hash=source_ir_hash,
        translator="nlreq.formal_lowering.cross_module_causal",
        translator_version=FORMAL_LOWERING_VERSION,
        status="lowered",
        content=content,
        content_hash=sha256_text(content),
        temporal_bounds=temporal_bounds,
        metadata={"evidence": "lowered", "semantics": "non_vacuous", "claim_class": claim_class},
    )


def _lower_refused_unsupported_class(
    ir: RequirementIRV2, claim_class: str
) -> LoweredFormalArtifact:
    """Refuse, on the live path, an IR that declares a PRESENT-but-unsupported requirement_class.

    The supported classes all lower non-vacuously (or refuse on a bad shape) above; reaching here
    means the IR carries a ``requirement_class`` the lowering does not recognize. The DSL v3 parser
    never emits such a class, so it can only come from a hand-built IR — a genuine error. Rather than
    emit the vacuous ``not_checked`` skeleton (which the backends would treat as a runnable-but-
    meaningless module), refuse with a source-spanned diagnostic. (An ABSENT class is the legacy DSL v2
    path and still skeletons — see lower_ir_v2_to_tla.)
    """
    label = repr(claim_class)
    return LoweredFormalArtifact(
        requirement_id=ir.requirement_id,
        source_ir_version=ir.ir_version,
        source_ir_hash=sha256_json(ir),
        status="refused",
        temporal_bounds=_temporal_bounds(ir.semantic_ir),
        diagnostics=[
            LoweringDiagnostic(
                node_id=ir.semantic_ir.node_id,
                kind="unsupported_requirement_class",
                reason=(
                    f"requirement_class {label} has no non-vacuous TLA+ lowering; the live path "
                    "refuses rather than emit a not_checked skeleton. Supported classes: "
                    "authorization_precondition, state_precondition, state_postcondition, "
                    "numeric_invariant, bounded_temporal, event_state_correspondence, "
                    "cross_module_causal_obligation. (Pass legacy_skeleton=True for the deprecated "
                    "vacuous skeleton.)"
                ),
                source_spans=ir.semantic_ir.source_spans,
            )
        ],
        metadata={"refusal_code": "NLR-LOWERING-UNSUPPORTED-CLASS"},
    )


def _lower_skeleton(ir: RequirementIRV2) -> LoweredFormalArtifact:
    """Legacy vacuous skeleton lowering — reachable only via ``lower_ir_v2_to_tla(legacy_skeleton=True)``.

    DEPRECATED: predicates lower to ``TRUE``, identifiers to ``== 0``, and temporal obligations to the
    ``Within(event, amount, unit) == event`` passthrough — a tautology the backends cannot
    meaningfully check (``metadata={"evidence": "not_checked"}``). Retained only so the historical
    golden tests can pin this shape; the live path (``legacy_skeleton=False``) lowers supported classes
    non-vacuously and refuses everything else.
    """
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
