from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from .coverage_alignment import SpecCoverageReport
from .models import Counterexample, NormalizedTraceArtifact, RequirementIRV2, SemanticNode, TraceEvent


TRACE_REPLAY_SCHEMA_VERSION = "0.1"


class TraceReplayObservation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    trace_id: str
    requirement_id: str
    status: Literal["satisfied", "violating", "uncovered", "unsupported"]
    event_ids: list[str] = Field(default_factory=list)
    expected: dict[str, Any] = Field(default_factory=dict)
    actual: dict[str, Any] = Field(default_factory=dict)
    reason: str | None = None
    warnings: list[str] = Field(default_factory=list)


class TraceReplayReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["0.1"] = TRACE_REPLAY_SCHEMA_VERSION
    requirement_id: str
    result: Literal["passed", "blocked"]
    observations: list[TraceReplayObservation] = Field(default_factory=list)
    counterexamples: list[Counterexample] = Field(default_factory=list)


def build_trace_replay_report(
    *,
    requirement: RequirementIRV2,
    traces: NormalizedTraceArtifact,
    coverage: SpecCoverageReport,
) -> TraceReplayReport:
    action = _requirement_action(requirement.semantic_ir)
    obligations = _obligations(requirement.semantic_ir)
    observations: list[TraceReplayObservation] = []
    counterexamples: list[Counterexample] = []
    for trace in traces.root:
        warnings = _lossy_warnings(trace)
        if coverage.result != "passed":
            observations.append(
                TraceReplayObservation(
                    trace_id=trace.trace_id,
                    requirement_id=requirement.requirement_id,
                    status="unsupported",
                    expected={"coverage": "passed"},
                    actual={"coverage": coverage.result},
                    reason="spec coverage did not pass",
                    warnings=warnings,
                )
            )
            continue
        if action is None:
            observations.append(
                TraceReplayObservation(
                    trace_id=trace.trace_id,
                    requirement_id=requirement.requirement_id,
                    status="unsupported",
                    reason="requirement has no replayable action",
                    warnings=warnings,
                )
            )
            continue
        action_events = [event for event in trace.events if event.action == action]
        if not action_events:
            observations.append(
                TraceReplayObservation(
                    trace_id=trace.trace_id,
                    requirement_id=requirement.requirement_id,
                    status="uncovered",
                    expected={"action": action},
                    actual={"actions": [event.action for event in trace.events]},
                    reason="requirement action was not observed",
                    warnings=warnings,
                )
            )
            continue
        observation = _replay_obligations(
            requirement=requirement,
            trace_id=trace.trace_id,
            events=trace.events,
            action_event=action_events[0],
            obligations=obligations,
            warnings=warnings,
        )
        observations.append(observation)
        if observation.status == "violating":
            counterexamples.append(
                Counterexample(
                    counterexample_id=f"{trace.trace_id}:{requirement.requirement_id}:trace-replay",
                    backend="trace_replay",
                    claim_id=requirement.requirement_id,
                    description=observation.reason or "trace replay violation",
                    expected=observation.expected,
                    actual=observation.actual,
                    metadata={"event_ids": observation.event_ids},
                )
            )
    blocked = any(observation.status != "satisfied" for observation in observations)
    return TraceReplayReport(
        requirement_id=requirement.requirement_id,
        result="blocked" if blocked else "passed",
        observations=observations,
        counterexamples=counterexamples,
    )


def _replay_obligations(
    *,
    requirement: RequirementIRV2,
    trace_id: str,
    events: list[TraceEvent],
    action_event: TraceEvent,
    obligations: list[SemanticNode],
    warnings: list[str],
) -> TraceReplayObservation:
    action_index = events.index(action_event)
    event_ids = [action_event.event_id]
    for obligation in obligations:
        if obligation.kind == "within":
            expected_event = _within_event_name(obligation)
            matching = [
                event
                for event in events[action_index + 1 :]
                if event.action == expected_event
            ]
            if not matching:
                return TraceReplayObservation(
                    trace_id=trace_id,
                    requirement_id=requirement.requirement_id,
                    status="violating",
                    event_ids=event_ids,
                    expected={
                        "event_after_action": expected_event,
                        "action_event_id": action_event.event_id,
                    },
                    actual={"observed_actions": [event.action for event in events]},
                    reason="required event was not observed after the action",
                    warnings=warnings,
                )
            event_ids.append(matching[0].event_id)
            continue
        if obligation.kind in {"gte", "lte"}:
            result = _replay_comparison(obligation, events[action_index:])
            if result is None:
                return TraceReplayObservation(
                    trace_id=trace_id,
                    requirement_id=requirement.requirement_id,
                    status="unsupported",
                    event_ids=event_ids,
                    expected={"comparison": obligation.kind},
                    actual={"state_fragments": _state_fragments(events[action_index:])},
                    reason="comparison obligation has no replayable state values",
                    warnings=warnings,
                )
            ok, event, expected, actual = result
            event_ids.append(event.event_id)
            if not ok:
                return TraceReplayObservation(
                    trace_id=trace_id,
                    requirement_id=requirement.requirement_id,
                    status="violating",
                    event_ids=event_ids,
                    expected=expected,
                    actual=actual,
                    reason="state comparison failed during trace replay",
                    warnings=warnings,
                )
            continue
    return TraceReplayObservation(
        trace_id=trace_id,
        requirement_id=requirement.requirement_id,
        status="satisfied",
        event_ids=event_ids,
        expected={"obligations": [obligation.kind for obligation in obligations]},
        actual={"observed_actions": [event.action for event in events]},
        warnings=warnings,
    )


def _replay_comparison(
    obligation: SemanticNode, events: list[TraceEvent]
) -> tuple[bool, TraceEvent, dict[str, Any], dict[str, Any]] | None:
    if len(obligation.args) < 2:
        return None
    left_name = str(obligation.args[0].value)
    right_name = str(obligation.args[1].value)
    for event in events:
        state = event.post_state or {}
        if left_name not in state or right_name not in state:
            continue
        left = state[left_name]
        right = state[right_name]
        if not isinstance(left, (int, float)) or not isinstance(right, (int, float)):
            return None
        ok = left >= right if obligation.kind == "gte" else left <= right
        return (
            ok,
            event,
            {left_name: f"{obligation.kind} {right_name}"},
            {left_name: left, right_name: right},
        )
    return None


def _obligations(root: SemanticNode) -> list[SemanticNode]:
    action_obligation = root.obligation
    if action_obligation is None or action_obligation.must is None:
        return []
    must = action_obligation.must
    return must.children if must.kind == "and" else [must]


def _within_event_name(node: SemanticNode) -> str | None:
    if node.children and node.children[0].kind == "event":
        return node.children[0].name
    return None


def _requirement_action(node: SemanticNode) -> str | None:
    if node.kind == "action" and node.name:
        return node.name
    for child in [*node.scope, node.premise, node.obligation, node.action, node.must, *node.children]:
        if isinstance(child, SemanticNode):
            found = _requirement_action(child)
            if found:
                return found
    return None


def _lossy_warnings(trace) -> list[str]:
    warnings: list[str] = []
    if trace.metadata.get("lossy_normalization") is True:
        warnings.append("trace metadata declares lossy_normalization")
    for event in trace.events:
        if event.metadata.get("lossy_normalization") is True:
            warnings.append(f"event {event.event_id} declares lossy_normalization")
    return warnings


def _state_fragments(events: list[TraceEvent]) -> list[dict[str, Any]]:
    return [
        {"event_id": event.event_id, "post_state": event.post_state}
        for event in events
        if event.post_state
    ]
