from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from .jsonutil import sha256_text
from .models import RequirementIRV2, SemanticNode, SourceSpan
from .translator import LoweredFormalArtifact
from .translator_agreement import TranslationAgreementReport


PROVENANCE_SCHEMA_VERSION = "0.1"


class ProvenanceNode(BaseModel):
    model_config = ConfigDict(extra="forbid")

    node_id: str
    kind: Literal["text_span", "ir_node", "formal_fragment", "refusal_reason"]
    label: str
    source_span: SourceSpan | None = None
    artifact_hash: str | None = None


class ProvenanceEdge(BaseModel):
    model_config = ConfigDict(extra="forbid")

    from_node: str
    to_node: str
    relation: Literal["parsed_to", "lowered_to", "explains", "refuses"]


class ProvenanceGraph(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["0.1"] = PROVENANCE_SCHEMA_VERSION
    requirement_id: str
    nodes: list[ProvenanceNode] = Field(default_factory=list)
    edges: list[ProvenanceEdge] = Field(default_factory=list)


class ClarificationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["0.1"] = PROVENANCE_SCHEMA_VERSION
    clarification_id: str
    requirement_id: str
    question: str
    source_spans: list[SourceSpan] = Field(default_factory=list)
    target_node_ids: list[str] = Field(default_factory=list)
    reason: str


class ClarificationResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["0.1"] = PROVENANCE_SCHEMA_VERSION
    clarification_id: str
    answered_by: str
    answered_at: str
    replacement_text: str
    target_start_char: int
    target_end_char: int


class ClarifiedControlledText(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["0.1"] = PROVENANCE_SCHEMA_VERSION
    previous_text_hash: str
    new_text: str
    new_text_hash: str
    applied_clarification_id: str


def build_provenance_graph(
    requirement: RequirementIRV2,
    *,
    lowered: LoweredFormalArtifact | None = None,
) -> ProvenanceGraph:
    nodes: list[ProvenanceNode] = []
    edges: list[ProvenanceEdge] = []
    for node in _walk_nodes(requirement.semantic_ir):
        ir_node_id = f"ir:{node.node_id}"
        nodes.append(ProvenanceNode(node_id=ir_node_id, kind="ir_node", label=node.kind))
        for index, span in enumerate(node.source_spans):
            text_node_id = f"text:{node.node_id}:{index}"
            nodes.append(
                ProvenanceNode(
                    node_id=text_node_id,
                    kind="text_span",
                    label=span.text,
                    source_span=span,
                )
            )
            edges.append(ProvenanceEdge(from_node=text_node_id, to_node=ir_node_id, relation="parsed_to"))
    if lowered is not None:
        formal_id = "formal:lowered"
        nodes.append(
            ProvenanceNode(
                node_id=formal_id,
                kind="formal_fragment",
                label=lowered.target,
                artifact_hash=lowered.content_hash,
            )
        )
        edges.append(ProvenanceEdge(from_node="ir:rule.root", to_node=formal_id, relation="lowered_to"))
        for diagnostic in lowered.diagnostics:
            refusal_id = f"refusal:{diagnostic.node_id}"
            nodes.append(ProvenanceNode(node_id=refusal_id, kind="refusal_reason", label=diagnostic.reason))
            edges.append(ProvenanceEdge(from_node=f"ir:{diagnostic.node_id}", to_node=refusal_id, relation="refuses"))
    return ProvenanceGraph(requirement_id=requirement.requirement_id, nodes=nodes, edges=edges)


def clarification_requests_from_agreement(
    agreement: TranslationAgreementReport,
) -> list[ClarificationRequest]:
    return [
        ClarificationRequest(
            clarification_id=item.question_id,
            requirement_id=agreement.requirement_id,
            question=item.question,
            target_node_ids=[item.path],
            reason="translator_disagreement",
        )
        for item in agreement.clarifications
    ]


def apply_clarification_response(
    controlled_text: str,
    response: ClarificationResponse,
) -> ClarifiedControlledText:
    if response.target_start_char < 0 or response.target_end_char < response.target_start_char:
        raise ValueError("invalid clarification target span")
    new_text = (
        controlled_text[: response.target_start_char]
        + response.replacement_text
        + controlled_text[response.target_end_char :]
    )
    return ClarifiedControlledText(
        previous_text_hash=sha256_text(controlled_text),
        new_text=new_text,
        new_text_hash=sha256_text(new_text),
        applied_clarification_id=response.clarification_id,
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
