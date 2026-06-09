"""PC-9 — call-graph-derived impact cross-validated against a semantic (LLM) estimate.

The affected set is derived from the REAL Python call graph (``analyze_source_impact``); a recorded
LLM estimate is cross-validated against it and any disagreement — in either direction — is surfaced
as a review flag rather than silently reconciled. The LLM estimate is offline/deterministic via
``RecordedLlmClient`` (no live model), and is never gateable on its own: a module the model names but
the call graph never reaches does not enter the affected set.
"""

from pathlib import Path

import pytest

from nlreq import slither_client
from nlreq.impact import (
    analyze_source_impact,
    cross_validate_impact,
    cross_validate_impact_with_llm,
)
from nlreq.llm_client import RecordedLlmClient, parse_impact_estimate
from nlreq.production_source_adapters import SoliditySourceAdapter
from nlreq.python_source_adapter import PythonSourceLanguageAdapter
from nlreq.source_adapter import SourceManifest
from nlreq.source_impact import analyze_production_source_impact, llm_semantic_suggestions


_SOLIDITY_FIXTURE_ROOT = Path(__file__).parent / "fixtures" / "solidity"

requires_slither = pytest.mark.skipif(
    not slither_client.slither_available(),
    reason="slither is not installed; run with slither on PATH to exercise the real analyzer",
)


def _solidity_manifest() -> SourceManifest:
    return SourceManifest.model_validate(
        {
            "schema_version": "0.1",
            "adapter": "solidity-source",
            "language": "solidity",
            "runtime": "evm",
            "modules": [
                {"module_id": "base", "path": "src/Base.sol", "symbols": ["Base", "Redeemed", "_audit"]},
                {"module_id": "vault", "path": "src/Vault.sol", "symbols": ["Vault", "withdraw", "total"]},
            ],
        }
    )


def _project(tmp_path: Path) -> SourceManifest:
    src = tmp_path / "src"
    src.mkdir()
    (src / "auth.py").write_text(
        "from state import state_change\n\n"
        "def operation(actor):\n"
        "    return state_change()\n"
    )
    (src / "state.py").write_text("def state_change():\n    return 'changed'\n")
    return SourceManifest.model_validate(
        {
            "schema_version": "0.1",
            "adapter": "python-source",
            "language": "python",
            "runtime": "cpython",
            "modules": [
                {"module_id": "auth", "path": "src/auth.py", "symbols": ["operation"]},
                {"module_id": "state", "path": "src/state.py", "symbols": ["state_change"]},
                {"module_id": "billing", "path": "src/billing.py", "symbols": ["charge"]},
            ],
        }
    )


def test_affected_set_is_call_graph_derived_not_the_llm_estimate(tmp_path: Path) -> None:
    """The affected set is the call-graph-reachable set; the LLM estimate cannot widen or narrow it."""
    manifest = _project(tmp_path)
    adapter = PythonSourceLanguageAdapter(project_root=tmp_path)
    impact = analyze_source_impact(adapter, manifest, symbols=["operation"])
    assert impact.affected_modules == ["auth", "state"]

    # The LLM under-includes (omits "state") AND over-includes ("billing"): neither changes the set.
    client = RecordedLlmClient("unused-rewrite", impact_fixture='["auth", "billing"]')
    report = cross_validate_impact_with_llm(
        impact,
        client=client,
        prose="when operation runs the state changes",
        symbols=["operation"],
        candidate_modules=[m.module_id for m in manifest.modules],
    )

    # Authoritative affected set is unchanged — exactly the call-graph set.
    assert report.affected_modules == ["auth", "state"]
    assert report.call_graph_modules == ["auth", "state"]


def test_planted_llm_call_graph_disagreement_is_surfaced_both_directions(tmp_path: Path) -> None:
    """A planted disagreement is surfaced as review flags in BOTH directions, never resolved away."""
    manifest = _project(tmp_path)
    adapter = PythonSourceLanguageAdapter(project_root=tmp_path)
    impact = analyze_source_impact(adapter, manifest, symbols=["operation"])

    client = RecordedLlmClient("unused-rewrite", impact_fixture='["auth", "billing"]')
    report = cross_validate_impact_with_llm(
        impact,
        client=client,
        prose="when operation runs the state changes",
        symbols=["operation"],
        candidate_modules=[m.module_id for m in manifest.modules],
    )

    assert report.disagreement is True
    assert report.agreed_modules == ["auth"]
    # "state" is reachable by the call graph but the LLM missed it.
    assert report.call_graph_only_modules == ["state"]
    # "billing" is named by the LLM but the call graph never reaches it.
    assert report.semantic_only_modules == ["billing"]
    flagged = {(flag.category, flag.module_id) for flag in report.flags}
    assert ("call_graph_only", "state") in flagged
    assert ("semantic_only", "billing") in flagged
    assert all(flag.severity == "review" for flag in report.flags)


def test_full_agreement_produces_no_disagreement_flags(tmp_path: Path) -> None:
    manifest = _project(tmp_path)
    adapter = PythonSourceLanguageAdapter(project_root=tmp_path)
    impact = analyze_source_impact(adapter, manifest, symbols=["operation"])

    report = cross_validate_impact(impact, semantic_modules=["auth", "state"])

    assert report.disagreement is False
    assert report.flags == []
    assert report.agreed_modules == ["auth", "state"]


def test_llm_semantic_suggestions_feed_production_impact_disagreement(tmp_path: Path) -> None:
    """The LLM estimate, routed through the production report, surfaces disagreement in BOTH
    directions — a module the estimate named outside the call graph (semantic_only), and the
    deterministic call-graph modules the estimate omitted (call_graph_only) — each as a non-gateable
    review finding, never silently reconciled. Wires the PC-9 producer into the disagreement infra."""
    manifest = _project(tmp_path)
    adapter = PythonSourceLanguageAdapter(project_root=tmp_path)
    # The estimate names only "billing" — it OMITS the deterministic call-graph modules auth/state.
    client = RecordedLlmClient("unused-rewrite", impact_fixture='["billing"]')

    suggestions = llm_semantic_suggestions(
        client,
        prose="when operation runs the state changes",
        symbols=["operation"],
        candidate_modules=[m.module_id for m in manifest.modules],
    )
    assert [s.module_id for s in suggestions] == ["billing"]
    assert suggestions[0].source == "llm"

    report = analyze_production_source_impact(
        adapter, manifest, symbols=["operation"], semantic_suggestions=suggestions
    )
    # The deterministic call-graph set drives the gateable impact; "billing" is a non-gateable
    # semantic suggestion surfaced as a disagreement, never folded into the gateable set.
    assert report.deterministic_modules == ["auth", "state"]
    assert "billing" not in report.deterministic_modules
    assert any(d.module_id == "billing" and d.semantic_suggestion for d in report.disagreements)
    assert any(
        finding.category == "semantic_suggestion" and finding.module_id == "billing"
        for finding in report.findings
    )
    # The OTHER direction: the estimate omitted auth/state. Each omission is a call-graph-only
    # disagreement (deterministic, no suggestion) and a semantic_omission review finding — the
    # authoritative set still includes them, so this is a review signal, not a block.
    omitted = {
        d.module_id for d in report.disagreements if d.deterministic and not d.semantic_suggestion
    }
    assert omitted == {"auth", "state"}
    omission_findings = {f.module_id for f in report.findings if f.category == "semantic_omission"}
    assert omission_findings == {"auth", "state"}
    assert report.closure_effect == "review"


def test_estimate_free_production_impact_has_no_omission_flags(tmp_path: Path) -> None:
    """Without a semantic estimate there is nothing to disagree with, so no deterministic module is
    flagged as omitted — the call_graph_only direction fires only when an estimate was provided."""
    manifest = _project(tmp_path)
    adapter = PythonSourceLanguageAdapter(project_root=tmp_path)

    report = analyze_production_source_impact(adapter, manifest, symbols=["operation"])

    assert report.deterministic_modules == ["auth", "state"]
    assert report.disagreements == []
    assert all(f.category != "semantic_omission" for f in report.findings)


@requires_slither
def test_slither_call_graph_impact_cross_validated_against_planted_llm_omission() -> None:
    """PC-9 over the REAL Slither call graph: ``withdraw`` reaches ``base._audit`` across the
    inheritance edge, so the call-graph-derived affected set is ``["base", "vault"]``. A planted LLM
    estimate that OMITS ``base`` is surfaced as a ``call_graph_only`` review flag — the authoritative
    affected set stays the call-graph set, never narrowed by the estimate."""
    adapter = SoliditySourceAdapter(project_root=_SOLIDITY_FIXTURE_ROOT)
    impact = analyze_source_impact(adapter, _solidity_manifest(), symbols=["withdraw"])

    # The affected set is derived from the real Slither call graph, not from the LLM estimate.
    assert impact.affected_modules == ["base", "vault"]

    # The recorded LLM estimate names only "vault" — it OMITS the deterministic module "base".
    client = RecordedLlmClient("unused-rewrite", impact_fixture='["vault"]')
    report = cross_validate_impact_with_llm(
        impact,
        client=client,
        prose="withdraw moves funds and audits the caller",
        symbols=["withdraw"],
        candidate_modules=[m.module_id for m in _solidity_manifest().modules],
    )

    # The authoritative affected set stays the call-graph set; the estimate cannot narrow it.
    assert report.affected_modules == ["base", "vault"]
    assert report.call_graph_modules == ["base", "vault"]
    # The omission is surfaced in the call_graph_only direction as a review flag, never resolved away.
    assert report.disagreement is True
    assert report.call_graph_only_modules == ["base"]
    assert report.semantic_only_modules == []
    flagged = {(flag.category, flag.module_id) for flag in report.flags}
    assert ("call_graph_only", "base") in flagged
    assert all(flag.severity == "review" for flag in report.flags)


def test_parse_impact_estimate_tolerates_untrusted_output() -> None:
    assert parse_impact_estimate('["a", "b", "a"]') == ["a", "b"]
    assert parse_impact_estimate('```json\n["x", "y"]\n```') == ["x", "y"]
    # Prose-wrapped bare list falls back to comma/newline splitting.
    assert parse_impact_estimate("a, b\nc") == ["a", "b", "c"]
    # Unparseable / empty output never raises — it yields an empty estimate.
    assert parse_impact_estimate("{}") == []
    assert parse_impact_estimate("") == []


def test_recorded_client_impact_fixture_falls_back_to_main_fixture() -> None:
    # A client constructed solely with the JSON list serves it as the impact estimate.
    only = RecordedLlmClient('["auth", "state"]')
    assert parse_impact_estimate(
        only.estimate_impacted_modules(prose="p", symbols=["s"], candidate_modules=["auth"])
    ) == ["auth", "state"]
