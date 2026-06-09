"""PC-4 — SoliditySourceAdapter trace extraction backed by a real Foundry run.

The forge-present tests skip with a recorded reason when forge is absent (like the Apalache/cvc5
real-run tests). The adapter PRODUCES the trace from a real ``forge test`` rather than ingesting
pre-supplied JSON, and the produced trace answers the sample claim "the Redeemed event is emitted
before the state change". The forced-absent test confirms the adapter degrades to ingestion (no
producer provenance) instead of fabricating a trace.
"""

from pathlib import Path

import pytest

from nlreq import foundry_client
from nlreq.adapter_certification import certify_adapter
from nlreq.models import NormalizedTraceProducer, SymbolRef
from nlreq.production_source_adapters import SoliditySourceAdapter
from nlreq.source_adapter import SourceManifest


FIXTURE_ROOT = Path(__file__).parent / "fixtures" / "foundry"

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


@requires_forge
def test_adapter_produces_a_foundry_trace_with_recorded_provenance() -> None:
    adapter = SoliditySourceAdapter(project_root=FIXTURE_ROOT)

    artifact = adapter.extract_traces(_manifest())

    assert len(artifact.root) >= 1
    trace = next(t for t in artifact.root if "VaultTest" in t.trace_id)
    # The trace was produced by a real tool: it carries forge producer provenance over a real
    # artifact hash (not ingested JSON, which would leave producer None).
    assert isinstance(trace.producer, NormalizedTraceProducer)
    assert "forge" in (trace.producer.tool_version or "").lower()
    assert trace.source_hash.startswith("sha256:")
    assert trace.metadata["producer"] == "foundry"
    assert trace.metadata["test_status"] == "Success"


@requires_forge
def test_trace_answers_event_emitted_before_state_change() -> None:
    adapter = SoliditySourceAdapter(project_root=FIXTURE_ROOT)

    artifact = adapter.extract_traces(_manifest())
    trace = next(t for t in artifact.root if "VaultTest" in t.trace_id)

    redeemed = [event for event in trace.events if event.action.startswith("Redeemed(")]
    assert redeemed, "the Redeemed event must appear in the extracted trace"
    redeemed_ordinal = redeemed[0].timestamp

    # `total()` view reads bracket the redemption: the pre-read returns 0, the post-read returns 5,
    # so the state change is observable at call granularity.
    total_reads = [
        event
        for event in trace.events
        if event.action == "total()" and event.metadata.get("decoded_output") is not None
    ]
    observed_values = [event.metadata["decoded_output"] for event in total_reads]
    assert "0" in observed_values and "5" in observed_values

    state_change_read = next(
        event for event in total_reads if event.metadata["decoded_output"] == "5"
    )
    # The claim holds: the event was emitted before the read that observes the changed state.
    assert redeemed_ordinal < state_change_read.timestamp
    # And the decoded event params survived the projection.
    assert redeemed[0].metadata["params"]["amount"] == "5"


@requires_forge
def test_trace_preserves_nested_external_call_path_and_revert() -> None:
    """The projection keeps call-path/parent linkage and a reverted sub-call's success=False + reason.

    (Events and decoded params are covered by the VaultTest trace above; this nested-revert path has
    no events, so the two tests together cover all four normalized facets.)"""
    adapter = SoliditySourceAdapter(project_root=FIXTURE_ROOT)

    artifact = adapter.extract_traces(_manifest())
    trace = next(t for t in artifact.root if "RevertPathTest" in t.trace_id)

    # The reverting leaf is observable as a failed sub-call carrying its decoded Error(string) reason.
    reverts = [
        event
        for event in trace.events
        if event.action == "willRevert()" and event.metadata.get("reverted") is True
    ]
    assert reverts, "the reverting willRevert() call must appear in the trace"
    revert = reverts[0]
    assert revert.metadata["success"] is False
    assert revert.metadata["revert_reason"] == "child reverted"

    # Call-path / parent linkage is preserved: willRevert() is nested under attempt(), which itself
    # succeeded — a real nested external call path, not a flat ordered list.
    assert revert.metadata["call_path"][-2:] == ["attempt()", "willRevert()"]
    parent = next(
        event for event in trace.events if event.timestamp == revert.metadata["parent_ordinal"]
    )
    assert parent.action == "attempt()"
    assert parent.metadata["success"] is True
    assert revert.causal_predecessor == f"call-{revert.metadata['parent_ordinal']}"


@requires_forge
def test_real_foundry_trace_lifts_certification_above_static_resolution() -> None:
    """A real, provenanced Foundry trace is the evidence PC-1's gate requires, so certification
    reaches a trace level rather than capping at static_resolution like ingested JSON."""
    adapter = SoliditySourceAdapter(project_root=FIXTURE_ROOT)

    report = certify_adapter(
        adapter,
        _manifest(),
        symbol_refs=[SymbolRef(name="requestRedemption")],
        required_capabilities=["runtime_trace_extraction"],
    )

    assert report.result == "certified"
    assert report.trace_count >= 1
    assert report.level in {"trace_capable", "production_candidate"}


def test_forge_absent_falls_back_to_ingestion_without_provenance(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        foundry_client,
        "extract_foundry_traces",
        lambda *args, **kwargs: foundry_client.FoundryClientResult(
            status="unavailable", reason="forge forced absent for test"
        ),
    )
    adapter = SoliditySourceAdapter(project_root=FIXTURE_ROOT)

    # The foundry manifest declares no trace_sources, so ingestion yields nothing — and crucially no
    # provenanced trace is fabricated.
    artifact = adapter.extract_traces(_manifest())
    assert all(trace.producer is None for trace in artifact.root)
