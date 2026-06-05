from __future__ import annotations

from pathlib import Path
from typing import Any, Iterable, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from .adoption import find_package_dirs
from .coverage_alignment import SpecCoverageReport
from .jsonutil import sha256_json, sha256_text
from .models import (
    BackendResult,
    Counterexample,
    EvidenceLevel,
    NormalizedTrace,
    NormalizedTraceArtifact,
    RequirementIR,
    TraceEvent,
)
from .spec_freshness import SpecFreshnessDriftCiReport
from .trace_replay import TraceReplayReport, build_trace_replay_report


TRACE_VALIDATION_VERSION = "0.1"
TRACE_VALIDATOR_VERSION = "0.1"
TRACE_VALIDATION_GATE_VERSION = "0.2"
ACCEPTABLE_REDACTION_STATUSES = {"redacted", "not_required"}


class TraceValidationResultsArtifact(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["0.1"] = TRACE_VALIDATION_VERSION
    adapter: Literal["trace"] = "trace"
    results: list[BackendResult] = Field(default_factory=list)
    counterexamples: list[Counterexample] = Field(default_factory=list)


class TraceValidationGateOutcome(BaseModel):
    model_config = ConfigDict(extra="forbid")

    trace_id: str
    requirement_id: str
    status: Literal[
        "satisfied",
        "violation",
        "coverage_gap",
        "lossy",
        "stale",
        "unsupported",
    ]
    closure_effect: Literal["allow", "block", "review"]
    evidence_label: Literal["trace_grounding", "none"]
    event_ids: list[str] = Field(default_factory=list)
    reason: str | None = None
    counterexample_id: str | None = None
    warnings: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class TraceValidationGateReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["0.2"] = TRACE_VALIDATION_GATE_VERSION
    requirement_id: str
    result: Literal["satisfied", "blocked", "needs_review"]
    closure_effect: Literal["allow", "block", "review"]
    evidence_label: Literal["trace_grounding", "none"]
    outcomes: list[TraceValidationGateOutcome] = Field(default_factory=list)
    counterexamples: list[Counterexample] = Field(default_factory=list)
    refusal_reasons: list[str] = Field(default_factory=list)
    replay: TraceReplayReport


def build_trace_validation_report(
    packages_dir: Path,
    *,
    trace_artifact_paths: Iterable[Path],
    requirement_ids: list[str] | None = None,
) -> dict[str, Any]:
    packages = _load_packages(packages_dir)
    selected = set(requirement_ids or [])
    results: list[BackendResult] = []
    counterexamples: list[Counterexample] = []
    findings: list[dict[str, Any]] = []
    artifact_summaries: list[dict[str, Any]] = []

    for trace_artifact_path in trace_artifact_paths:
        path = Path(trace_artifact_path)
        try:
            artifact = NormalizedTraceArtifact.model_validate_json(path.read_text())
        except (OSError, ValidationError, ValueError) as exc:
            findings.append(
                _finding(
                    "error",
                    "invalid_trace_artifact",
                    None,
                    path.as_posix(),
                    str(exc),
                )
            )
            artifact_summaries.append(
                {
                    "path": path.as_posix(),
                    "status": "invalid",
                    "trace_count": 0,
                }
            )
            continue

        trace_count = 0
        for trace in artifact.root:
            trace_count += 1
            trace_requirement_ids = _trace_requirement_ids(trace)
            if selected:
                trace_requirement_ids = [
                    requirement_id
                    for requirement_id in trace_requirement_ids
                    if requirement_id in selected
                ]
            if not trace_requirement_ids:
                findings.append(
                    _finding(
                        "warning",
                        "trace_missing_requirement_ids",
                        None,
                        path.as_posix(),
                        f"trace {trace.trace_id} has no selected requirement ids",
                    )
                )
                continue
            for requirement_id in trace_requirement_ids:
                package = packages.get(requirement_id)
                if package is None:
                    findings.append(
                        _finding(
                            "warning",
                            "trace_unknown_requirement",
                            requirement_id,
                            path.as_posix(),
                            f"trace {trace.trace_id} references unknown requirement {requirement_id}",
                        )
                    )
                    continue
                result, counterexample = _validate_trace_for_requirement(
                    trace,
                    path=path,
                    ir=package["ir"],
                    package_hash=package["hash"],
                )
                results.append(result)
                if counterexample is not None:
                    counterexamples.append(counterexample)
                findings.extend(_findings_for_result(result, path))
        artifact_summaries.append(
            {
                "path": path.as_posix(),
                "status": "valid",
                "trace_count": trace_count,
            }
        )

    artifact = TraceValidationResultsArtifact(
        results=results,
        counterexamples=counterexamples,
    )
    return {
        "report_version": TRACE_VALIDATION_VERSION,
        "mode": "trace_validation",
        "result": "report_only",
        "summary": {
            "artifacts": len(artifact_summaries),
            "results": len(results),
            "valid": sum(1 for result in results if result.status == "valid"),
            "invalid": sum(1 for result in results if result.status in {"invalid", "counterexample"}),
            "unsupported": sum(1 for result in results if result.status == "unsupported"),
            "needs_review": sum(1 for result in results if result.status == "needs_review"),
            "counterexamples": len(counterexamples),
            "findings": len(findings),
        },
        "artifacts": artifact_summaries,
        "results": [result.model_dump(mode="json", exclude_none=True) for result in artifact.results],
        "counterexamples": [
            counterexample.model_dump(mode="json", exclude_none=True)
            for counterexample in artifact.counterexamples
        ],
        "findings": findings,
    }


def build_trace_validation_gate_report(
    *,
    requirement,
    traces: NormalizedTraceArtifact,
    coverage: SpecCoverageReport,
    freshness: SpecFreshnessDriftCiReport | None = None,
    high_assurance: bool = True,
) -> TraceValidationGateReport:
    replay = build_trace_replay_report(
        requirement=requirement,
        traces=traces,
        coverage=coverage,
    )
    stale_modules = [
        status.module_id
        for status in freshness.statuses
        if status.closure_effect == "block"
    ] if freshness is not None else []
    outcomes: list[TraceValidationGateOutcome] = []
    for observation in replay.observations:
        counterexample = _counterexample_for_observation(
            observation.event_ids,
            replay.counterexamples,
        )
        outcome = _gate_outcome_for_observation(
            observation,
            coverage=coverage,
            stale_modules=stale_modules,
            counterexample=counterexample,
            high_assurance=high_assurance,
        )
        outcomes.append(outcome)
    closure_effect = _trace_gate_closure(outcomes)
    refusal_reasons = [
        outcome.reason or outcome.status
        for outcome in outcomes
        if outcome.closure_effect != "allow"
    ]
    return TraceValidationGateReport(
        requirement_id=requirement.requirement_id,
        result="satisfied" if closure_effect == "allow" else ("blocked" if closure_effect == "block" else "needs_review"),
        closure_effect=closure_effect,
        evidence_label="trace_grounding" if closure_effect == "allow" else "none",
        outcomes=outcomes,
        counterexamples=replay.counterexamples,
        refusal_reasons=refusal_reasons,
        replay=replay,
    )


def trace_validation_markdown(report: dict[str, Any]) -> str:
    summary = report["summary"]
    lines = [
        "# NLReq Trace Validation Report",
        "",
        f"Result: `{report['result']}`",
        "",
        "## Summary",
        "",
        f"- Results: {summary['results']}",
        f"- Valid: {summary['valid']}",
        f"- Invalid: {summary['invalid']}",
        f"- Unsupported: {summary['unsupported']}",
        f"- Needs review: {summary['needs_review']}",
        f"- Counterexamples: {summary['counterexamples']}",
        f"- Findings: {summary['findings']}",
        "",
        "## Results",
        "",
    ]
    results = report.get("results", [])
    if not results:
        lines.append("No trace-validation results.")
    else:
        lines.extend(
            [
                "| Status | Requirement | Trace | Validator |",
                "|---|---|---|---|",
            ]
        )
        for result in results:
            details = result.get("details", {})
            lines.append(
                "| {status} | {requirement_id} | {trace_id} | {validator_id} |".format(
                    status=result.get("status"),
                    requirement_id=details.get("requirement_id") or "-",
                    trace_id=details.get("trace_id") or "-",
                    validator_id=details.get("validator_id") or "-",
                )
            )
    if report.get("findings"):
        lines.extend(["", "## Findings", ""])
        lines.extend(
            [
                "| Severity | Category | Requirement | Message |",
                "|---|---|---|---|---|",
            ]
        )
        for finding in report["findings"]:
            lines.append(
                "| {severity} | {category} | {requirement_id} | {message} |".format(
                    severity=finding["severity"],
                    category=finding["category"],
                    requirement_id=finding.get("requirement_id") or "-",
                    message=_escape_markdown_table(finding["message"]),
                )
            )
    return "\n".join(lines) + "\n"


def trace_validation_gate_markdown(report: TraceValidationGateReport) -> str:
    lines = [
        "# NLReq Trace Validation Gate Report",
        "",
        f"Result: `{report.result}`",
        f"Evidence: `{report.evidence_label}`",
        "",
        "| Status | Requirement | Trace | Closure | Reason |",
        "|---|---|---|---|---|",
    ]
    for outcome in report.outcomes:
        lines.append(
            "| {status} | {requirement_id} | {trace_id} | {closure} | {reason} |".format(
                status=outcome.status,
                requirement_id=outcome.requirement_id,
                trace_id=outcome.trace_id,
                closure=outcome.closure_effect,
                reason=_escape_markdown_table(outcome.reason or "-"),
            )
        )
    return "\n".join(lines) + "\n"


def _validate_trace_for_requirement(
    trace: NormalizedTrace,
    *,
    path: Path,
    ir: RequirementIR,
    package_hash: str,
) -> tuple[BackendResult, Counterexample | None]:
    base_details = _base_details(trace, path=path, ir=ir, package_hash=package_hash)
    redaction_status = _redaction_status(trace)
    if redaction_status not in ACCEPTABLE_REDACTION_STATUSES:
        return (
            BackendResult(
                backend="trace",
                status="needs_review",
                # No trace was validated — a non-gateable redaction status blocks before any
                # observed→fragment mapping is built — so this result claims no evidence level.
                evidence_level=None,
                details={
                    **base_details,
                    "reason": "trace redaction status is not gateable",
                    "redaction_status": redaction_status,
                },
            ),
            None,
        )

    if _supports_auth_rejection_before_state_change(ir):
        return _validate_auth_rejection_before_state_change(trace, ir, base_details)
    if _supports_success_emits_event(ir):
        return _validate_success_emits_event(trace, ir, base_details)
    if _supports_absence_validator(ir):
        return _validate_forbidden_event_absent(trace, ir, base_details)

    return (
        BackendResult(
            backend="trace",
            status="unsupported",
            # No validator ran for this claim shape, so nothing was mapped from the trace; the
            # result carries no evidence level rather than over-claim TRACE_VALIDATED.
            evidence_level=None,
            details={
                **base_details,
                "reason": "requirement claim shape has no trace validator",
                "claim_kind": ir.claim.kind,
                "expected_kind": ir.claim.expected.kind,
            },
        ),
        None,
    )


def _validate_auth_rejection_before_state_change(
    trace: NormalizedTrace,
    ir: RequirementIR,
    details: dict[str, Any],
) -> tuple[BackendResult, Counterexample | None]:
    state_change = ir.claim.expected.target
    rejection_events = [event for event in trace.events if _is_rejection_event(event, ir.claim.action)]
    forbidden_events = [event for event in trace.events if event.action == state_change]
    if rejection_events and not forbidden_events:
        return (
            BackendResult(
                backend="trace",
                status="valid",
                evidence_level=EvidenceLevel.TRACE_VALIDATED,
                details={
                    **details,
                    "validator_id": "authorization-before-state-change",
                    "observed_events": [event.action for event in trace.events],
                    "forbidden_events_absent": [state_change],
                    "trace_mapping": _trace_mapping(
                        validator_id="authorization-before-state-change",
                        trace=trace,
                        ir=ir,
                        fragment={"forbidden_events_absent": [state_change]},
                    ),
                },
            ),
            None,
        )

    reason = "state-change event was observed" if forbidden_events else "rejection event was not observed"
    counterexample = _counterexample(
        trace,
        ir,
        validator_id="authorization-before-state-change",
        reason=reason,
        expected={
            "rejection_observed": True,
            "forbidden_events_absent": [state_change],
        },
        actual={
            "observed_events": [event.action for event in trace.events],
            "forbidden_events": [event.action for event in forbidden_events],
        },
    )
    return (
        BackendResult(
            backend="trace",
            status="counterexample",
            evidence_level=EvidenceLevel.TRACE_VALIDATED,
            details={
                **details,
                "validator_id": "authorization-before-state-change",
                "reason": reason,
                "counterexample_id": counterexample.counterexample_id,
                "trace_mapping": _trace_mapping(
                    validator_id="authorization-before-state-change",
                    trace=trace,
                    ir=ir,
                    fragment={"forbidden_events_absent": [state_change]},
                ),
            },
        ),
        counterexample,
    )


def _validate_success_emits_event(
    trace: NormalizedTrace,
    ir: RequirementIR,
    details: dict[str, Any],
) -> tuple[BackendResult, Counterexample | None]:
    required_event = ir.claim.expected.target
    success_index = next(
        (index for index, event in enumerate(trace.events) if _is_success_event(event, ir.claim.action)),
        None,
    )
    emitted_index = next(
        (
            index
            for index, event in enumerate(trace.events)
            if event.action == required_event and (success_index is None or index >= success_index)
        ),
        None,
    )
    if success_index is not None and emitted_index is not None:
        return (
            BackendResult(
                backend="trace",
                status="valid",
                evidence_level=EvidenceLevel.TRACE_VALIDATED,
                details={
                    **details,
                    "validator_id": "successful-operation-emits-required-event",
                    "observed_events": [event.action for event in trace.events],
                    "required_event": required_event,
                    "trace_mapping": _trace_mapping(
                        validator_id="successful-operation-emits-required-event",
                        trace=trace,
                        ir=ir,
                        fragment={"required_event": required_event},
                    ),
                },
            ),
            None,
        )
    reason = "successful operation was not observed" if success_index is None else "required event was not emitted"
    counterexample = _counterexample(
        trace,
        ir,
        validator_id="successful-operation-emits-required-event",
        reason=reason,
        expected={"required_event": required_event},
        actual={"observed_events": [event.action for event in trace.events]},
    )
    return (
        BackendResult(
            backend="trace",
            status="counterexample",
            evidence_level=EvidenceLevel.TRACE_VALIDATED,
            details={
                **details,
                "validator_id": "successful-operation-emits-required-event",
                "reason": reason,
                "counterexample_id": counterexample.counterexample_id,
                "trace_mapping": _trace_mapping(
                    validator_id="successful-operation-emits-required-event",
                    trace=trace,
                    ir=ir,
                    fragment={"required_event": required_event},
                ),
            },
        ),
        counterexample,
    )


def _validate_forbidden_event_absent(
    trace: NormalizedTrace,
    ir: RequirementIR,
    details: dict[str, Any],
) -> tuple[BackendResult, Counterexample | None]:
    forbidden_event = ir.claim.expected.target
    operation_observed = any(event.action == ir.claim.action for event in trace.events)
    forbidden_events = [event for event in trace.events if event.action == forbidden_event]
    if operation_observed and not forbidden_events:
        return (
            BackendResult(
                backend="trace",
                status="valid",
                evidence_level=EvidenceLevel.TRACE_VALIDATED,
                details={
                    **details,
                    "validator_id": "forbidden-event-absent",
                    "observed_events": [event.action for event in trace.events],
                    "forbidden_events_absent": [forbidden_event],
                    "trace_mapping": _trace_mapping(
                        validator_id="forbidden-event-absent",
                        trace=trace,
                        ir=ir,
                        fragment={"forbidden_events_absent": [forbidden_event]},
                    ),
                },
            ),
            None,
        )
    reason = "forbidden event was observed" if forbidden_events else "operation window was not observed"
    counterexample = _counterexample(
        trace,
        ir,
        validator_id="forbidden-event-absent",
        reason=reason,
        expected={"forbidden_events_absent": [forbidden_event]},
        actual={"observed_events": [event.action for event in trace.events]},
    )
    return (
        BackendResult(
            backend="trace",
            status="counterexample",
            evidence_level=EvidenceLevel.TRACE_VALIDATED,
            details={
                **details,
                "validator_id": "forbidden-event-absent",
                "reason": reason,
                "counterexample_id": counterexample.counterexample_id,
                "trace_mapping": _trace_mapping(
                    validator_id="forbidden-event-absent",
                    trace=trace,
                    ir=ir,
                    fragment={"forbidden_events_absent": [forbidden_event]},
                ),
            },
        ),
        counterexample,
    )


def _supports_auth_rejection_before_state_change(ir: RequirementIR) -> bool:
    return (
        ir.claim.kind == "authorization_precondition"
        and ir.claim.expected.kind == "rejected_before"
        and ir.claim.expected.target is not None
    )


def _supports_success_emits_event(ir: RequirementIR) -> bool:
    return ir.claim.expected.kind == "emit" and ir.claim.expected.target is not None


def _supports_absence_validator(ir: RequirementIR) -> bool:
    return ir.claim.expected.kind == "not_change" and ir.claim.expected.target is not None


def _base_details(
    trace: NormalizedTrace,
    *,
    path: Path,
    ir: RequirementIR,
    package_hash: str,
) -> dict[str, Any]:
    return {
        "validator_version": TRACE_VALIDATOR_VERSION,
        "requirement_id": ir.requirement_id,
        "trace_id": trace.trace_id,
        "adapter_id": trace.adapter_id,
        "trace_artifact_path": path.as_posix(),
        "trace_hash": sha256_json(trace),
        "trace_source_hash": trace.source_hash,
        "package_hash": package_hash,
        "event_count": len(trace.events),
    }


def _trace_mapping(
    *,
    validator_id: str,
    trace: NormalizedTrace,
    ir: RequirementIR,
    fragment: dict[str, Any],
) -> dict[str, Any]:
    """The observed→fragment mapping a trace validator used to reach its verdict.

    A TRACE_VALIDATED result asserts observed runtime behavior was mapped onto the requirement's
    formal fragment. Recording that mapping — the validator that ran, the requirement fragment it
    covers, and the concrete events it read — is what makes the claim non-lossy and replayable;
    the BackendResult guard refuses TRACE_VALIDATED without it.
    """
    return {
        "validator_id": validator_id,
        "requirement_id": ir.requirement_id,
        "claim_kind": ir.claim.kind,
        "expected_kind": ir.claim.expected.kind,
        "observed_events": [event.action for event in trace.events],
        "fragment": fragment,
    }


def _counterexample(
    trace: NormalizedTrace,
    ir: RequirementIR,
    *,
    validator_id: str,
    reason: str,
    expected: Any,
    actual: Any,
) -> Counterexample:
    return Counterexample(
        counterexample_id=f"{trace.trace_id}:{ir.requirement_id}:{validator_id}",
        backend="trace",
        claim_id=ir.requirement_id,
        description=reason,
        inputs={
            "trace_id": trace.trace_id,
            "events": [
                {
                    "event_id": event.event_id,
                    "timestamp": event.timestamp,
                    "action": event.action,
                    "metadata": event.metadata,
                }
                for event in trace.events
            ],
        },
        expected=expected,
        actual=actual,
        metadata={
            "validator_id": validator_id,
            "validator_version": TRACE_VALIDATOR_VERSION,
        },
    )


def _trace_requirement_ids(trace: NormalizedTrace) -> list[str]:
    requirement_ids = trace.metadata.get("requirement_ids", [])
    if not isinstance(requirement_ids, list):
        return []
    return [str(requirement_id) for requirement_id in requirement_ids]


def _redaction_status(trace: NormalizedTrace) -> str | None:
    redaction = trace.metadata.get("redaction")
    if not isinstance(redaction, dict):
        return None
    status = redaction.get("status")
    return str(status) if status is not None else None


def _is_rejection_event(event: TraceEvent, action: str) -> bool:
    status = str(event.metadata.get("status", "")).lower()
    result = str(event.metadata.get("result", "")).lower()
    return (
        event.action in {"rejected", "request_rejected", f"{action}_rejected"}
        or status == "rejected"
        or result == "rejected"
    )


def _is_success_event(event: TraceEvent, action: str) -> bool:
    status = str(event.metadata.get("status", "")).lower()
    result = str(event.metadata.get("result", "")).lower()
    return (
        event.action in {action, f"{action}_success", f"{action}_succeeded"}
        and (not status or status in {"ok", "success", "succeeded"})
        and (not result or result in {"ok", "success", "succeeded"})
    )


def _findings_for_result(result: BackendResult, path: Path) -> list[dict[str, Any]]:
    details = result.details
    requirement_id = details.get("requirement_id")
    trace_id = details.get("trace_id")
    if result.status == "valid":
        return []
    severity = "warning" if result.status in {"unsupported", "needs_review"} else "error"
    category = {
        "counterexample": "trace_validation_counterexample",
        "invalid": "trace_validation_invalid",
        "unsupported": "trace_validation_unsupported",
        "needs_review": "trace_validation_needs_review",
        "timeout": "trace_validation_timeout",
    }.get(result.status, "trace_validation")
    reason = str(details.get("reason") or result.status)
    return [
        _finding(
            severity,
            category,
            str(requirement_id) if requirement_id else None,
            path.as_posix(),
            f"trace {trace_id} {reason}",
        )
    ]


def _load_packages(packages_dir: Path) -> dict[str, dict[str, Any]]:
    packages: dict[str, dict[str, Any]] = {}
    for package_dir in find_package_dirs(packages_dir):
        ir_path = package_dir / "requirement.ir.json"
        ir = RequirementIR.model_validate_json(ir_path.read_text())
        packages[ir.requirement_id] = {
            "path": package_dir,
            "ir": ir,
            "hash": sha256_text(ir_path.read_text()),
        }
    return packages


def _finding(
    severity: str,
    category: str,
    requirement_id: str | None,
    path: str,
    message: str,
) -> dict[str, Any]:
    return {
        "severity": severity,
        "category": category,
        "requirement_id": requirement_id,
        "path": path,
        "message": message,
    }


def _escape_markdown_table(value: str) -> str:
    return value.replace("|", "\\|").replace("\n", " ")


def _gate_outcome_for_observation(
    observation,
    *,
    coverage: SpecCoverageReport,
    stale_modules: list[str],
    counterexample: Counterexample | None,
    high_assurance: bool,
) -> TraceValidationGateOutcome:
    base = {
        "trace_id": observation.trace_id,
        "requirement_id": observation.requirement_id,
        "event_ids": observation.event_ids,
        "counterexample_id": counterexample.counterexample_id if counterexample else None,
        "warnings": observation.warnings,
    }
    if stale_modules:
        return TraceValidationGateOutcome(
            **base,
            status="stale",
            closure_effect="block",
            evidence_label="none",
            reason="freshness drift blocks trace grounding",
            metadata={"stale_modules": ",".join(stale_modules)},
        )
    if observation.warnings and high_assurance:
        return TraceValidationGateOutcome(
            **base,
            status="lossy",
            closure_effect="block",
            evidence_label="none",
            reason="lossy trace cannot satisfy high-assurance closure",
        )
    if observation.status == "satisfied":
        return TraceValidationGateOutcome(
            **base,
            status="satisfied",
            closure_effect="allow",
            evidence_label="trace_grounding",
            reason=observation.reason,
        )
    if observation.status == "violating":
        return TraceValidationGateOutcome(
            **base,
            status="violation",
            closure_effect="block",
            evidence_label="none",
            reason=observation.reason or "trace violates requirement",
        )
    if observation.status == "uncovered" or coverage.result != "passed":
        return TraceValidationGateOutcome(
            **base,
            status="coverage_gap",
            closure_effect="block",
            evidence_label="none",
            reason=observation.reason or "trace coverage gap",
        )
    return TraceValidationGateOutcome(
        **base,
        status="unsupported",
        closure_effect="review",
        evidence_label="none",
        reason=observation.reason or "claim has no supported trace predicate",
    )


def _counterexample_for_observation(
    event_ids: list[str],
    counterexamples: list[Counterexample],
) -> Counterexample | None:
    for counterexample in counterexamples:
        if counterexample.metadata.get("event_ids") == event_ids:
            return counterexample
    return None


def _trace_gate_closure(
    outcomes: list[TraceValidationGateOutcome],
) -> Literal["allow", "block", "review"]:
    if any(outcome.closure_effect == "block" for outcome in outcomes):
        return "block"
    if any(outcome.closure_effect == "review" for outcome in outcomes):
        return "review"
    return "allow"
