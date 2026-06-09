"""PC-5 — Specula-style candidate S extraction for Solidity, gated by trace validation.

Mirrors the Go suite (PC-8): the candidate S is proposed by a deterministic RecordedLlmClient reading
the contract SOURCE (no live LLM); its trace-observable obligations are then validated against the
module's real Foundry traces. The Solidity obligations are EVM-shaped — beyond an emitted event or a
forbidden action, a Foundry trace witnesses a view read reaching a value (``state_value_reached``) and
a call that reverts (``action_reverts``) — so a candidate is promotable only if those obligations are
REPRODUCED by the real traces, and a paper-only candidate (a value a read never reaches, a revert that
never happens, an event never emitted) is rejected. The gate-logic tests run fully offline against a
constructed real-shaped Foundry trace; one end-to-end test extracts the trace from a real ``forge``
run.
"""

import json
from pathlib import Path

import pytest

from nlreq import foundry_client
from nlreq.cli import main
from nlreq.dsl_v2 import DslV2Parser
from nlreq.impact import ImpactAnalysisArtifact
from nlreq.jsonutil import read_json
from nlreq.llm_client import RecordedLlmClient
from nlreq.models import (
    NormalizedTrace,
    NormalizedTraceArtifact,
    RequirementIRV2,
    SymbolRef,
    TraceEvent,
)
from nlreq.production_source_adapters import SoliditySourceAdapter
from nlreq.source_adapter import CodePresentation, SourceManifest
from nlreq.spec_extraction import (
    SOLIDITY_TRACE_KINDS,
    build_specula_extraction_integration_report,
    candidate_to_draft_spec_entry,
    extract_solidity_candidate_spec,
    parse_spec_extraction,
    promote_candidate_spec_with_review,
)
from nlreq.system_spec import SystemSpecRegistry


FOUNDRY_ROOT = Path(__file__).parent / "fixtures" / "foundry"
REQUIREMENTS = Path(__file__).parent / "fixtures" / "requirements"

requires_forge = pytest.mark.skipif(
    not foundry_client.foundry_available(),
    reason="forge (Foundry) is not installed; run with forge on PATH to extract a real trace",
)


# A candidate S whose invariants + EVM-shaped trace obligations are read from the Vault SOURCE: the
# Redeemed event the contract emits and the total() read that reaches 5 after the redemption.
_REAL_EXTRACTION = json.dumps(
    {
        "module": "vault",
        "invariants": [
            {"name": "RedeemedWithinTotal", "tla": "redeemed <= total"},
            {"name": "TotalNonNegative", "tla": "total >= 0"},
        ],
        "trace_expectations": [
            {"expectation_id": "exp-redeemed", "kind": "event_emitted", "target": "Redeemed"},
            {
                "expectation_id": "exp-total",
                "kind": "state_value_reached",
                "target": "total",
                "value": "5",
            },
        ],
    }
)

# A paper-only candidate: it asserts the total() read reaches 100, a value the contract never produces
# (the read returns 5). The trace actively CONTRADICTS it (a populated delta), not merely no-coverage.
_PAPER_ONLY_VALUE_EXTRACTION = json.dumps(
    {
        "module": "vault",
        "invariants": [{"name": "TotalIsHundred", "tla": "total = 100"}],
        "trace_expectations": [
            {
                "expectation_id": "exp-total-100",
                "kind": "state_value_reached",
                "target": "total",
                "value": "100",
            }
        ],
    }
)


def _requirement() -> RequirementIRV2:
    return DslV2Parser().parse_ir(
        (REQUIREMENTS / "dsl_v2_redemption.nlreq2").read_text(),
        requirement_id="REQ-SOL-EXTRACT-001",
        title="Solidity spec extraction",
    )


def _impact() -> ImpactAnalysisArtifact:
    return ImpactAnalysisArtifact(
        adapter_id="solidity-source",
        language="solidity",
        input_symbols=["requestRedemption"],
        affected_modules=["vault"],
    )


def _presentation() -> CodePresentation:
    return CodePresentation(
        adapter_id="solidity-source",
        language="solidity",
        snippets=[
            {
                "path": "src/Vault.sol",
                "content": "function requestRedemption(uint256 amount) external { ... emit Redeemed(...); }",
            }
        ],
    )


def _solidity_traces() -> NormalizedTraceArtifact:
    """A real-shaped Foundry trace (the redemption call, a total() read reaching 5, the Redeemed log,
    and a reverting sub-call) for the offline gate-logic tests. The end-to-end test below extracts the
    equivalent trace from a real ``forge`` run. The event shapes mirror SoliditySourceAdapter's
    `_normalize_foundry_event`: a view read carries metadata['decoded_output'], a revert carries
    metadata['reverted']/['revert_reason']."""

    def call(
        ordinal: int,
        action: str,
        *,
        decoded_output: str | None = None,
        reverted: bool = False,
        revert_reason: str | None = None,
    ) -> TraceEvent:
        metadata: dict[str, object] = {"kind": "call", "depth": 0, "evm_runtime": "foundry"}
        post_state: dict[str, object] | None = None
        if decoded_output is not None:
            metadata["decoded_output"] = decoded_output
            post_state = {"return": decoded_output}
        if reverted:
            metadata["success"] = False
            metadata["reverted"] = True
            if revert_reason is not None:
                metadata["revert_reason"] = revert_reason
        else:
            metadata["success"] = True
        return TraceEvent(
            event_id=f"call-{ordinal}",
            timestamp=ordinal,
            actor="0xcaller",
            action=action,
            post_state=post_state,
            language="solidity",
            runtime="evm",
            metadata=metadata,
        )

    def log(ordinal: int, action: str, params: dict[str, str]) -> TraceEvent:
        return TraceEvent(
            event_id=f"log-{ordinal}",
            timestamp=ordinal,
            actor="0xcaller",
            action=action,
            post_state={"event_params": params},
            language="solidity",
            runtime="evm",
            metadata={"kind": "log", "depth": 0, "evm_runtime": "foundry", "params": params},
        )

    trace = NormalizedTrace(
        trace_id="VaultTest::testRedemption",
        adapter_id="solidity-source",
        source_hash="sha256:" + "0" * 64,
        language="solidity",
        runtime="evm",
        events=[
            call(0, "requestRedemption()"),
            call(1, "total()", decoded_output="5"),
            log(2, "Redeemed(address,uint256)", {"redeemer": "0xabc", "amount": "5"}),
            call(3, "willRevert()", reverted=True, revert_reason="child reverted"),
        ],
        metadata={"producer": "foundry", "suite": "VaultTest", "test": "testRedemption"},
    )
    return NormalizedTraceArtifact.model_validate([trace])


def test_real_candidate_is_trace_validated_and_promotable() -> None:
    report = extract_solidity_candidate_spec(
        requirement=_requirement(),
        module_id="vault",
        impact=_impact(),
        code_presentation=_presentation(),
        traces=_solidity_traces(),
        llm=RecordedLlmClient("", spec_fixture=_REAL_EXTRACTION),
    )

    assert report.promotable is True
    assert report.candidate.trace_grounding_status == "passed"
    assert report.trace_contract.provenance == "specula_extracted"
    # The candidate S is REAL, not the vacuous `CandidateInvariant == TRUE` placeholder.
    assert "== TRUE" not in report.candidate.content
    assert "RedeemedWithinTotal" in report.candidate.content
    # An EVM-shaped obligation (the total() read reaching its claimed value) is part of the contract.
    assert "[state_value_reached]: total = 5" in report.candidate.content
    # Every declared obligation is reproduced by the real traces (an emitted event AND a value read).
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


def test_paper_only_value_candidate_is_rejected_by_the_trace_guard() -> None:
    """The EVM-specific paper-only shape: the spec claims a value the read never reaches. The traces
    actively contradict it (a populated delta), so it is rejected — not silently passed."""
    report = extract_solidity_candidate_spec(
        requirement=_requirement(),
        module_id="vault",
        impact=_impact(),
        code_presentation=_presentation(),
        traces=_solidity_traces(),
        llm=RecordedLlmClient("", spec_fixture=_PAPER_ONLY_VALUE_EXTRACTION),
    )

    assert report.promotable is False
    assert report.candidate.trace_grounding_status == "blocked"
    # The read IS observed but never reaches 100 — a violation (delta), distinct from no-coverage.
    assert [observation.outcome for observation in report.spec_trace_replay.observations] == [
        "violated"
    ]
    assert report.rejection_reasons

    promotion = promote_candidate_spec_with_review(
        report.candidate,
        approved_hash=report.candidate.content_hash,
        version="1",
        reviewer_id="reviewer",
        reviewed_at="2026-06-09T00:00:00Z",
    )
    assert promotion.decision == "blocked"
    assert promotion.promoted_spec is None


def test_paper_only_event_candidate_is_rejected() -> None:
    """A candidate asserting an event the contract never emits has no coverage: the trace never
    witnesses it, so it is rejected (mirrors the Go paper-only `event_emitted` shape)."""
    extraction = json.dumps(
        {
            "module": "vault",
            "invariants": [{"name": "SettledFinalizes", "tla": "settled => finalized"}],
            "trace_expectations": [
                {"expectation_id": "exp-settled", "kind": "event_emitted", "target": "Settled"}
            ],
        }
    )
    report = extract_solidity_candidate_spec(
        requirement=_requirement(),
        module_id="vault",
        impact=_impact(),
        code_presentation=_presentation(),
        traces=_solidity_traces(),
        llm=RecordedLlmClient("", spec_fixture=extraction),
    )

    assert report.promotable is False
    assert report.candidate.trace_grounding_status == "blocked"
    assert [observation.outcome for observation in report.spec_trace_replay.observations] == [
        "no_coverage"
    ]
    assert report.rejection_reasons


def test_action_reverts_candidate_is_promotable() -> None:
    """An ``action_reverts`` obligation the contract reproduces (the call reverts with the claimed
    reason) is positively witnessed by the revert events, so the candidate is promotable."""
    extraction = json.dumps(
        {
            "module": "vault",
            "invariants": [{"name": "GuardedCall", "tla": "guarded => safe"}],
            "trace_expectations": [
                {
                    "expectation_id": "exp-revert",
                    "kind": "action_reverts",
                    "target": "willRevert",
                    "value": "child reverted",
                }
            ],
        }
    )
    report = extract_solidity_candidate_spec(
        requirement=_requirement(),
        module_id="vault",
        impact=_impact(),
        code_presentation=_presentation(),
        traces=_solidity_traces(),
        llm=RecordedLlmClient("", spec_fixture=extraction),
    )

    assert report.promotable is True
    assert report.candidate.trace_grounding_status == "passed"
    assert [observation.outcome for observation in report.spec_trace_replay.observations] == [
        "satisfied"
    ]
    # The revert is positively witnessed — the matched event ids are the reverting call.
    assert report.spec_trace_replay.observations[0].matched_event_ids


def test_action_reverts_violated_when_call_never_reverts() -> None:
    """An ``action_reverts`` obligation against a call that IS observed but never reverts is a
    violation (delta), so the candidate is rejected."""
    extraction = json.dumps(
        {
            "module": "vault",
            "invariants": [{"name": "AlwaysReverts", "tla": "requested => reverted"}],
            "trace_expectations": [
                {
                    "expectation_id": "exp-req-revert",
                    "kind": "action_reverts",
                    "target": "requestRedemption",
                }
            ],
        }
    )
    report = extract_solidity_candidate_spec(
        requirement=_requirement(),
        module_id="vault",
        impact=_impact(),
        code_presentation=_presentation(),
        traces=_solidity_traces(),
        llm=RecordedLlmClient("", spec_fixture=extraction),
    )

    assert report.promotable is False
    assert [observation.outcome for observation in report.spec_trace_replay.observations] == [
        "violated"
    ]
    assert report.rejection_reasons


def test_candidate_with_no_trace_obligation_is_not_promotable() -> None:
    """A candidate that declares no trace-observable obligation cannot be validated against the
    contract's traces at all, so it is rejected as ungrounded rather than promoted on an empty
    contract."""
    extraction = json.dumps(
        {"invariants": [{"name": "Anything", "tla": "TRUE"}], "trace_expectations": []}
    )
    report = extract_solidity_candidate_spec(
        requirement=_requirement(),
        module_id="vault",
        impact=_impact(),
        code_presentation=_presentation(),
        traces=_solidity_traces(),
        llm=RecordedLlmClient("", spec_fixture=extraction),
    )

    assert report.promotable is False
    assert report.rejection_reasons


def test_solidity_candidate_without_invariant_is_not_promotable() -> None:
    """A candidate whose obligations the contract reproduces but which declares NO invariant would
    promote to a reviewed S with an empty invariant list — which the S ∧ R gate refuses. So it is
    rejected at extraction: the block is the absent safety property, NOT trace grounding."""
    extraction = json.dumps(
        {
            "module": "vault",
            "invariants": [],
            "trace_expectations": [
                {"expectation_id": "exp-redeemed", "kind": "event_emitted", "target": "Redeemed"}
            ],
        }
    )
    report = extract_solidity_candidate_spec(
        requirement=_requirement(),
        module_id="vault",
        impact=_impact(),
        code_presentation=_presentation(),
        traces=_solidity_traces(),
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


def test_absence_only_solidity_candidate_is_not_promotable() -> None:
    """A candidate whose ONLY obligation is an ``action_never`` against a target the contract never
    runs is "satisfied" by ABSENCE alone — it witnesses no real EVM behavior. PC-5 requires at least
    one positively-witnessed obligation, so it is rejected rather than promoted on negative evidence."""
    extraction = json.dumps(
        {
            "module": "vault",
            "invariants": [{"name": "NeverDrains", "tla": "~drained"}],
            "trace_expectations": [
                {"expectation_id": "exp-never-drain", "kind": "action_never", "target": "drain"}
            ],
        }
    )
    report = extract_solidity_candidate_spec(
        requirement=_requirement(),
        module_id="vault",
        impact=_impact(),
        code_presentation=_presentation(),
        traces=_solidity_traces(),
        llm=RecordedLlmClient("", spec_fixture=extraction),
    )

    assert report.promotable is False
    assert report.candidate.trace_grounding_status == "blocked"
    # The forbidden action is absent, so the obligation is 'satisfied' — but by ABSENCE, with no
    # matched event ids. The positive-witness rule rejects it.
    assert [observation.outcome for observation in report.spec_trace_replay.observations] == [
        "satisfied"
    ]
    assert report.spec_trace_replay.observations[0].matched_event_ids == []
    assert any("positively witnessed" in reason for reason in report.rejection_reasons)


def test_promoted_solidity_candidate_carries_extracted_invariant_names() -> None:
    """PC-5 draft→reviewed promotion must yield a USABLE reviewed S: the extracted invariant operator
    names are carried onto both the draft and the promoted SystemSpecEntry, so the promoted spec is
    not refused by the S ∧ R "no declared invariant" guard."""
    report = extract_solidity_candidate_spec(
        requirement=_requirement(),
        module_id="vault",
        impact=_impact(),
        code_presentation=_presentation(),
        traces=_solidity_traces(),
        llm=RecordedLlmClient("", spec_fixture=_REAL_EXTRACTION),
    )

    assert report.candidate.invariant_names == ["RedeemedWithinTotal", "TotalNonNegative"]

    draft = candidate_to_draft_spec_entry(report.candidate)
    assert draft.invariants == ["RedeemedWithinTotal", "TotalNonNegative"]

    promotion = promote_candidate_spec_with_review(
        report.candidate,
        approved_hash=report.candidate.content_hash,
        version="1",
        reviewer_id="reviewer",
        reviewed_at="2026-06-09T00:00:00Z",
    )
    assert promotion.promoted_spec is not None
    assert promotion.promoted_spec.invariants == ["RedeemedWithinTotal", "TotalNonNegative"]
    assert [spec for spec in [promotion.promoted_spec] if spec.invariants]


def _empty_registry() -> SystemSpecRegistry:
    return SystemSpecRegistry.model_validate({"schema_version": "0.1", "specs": []})


def test_integration_report_routes_solidity_module_through_real_extraction() -> None:
    """PC-5 wiring: the public integration entry point produces a REAL trace-grounded Solidity
    candidate (not the vacuous `CandidateInvariant == TRUE` placeholder) and clears when its
    obligations reproduce."""
    report = build_specula_extraction_integration_report(
        requirement=_requirement(),
        impact=_impact(),
        registry=_empty_registry(),
        project_root=Path("."),
        code_presentation=_presentation(),
        traces=_solidity_traces(),
        llm=RecordedLlmClient("", spec_fixture=_REAL_EXTRACTION),
    )

    assert report.result == "candidates"
    assert report.blockers == []
    candidate = report.candidates[0]
    assert "== TRUE" not in candidate.content
    assert "RedeemedWithinTotal" in candidate.content
    assert candidate.trace_grounding_status == "passed"
    draft = candidate_to_draft_spec_entry(candidate)
    assert draft.review_status == "draft"
    assert draft.module_ids == ["vault"]


def test_integration_report_blocks_paper_only_solidity_candidate_with_reason() -> None:
    """A paper-only Solidity candidate is blocked by the SAME integration gate, and the blocker
    surfaces WHY: its obligations are not reproduced by the contract's real traces."""
    report = build_specula_extraction_integration_report(
        requirement=_requirement(),
        impact=_impact(),
        registry=_empty_registry(),
        project_root=Path("."),
        code_presentation=_presentation(),
        traces=_solidity_traces(),
        llm=RecordedLlmClient("", spec_fixture=_PAPER_ONLY_VALUE_EXTRACTION),
    )

    assert report.result == "blocked"
    assert report.candidates[0].trace_grounding_status == "blocked"
    assert "trace validation has not passed" in report.blockers[0]
    assert "not reproduced" in report.blockers[0]


def test_integration_report_blocks_solidity_module_with_missing_inputs() -> None:
    """Without the offline LLM client + real traces, the Solidity path does NOT fall back to the
    vacuous `CandidateInvariant == TRUE` placeholder: it emits an explicit missing-input block naming
    which inputs are absent, and the integration gate blocks it."""
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
    assert "== TRUE" not in candidate.content
    assert candidate.trace_grounding_status == "missing"
    assert candidate.invariant_names == []
    assert any("real Solidity (Foundry) traces" in gap for gap in candidate.gaps)
    assert any("recorded LLM client" in gap for gap in candidate.gaps)
    assert "Solidity Specula extraction did not run" in report.blockers[0]


def test_specula_extract_cli_routes_solidity_module_offline(tmp_path: Path, capsys) -> None:
    """The specula-extract CLI drives the Solidity path fully offline: a recorded proposal + a
    real-shaped trace yield a REAL trace-grounded candidate, and the exit code gates on the
    integration result."""
    paths = {
        name: tmp_path / name
        for name in ("ir.json", "impact.json", "registry.json", "pres.json", "traces.json", "fixture.json", "out.json")
    }
    paths["ir.json"].write_text(_requirement().model_dump_json())
    paths["impact.json"].write_text(_impact().model_dump_json())
    paths["registry.json"].write_text(_empty_registry().model_dump_json())
    paths["pres.json"].write_text(_presentation().model_dump_json())
    paths["traces.json"].write_text(_solidity_traces().model_dump_json())
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
    assert "RedeemedWithinTotal" in report["candidates"][0]["content"]


def test_specula_extract_cli_blocks_paper_only_solidity_candidate(tmp_path: Path) -> None:
    """A paper-only proposal makes the offline CLI exit non-zero — the integration gate blocks it."""
    paths = {
        name: tmp_path / name
        for name in ("ir.json", "impact.json", "registry.json", "pres.json", "traces.json", "fixture.json", "out.json")
    }
    paths["ir.json"].write_text(_requirement().model_dump_json())
    paths["impact.json"].write_text(_impact().model_dump_json())
    paths["registry.json"].write_text(_empty_registry().model_dump_json())
    paths["pres.json"].write_text(_presentation().model_dump_json())
    paths["traces.json"].write_text(_solidity_traces().model_dump_json())
    paths["fixture.json"].write_text(_PAPER_ONLY_VALUE_EXTRACTION)

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


def test_parse_spec_extraction_allows_evm_kinds_for_solidity() -> None:
    """The Solidity extractor admits the EVM-shaped kinds (with the optional ``value``) that the Go
    default drops, so a state-value / revert obligation survives parsing for Solidity but not for the
    Go runtime/trace projection."""
    evm = json.dumps(
        {
            "invariants": [{"name": "I", "tla": "TRUE"}],
            "trace_expectations": [
                {"expectation_id": "x", "kind": "state_value_reached", "target": "total", "value": "5"},
                {"expectation_id": "y", "kind": "action_reverts", "target": "withdraw"},
            ],
        }
    )
    parsed = parse_spec_extraction(evm, allowed_kinds=SOLIDITY_TRACE_KINDS)
    assert {e.kind for e in parsed.trace_expectations} == {"state_value_reached", "action_reverts"}
    state_value = next(e for e in parsed.trace_expectations if e.kind == "state_value_reached")
    assert state_value.value == "5"

    # The Go default still drops these EVM kinds (the runtime/trace cannot witness them).
    assert parse_spec_extraction(evm).trace_expectations == []


def _foundry_manifest() -> SourceManifest:
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
def test_end_to_end_real_foundry_trace_promotes_extracted_candidate() -> None:
    """The full chain: the adapter extracts a REAL Foundry trace and presents real contract source,
    and the source-extracted candidate S is promotable because its EVM obligations (the Redeemed event
    and the total() read reaching 5) are reproduced by that real trace."""
    adapter = SoliditySourceAdapter(project_root=FOUNDRY_ROOT)
    manifest = _foundry_manifest()
    traces = adapter.extract_traces(manifest)
    presentation = adapter.present_to_llm([SymbolRef(name="requestRedemption")], manifest)

    report = extract_solidity_candidate_spec(
        requirement=_requirement(),
        module_id="vault",
        impact=_impact(),
        code_presentation=presentation,
        traces=traces,
        llm=RecordedLlmClient("", spec_fixture=_REAL_EXTRACTION),
    )

    assert report.promotable is True
    assert report.candidate.trace_grounding_status == "passed"
    assert {observation.outcome for observation in report.spec_trace_replay.observations} == {
        "satisfied"
    }
