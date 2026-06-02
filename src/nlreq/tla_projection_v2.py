from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from .jsonutil import sha256_json
from .models import RequirementIRV2, SemanticNode
from .translator import LoweredFormalArtifact, lower_ir_v2_to_tla


TLA_PROJECTION_V2_SCHEMA_VERSION = "0.1"
TLA_PROJECTION_V2_TOOL_VERSION = "0.1"


class TlaProjectionFragment(BaseModel):
    model_config = ConfigDict(extra="forbid")

    node_id: str
    kind: str
    status: Literal["projected", "unsupported"]
    reason: str | None = None


class TlaProjectionV2Report(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["0.1"] = TLA_PROJECTION_V2_SCHEMA_VERSION
    requirement_id: str
    result: Literal["projected", "unsupported"]
    lowered: LoweredFormalArtifact
    fragments: list[TlaProjectionFragment] = Field(default_factory=list)
    temporal_bounds: list[dict[str, str | int | float]] = Field(default_factory=list)
    input_hashes: dict[str, str] = Field(default_factory=dict)
    semantic_rules: list[str] = Field(default_factory=list)
    tool: str = "nlreq.tla_projection_v2"
    tool_version: str = TLA_PROJECTION_V2_TOOL_VERSION


def build_tla_projection_v2_report(requirement: RequirementIRV2) -> TlaProjectionV2Report:
    lowered = lower_ir_v2_to_tla(requirement)
    diagnostics = {diagnostic.node_id: diagnostic for diagnostic in lowered.diagnostics}
    fragments = [
        TlaProjectionFragment(
            node_id=node.node_id,
            kind=node.kind,
            status="unsupported" if node.node_id in diagnostics else "projected",
            reason=diagnostics[node.node_id].reason if node.node_id in diagnostics else None,
        )
        for node in _walk_nodes(requirement.semantic_ir)
    ]
    return TlaProjectionV2Report(
        requirement_id=requirement.requirement_id,
        result="projected" if lowered.status == "lowered" else "unsupported",
        lowered=lowered,
        fragments=fragments,
        temporal_bounds=[
            bound.model_dump(mode="json", exclude_none=True)
            for bound in lowered.temporal_bounds
        ],
        input_hashes={"requirement_ir": sha256_json(requirement)},
        semantic_rules=[
            "Unsupported IR fragments produce refused lowering, not partial proof.",
            "Temporal bounds are recorded as check bounds, not unbounded proof claims.",
            "Generated TLA content is an artifact for model checkers; it is not evidence until executed.",
        ],
    )


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
