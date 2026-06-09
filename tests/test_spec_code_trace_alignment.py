"""PC-11 — does the registered spec S reproduce the module's real (Foundry) traces?

Beyond the claim-vs-trace check, this validates that a spec's declared trace-observable obligations
are REPRODUCED by the code's real traces, classifying satisfies / violates-with-delta / no-coverage.
A spec describing a "paper system" the code does not implement is caught with a populated delta.

The real-trace test extracts a genuine Foundry trace (skipped with a recorded reason when forge is
absent, like the other PC-4 tests); the synthetic tests pin the replay+classification engine
deterministically without the tool.
"""

from pathlib import Path

import pytest

from nlreq import foundry_client
from nlreq.models import NormalizedTraceArtifact
from nlreq.production_source_adapters import SoliditySourceAdapter
from nlreq.source_adapter import SourceManifest
from nlreq.system_spec import SpecTraceContract, SpecTraceExpectation
from nlreq.trace_replay import replay_spec_against_traces
from nlreq.trace_validation import classify_spec_code_alignment


FOUNDRY_ROOT = Path(__file__).parent / "fixtures" / "foundry"

requires_forge = pytest.mark.skipif(
    not foundry_client.foundry_available(),
    reason="forge (Foundry) is not installed; run with forge on PATH to extract real traces",
)


def _manifest() -> SourceManifest:
    return SourceManifest.model_validate(
        {
            "schema_version": "0.1",
            "adapter": "solidity-source",
            "language": "solidity",
            "runtime": "evm",
            "modules": [
                {
                    "module_id": "vault",
                    "path": "src/Vault.sol",
                    "symbols": ["Vault", "requestRedemption", "Redeemed", "total"],
                }
            ],
        }
    )


def _contract(*expectations: SpecTraceExpectation) -> SpecTraceContract:
    return SpecTraceContract(
        spec_id="spec:vault", module_ids=["vault"], expectations=list(expectations)
    )


# --- Against a REAL Foundry trace --------------------------------------------------------------


@requires_forge
def test_spec_that_reproduces_the_real_trace_classifies_satisfies() -> None:
    adapter = SoliditySourceAdapter(project_root=FOUNDRY_ROOT)
    traces = adapter.extract_traces(_manifest())

    # S claims: the Redeemed event is emitted and total() reaches 5 — both true in the real trace.
    contract = _contract(
        SpecTraceExpectation(expectation_id="e-redeemed", kind="event_emitted", target="Redeemed"),
        SpecTraceExpectation(
            expectation_id="e-total", kind="state_value_reached", target="total()", value="5"
        ),
    )

    report = classify_spec_code_alignment(contract=contract, traces=traces)

    assert report.classification == "satisfies"
    assert report.closure_effect == "allow"
    assert report.deltas == []


@requires_forge
def test_paper_system_spec_is_caught_with_a_populated_delta() -> None:
    """A spec describing a system the code does NOT implement (total reaches a value it never does)
    cannot reproduce the real trace and is caught as violates-with-delta with a populated delta."""
    adapter = SoliditySourceAdapter(project_root=FOUNDRY_ROOT)
    traces = adapter.extract_traces(_manifest())

    contract = _contract(
        SpecTraceExpectation(
            expectation_id="e-paper", kind="state_value_reached", target="total()", value="999"
        ),
    )

    report = classify_spec_code_alignment(contract=contract, traces=traces)

    assert report.classification == "violates_with_delta"
    assert report.closure_effect == "block"
    assert len(report.deltas) == 1
    delta = report.deltas[0]
    assert delta.expectation_id == "e-paper"
    assert delta.expected == {"value": "999"}
    # The delta is POPULATED with what the code actually does — the values total() really reaches.
    observed = delta.actual["observed_values"]
    assert "999" not in observed
    assert "5" in observed  # the real redemption brings total to 5, never 999


@requires_forge
def test_obligation_the_trace_never_witnesses_classifies_no_coverage() -> None:
    adapter = SoliditySourceAdapter(project_root=FOUNDRY_ROOT)
    traces = adapter.extract_traces(_manifest())

    # balanceOf is never read in the Vault trace, so the obligation cannot be witnessed.
    contract = _contract(
        SpecTraceExpectation(
            expectation_id="e-uncovered", kind="state_value_reached", target="balanceOf", value="100"
        ),
    )

    report = classify_spec_code_alignment(contract=contract, traces=traces)

    assert report.classification == "no_coverage"
    assert report.closure_effect == "review"
    assert report.deltas == []


# --- Deterministic engine coverage (synthetic traces, no forge required) ------------------------


def _synthetic_traces() -> NormalizedTraceArtifact:
    """A small artifact mimicking the Foundry projection: a Redeemed event, two total() reads
    (0 then 5), and a reverting willRevert() call carrying its decoded reason."""
    return NormalizedTraceArtifact.model_validate(
        [
            {
                "trace_id": "VaultTest::test_redeem",
                "adapter_id": "solidity-source",
                "source_hash": "sha256:synthetic",
                "language": "solidity",
                "runtime": "evm",
                "events": [
                    {"event_id": "call-1", "timestamp": 1, "action": "total()",
                     "metadata": {"decoded_output": "0"}},
                    {"event_id": "log-2", "timestamp": 2, "action": "Redeemed(uint256)",
                     "metadata": {"params": {"amount": "5"}}},
                    {"event_id": "call-3", "timestamp": 3, "action": "total()",
                     "metadata": {"decoded_output": "5"}},
                    {"event_id": "call-4", "timestamp": 4, "action": "willRevert()",
                     "metadata": {"reverted": True, "revert_reason": "child reverted"}},
                ],
            }
        ]
    )


def test_satisfies_when_event_and_state_value_are_witnessed() -> None:
    report = classify_spec_code_alignment(
        contract=_contract(
            SpecTraceExpectation(expectation_id="e1", kind="event_emitted", target="Redeemed"),
            SpecTraceExpectation(expectation_id="e2", kind="state_value_reached", target="total", value="5"),
        ),
        traces=_synthetic_traces(),
    )
    assert report.classification == "satisfies"
    assert {obs.outcome for obs in report.observations} == {"satisfied"}


def test_state_value_violation_carries_observed_values_in_delta() -> None:
    report = classify_spec_code_alignment(
        contract=_contract(
            SpecTraceExpectation(expectation_id="e", kind="state_value_reached", target="total", value="42"),
        ),
        traces=_synthetic_traces(),
    )
    assert report.classification == "violates_with_delta"
    assert report.deltas[0].expected == {"value": "42"}
    assert sorted(report.deltas[0].actual["observed_values"]) == ["0", "5"]


def test_action_never_is_violated_when_the_forbidden_action_appears() -> None:
    report = classify_spec_code_alignment(
        contract=_contract(
            SpecTraceExpectation(expectation_id="e", kind="action_never", target="willRevert"),
        ),
        traces=_synthetic_traces(),
    )
    assert report.classification == "violates_with_delta"
    assert report.deltas[0].kind == "action_never"
    assert report.deltas[0].expected == {"forbidden": "willRevert"}
    assert "call-4" in report.deltas[0].actual["observed_event_ids"]


def test_action_reverts_satisfied_with_matching_reason_and_violated_otherwise() -> None:
    ok = classify_spec_code_alignment(
        contract=_contract(
            SpecTraceExpectation(
                expectation_id="e", kind="action_reverts", target="willRevert", value="child reverted"
            ),
        ),
        traces=_synthetic_traces(),
    )
    assert ok.classification == "satisfies"

    wrong_reason = classify_spec_code_alignment(
        contract=_contract(
            SpecTraceExpectation(
                expectation_id="e", kind="action_reverts", target="willRevert", value="different reason"
            ),
        ),
        traces=_synthetic_traces(),
    )
    assert wrong_reason.classification == "violates_with_delta"
    assert wrong_reason.deltas[0].expected == {"revert_reason": "different reason"}


def test_no_coverage_when_no_obligation_is_witnessed() -> None:
    report = classify_spec_code_alignment(
        contract=_contract(
            SpecTraceExpectation(expectation_id="e", kind="state_value_reached", target="missing", value="1"),
        ),
        traces=_synthetic_traces(),
    )
    assert report.classification == "no_coverage"
    assert report.deltas == []


def test_partial_coverage_does_not_close_as_satisfies_allow() -> None:
    """A spec with one witnessed obligation and one never-witnessed obligation must NOT close as
    satisfies/allow — the unwitnessed obligation is surfaced as no-coverage (review). Allowing here
    would silently claim grounding the traces never evidenced."""
    report = classify_spec_code_alignment(
        contract=_contract(
            # Witnessed: the Redeemed event is emitted in the trace.
            SpecTraceExpectation(expectation_id="e-witnessed", kind="event_emitted", target="Redeemed"),
            # Never witnessed: balanceOf is never read, so the obligation cannot be confirmed.
            SpecTraceExpectation(
                expectation_id="e-missing", kind="state_value_reached", target="balanceOf", value="1"
            ),
        ),
        traces=_synthetic_traces(),
    )

    assert report.classification == "no_coverage"
    assert report.closure_effect == "review"
    assert report.deltas == []
    # The partial signal is distinct from the none-witnessed signal and names the gap honestly.
    assert "partially" in report.reason
    outcomes = {obs.expectation_id: obs.outcome for obs in report.observations}
    assert outcomes == {"e-witnessed": "satisfied", "e-missing": "no_coverage"}


def test_replay_records_one_observation_per_expectation() -> None:
    contract = _contract(
        SpecTraceExpectation(expectation_id="a", kind="event_emitted", target="Redeemed"),
        SpecTraceExpectation(expectation_id="b", kind="state_value_reached", target="total", value="5"),
    )
    replay = replay_spec_against_traces(contract=contract, traces=_synthetic_traces())
    assert [obs.expectation_id for obs in replay.observations] == ["a", "b"]
    assert replay.trace_ids == ["VaultTest::test_redeem"]
