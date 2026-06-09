from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from .coverage_alignment import SpecCoverageReport
from .models import Counterexample, NormalizedTraceArtifact, RequirementIRV2, SemanticNode, TraceEvent
from .system_spec import SpecTraceContract, SpecTraceExpectation


TRACE_REPLAY_SCHEMA_VERSION = "0.1"
SPEC_TRACE_REPLAY_SCHEMA_VERSION = "0.1"


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


# --- PC-11: does the registered spec S reproduce the module's real traces? -----------------------
# trace_replay above replays the REQUIREMENT against a trace (claim-vs-trace). The functions below
# answer a different question — Specula's discipline — does the registered spec S reproduce the
# CODE's real traces? S's declared trace-observable obligations (a SpecTraceContract) are replayed
# against the real (e.g. Foundry-extracted) trace events; an obligation the trace actively
# contradicts is a delta, an obligation the trace cannot witness is no-coverage. A spec that cannot
# reproduce the code's traces is not a spec of the code.


class SpecTraceObservation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expectation_id: str
    kind: str
    target: str
    outcome: Literal["satisfied", "violated", "no_coverage"]
    expected: dict[str, Any] = Field(default_factory=dict)
    actual: dict[str, Any] = Field(default_factory=dict)
    matched_event_ids: list[str] = Field(default_factory=list)
    reason: str


class SpecTraceReplayReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["0.1"] = SPEC_TRACE_REPLAY_SCHEMA_VERSION
    spec_id: str
    trace_ids: list[str] = Field(default_factory=list)
    observations: list[SpecTraceObservation] = Field(default_factory=list)


def replay_spec_against_traces(
    *,
    contract: SpecTraceContract,
    traces: NormalizedTraceArtifact,
) -> SpecTraceReplayReport:
    """Replay a spec's declared trace-observable obligations against the code's real traces (PC-11).

    Events are pooled across all traces in the artifact (each test execution is one trace); an
    obligation is satisfied if any trace witnesses it, violated if the traces actively contradict it,
    and no-coverage if the traces never exercise the relevant context. Returns one observation per
    expectation so the three-way classification and the delta report (``trace_validation``) are
    derived from a transparent, per-obligation record.
    """
    events: list[TraceEvent] = [event for trace in traces.root for event in trace.events]
    observations = [_replay_expectation(expectation, events) for expectation in contract.expectations]
    return SpecTraceReplayReport(
        spec_id=contract.spec_id,
        trace_ids=[trace.trace_id for trace in traces.root],
        observations=observations,
    )


def _matches_target(action: str, target: str) -> bool:
    """An event action matches a target either exactly or as a signature head.

    So ``target='total'`` matches ``total()`` and ``target='Redeemed'`` matches ``Redeemed(uint256)``
    while a fully-qualified ``target='total()'`` still matches ``total()`` exactly.
    """
    return action == target or action.startswith(target + "(")


def _replay_expectation(
    expectation: SpecTraceExpectation, events: list[TraceEvent]
) -> SpecTraceObservation:
    matched = [event for event in events if _matches_target(event.action, expectation.target)]
    matched_ids = [event.event_id for event in matched]
    if expectation.kind == "event_emitted":
        if matched:
            return _observation(expectation, "satisfied", matched_ids, reason="event was emitted in the real traces")
        # A single observed trace not emitting the event does not prove the code never emits it, so
        # absence is no-coverage (not a contradiction) — the trace did not witness the obligation.
        return _observation(
            expectation, "no_coverage", [], reason="event was not observed in the real traces"
        )
    if expectation.kind == "state_value_reached":
        reads = [event for event in matched if event.metadata.get("decoded_output") is not None]
        observed_values = [str(event.metadata.get("decoded_output")) for event in reads]
        if not reads:
            return _observation(
                expectation,
                "no_coverage",
                [],
                reason="state read was never observed in the real traces",
                actual={"observed_values": observed_values},
            )
        if expectation.value in observed_values:
            witness = [event.event_id for event in reads if str(event.metadata.get("decoded_output")) == expectation.value]
            return _observation(
                expectation,
                "satisfied",
                witness,
                reason="state read reached the spec's claimed value",
                expected={"value": expectation.value},
                actual={"observed_values": observed_values},
            )
        return _observation(
            expectation,
            "violated",
            [event.event_id for event in reads],
            reason="state read never reached the spec's claimed value",
            expected={"value": expectation.value},
            actual={"observed_values": observed_values},
        )
    if expectation.kind == "action_reverts":
        reverts = [event for event in matched if event.metadata.get("reverted") is True]
        if not matched:
            return _observation(
                expectation, "no_coverage", [], reason="action was never observed in the real traces"
            )
        if not reverts:
            return _observation(
                expectation,
                "violated",
                matched_ids,
                reason="action was observed but never reverted",
                expected={"reverts": True},
                actual={"reverted": False},
            )
        revert_reasons = [str(event.metadata.get("revert_reason")) for event in reverts]
        if expectation.value is not None and expectation.value not in revert_reasons:
            return _observation(
                expectation,
                "violated",
                [event.event_id for event in reverts],
                reason="action reverted with a different reason than the spec claims",
                expected={"revert_reason": expectation.value},
                actual={"revert_reasons": revert_reasons},
            )
        return _observation(
            expectation,
            "satisfied",
            [event.event_id for event in reverts],
            reason="action reverted as the spec claims",
            actual={"revert_reasons": revert_reasons},
        )
    # action_never: a forbidden action; observing it contradicts the spec.
    if matched:
        return _observation(
            expectation,
            "violated",
            matched_ids,
            reason="forbidden action was observed in the real traces",
            expected={"forbidden": expectation.target},
            actual={"observed_event_ids": matched_ids},
        )
    return _observation(
        expectation, "satisfied", [], reason="forbidden action was absent from the real traces"
    )


def _observation(
    expectation: SpecTraceExpectation,
    outcome: Literal["satisfied", "violated", "no_coverage"],
    matched_event_ids: list[str],
    *,
    reason: str,
    expected: dict[str, Any] | None = None,
    actual: dict[str, Any] | None = None,
) -> SpecTraceObservation:
    return SpecTraceObservation(
        expectation_id=expectation.expectation_id,
        kind=expectation.kind,
        target=expectation.target,
        outcome=outcome,
        expected=expected or {},
        actual=actual or {},
        matched_event_ids=matched_event_ids,
        reason=reason,
    )
