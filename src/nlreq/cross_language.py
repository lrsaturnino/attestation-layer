from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from .jsonutil import sha256_json
from .models import NormalizedTraceArtifact
from .proof_closure import ProofObject
from .source_adapter import SourceManifest


CROSS_LANGUAGE_SCHEMA_VERSION = "0.1"
CROSS_LANGUAGE_V2_SCHEMA_VERSION = "0.2"
CROSS_LANGUAGE_TOOL_VERSION = "0.1"


class CrossLanguageEvidenceSlice(BaseModel):
    model_config = ConfigDict(extra="forbid")

    adapter_id: str
    language: str
    runtime: str | None = None
    module_ids: list[str] = Field(default_factory=list)
    trace_ids: list[str] = Field(default_factory=list)


class CausalTraceLink(BaseModel):
    model_config = ConfigDict(extra="forbid")

    from_trace_id: str
    from_event_id: str
    to_trace_id: str
    to_event_id: str
    relation: Literal["causes", "follows", "correlates"]
    evidence: str


class CrossLanguageProofBlocker(BaseModel):
    model_config = ConfigDict(extra="forbid")

    category: Literal[
        "proof",
        "language_diversity",
        "trace_link",
        "adapter_evidence",
        "replay_bundle",
    ]
    message: str
    subject: str | None = None


class CrossLanguageProofObject(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["0.1"] = CROSS_LANGUAGE_SCHEMA_VERSION
    proof_id: str
    requirement_id: str
    result: Literal["passed", "blocked"]
    proof_status: Literal["closed", "open", "blocked"]
    slices: list[CrossLanguageEvidenceSlice] = Field(default_factory=list)
    causal_links: list[CausalTraceLink] = Field(default_factory=list)
    blockers: list[CrossLanguageProofBlocker] = Field(default_factory=list)
    input_hashes: dict[str, str] = Field(default_factory=dict)
    tool: str = "nlreq.cross_language"
    tool_version: str = CROSS_LANGUAGE_TOOL_VERSION


class AdapterEvidenceReference(BaseModel):
    model_config = ConfigDict(extra="forbid")

    evidence_id: str
    adapter_id: str
    artifact_hash: str
    evidence_level: str | None = None
    producer_id: str | None = None
    replay_bundle_hash: str | None = None


class CausalTraceLinkV2(BaseModel):
    model_config = ConfigDict(extra="forbid")

    link_id: str
    from_adapter_id: str
    from_trace_id: str
    from_event_id: str
    to_adapter_id: str
    to_trace_id: str
    to_event_id: str
    relation: Literal["causes", "follows", "correlates"]
    required: bool = True
    status: Literal["satisfied", "missing_source", "missing_target", "unverified"] = "unverified"
    evidence_hash: str | None = None


class CrossLanguageEvidenceSliceV2(BaseModel):
    model_config = ConfigDict(extra="forbid")

    adapter_id: str
    language: str
    runtime: str | None = None
    module_ids: list[str] = Field(default_factory=list)
    trace_ids: list[str] = Field(default_factory=list)
    evidence: list[AdapterEvidenceReference] = Field(default_factory=list)
    blockers: list[CrossLanguageProofBlocker] = Field(default_factory=list)


class CrossLanguageProofObjectV2(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["0.2"] = CROSS_LANGUAGE_V2_SCHEMA_VERSION
    proof_id: str
    requirement_id: str
    result: Literal["accepted", "refused", "unknown"]
    closure_status: Literal["closed", "blocked"]
    proof_status: Literal["closed", "open", "blocked"]
    adapter_count: int = 0
    language_count: int = 0
    slices: list[CrossLanguageEvidenceSliceV2] = Field(default_factory=list)
    causal_links: list[CausalTraceLinkV2] = Field(default_factory=list)
    blockers: list[CrossLanguageProofBlocker] = Field(default_factory=list)
    input_hashes: dict[str, str] = Field(default_factory=dict)
    tool: str = "nlreq.cross_language"
    tool_version: str = CROSS_LANGUAGE_TOOL_VERSION


def build_cross_language_proof_object(
    *,
    proof: ProofObject,
    manifests: list[SourceManifest],
    traces: list[NormalizedTraceArtifact] | None = None,
    causal_links: list[CausalTraceLink] | None = None,
) -> CrossLanguageProofObject:
    traces = traces or []
    causal_links = causal_links or []
    trace_ids_by_adapter: dict[str, list[str]] = {}
    event_ids = set()
    for artifact in traces:
        for trace in artifact.root:
            trace_ids_by_adapter.setdefault(trace.adapter_id, []).append(trace.trace_id)
            for event in trace.events:
                event_ids.add((trace.trace_id, event.event_id))

    slices = [
        CrossLanguageEvidenceSlice(
            adapter_id=manifest.adapter,
            language=manifest.language,
            runtime=manifest.runtime,
            module_ids=[module.module_id for module in manifest.modules],
            trace_ids=sorted(trace_ids_by_adapter.get(manifest.adapter, [])),
        )
        for manifest in manifests
    ]
    blockers: list[CrossLanguageProofBlocker] = []
    if proof.status != "closed":
        blockers.append(
            CrossLanguageProofBlocker(
                category="proof",
                subject=proof.proof_id,
                message="cross-language proof requires a closed proof object",
            )
        )
    if len({item.language for item in slices}) < 2:
        blockers.append(
            CrossLanguageProofBlocker(
                category="language_diversity",
                message="at least two source languages are required",
            )
        )
    for link in causal_links:
        if (link.from_trace_id, link.from_event_id) not in event_ids:
            blockers.append(
                CrossLanguageProofBlocker(
                    category="trace_link",
                    subject=f"{link.from_trace_id}:{link.from_event_id}",
                    message="causal link source event is missing",
                )
            )
        if (link.to_trace_id, link.to_event_id) not in event_ids:
            blockers.append(
                CrossLanguageProofBlocker(
                    category="trace_link",
                    subject=f"{link.to_trace_id}:{link.to_event_id}",
                    message="causal link target event is missing",
                )
            )
    return CrossLanguageProofObject(
        proof_id=proof.proof_id,
        requirement_id=proof.requirement_id,
        result="blocked" if blockers else "passed",
        proof_status=proof.status,
        slices=slices,
        causal_links=causal_links,
        blockers=blockers,
        input_hashes={
            "proof_object": sha256_json(proof),
            "source_manifests": sha256_json(manifests),
            "traces": sha256_json(traces),
            "causal_links": sha256_json(causal_links),
        },
    )


def build_cross_language_causal_proof_object(
    *,
    proof: ProofObject,
    manifests: list[SourceManifest],
    traces: list[NormalizedTraceArtifact] | None = None,
    evidence: list[AdapterEvidenceReference] | None = None,
    causal_links: list[CausalTraceLinkV2] | None = None,
    required_adapter_ids: list[str] | None = None,
    require_causal_links: bool = True,
) -> CrossLanguageProofObjectV2:
    """Build the stricter phase 144 multi-adapter closure object."""

    traces = traces or []
    evidence = evidence or []
    causal_links = causal_links or []
    required_adapter_ids = required_adapter_ids or []
    trace_ids_by_adapter, event_ids = _trace_indexes(traces)
    evidence_by_adapter: dict[str, list[AdapterEvidenceReference]] = {}
    for item in evidence:
        evidence_by_adapter.setdefault(item.adapter_id, []).append(item)

    slices = [
        CrossLanguageEvidenceSliceV2(
            adapter_id=manifest.adapter,
            language=manifest.language,
            runtime=manifest.runtime,
            module_ids=[module.module_id for module in manifest.modules],
            trace_ids=sorted(trace_ids_by_adapter.get(manifest.adapter, [])),
            evidence=sorted(
                evidence_by_adapter.get(manifest.adapter, []),
                key=lambda item: item.evidence_id,
            ),
        )
        for manifest in manifests
    ]
    blockers = _cross_language_v2_blockers(
        proof=proof,
        slices=slices,
        causal_links=causal_links,
        event_ids=event_ids,
        required_adapter_ids=required_adapter_ids,
        require_causal_links=require_causal_links,
    )
    normalized_links = [
        _causal_link_status(link, event_ids)
        for link in causal_links
    ]
    result: Literal["accepted", "refused", "unknown"] = "accepted"
    if blockers:
        result = "unknown" if any(blocker.category == "proof" for blocker in blockers) else "refused"
    return CrossLanguageProofObjectV2(
        proof_id=proof.proof_id,
        requirement_id=proof.requirement_id,
        result=result,
        closure_status="blocked" if blockers else "closed",
        proof_status=proof.status,
        adapter_count=len(slices),
        language_count=len({item.language for item in slices}),
        slices=slices,
        causal_links=normalized_links,
        blockers=blockers,
        input_hashes={
            "proof_object": sha256_json(proof),
            "source_manifests": sha256_json(manifests),
            "traces": sha256_json(traces),
            "evidence": sha256_json(evidence),
            "causal_links": sha256_json(causal_links),
            "required_adapter_ids": sha256_json(required_adapter_ids),
        },
    )


def _trace_indexes(
    traces: list[NormalizedTraceArtifact],
) -> tuple[dict[str, list[str]], set[tuple[str, str]]]:
    trace_ids_by_adapter: dict[str, list[str]] = {}
    event_ids: set[tuple[str, str]] = set()
    for artifact in traces:
        for trace in artifact.root:
            trace_ids_by_adapter.setdefault(trace.adapter_id, []).append(trace.trace_id)
            for event in trace.events:
                event_ids.add((trace.trace_id, event.event_id))
    return trace_ids_by_adapter, event_ids


def _cross_language_v2_blockers(
    *,
    proof: ProofObject,
    slices: list[CrossLanguageEvidenceSliceV2],
    causal_links: list[CausalTraceLinkV2],
    event_ids: set[tuple[str, str]],
    required_adapter_ids: list[str],
    require_causal_links: bool,
) -> list[CrossLanguageProofBlocker]:
    blockers: list[CrossLanguageProofBlocker] = []
    if proof.status != "closed":
        blockers.append(
            CrossLanguageProofBlocker(
                category="proof",
                subject=proof.proof_id,
                message="cross-language closure requires a closed proof object",
            )
        )
    if len({item.language for item in slices}) < 2:
        blockers.append(
            CrossLanguageProofBlocker(
                category="language_diversity",
                message="at least two source languages are required",
            )
        )
    present_adapter_ids = {item.adapter_id for item in slices}
    for adapter_id in sorted(set(required_adapter_ids) - present_adapter_ids):
        blockers.append(
            CrossLanguageProofBlocker(
                category="adapter_evidence",
                subject=adapter_id,
                message="required adapter evidence slice is missing",
            )
        )
    for item in slices:
        if not item.evidence:
            blockers.append(
                CrossLanguageProofBlocker(
                    category="adapter_evidence",
                    subject=item.adapter_id,
                    message="adapter slice has no retained evidence reference",
                )
            )
        if any(ref.replay_bundle_hash is None for ref in item.evidence):
            blockers.append(
                CrossLanguageProofBlocker(
                    category="replay_bundle",
                    subject=item.adapter_id,
                    message="adapter evidence is missing replay bundle hash",
                )
            )
    if require_causal_links and not causal_links:
        blockers.append(
            CrossLanguageProofBlocker(
                category="trace_link",
                message="at least one required causal trace link is required",
            )
        )
    for link in causal_links:
        status = _causal_link_status(link, event_ids).status
        if link.required and status != "satisfied":
            blockers.append(
                CrossLanguageProofBlocker(
                    category="trace_link",
                    subject=link.link_id,
                    message=f"required causal trace link is {status}",
                )
            )
    return blockers


def _causal_link_status(
    link: CausalTraceLinkV2,
    event_ids: set[tuple[str, str]],
) -> CausalTraceLinkV2:
    source_present = (link.from_trace_id, link.from_event_id) in event_ids
    target_present = (link.to_trace_id, link.to_event_id) in event_ids
    if not source_present:
        return link.model_copy(update={"status": "missing_source"})
    if not target_present:
        return link.model_copy(update={"status": "missing_target"})
    return link.model_copy(update={"status": "satisfied"})
