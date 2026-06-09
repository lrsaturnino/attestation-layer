from __future__ import annotations

import json
import re
from pathlib import Path, PurePosixPath
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from .impact import ImpactAnalysisArtifact
from .jsonutil import sha256_json, sha256_text
from .llm_client import LlmClient
from .models import NormalizedTraceArtifact, RequirementIRV2
from .source_adapter import CodePresentation
from .system_spec import (
    SpecTraceContract,
    SpecTraceExpectation,
    SystemSpecEntry,
    SystemSpecRegistry,
    build_system_spec_registry_report,
)
from .trace_replay import SpecTraceReplayReport, TraceReplayReport, replay_spec_against_traces


SPEC_EXTRACTION_SCHEMA_VERSION = "0.1"
SPEC_EXTRACTION_V2_SCHEMA_VERSION = "0.2"
SPEC_EXTRACTION_GO_SCHEMA_VERSION = "0.1"


class CandidateSpecProvenance(BaseModel):
    model_config = ConfigDict(extra="forbid")

    extraction_tool: str = "nlreq.spec_extraction"
    extraction_version: str = SPEC_EXTRACTION_SCHEMA_VERSION
    requirement_id: str
    impact_hash: str
    code_presentation_hash: str | None = None
    trace_replay_hash: str | None = None
    llm_draft_used: bool = False
    metadata: dict[str, str] = Field(default_factory=dict)


class CandidateSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    candidate_id: str
    module_id: str
    formalism: Literal["tla", "smt", "ltl", "alloy", "lean", "other"] = "tla"
    path: str
    review_status: Literal["draft"] = "draft"
    freshness: Literal["unknown"] = "unknown"
    content: str
    content_hash: str
    trace_grounding_status: Literal["passed", "blocked", "missing"]
    gaps: list[str] = Field(default_factory=list)
    provenance: CandidateSpecProvenance


class SpecExtractionWorkbenchReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["0.1"] = SPEC_EXTRACTION_SCHEMA_VERSION
    requirement_id: str
    result: Literal["candidates", "none"]
    candidates: list[CandidateSpec] = Field(default_factory=list)


class CandidateSpecStructuralValidation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    candidate_id: str
    status: Literal["valid", "invalid"]
    issues: list[str] = Field(default_factory=list)
    checked_invariants: list[str] = Field(default_factory=list)
    trace_validation_required: bool = True


class SpeculaExtractionIntegrationReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["0.2"] = SPEC_EXTRACTION_V2_SCHEMA_VERSION
    requirement_id: str
    result: Literal["candidates", "blocked", "none"]
    trust_boundary: Literal["candidate_only"] = "candidate_only"
    trace_validation_required: bool = True
    candidates: list[CandidateSpec] = Field(default_factory=list)
    structural_validations: list[CandidateSpecStructuralValidation] = Field(default_factory=list)
    blockers: list[str] = Field(default_factory=list)


class CandidateSpecReviewChecklistItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    item_id: str
    status: Literal["approved", "rejected"]
    notes: str | None = None


class CandidateSpecReviewReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["0.2"] = SPEC_EXTRACTION_V2_SCHEMA_VERSION
    candidate_id: str
    decision: Literal["promoted", "rejected", "blocked"]
    reviewer_id: str
    reviewed_at: str
    candidate_hash: str
    approved_hash: str | None = None
    promoted_spec: SystemSpecEntry | None = None
    rejection_reasons: list[str] = Field(default_factory=list)
    blockers: list[str] = Field(default_factory=list)
    checklist: list[CandidateSpecReviewChecklistItem] = Field(default_factory=list)


def build_spec_extraction_workbench_report(
    *,
    requirement: RequirementIRV2,
    impact: ImpactAnalysisArtifact,
    registry: SystemSpecRegistry,
    project_root: Path,
    code_presentation: CodePresentation | None = None,
    trace_replay: TraceReplayReport | None = None,
    traces: NormalizedTraceArtifact | None = None,
    llm: LlmClient | None = None,
) -> SpecExtractionWorkbenchReport:
    registry_report = build_system_spec_registry_report(
        registry,
        project_root=project_root,
        module_ids=impact.affected_modules,
    )
    fresh_modules = {
        module_id
        for status in registry_report.statuses
        if status.status == "fresh"
        for module_id in status.module_ids
    }
    # A Go module gets a REAL Specula candidate S read from its source (LLM) and trace-validated
    # against its real Go traces (PC-8), not the vacuous `CandidateInvariant == TRUE` placeholder —
    # but only when the caller supplies the offline LLM client + the real traces the extraction needs.
    # Without them (or for any other language) the generic draft placeholder is produced, which carries
    # `trace_grounding_status="missing"` and so is blocked, never falsely promoted, by the integration
    # gate. The Go candidate's `trace_grounding_status` is set by the trace replay inside
    # extract_go_candidate_spec, so the SAME integration gate blocks a paper-only candidate.
    go_extraction = (
        impact.language == "go"
        and traces is not None
        and llm is not None
        and code_presentation is not None
    )
    candidates: list[CandidateSpec] = []
    for module_id in impact.affected_modules:
        if module_id in fresh_modules:
            continue
        if go_extraction:
            candidates.append(
                extract_go_candidate_spec(
                    requirement=requirement,
                    module_id=module_id,
                    impact=impact,
                    code_presentation=code_presentation,
                    traces=traces,
                    llm=llm,
                ).candidate
            )
        else:
            candidates.append(
                _candidate_for_module(
                    module_id,
                    requirement=requirement,
                    impact=impact,
                    code_presentation=code_presentation,
                    trace_replay=trace_replay,
                )
            )
    return SpecExtractionWorkbenchReport(
        requirement_id=requirement.requirement_id,
        result="candidates" if candidates else "none",
        candidates=candidates,
    )


def build_specula_extraction_integration_report(
    *,
    requirement: RequirementIRV2,
    impact: ImpactAnalysisArtifact,
    registry: SystemSpecRegistry,
    project_root: Path,
    code_presentation: CodePresentation | None = None,
    trace_replay: TraceReplayReport | None = None,
    traces: NormalizedTraceArtifact | None = None,
    llm: LlmClient | None = None,
) -> SpeculaExtractionIntegrationReport:
    workbench = build_spec_extraction_workbench_report(
        requirement=requirement,
        impact=impact,
        registry=registry,
        project_root=project_root,
        code_presentation=code_presentation,
        trace_replay=trace_replay,
        traces=traces,
        llm=llm,
    )
    validations = [
        validate_candidate_spec_structure(candidate) for candidate in workbench.candidates
    ]
    blockers: list[str] = []
    for validation in validations:
        blockers.extend(
            f"{validation.candidate_id}: {issue}" for issue in validation.issues
        )
    for candidate in workbench.candidates:
        if candidate.trace_grounding_status != "passed":
            # Surface WHY trace validation did not pass — the candidate's own gaps name it (e.g. for a
            # paper-only Go candidate, "trace obligations are not reproduced by the code's real
            # traces") — while keeping the stable "trace validation has not passed" lead phrase.
            why = "; ".join(candidate.gaps) if candidate.gaps else candidate.trace_grounding_status
            blockers.append(
                f"{candidate.candidate_id}: trace validation has not passed ({why})"
            )
    if not workbench.candidates:
        result: Literal["candidates", "blocked", "none"] = "none"
    else:
        result = "blocked" if blockers else "candidates"
    return SpeculaExtractionIntegrationReport(
        requirement_id=requirement.requirement_id,
        result=result,
        candidates=workbench.candidates,
        structural_validations=validations,
        blockers=blockers,
    )


def candidate_to_draft_spec_entry(candidate: CandidateSpec) -> SystemSpecEntry:
    return SystemSpecEntry(
        spec_id=f"candidate:{candidate.candidate_id}",
        module_ids=[candidate.module_id],
        formalism=candidate.formalism,
        path=candidate.path,
        version="candidate",
        review_status="draft",
        freshness="unknown",
        recorded_hash=candidate.content_hash,
        metadata={"source": "spec_extraction_workbench"},
    )


def promote_candidate_spec(
    candidate: CandidateSpec,
    *,
    approved_hash: str,
    version: str,
) -> SystemSpecEntry:
    if approved_hash != candidate.content_hash:
        raise ValueError("approved candidate hash does not match extracted content")
    return SystemSpecEntry(
        spec_id=f"spec:{candidate.module_id}",
        module_ids=[candidate.module_id],
        formalism=candidate.formalism,
        path=candidate.path,
        version=version,
        review_status="reviewed",
        freshness="fresh",
        recorded_hash=approved_hash,
        metadata={"source": "spec_extraction_workbench", "candidate_id": candidate.candidate_id},
    )


def validate_candidate_spec_structure(
    candidate: CandidateSpec,
) -> CandidateSpecStructuralValidation:
    issues: list[str] = []
    checked = [
        "candidate remains draft",
        "content hash matches content",
        "TLA module envelope is present",
    ]
    if candidate.review_status != "draft":
        issues.append("candidate review_status must remain draft before promotion")
    if candidate.content_hash != sha256_text(candidate.content):
        issues.append("candidate content_hash does not match content")
    if candidate.formalism == "tla":
        if not candidate.content.startswith("---- MODULE "):
            issues.append("candidate TLA content is missing module header")
        if "====" not in candidate.content:
            issues.append("candidate TLA content is missing module terminator")
    return CandidateSpecStructuralValidation(
        candidate_id=candidate.candidate_id,
        status="invalid" if issues else "valid",
        issues=issues,
        checked_invariants=checked,
    )


def promote_candidate_spec_with_review(
    candidate: CandidateSpec,
    *,
    approved_hash: str,
    version: str,
    reviewer_id: str,
    reviewed_at: str,
    checklist: list[CandidateSpecReviewChecklistItem] | None = None,
) -> CandidateSpecReviewReport:
    checklist = checklist or [
        CandidateSpecReviewChecklistItem(
            item_id="semantic-review",
            status="approved",
            notes="reviewer accepted generated spec semantics",
        ),
        CandidateSpecReviewChecklistItem(
            item_id="trace-grounding",
            status="approved",
            notes="trace grounding passed before promotion",
        ),
    ]
    blockers: list[str] = []
    validation = validate_candidate_spec_structure(candidate)
    blockers.extend(validation.issues)
    if approved_hash != candidate.content_hash:
        blockers.append("approved candidate hash does not match extracted content")
    if candidate.trace_grounding_status != "passed":
        blockers.append("candidate trace grounding has not passed")
    if any(item.status != "approved" for item in checklist):
        blockers.append("review checklist contains rejected items")
    promoted = None
    if not blockers:
        promoted = promote_candidate_spec(
            candidate,
            approved_hash=approved_hash,
            version=version,
        )
    return CandidateSpecReviewReport(
        candidate_id=candidate.candidate_id,
        decision="blocked" if blockers else "promoted",
        reviewer_id=reviewer_id,
        reviewed_at=reviewed_at,
        candidate_hash=candidate.content_hash,
        approved_hash=approved_hash,
        promoted_spec=promoted,
        blockers=blockers,
        checklist=checklist,
    )


def reject_candidate_spec(
    candidate: CandidateSpec,
    *,
    reviewer_id: str,
    reviewed_at: str,
    rejection_reasons: list[str],
    checklist: list[CandidateSpecReviewChecklistItem] | None = None,
) -> CandidateSpecReviewReport:
    return CandidateSpecReviewReport(
        candidate_id=candidate.candidate_id,
        decision="rejected",
        reviewer_id=reviewer_id,
        reviewed_at=reviewed_at,
        candidate_hash=candidate.content_hash,
        rejection_reasons=rejection_reasons,
        checklist=checklist or [],
    )


# --- PC-8: Specula-style candidate S extraction for Go, gated by trace validation ----------------
# The shared `_candidate_for_module` below emits a vacuous draft placeholder for languages without a
# Specula extractor. The Go path here instead extracts a REAL candidate S: an LLM reads the module's
# SOURCE and proposes candidate invariants plus the trace-observable obligations those invariants
# imply — derived from the code, NEVER from the trace. The trace is the independent validator: the
# candidate is promotable only if its obligations are REPRODUCED by the module's real Go traces
# (PC-7), reusing the PC-11 spec↔trace replay. A paper-only candidate, asserting an operation the
# code never runs, is rejected by that guard. This is the discipline that keeps Specula from
# specifying "the paper, not the code".


class ExtractedInvariant(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    tla: str


class ExtractedTraceExpectation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    # Only the obligation kinds a runtime/trace can witness are honest for Go: an operation that runs
    # (``event_emitted``) or one that must never run (``action_never``). State-value and revert kinds
    # are EVM-shaped and out of scope for the runtime/trace projection.
    expectation_id: str
    kind: Literal["event_emitted", "action_never"]
    target: str
    description: str = ""


class ExtractedSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    module: str = ""
    invariants: list[ExtractedInvariant] = Field(default_factory=list)
    trace_expectations: list[ExtractedTraceExpectation] = Field(default_factory=list)


def parse_spec_extraction(text: str) -> ExtractedSpec:
    """Parse an UNTRUSTED LLM spec-extraction proposal into a structured :class:`ExtractedSpec`.

    Defensive because the output is untrusted (mirrors :func:`nlreq.llm_client.parse_impact_estimate`):
    it strips a surrounding markdown code fence, tolerates malformed JSON by yielding an empty
    extraction (no invariants, no obligations — which the trace gate rejects rather than promotes),
    and drops individual malformed entries and any trace obligation whose kind a runtime/trace cannot
    witness. It NEVER raises on malformed output.
    """
    stripped = text.strip()
    fence = re.match(r"^```(?:json)?\s*(.*?)\s*```$", stripped, re.DOTALL)
    if fence:
        stripped = fence.group(1).strip()
    try:
        payload = json.loads(stripped)
    except (ValueError, TypeError):
        return ExtractedSpec()
    if not isinstance(payload, dict):
        return ExtractedSpec()
    invariants: list[ExtractedInvariant] = []
    for entry in payload.get("invariants", []) or []:
        if not isinstance(entry, dict):
            continue
        name = entry.get("name")
        tla = entry.get("tla")
        if isinstance(name, str) and name.strip() and isinstance(tla, str) and tla.strip():
            invariants.append(ExtractedInvariant(name=name.strip(), tla=tla.strip()))
    expectations: list[ExtractedTraceExpectation] = []
    for entry in payload.get("trace_expectations", []) or []:
        if not isinstance(entry, dict):
            continue
        kind = entry.get("kind")
        target = entry.get("target")
        if kind not in {"event_emitted", "action_never"}:
            continue
        if not isinstance(target, str) or not target.strip():
            continue
        expectation_id = entry.get("expectation_id")
        if not isinstance(expectation_id, str) or not expectation_id.strip():
            expectation_id = f"{kind}:{target.strip()}"
        description = entry.get("description")
        expectations.append(
            ExtractedTraceExpectation(
                expectation_id=expectation_id.strip(),
                kind=kind,
                target=target.strip(),
                description=description.strip() if isinstance(description, str) else "",
            )
        )
    module = payload.get("module")
    return ExtractedSpec(
        module=module.strip() if isinstance(module, str) else "",
        invariants=invariants,
        trace_expectations=expectations,
    )


class GoCandidateExtractionReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["0.1"] = SPEC_EXTRACTION_GO_SCHEMA_VERSION
    requirement_id: str
    module_id: str
    candidate: CandidateSpec
    trace_contract: SpecTraceContract
    spec_trace_replay: SpecTraceReplayReport
    promotable: bool
    rejection_reasons: list[str] = Field(default_factory=list)


def extract_go_candidate_spec(
    *,
    requirement: RequirementIRV2,
    module_id: str,
    impact: ImpactAnalysisArtifact,
    code_presentation: CodePresentation,
    traces: NormalizedTraceArtifact,
    llm: LlmClient,
) -> GoCandidateExtractionReport:
    """Extract a candidate Go ``S`` from source (LLM) and validate it against the real traces (PC-8).

    The candidate's invariants and trace-observable obligations are proposed by the LLM reading the
    module's SOURCE; the obligations are then replayed against the module's real Go traces (PC-7) with
    the PC-11 spec↔trace validator. ``promotable`` is true only when every obligation is REPRODUCED by
    the traces — so a paper-only candidate (asserting an operation the code never runs) is not
    promotable, and a candidate that declares no trace-observable obligation cannot be validated and is
    rejected. The returned candidate carries ``trace_grounding_status`` so the existing
    :func:`promote_candidate_spec_with_review` gate promotes a reproduced candidate and blocks a
    paper-only one.
    """
    raw = llm.extract_spec_invariants(
        module_id=module_id,
        code_presentation=_serialize_presentation(code_presentation),
        language="go",
    )
    extracted = parse_spec_extraction(raw)
    content = _go_candidate_tla_content(module_id, requirement, extracted)
    contract = SpecTraceContract(
        spec_id=f"candidate:{requirement.requirement_id}:{module_id}",
        module_ids=[module_id],
        expectations=[
            SpecTraceExpectation(
                expectation_id=expectation.expectation_id,
                kind=expectation.kind,
                target=expectation.target,
                description=expectation.description,
            )
            for expectation in extracted.trace_expectations
        ],
        provenance="specula_extracted",
    )
    replay = replay_spec_against_traces(contract=contract, traces=traces)
    rejection_reasons = _spec_trace_rejection_reasons(replay)
    promotable = not rejection_reasons
    trace_status: Literal["passed", "blocked", "missing"] = "passed" if promotable else "blocked"
    candidate = CandidateSpec(
        candidate_id=f"{requirement.requirement_id}:{module_id}",
        module_id=module_id,
        path=f"specs/candidates/{_safe_path_part(module_id)}.tla",
        content=content,
        content_hash=sha256_text(content),
        trace_grounding_status=trace_status,
        gaps=_go_candidate_gaps(extracted, promotable),
        provenance=CandidateSpecProvenance(
            requirement_id=requirement.requirement_id,
            impact_hash=sha256_json(impact),
            code_presentation_hash=sha256_json(code_presentation),
            trace_replay_hash=sha256_json(replay),
            llm_draft_used=True,
            metadata={"module_id": module_id, "extraction": "specula_go"},
        ),
    )
    return GoCandidateExtractionReport(
        requirement_id=requirement.requirement_id,
        module_id=module_id,
        candidate=candidate,
        trace_contract=contract,
        spec_trace_replay=replay,
        promotable=promotable,
        rejection_reasons=rejection_reasons,
    )


def _spec_trace_rejection_reasons(replay: SpecTraceReplayReport) -> list[str]:
    """Reasons a candidate is NOT promotable: any obligation the traces do not reproduce, or none.

    A candidate with no trace-observable obligation cannot be validated against the code's traces at
    all, so it is rejected as ungrounded rather than promoted on an empty contract.
    """
    if not replay.observations:
        return ["candidate declares no trace-observable obligation to validate against the code"]
    reasons: list[str] = []
    for observation in replay.observations:
        if observation.outcome != "satisfied":
            reasons.append(
                f"{observation.expectation_id}: {observation.outcome} — {observation.reason}"
            )
    return reasons


def _go_candidate_tla_content(
    module_id: str, requirement: RequirementIRV2, extracted: ExtractedSpec
) -> str:
    module_name = "Candidate_" + _safe_tla_name(module_id)
    lines = [
        f"---- MODULE {module_name} ----",
        f"\\* Specula-extracted candidate S for Go module {module_id} (untrusted; trace-gated).",
        f"\\* Requirement: {requirement.requirement_id}",
    ]
    for expectation in extracted.trace_expectations:
        lines.append(f"\\* trace obligation [{expectation.kind}]: {expectation.target}")
    for invariant in extracted.invariants:
        lines.append(f"{_safe_tla_name(invariant.name)} == {invariant.tla}")
    if extracted.invariants:
        conjuncts = " /\\ ".join(_safe_tla_name(inv.name) for inv in extracted.invariants)
        lines.append(f"CandidateInvariant == {conjuncts}")
    else:
        lines.append("\\* no invariants were extracted from the source")
    lines.append("====")
    return "\n".join(lines) + "\n"


def _go_candidate_gaps(extracted: ExtractedSpec, promotable: bool) -> list[str]:
    gaps = ["candidate spec is draft and cannot satisfy coverage until reviewed"]
    if not extracted.invariants:
        gaps.append("no invariants were extracted from the source")
    if not promotable:
        gaps.append("trace obligations are not reproduced by the code's real traces")
    return gaps


def _serialize_presentation(code_presentation: CodePresentation) -> str:
    parts: list[str] = []
    for snippet in code_presentation.snippets:
        path = snippet.get("path", "")
        content = snippet.get("content", "")
        parts.append(f"// {path}\n{content}" if path else content)
    return "\n\n".join(parts)


def _candidate_for_module(
    module_id: str,
    *,
    requirement: RequirementIRV2,
    impact: ImpactAnalysisArtifact,
    code_presentation: CodePresentation | None,
    trace_replay: TraceReplayReport | None,
) -> CandidateSpec:
    path = f"specs/candidates/{_safe_path_part(module_id)}.tla"
    content = _candidate_tla_content(module_id, requirement)
    gaps = [
        "candidate spec is draft and cannot satisfy coverage",
        "semantic obligations require human review",
    ]
    if code_presentation is None:
        gaps.append("code presentation was not supplied")
    if trace_replay is None:
        gaps.append("trace grounding was not supplied")
    trace_status = trace_replay.result if trace_replay is not None else "missing"
    return CandidateSpec(
        candidate_id=f"{requirement.requirement_id}:{module_id}",
        module_id=module_id,
        path=path,
        content=content,
        content_hash=sha256_text(content),
        trace_grounding_status=trace_status,
        gaps=gaps,
        provenance=CandidateSpecProvenance(
            requirement_id=requirement.requirement_id,
            impact_hash=sha256_json(impact),
            code_presentation_hash=sha256_json(code_presentation)
            if code_presentation is not None
            else None,
            trace_replay_hash=sha256_json(trace_replay) if trace_replay is not None else None,
            metadata={"module_id": module_id},
        ),
    )


def _candidate_tla_content(module_id: str, requirement: RequirementIRV2) -> str:
    module_name = "Candidate_" + _safe_tla_name(module_id)
    return (
        f"---- MODULE {module_name} ----\n"
        f"\\* Draft candidate spec for module {module_id}\n"
        f"\\* Requirement: {requirement.requirement_id}\n\n"
        "CandidateInvariant == TRUE\n\n"
        "====\n"
    )


def _safe_tla_name(value: str) -> str:
    cleaned = "".join(char if char.isalnum() else "_" for char in value)
    if not cleaned:
        return "Module"
    if cleaned[0].isdigit():
        return "_" + cleaned
    return cleaned


def _safe_path_part(value: str) -> str:
    cleaned = PurePosixPath(_safe_tla_name(value)).name
    return cleaned or "module"
