from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from .formal_backend import FormalBackendResponse
from .jsonutil import sha256_json
from .models import RequirementIRV2, SemanticNode
from .proof_closure import ProofObject
from .source_adapter import SourceManifest


AGNOSTIC_WEDGE_SCHEMA_VERSION = "0.1"
AGNOSTIC_WEDGE_TOOL_VERSION = "0.1"
ADAPTER_SPECIFIC_METADATA_KEYS = {
    "adapter",
    "adapter_id",
    "backend",
    "language",
    "path",
    "runtime",
    "source_path",
    "target",
}


class SourceLanguageSlice(BaseModel):
    model_config = ConfigDict(extra="forbid")

    adapter: str
    language: str
    runtime: str | None = None
    module_ids: list[str] = Field(default_factory=list)


class FormalTargetSlice(BaseModel):
    model_config = ConfigDict(extra="forbid")

    backend_id: str
    target: str
    result_status: str
    evidence_level: str | None = None


class AgnosticWedgeBlocker(BaseModel):
    model_config = ConfigDict(extra="forbid")

    category: Literal[
        "missing_input",
        "proof_not_closed",
        "insufficient_diversity",
        "formal_backend",
        "ir_boundary",
    ]
    message: str
    subject: str | None = None


class AgnosticWedgeReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["0.1"] = AGNOSTIC_WEDGE_SCHEMA_VERSION
    requirement_id: str
    proof_id: str
    result: Literal["passed", "blocked"]
    wedge_type: Literal["cross_language", "cross_formalism", "none"]
    proof_status: Literal["closed", "open", "blocked"]
    source_languages: list[SourceLanguageSlice] = Field(default_factory=list)
    formal_targets: list[FormalTargetSlice] = Field(default_factory=list)
    blockers: list[AgnosticWedgeBlocker] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    input_hashes: dict[str, str] = Field(default_factory=dict)
    tool: str = "nlreq.agnostic_wedge"
    tool_version: str = AGNOSTIC_WEDGE_TOOL_VERSION


def build_agnostic_wedge_report(
    *,
    proof: ProofObject,
    source_manifests: list[SourceManifest] | None = None,
    formal_responses: list[FormalBackendResponse] | None = None,
    requirement: RequirementIRV2 | None = None,
) -> AgnosticWedgeReport:
    source_manifests = source_manifests or []
    formal_responses = formal_responses or []
    source_languages = [_source_language_slice(manifest) for manifest in source_manifests]
    formal_targets = [_formal_target_slice(response) for response in formal_responses]
    blockers: list[AgnosticWedgeBlocker] = []

    if proof.status != "closed":
        blockers.append(
            AgnosticWedgeBlocker(
                category="proof_not_closed",
                message="agnostic wedge requires a closed proof object",
                subject=proof.proof_id,
            )
        )
    if not source_languages and not formal_targets:
        blockers.append(
            AgnosticWedgeBlocker(
                category="missing_input",
                message="at least two source manifests or two formal backend responses are required",
            )
        )

    proof_backends = {result.backend for result in proof.backend_results}
    for target in formal_targets:
        if target.backend_id not in proof_backends:
            blockers.append(
                AgnosticWedgeBlocker(
                    category="formal_backend",
                    subject=target.backend_id,
                    message="formal backend response is not present in the proof object",
                )
            )
        if target.result_status != "valid":
            blockers.append(
                AgnosticWedgeBlocker(
                    category="formal_backend",
                    subject=target.backend_id,
                    message=f"formal backend result status is {target.result_status}",
                )
            )

    if requirement is not None:
        for node_id, key in _semantic_ir_adapter_facts(requirement.semantic_ir):
            blockers.append(
                AgnosticWedgeBlocker(
                    category="ir_boundary",
                    subject=node_id,
                    message=f"semantic IR metadata contains adapter-specific key {key}",
                )
            )

    distinct_languages = {item.language for item in source_languages}
    distinct_targets = {item.target for item in formal_targets}
    if len(distinct_languages) >= 2:
        wedge_type: Literal["cross_language", "cross_formalism", "none"] = "cross_language"
    elif len(distinct_targets) >= 2:
        wedge_type = "cross_formalism"
    else:
        wedge_type = "none"
        blockers.append(
            AgnosticWedgeBlocker(
                category="insufficient_diversity",
                message="wedge requires at least two source languages or two formal targets",
            )
        )

    limitations = _limitations(
        wedge_type=wedge_type,
        source_languages=source_languages,
        formal_targets=formal_targets,
        requirement=requirement,
    )
    input_hashes = {
        "proof_object": sha256_json(proof),
        "source_manifests": sha256_json(source_manifests),
        "formal_responses": sha256_json(formal_responses),
    }
    if requirement is not None:
        input_hashes["requirement_ir"] = sha256_json(requirement)

    return AgnosticWedgeReport(
        requirement_id=proof.requirement_id,
        proof_id=proof.proof_id,
        result="blocked" if blockers else "passed",
        wedge_type=wedge_type,
        proof_status=proof.status,
        source_languages=source_languages,
        formal_targets=formal_targets,
        blockers=blockers,
        limitations=limitations,
        input_hashes=input_hashes,
    )


def _source_language_slice(manifest: SourceManifest) -> SourceLanguageSlice:
    return SourceLanguageSlice(
        adapter=manifest.adapter,
        language=manifest.language,
        runtime=manifest.runtime,
        module_ids=[module.module_id for module in manifest.modules],
    )


def _formal_target_slice(response: FormalBackendResponse) -> FormalTargetSlice:
    return FormalTargetSlice(
        backend_id=response.backend_id,
        target=response.target,
        result_status=response.result.status,
        evidence_level=(
            response.result.evidence_level.value
            if response.result.evidence_level is not None
            else None
        ),
    )


def _semantic_ir_adapter_facts(node: SemanticNode) -> list[tuple[str, str]]:
    facts = [
        (node.node_id, key)
        for key in sorted(node.metadata)
        if key in ADAPTER_SPECIFIC_METADATA_KEYS
    ]
    for child in node.scope:
        facts.extend(_semantic_ir_adapter_facts(child))
    if node.premise is not None:
        facts.extend(_semantic_ir_adapter_facts(node.premise))
    if node.obligation is not None:
        facts.extend(_semantic_ir_adapter_facts(node.obligation))
    if node.action is not None:
        facts.extend(_semantic_ir_adapter_facts(node.action))
    if node.must is not None:
        facts.extend(_semantic_ir_adapter_facts(node.must))
    for child in node.children:
        facts.extend(_semantic_ir_adapter_facts(child))
    if isinstance(node.left, SemanticNode):
        facts.extend(_semantic_ir_adapter_facts(node.left))
    if isinstance(node.right, SemanticNode):
        facts.extend(_semantic_ir_adapter_facts(node.right))
    return facts


def _limitations(
    *,
    wedge_type: Literal["cross_language", "cross_formalism", "none"],
    source_languages: list[SourceLanguageSlice],
    formal_targets: list[FormalTargetSlice],
    requirement: RequirementIRV2 | None,
) -> list[str]:
    limitations: list[str] = []
    if wedge_type != "cross_language":
        limitations.append("cross-language source diversity is not demonstrated")
    if wedge_type != "cross_formalism":
        limitations.append("cross-formalism backend diversity is not demonstrated")
    if source_languages and formal_targets:
        limitations.append(
            "cross-language trace causality remains delegated to normalized trace artifacts"
        )
    if requirement is None:
        limitations.append("semantic IR adapter-fact scan was not run")
    return limitations
