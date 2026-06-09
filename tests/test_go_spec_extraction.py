"""PC-8 — Specula-style candidate S extraction for Go, gated by trace validation.

The candidate S is proposed by a deterministic RecordedLlmClient reading the module SOURCE (no live
LLM); its trace-observable obligations are then validated against the module's real Go traces. A
candidate whose obligations the traces reproduce is promotable; a paper-only candidate (asserting an
operation the code never runs) is rejected. The gate-logic tests run fully offline against a
constructed real-shaped trace; one end-to-end test extracts the trace from a real Go execution.
"""

import json
from pathlib import Path

import pytest

from nlreq import go_client
from nlreq.dsl_v2 import DslV2Parser
from nlreq.impact import ImpactAnalysisArtifact
from nlreq.llm_client import RecordedLlmClient
from nlreq.models import (
    NormalizedTrace,
    NormalizedTraceArtifact,
    RequirementIRV2,
    SymbolRef,
    TraceEvent,
)
from nlreq.production_source_adapters import GoSourceAdapter
from nlreq.source_adapter import CodePresentation, SourceManifest
from nlreq.spec_extraction import (
    extract_go_candidate_spec,
    parse_spec_extraction,
    promote_candidate_spec_with_review,
)


FIXTURE_ROOT = Path(__file__).parent / "fixtures" / "go"
REQUIREMENTS = Path(__file__).parent / "fixtures" / "requirements"

requires_go = pytest.mark.skipif(
    not go_client.go_trace_tools_available(),
    reason="go is not installed; run with go on PATH to extract a real runtime/trace",
)

requires_go_tools = pytest.mark.skipif(
    not go_client.go_symbol_tools_available(),
    reason="go/gopls/callgraph are not installed; run with the Go toolchain on PATH",
)


def _go_manifest() -> SourceManifest:
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
                    "symbols": ["Coordinate"],
                }
            ],
        }
    )

# A candidate S whose invariants + trace obligations are read from the coordinator SOURCE: the
# validate and record stages the code actually runs.
_REAL_EXTRACTION = json.dumps(
    {
        "module": "coordinator",
        "invariants": [
            {"name": "ValidateBeforeRecord", "tla": "validate_done => record_started"},
            {"name": "TotalNonNegative", "tla": "total >= 0"},
        ],
        "trace_expectations": [
            {"expectation_id": "exp-validate", "kind": "event_emitted", "target": "validate"},
            {"expectation_id": "exp-record", "kind": "event_emitted", "target": "record"},
        ],
    }
)

# A paper-only candidate: it asserts a "settle" stage that exists in the whitepaper but that the code
# never runs. The trace can never witness it.
_PAPER_ONLY_EXTRACTION = json.dumps(
    {
        "module": "coordinator",
        "invariants": [{"name": "SettlementFinalizes", "tla": "settle_done => finalized"}],
        "trace_expectations": [
            {"expectation_id": "exp-settle", "kind": "event_emitted", "target": "settle"}
        ],
    }
)


def _requirement() -> RequirementIRV2:
    return DslV2Parser().parse_ir(
        (REQUIREMENTS / "dsl_v2_redemption.nlreq2").read_text(),
        requirement_id="REQ-GO-EXTRACT-001",
        title="Go spec extraction",
    )


def _impact() -> ImpactAnalysisArtifact:
    return ImpactAnalysisArtifact(
        adapter_id="go-source",
        language="go",
        input_symbols=["Coordinate"],
        affected_modules=["coordinator"],
    )


def _presentation() -> CodePresentation:
    return CodePresentation(
        adapter_id="go-source",
        language="go",
        snippets=[
            {
                "path": "coordinator/coordinator.go",
                "content": "func Coordinate(amount int, stages []Stage) int { ... }",
            }
        ],
    )


def _go_traces() -> NormalizedTraceArtifact:
    """A real-shaped Go trace (validate then record stages on a worker goroutine) for the offline
    gate-logic tests. The end-to-end test below extracts the equivalent trace from a real run."""

    def event(ordinal: int, action: str, goroutine: int) -> TraceEvent:
        return TraceEvent(
            event_id=f"region-{ordinal}",
            timestamp=ordinal,
            actor=f"goroutine-{goroutine}",
            action=action,
            language="go",
            runtime="go",
            metadata={"goroutine": goroutine, "kind": "RegionBegin"},
        )

    trace = NormalizedTrace(
        trace_id="go::./coordinator/",
        adapter_id="go-source",
        source_hash="sha256:" + "0" * 64,
        language="go",
        runtime="go",
        events=[event(0, "redeem", 7), event(1, "validate", 8), event(2, "record", 8)],
        metadata={"producer": "go-runtime-trace"},
    )
    return NormalizedTraceArtifact.model_validate([trace])


def test_real_candidate_is_trace_validated_and_promotable() -> None:
    report = extract_go_candidate_spec(
        requirement=_requirement(),
        module_id="coordinator",
        impact=_impact(),
        code_presentation=_presentation(),
        traces=_go_traces(),
        llm=RecordedLlmClient("", spec_fixture=_REAL_EXTRACTION),
    )

    assert report.promotable is True
    assert report.candidate.trace_grounding_status == "passed"
    assert report.trace_contract.provenance == "specula_extracted"
    # The candidate S is REAL, not the vacuous `CandidateInvariant == TRUE` placeholder.
    assert "== TRUE" not in report.candidate.content
    assert "ValidateBeforeRecord" in report.candidate.content
    # Every declared obligation is reproduced by the real traces.
    assert {observation.outcome for observation in report.spec_trace_replay.observations} == {
        "satisfied"
    }

    # The candidate flows through the existing trace-gated promotion to a reviewed spec.
    promotion = promote_candidate_spec_with_review(
        report.candidate,
        approved_hash=report.candidate.content_hash,
        version="1",
        reviewer_id="reviewer",
        reviewed_at="2026-06-09T00:00:00Z",
    )
    assert promotion.decision == "promoted"
    assert promotion.promoted_spec is not None
    assert promotion.promoted_spec.review_status == "reviewed"


def test_paper_only_candidate_is_rejected_by_the_trace_guard() -> None:
    report = extract_go_candidate_spec(
        requirement=_requirement(),
        module_id="coordinator",
        impact=_impact(),
        code_presentation=_presentation(),
        traces=_go_traces(),
        llm=RecordedLlmClient("", spec_fixture=_PAPER_ONLY_EXTRACTION),
    )

    assert report.promotable is False
    assert report.candidate.trace_grounding_status == "blocked"
    # The "settle" obligation has no coverage: the trace never witnesses it.
    assert [observation.outcome for observation in report.spec_trace_replay.observations] == [
        "no_coverage"
    ]
    assert report.rejection_reasons

    # The existing trace-gated promotion blocks a candidate the traces do not reproduce.
    promotion = promote_candidate_spec_with_review(
        report.candidate,
        approved_hash=report.candidate.content_hash,
        version="1",
        reviewer_id="reviewer",
        reviewed_at="2026-06-09T00:00:00Z",
    )
    assert promotion.decision == "blocked"
    assert promotion.promoted_spec is None


def test_candidate_with_no_trace_obligation_is_not_promotable() -> None:
    """A candidate that declares no trace-observable obligation cannot be validated against the
    code's traces at all, so it is rejected as ungrounded rather than promoted on an empty contract."""
    extraction = json.dumps(
        {"invariants": [{"name": "Anything", "tla": "TRUE"}], "trace_expectations": []}
    )
    report = extract_go_candidate_spec(
        requirement=_requirement(),
        module_id="coordinator",
        impact=_impact(),
        code_presentation=_presentation(),
        traces=_go_traces(),
        llm=RecordedLlmClient("", spec_fixture=extraction),
    )

    assert report.promotable is False
    assert report.rejection_reasons


def test_parse_spec_extraction_is_defensive() -> None:
    """The untrusted proposal parser tolerates fences and malformed input and drops obligation kinds a
    runtime/trace cannot witness."""
    fenced = "```json\n" + _REAL_EXTRACTION + "\n```"
    parsed = parse_spec_extraction(fenced)
    assert len(parsed.invariants) == 2
    assert {expectation.target for expectation in parsed.trace_expectations} == {"validate", "record"}

    # Malformed output yields an empty extraction (which the gate rejects), never a crash.
    assert parse_spec_extraction("not json at all").invariants == []

    # An EVM-shaped obligation kind a runtime/trace cannot witness is dropped.
    evm_shaped = json.dumps(
        {
            "invariants": [],
            "trace_expectations": [
                {"expectation_id": "x", "kind": "action_reverts", "target": "withdraw"}
            ],
        }
    )
    assert parse_spec_extraction(evm_shaped).trace_expectations == []


def _presentation_text(presentation: CodePresentation) -> str:
    return "\n\n".join(snippet.get("content", "") for snippet in presentation.snippets)


@requires_go_tools
def test_go_presentation_is_source_grounded_with_callee_bodies() -> None:
    """PC-8 source grounding: the Go presentation carries the requested symbol's FULL declaration body
    plus the bodies of the in-module callees CHA resolves the interface dispatch to — not just the
    gopls identifier token. So a candidate S extracted for Coordinate is grounded in the validate and
    record logic, not in a bare name."""
    adapter = GoSourceAdapter(project_root=FIXTURE_ROOT)

    presentation = adapter.present_to_llm([SymbolRef(name="Coordinate")], _go_manifest())

    assert presentation.metadata["analysis"] == "gopls"
    text = _presentation_text(presentation)
    # The requested symbol's full body, including the interface dispatch call site.
    assert "func Coordinate(" in text
    assert "s.Run(out)" in text
    # The callee implementations reached ONLY via CHA dispatch — a lexical pass that sees `s.Run(out)`
    # cannot attribute these concrete receivers, so identifier-only presentation would omit them.
    assert "func (Validator) Run(" in text
    assert "func (r *Recorder) Run(" in text


@requires_go
@requires_go_tools
def test_end_to_end_real_go_trace_promotes_extracted_candidate() -> None:
    """The full chain: the adapter extracts a REAL Go runtime/trace and presents real source bodies,
    and the source-extracted candidate S is promotable because its obligations are reproduced by that
    real trace."""
    adapter = GoSourceAdapter(project_root=FIXTURE_ROOT)
    manifest = _go_manifest()
    traces = adapter.extract_traces(manifest)
    presentation = adapter.present_to_llm([SymbolRef(name="Coordinate")], manifest)

    # The presentation the candidate is grounded in carries real source — Coordinate's body and the
    # Validator.Run / (*Recorder).Run implementations — BEFORE the (recorded) LLM reads it.
    presented = _presentation_text(presentation)
    assert "func Coordinate(" in presented
    assert "func (Validator) Run(" in presented
    assert "func (r *Recorder) Run(" in presented

    report = extract_go_candidate_spec(
        requirement=_requirement(),
        module_id="coordinator",
        impact=_impact(),
        code_presentation=presentation,
        traces=traces,
        llm=RecordedLlmClient("", spec_fixture=_REAL_EXTRACTION),
    )

    assert report.promotable is True
    assert report.candidate.trace_grounding_status == "passed"
