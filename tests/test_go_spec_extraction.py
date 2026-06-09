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
from nlreq.cli import main
from nlreq.jsonutil import read_json
from nlreq.production_source_adapters import GoSourceAdapter
from nlreq.source_adapter import CodePresentation, SourceManifest
from nlreq.spec_extraction import (
    build_specula_extraction_integration_report,
    candidate_to_draft_spec_entry,
    extract_go_candidate_spec,
    parse_spec_extraction,
    promote_candidate_spec_with_review,
)
from nlreq.system_spec import SystemSpecRegistry


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


def test_promoted_go_candidate_carries_extracted_invariant_names() -> None:
    """PC-8 draft→reviewed promotion must yield a USABLE reviewed S: the extracted invariant operator
    names are carried onto both the draft and the promoted SystemSpecEntry, so the promoted spec is
    not refused by the S ∧ R "no declared invariant" guard (end_to_end_gate.py `if spec.invariants`)."""
    report = extract_go_candidate_spec(
        requirement=_requirement(),
        module_id="coordinator",
        impact=_impact(),
        code_presentation=_presentation(),
        traces=_go_traces(),
        llm=RecordedLlmClient("", spec_fixture=_REAL_EXTRACTION),
    )

    # The candidate records the operator names its TLA actually defines.
    assert report.candidate.invariant_names == ["ValidateBeforeRecord", "TotalNonNegative"]

    # The draft entry carries them so registry consumers see the declared invariants.
    draft = candidate_to_draft_spec_entry(report.candidate)
    assert draft.invariants == ["ValidateBeforeRecord", "TotalNonNegative"]

    # The promoted reviewed entry carries them and is therefore checkable by the S ∧ R gate.
    promotion = promote_candidate_spec_with_review(
        report.candidate,
        approved_hash=report.candidate.content_hash,
        version="1",
        reviewer_id="reviewer",
        reviewed_at="2026-06-09T00:00:00Z",
    )
    assert promotion.promoted_spec is not None
    assert promotion.promoted_spec.invariants == ["ValidateBeforeRecord", "TotalNonNegative"]
    # Mirrors the gate guard at end_to_end_gate.py:590 — a reviewed spec WITH a declared invariant is
    # checkable, not refused with refusal_kind "no_system_invariant".
    assert [spec for spec in [promotion.promoted_spec] if spec.invariants]


def test_go_candidate_without_invariant_is_not_promotable() -> None:
    """A candidate whose trace obligations the code reproduces but which declares NO invariant would
    promote to a reviewed S with an empty invariant list — which the S ∧ R gate refuses. So it is
    rejected at extraction: the block is the absent safety property, NOT trace grounding."""
    extraction = json.dumps(
        {
            "module": "coordinator",
            "invariants": [],
            "trace_expectations": [
                {"expectation_id": "exp-validate", "kind": "event_emitted", "target": "validate"}
            ],
        }
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
    assert report.candidate.invariant_names == []
    # The trace obligation IS positively reproduced — so the rejection is the missing invariant.
    assert [observation.outcome for observation in report.spec_trace_replay.observations] == [
        "satisfied"
    ]
    assert report.spec_trace_replay.observations[0].matched_event_ids
    assert any("no invariant" in reason for reason in report.rejection_reasons)
    # The faithful gap names the missing invariant, never a false "not reproduced".
    assert any("no invariants were extracted" in gap for gap in report.candidate.gaps)
    assert not any("not reproduced" in gap for gap in report.candidate.gaps)


def test_absence_only_go_candidate_is_not_promotable() -> None:
    """A candidate whose ONLY obligation is an `action_never` against a target the code never runs is
    "satisfied" by ABSENCE alone — it witnesses no real Go behavior. PC-8 requires at least one
    positively-witnessed obligation, so it is rejected rather than promoted on negative evidence."""
    extraction = json.dumps(
        {
            "module": "coordinator",
            "invariants": [{"name": "NeverSettles", "tla": "~settle_done"}],
            "trace_expectations": [
                {"expectation_id": "exp-never-settle", "kind": "action_never", "target": "settle"}
            ],
        }
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
    assert report.candidate.trace_grounding_status == "blocked"
    # The forbidden action is absent, so the obligation is 'satisfied' — but by ABSENCE, with no
    # matched event ids. The old all-satisfied check would have promoted this; the positive-witness
    # rule rejects it. (The candidate DOES declare an invariant, so this isolates the witness rule.)
    assert [observation.outcome for observation in report.spec_trace_replay.observations] == [
        "satisfied"
    ]
    assert report.spec_trace_replay.observations[0].matched_event_ids == []
    assert any("positively witnessed" in reason for reason in report.rejection_reasons)

    # The existing trace-gated promotion blocks it too — no reviewed spec from absence alone.
    promotion = promote_candidate_spec_with_review(
        report.candidate,
        approved_hash=report.candidate.content_hash,
        version="1",
        reviewer_id="reviewer",
        reviewed_at="2026-06-09T00:00:00Z",
    )
    assert promotion.decision == "blocked"
    assert promotion.promoted_spec is None


def _empty_registry() -> SystemSpecRegistry:
    return SystemSpecRegistry.model_validate({"schema_version": "0.1", "specs": []})


def test_integration_report_routes_go_module_through_real_extraction() -> None:
    """PC-8 wiring: the public integration entry point produces a REAL trace-grounded Go candidate (not
    the vacuous `CandidateInvariant == TRUE` placeholder) and clears when its obligations reproduce."""
    report = build_specula_extraction_integration_report(
        requirement=_requirement(),
        impact=_impact(),
        registry=_empty_registry(),
        project_root=Path("."),
        code_presentation=_presentation(),
        traces=_go_traces(),
        llm=RecordedLlmClient("", spec_fixture=_REAL_EXTRACTION),
    )

    assert report.result == "candidates"
    assert report.blockers == []
    candidate = report.candidates[0]
    assert "== TRUE" not in candidate.content
    assert "ValidateBeforeRecord" in candidate.content
    assert candidate.trace_grounding_status == "passed"
    # The candidate is a draft entry suitable for the SystemSpecRegistry.
    draft = candidate_to_draft_spec_entry(candidate)
    assert draft.review_status == "draft"
    assert draft.module_ids == ["coordinator"]


def test_integration_report_blocks_paper_only_go_candidate_with_reason() -> None:
    """A paper-only Go candidate is blocked by the SAME integration gate, and the blocker surfaces WHY:
    its obligations are not reproduced by the code's real traces."""
    report = build_specula_extraction_integration_report(
        requirement=_requirement(),
        impact=_impact(),
        registry=_empty_registry(),
        project_root=Path("."),
        code_presentation=_presentation(),
        traces=_go_traces(),
        llm=RecordedLlmClient("", spec_fixture=_PAPER_ONLY_EXTRACTION),
    )

    assert report.result == "blocked"
    assert report.candidates[0].trace_grounding_status == "blocked"
    assert "trace validation has not passed" in report.blockers[0]
    assert "not reproduced" in report.blockers[0]


def test_integration_report_blocks_go_module_with_missing_inputs() -> None:
    """Without the offline LLM client + real traces, the Go path does NOT fall back to the vacuous
    `CandidateInvariant == TRUE` placeholder: it emits an explicit missing-input block naming which
    inputs are absent, and the integration gate blocks it. (`_impact` is a Go impact, so the Go
    missing-input path — not the generic placeholder — is exercised.)"""
    report = build_specula_extraction_integration_report(
        requirement=_requirement(),
        impact=_impact(),
        registry=_empty_registry(),
        project_root=Path("."),
        code_presentation=_presentation(),
        # traces and llm intentionally omitted — extraction cannot run.
    )

    assert report.result == "blocked"
    candidate = report.candidates[0]
    # The vacuous placeholder is gone; the block names exactly why it could not run.
    assert "== TRUE" not in candidate.content
    assert candidate.trace_grounding_status == "missing"
    assert candidate.invariant_names == []
    assert any("real Go traces" in gap for gap in candidate.gaps)
    assert any("recorded LLM client" in gap for gap in candidate.gaps)
    assert "Go Specula extraction did not run" in report.blockers[0]


def test_specula_extract_cli_routes_go_module_offline(tmp_path: Path, capsys) -> None:
    """The specula-extract CLI drives the Go path fully offline: a recorded proposal + a real-shaped
    trace yield a REAL trace-grounded candidate, and the exit code gates on the integration result."""
    paths = {name: tmp_path / name for name in ("ir.json", "impact.json", "registry.json", "pres.json", "traces.json", "fixture.json", "out.json")}
    paths["ir.json"].write_text(_requirement().model_dump_json())
    paths["impact.json"].write_text(_impact().model_dump_json())
    paths["registry.json"].write_text(_empty_registry().model_dump_json())
    paths["pres.json"].write_text(_presentation().model_dump_json())
    paths["traces.json"].write_text(_go_traces().model_dump_json())
    paths["fixture.json"].write_text(_REAL_EXTRACTION)

    exit_code = main(
        [
            "specula-extract",
            "--requirement-ir", str(paths["ir.json"]),
            "--impact", str(paths["impact.json"]),
            "--registry", str(paths["registry.json"]),
            "--code-presentation", str(paths["pres.json"]),
            "--traces", str(paths["traces.json"]),
            "--spec-fixture", str(paths["fixture.json"]),
            "--out", str(paths["out.json"]),
        ]
    )

    assert exit_code == 0
    assert "Specula extraction integration report:" in capsys.readouterr().out
    report = read_json(paths["out.json"])
    assert report["result"] == "candidates"
    assert "== TRUE" not in report["candidates"][0]["content"]
    assert "ValidateBeforeRecord" in report["candidates"][0]["content"]


def test_specula_extract_cli_blocks_paper_only_go_candidate(tmp_path: Path, capsys) -> None:
    """A paper-only proposal makes the offline CLI exit non-zero — the integration gate blocks it."""
    paths = {name: tmp_path / name for name in ("ir.json", "impact.json", "registry.json", "pres.json", "traces.json", "fixture.json", "out.json")}
    paths["ir.json"].write_text(_requirement().model_dump_json())
    paths["impact.json"].write_text(_impact().model_dump_json())
    paths["registry.json"].write_text(_empty_registry().model_dump_json())
    paths["pres.json"].write_text(_presentation().model_dump_json())
    paths["traces.json"].write_text(_go_traces().model_dump_json())
    paths["fixture.json"].write_text(_PAPER_ONLY_EXTRACTION)

    exit_code = main(
        [
            "specula-extract",
            "--requirement-ir", str(paths["ir.json"]),
            "--impact", str(paths["impact.json"]),
            "--registry", str(paths["registry.json"]),
            "--code-presentation", str(paths["pres.json"]),
            "--traces", str(paths["traces.json"]),
            "--spec-fixture", str(paths["fixture.json"]),
            "--out", str(paths["out.json"]),
        ]
    )

    assert exit_code == 1
    assert read_json(paths["out.json"])["result"] == "blocked"


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
