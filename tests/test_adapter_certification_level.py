"""PC-1 — per-capability certification level + source-bound trace-provenance gate.

These run with no external tools installed: they pin the level computation and the provenance gate
directly, so the boundaries the Foundry/Slither fixtures exercise end-to-end (skip-when-absent) are
also covered deterministically here.

Two boundaries are pinned:
  * ``production_candidate`` requires a *tool-backed* call graph AND provenanced traces — a regex
    fallback call graph caps the run at ``trace_capable`` even with real traces present.
  * trace evidence is *source-bound*: a producer stamped over ingested JSON (no real forge report as
    its ``raw_output``) is rejected, however well-formed its hash and version strings look.
"""

import hashlib
import json

from nlreq.adapter_certification import (
    _call_graph_is_tool_backed,
    _level,
    trace_has_real_tool_provenance,
)
from nlreq.models import NormalizedTrace, NormalizedTraceProducer, TraceEvent
from nlreq.source_adapter import SourceCallGraph


def _forge_report(suite: str = "VaultTest", test: str = "testRedeem()") -> str:
    """A minimal but genuinely forge-``--json``-shaped report (suite -> test_results -> traces)."""
    return json.dumps({suite: {"test_results": {test: {"status": "Success", "traces": [["Execution", {"arena": []}]]}}}})


def _trace(
    *,
    raw_output: str | None,
    source_hash: str | None = None,
    tool: str = "forge",
    tool_version: str = "forge 1.5.0-stable",
    metadata: dict | None = None,
) -> NormalizedTrace:
    if source_hash is None and raw_output is not None:
        source_hash = "sha256:" + hashlib.sha256(raw_output.encode("utf-8")).hexdigest()
    return NormalizedTrace(
        trace_id="t",
        adapter_id="solidity-source",
        source_hash=source_hash or "sha256:" + "0" * 64,
        events=[TraceEvent(event_id="e1", timestamp=0, action="requestRedemption")],
        producer=NormalizedTraceProducer(tool=tool, tool_version=tool_version, raw_output=raw_output),
        metadata=metadata or {},
    )


def _call_graph(metadata: dict) -> SourceCallGraph:
    return SourceCallGraph(
        adapter_id="solidity-source",
        language="solidity",
        modules=["vault"],
        edges=[],
        metadata=metadata,
    )


# --- level computation (PC-1 Action 3/4: per-capability evidence) -------------------------------


def test_tool_backed_call_graph_plus_traces_reaches_production_candidate() -> None:
    level = _level(resolved=1, unresolved=0, edges=1, provenanced_traces=1, tool_backed_call_graph=True)
    assert level == "production_candidate"


def test_regex_call_graph_with_real_traces_caps_below_production_candidate() -> None:
    """The HELPER's flagged boundary: a regex/static call-graph edge must NOT contribute to a
    production_candidate result even when provenanced Foundry traces are present."""
    level = _level(resolved=1, unresolved=0, edges=1, provenanced_traces=1, tool_backed_call_graph=False)
    assert level == "trace_capable"


def test_tool_backed_call_graph_without_edges_is_only_trace_capable() -> None:
    """The real Foundry fixture's case: Slither runs (tool-backed) but emits no edges, so even with
    provenanced traces the achieved level is trace_capable, not production_candidate."""
    level = _level(resolved=1, unresolved=0, edges=0, provenanced_traces=1, tool_backed_call_graph=True)
    assert level == "trace_capable"


def test_tool_backed_call_graph_without_traces_is_static_resolution() -> None:
    level = _level(resolved=1, unresolved=0, edges=1, provenanced_traces=0, tool_backed_call_graph=True)
    assert level == "static_resolution"


def test_unresolved_symbol_caps_at_manifest_only() -> None:
    level = _level(resolved=1, unresolved=1, edges=1, provenanced_traces=1, tool_backed_call_graph=True)
    assert level == "manifest_only"


# --- call-graph backing signal ------------------------------------------------------------------


def test_slither_analyzed_with_version_is_tool_backed() -> None:
    assert _call_graph_is_tool_backed(
        _call_graph({"analysis": "slither", "slither_status": "analyzed", "slither_version": "0.9.6"})
    )


def test_regex_fallback_call_graph_is_not_tool_backed() -> None:
    assert not _call_graph_is_tool_backed(
        _call_graph({"analysis": "regex-static", "slither_status": "unavailable"})
    )


def test_slither_analyzed_without_recorded_version_is_not_tool_backed() -> None:
    """A recorded tool version is required, not just an ``analyzed`` status."""
    assert not _call_graph_is_tool_backed(_call_graph({"slither_status": "analyzed"}))


# --- source-bound trace-provenance gate (PC-1 Action 1/2) ---------------------------------------


def test_real_forge_report_is_source_bound_evidence() -> None:
    report = _forge_report()
    trace = _trace(raw_output=report, metadata={"suite": "VaultTest", "test": "testRedeem()"})
    assert trace_has_real_tool_provenance(trace)


def test_normalized_trace_blob_stamped_with_self_hash_is_rejected() -> None:
    """The exact loophole: stamp a producer + a self-consistent sha256 over a NormalizedTrace blob.
    The hash recompute passes, but the carried bytes are not a forge report, so the gate rejects it."""
    blob = _trace(raw_output=None).model_dump_json()
    self_hashed = _trace(raw_output=blob)  # source_hash defaults to sha256(blob)
    assert not trace_has_real_tool_provenance(self_hashed)


def test_hash_not_matching_carried_output_is_rejected() -> None:
    report = _forge_report()
    trace = _trace(raw_output=report, source_hash="sha256:" + "a" * 64)
    assert not trace_has_real_tool_provenance(trace)


def test_missing_raw_output_is_rejected() -> None:
    trace = _trace(raw_output=None, source_hash="sha256:" + "b" * 64)
    assert not trace_has_real_tool_provenance(trace)


def test_unknown_tool_has_no_validator_and_is_rejected() -> None:
    report = _forge_report()
    trace = _trace(raw_output=report, tool="mystery-tracer")
    assert not trace_has_real_tool_provenance(trace)


def test_suite_or_test_name_mismatch_breaks_the_binding() -> None:
    """When the trace records its own suite/test, they must appear in the carried forge report."""
    report = _forge_report(suite="VaultTest", test="testRedeem()")
    mismatch = _trace(raw_output=report, metadata={"suite": "OtherTest", "test": "testRedeem()"})
    assert not trace_has_real_tool_provenance(mismatch)
