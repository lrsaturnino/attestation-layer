from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from .jsonutil import sha256_json
from .models import NormalizedTraceArtifact
from .proof_closure import ProofObject
from .source_adapter import SourceManifest


CROSS_LANGUAGE_SCHEMA_VERSION = "0.1"
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

    category: Literal["proof", "language_diversity", "trace_link"]
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
