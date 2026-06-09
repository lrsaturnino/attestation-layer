"""PC-7 — GoSourceAdapter trace extraction backed by a real `go test -trace` runtime/trace.

The go-present tests skip with a recorded reason when go is absent (like the Apalache/Slither/Foundry
real-run tests). The adapter PRODUCES the trace from a real Go execution rather than ingesting
pre-supplied JSON, and the goroutine/interleaving metadata survives normalization. The forced-absent
test confirms the adapter degrades to ingestion (no producer provenance) instead of fabricating a
trace.
"""

import base64
from pathlib import Path

import pytest

from nlreq import go_client
from nlreq.adapter_certification import (
    _go_runtime_trace_is_well_formed,
    certify_adapter,
    trace_has_real_tool_provenance,
)
from nlreq.models import NormalizedTrace, NormalizedTraceProducer, SymbolRef
from nlreq.production_source_adapters import GoSourceAdapter
from nlreq.source_adapter import SourceManifest


FIXTURE_ROOT = Path(__file__).parent / "fixtures" / "go"

requires_go = pytest.mark.skipif(
    not go_client.go_trace_tools_available(),
    reason="go is not installed; run with go on PATH to extract a real runtime/trace",
)


def _manifest() -> SourceManifest:
    return SourceManifest.model_validate(
        {
            "schema_version": "0.1",
            "adapter": "go-source",
            "language": "go",
            "runtime": "go",
            "modules": [
                {
                    "module_id": "coordinator",
                    "path": "coordinator/coordinator.go",
                    "symbols": ["Coordinate", "Run", "Total"],
                }
            ],
        }
    )


@requires_go
def test_adapter_produces_a_go_trace_with_recorded_provenance() -> None:
    adapter = GoSourceAdapter(project_root=FIXTURE_ROOT)

    artifact = adapter.extract_traces(_manifest())

    assert len(artifact.root) >= 1
    trace = artifact.root[0]
    # The trace was produced by a real tool: it carries `go` producer provenance over a real artifact
    # hash (not ingested JSON, which would leave producer None).
    assert isinstance(trace.producer, NormalizedTraceProducer)
    assert trace.producer.tool == "go"
    assert "go" in (trace.producer.tool_version or "").lower()
    assert trace.source_hash.startswith("sha256:")
    assert trace.metadata["producer"] == "go-runtime-trace"
    assert trace.metadata["test_status"] == "Success"
    # The provenance is SOURCE-BOUND: the producer carries the base64 of the REAL binary runtime/trace
    # (whose magic header the gate decodes and checks), sha256(raw_output) == source_hash.
    assert trace.producer.raw_output
    assert base64.b64decode(trace.producer.raw_output).startswith(b"go ")
    assert trace_has_real_tool_provenance(trace)


@requires_go
def test_goroutine_interleaving_metadata_survives_normalization() -> None:
    adapter = GoSourceAdapter(project_root=FIXTURE_ROOT)

    artifact = adapter.extract_traces(_manifest())
    trace = artifact.root[0]

    # Every event carries its goroutine id and the observed (linearized) order.
    assert all("goroutine" in event.metadata for event in trace.events)
    assert [event.timestamp for event in trace.events] == sorted(
        event.timestamp for event in trace.events
    )

    # The "redeem" task is created on its owning goroutine; the "validate"/"record" stage regions run
    # on the spawned worker goroutine. That the task owner and the stage regions live on DIFFERENT
    # goroutines is the interleaving the normalization must preserve.
    task_goroutines = {
        event.metadata["goroutine"] for event in trace.events if event.action == "redeem"
    }
    stage_goroutines = {
        event.metadata["goroutine"]
        for event in trace.events
        if event.action in {"validate", "record"}
    }
    assert task_goroutines and stage_goroutines
    assert task_goroutines.isdisjoint(stage_goroutines)

    # The stage regions appear, in order, so a spec trace contract can match them (PC-8).
    actions = [event.action for event in trace.events]
    assert actions.index("validate") < actions.index("record")


@requires_go
def test_real_go_trace_lifts_certification_to_production_candidate() -> None:
    """A real, provenanced Go trace plus a tool-backed CHA call graph with edges is the complete Go
    vertical: certification reaches production_candidate (unlike the Foundry fixture, which has no
    Slither edges and so caps at trace_capable)."""
    adapter = GoSourceAdapter(project_root=FIXTURE_ROOT)

    report = certify_adapter(
        adapter,
        _manifest(),
        symbol_refs=[SymbolRef(name="Coordinate")],
        required_capabilities=["runtime_trace_extraction"],
    )

    assert report.result == "certified"
    assert report.trace_count >= 1
    assert report.call_graph_edges >= 1
    assert report.call_graph_tool_backed is True
    assert report.level == "production_candidate"


def test_go_runtime_trace_validator_accepts_magic_rejects_ingested_json() -> None:
    """The Go raw-output validator is deterministic and tool-independent, so it is pinned directly: a
    base64 of the Go trace magic header is accepted; a normalized-trace JSON blob is rejected (the
    stamp-over-ingested-JSON loophole PC-1 closes)."""
    real = base64.b64encode(b"go 1.26 trace\x00\x00\x00rest-of-trace").decode("ascii")
    trace = NormalizedTrace(
        trace_id="t", adapter_id="go-source", source_hash="sha256:" + "0" * 64, events=[]
    )
    assert _go_runtime_trace_is_well_formed(real, trace) is True

    ingested = base64.b64encode(b'[{"trace_id":"t","events":[],"producer":null}]').decode("ascii")
    assert _go_runtime_trace_is_well_formed(ingested, trace) is False
    assert _go_runtime_trace_is_well_formed("not base64 @@@", trace) is False


@requires_go
def test_reader_degrades_on_unparseable_trace(tmp_path: Path) -> None:
    """A trace the pinned reader cannot parse (a corrupt file, or a format version newer than the
    vendored x/exp/trace supports) must degrade to a recorded reason — never a crash, never a
    fabricated trace. The adapter then falls back to ingestion (no provenance)."""
    corrupt = tmp_path / "corrupt.trace"
    corrupt.write_bytes(b"this is not a go runtime trace")

    events, reason = go_client._run_reader(
        go_client.go_binary(), corrupt, timeout_seconds=120
    )

    assert events is None
    assert reason and "reader" in reason


def test_go_absent_falls_back_to_ingestion_without_provenance(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        go_client,
        "extract_go_traces",
        lambda *args, **kwargs: go_client.GoTraceResult(
            status="unavailable", reason="go forced absent for test"
        ),
    )
    adapter = GoSourceAdapter(project_root=FIXTURE_ROOT)

    # The go manifest declares no trace_sources, so ingestion yields nothing — and crucially no
    # provenanced trace is fabricated.
    artifact = adapter.extract_traces(_manifest())
    assert all(trace.producer is None for trace in artifact.root)
