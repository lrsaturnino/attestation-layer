"""PC-9 — call-graph-derived impact cross-validated against a semantic (LLM) estimate.

The affected set is derived from the REAL Python call graph (``analyze_source_impact``); a recorded
LLM estimate is cross-validated against it and any disagreement — in either direction — is surfaced
as a review flag rather than silently reconciled. The LLM estimate is offline/deterministic via
``RecordedLlmClient`` (no live model), and is never gateable on its own: a module the model names but
the call graph never reaches does not enter the affected set.
"""

from pathlib import Path

from nlreq.impact import (
    analyze_source_impact,
    cross_validate_impact,
    cross_validate_impact_with_llm,
)
from nlreq.llm_client import RecordedLlmClient, parse_impact_estimate
from nlreq.python_source_adapter import PythonSourceLanguageAdapter
from nlreq.source_adapter import SourceManifest
from nlreq.source_impact import analyze_production_source_impact, llm_semantic_suggestions


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
    """The LLM estimate, routed through the production report, surfaces an out-of-call-graph module
    as a non-gateable review finding — wiring the PC-9 producer into the existing disagreement infra."""
    manifest = _project(tmp_path)
    adapter = PythonSourceLanguageAdapter(project_root=tmp_path)
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
    assert "billing" not in report.deterministic_modules
    assert any(d.module_id == "billing" and d.semantic_suggestion for d in report.disagreements)
    assert any(
        finding.category == "semantic_suggestion" and finding.module_id == "billing"
        for finding in report.findings
    )


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
