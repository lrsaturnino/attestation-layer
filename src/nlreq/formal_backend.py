from __future__ import annotations

from typing import Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field

from .models import BackendResult, RequirementIRV2, SemanticNode


FORMAL_BACKEND_SCHEMA_VERSION = "0.1"


FormalBackendTarget = Literal["tla", "smt", "ltl", "alloy", "lean"]


class FormalBackendBudget(BaseModel):
    model_config = ConfigDict(extra="forbid")

    timeout_seconds: int | None = Field(default=None, gt=0)
    max_states: int | None = Field(default=None, gt=0)
    max_depth: int | None = Field(default=None, gt=0)


class UnsupportedConstruct(BaseModel):
    model_config = ConfigDict(extra="forbid")

    node_id: str
    kind: str
    reason: str


class ConsumedAnnotation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    node_id: str
    namespace: str
    schema_version: str
    keys: list[str] = Field(default_factory=list)


class FormalBackendRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["0.1"] = FORMAL_BACKEND_SCHEMA_VERSION
    backend_id: str
    target: FormalBackendTarget
    requirement: RequirementIRV2
    entry_node_id: str = "rule.root"
    budget: FormalBackendBudget | None = None


class FormalBackendResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["0.1"] = FORMAL_BACKEND_SCHEMA_VERSION
    backend_id: str
    target: FormalBackendTarget
    result: BackendResult
    unsupported_constructs: list[UnsupportedConstruct] = Field(default_factory=list)
    consumed_annotations: list[ConsumedAnnotation] = Field(default_factory=list)
    lowered_artifact_hash: str | None = None


class FormalBackend(Protocol):
    backend_id: str
    target: FormalBackendTarget

    def check(self, request: FormalBackendRequest) -> FormalBackendResponse:
        ...


class TlaBoundaryBackend:
    backend_id = "tla-boundary"
    target: FormalBackendTarget = "tla"
    annotation_namespace = "tla"
    supported_node_kinds = {
        "rule",
        "forall",
        "and",
        "predicate",
        "action_obligation",
        "action",
        "before",
        "transition",
        "state_ref",
        "invariant",
        "state_delta",
        "event",
    }

    def check(self, request: FormalBackendRequest) -> FormalBackendResponse:
        if request.backend_id != self.backend_id:
            raise ValueError(
                f"backend_id mismatch: request {request.backend_id}, backend {self.backend_id}"
            )
        if request.target != self.target:
            raise ValueError(f"target mismatch: request {request.target}, backend {self.target}")

        unsupported: list[UnsupportedConstruct] = []
        consumed: list[ConsumedAnnotation] = []
        for node in _walk_nodes(request.requirement.semantic_ir):
            if node.kind not in self.supported_node_kinds:
                unsupported.append(
                    UnsupportedConstruct(
                        node_id=node.node_id,
                        kind=node.kind,
                        reason=f"node kind is not supported by backend {self.backend_id}",
                    )
                )
            annotation = node.annotations.get(self.annotation_namespace)
            if annotation is not None:
                schema_version = annotation.get("schema_version")
                if not isinstance(schema_version, str) or not schema_version:
                    unsupported.append(
                        UnsupportedConstruct(
                            node_id=node.node_id,
                            kind=node.kind,
                            reason=(
                                f"{self.annotation_namespace} annotation requires schema_version"
                            ),
                        )
                    )
                else:
                    consumed.append(
                        ConsumedAnnotation(
                            node_id=node.node_id,
                            namespace=self.annotation_namespace,
                            schema_version=schema_version,
                            keys=sorted(annotation),
                        )
                    )

        status = "unsupported" if unsupported else "needs_review"
        details = {
            "entry_node_id": request.entry_node_id,
            "checked_node_count": len(list(_walk_nodes(request.requirement.semantic_ir))),
            "boundary": "lowering_shape_only",
            "execution": "not_run",
        }
        if unsupported:
            details["unsupported_constructs"] = [
                item.model_dump(mode="json", exclude_none=True) for item in unsupported
            ]

        return FormalBackendResponse(
            backend_id=self.backend_id,
            target=self.target,
            result=BackendResult(
                backend=self.backend_id,
                status=status,
                evidence_level=None,
                details=details,
            ),
            unsupported_constructs=unsupported,
            consumed_annotations=consumed,
        )


def formal_backend_for_id(backend_id: str) -> FormalBackend:
    if backend_id == TlaBoundaryBackend.backend_id:
        return TlaBoundaryBackend()
    raise ValueError(f"unknown formal backend: {backend_id}")


def build_formal_backend_request(
    requirement: RequirementIRV2,
    *,
    backend_id: str,
    budget: FormalBackendBudget | None = None,
) -> FormalBackendRequest:
    backend = formal_backend_for_id(backend_id)
    return FormalBackendRequest(
        backend_id=backend.backend_id,
        target=backend.target,
        requirement=requirement,
        budget=budget,
    )


def check_formal_backend(request: FormalBackendRequest) -> FormalBackendResponse:
    return formal_backend_for_id(request.backend_id).check(request)


def existing_formal_boundaries() -> list[dict[str, str]]:
    return [
        {
            "backend_id": "core_smt",
            "target": "smt",
            "scope": "flat ir_version 0.1 self-consistency and supported claim shape",
        },
        {
            "backend_id": "tla",
            "target": "tla",
            "scope": "reviewed TLA+ model/config execution, not compositional IR lowering",
        },
        {
            "backend_id": TlaBoundaryBackend.backend_id,
            "target": TlaBoundaryBackend.target,
            "scope": "compositional IR lowering boundary shape check",
        },
    ]


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
