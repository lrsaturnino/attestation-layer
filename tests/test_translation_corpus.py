"""PA-9 labeled translation corpus + per-domain metrics + CI gate.

The committed corpus is the release bar: running it offline through the recorded
front-half must yield zero false-acceptance and zero false-refusal per domain. The
non-vacuity tests prove the instrument actually discriminates — a planted wrong-but-
parseable output is flagged as false-acceptance, a garbled output as false-refusal —
so the zeros on the release corpus are a real signal, not a constant.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from nlreq.cli import main
from nlreq.llm_client import _DRAFTING_PROMPT_VERSION
from nlreq.translation_benchmark import (
    RequirementTranslationCase,
    RequirementTranslationCaseResult,
    RequirementTranslationCorpus,
    RequirementTranslationExpected,
    RequirementTranslationReleaseThresholds,
    RequirementTranslationResults,
    build_translation_benchmark_report,
    evaluate_translation_benchmark_release_bar,
    run_translation_corpus,
)


CORPUS_PATH = (
    Path(__file__).resolve().parents[1] / "benchmarks" / "translation-corpus" / "corpus.json"
)

# A verified-good authorization claim and a wrong-but-parseable twin (inverted premise
# polarity) used to prove the harness flags a divergent-yet-accepted claim.
_AUTH_GOLD = (
    "requirement authorization_precondition:\n"
    "scope withdrawal\n"
    "when account is not authorized\n"
    "then withdraw must reject before settled\n"
)
_AUTH_INVERTED = (
    "requirement authorization_precondition:\n"
    "scope withdrawal\n"
    "when account is authorized\n"
    "then withdraw must reject before settled\n"
)


def _load_corpus() -> RequirementTranslationCorpus:
    return RequirementTranslationCorpus.model_validate_json(CORPUS_PATH.read_text())


def test_release_corpus_has_two_unrelated_domains_each_over_thirty() -> None:
    corpus = _load_corpus()
    by_domain: dict[str, int] = {}
    for case in corpus.cases:
        assert case.domain is not None, f"{case.case_id} has no domain"
        by_domain[case.domain] = by_domain.get(case.domain, 0) + 1
    assert set(by_domain) == {"procurement-approval", "protocol-safety"}
    for domain, count in by_domain.items():
        assert count >= 30, f"domain {domain} has only {count} cases (need >= 30)"


def test_release_corpus_passes_with_zero_false_rates_per_domain() -> None:
    corpus = _load_corpus()
    report = build_translation_benchmark_report(corpus, run_translation_corpus(corpus))

    assert report.result == "passed"
    assert report.false_acceptance_count == 0
    assert report.false_refusal_count == 0
    # Both rates reported per domain, never collapsed into one accuracy number.
    assert {d.domain for d in report.domains} == {"procurement-approval", "protocol-safety"}
    for domain in report.domains:
        # The gate itself enforces the >=30-per-domain floor, so a future corpus truncation
        # cannot silently shrink the bar while still reading as "passed".
        assert domain.total_cases >= 30
        assert domain.false_acceptance_count == 0
        assert domain.false_refusal_count == 0
        assert domain.false_acceptance_rate == 0.0
        assert domain.false_refusal_rate == 0.0


def test_release_corpus_clears_the_per_domain_false_acceptance_gate() -> None:
    corpus = _load_corpus()
    report = build_translation_benchmark_report(corpus, run_translation_corpus(corpus))
    bar = evaluate_translation_benchmark_release_bar(
        report,
        thresholds=RequirementTranslationReleaseThresholds(
            false_acceptance_budget=0,
            per_domain_false_acceptance_budget=0,
            min_semantic_match_rate=0.0,
            required_expected_outcomes=["accepted", "refused"],
        ),
    )
    assert bar.result == "passed"
    assert bar.blockers == []


def _case(case_id: str, recorded: str, *, gold: str | None, outcome: str, domain: str = "d"):
    return RequirementTranslationCase(
        case_id=case_id,
        title="t",
        input_text="Reject an unauthorized withdrawal.",
        input_kind="messy_prose",
        domain=domain,
        gold_controlled_text=gold,
        recorded_controlled_text=recorded,
        expected=RequirementTranslationExpected(outcome=outcome),  # type: ignore[arg-type]
    )


def test_instrument_flags_wrong_but_parseable_output_as_false_acceptance() -> None:
    # A recorded output that parses and lowers but encodes a DIFFERENT claim than gold is a
    # false-acceptance: the gate let a wrong claim through. This is what makes the budget bite.
    corpus = RequirementTranslationCorpus(
        corpus_id="nonvacuity",
        version="0.1",
        cases=[_case("wrong", _AUTH_INVERTED, gold=_AUTH_GOLD, outcome="accepted")],
    )
    results = run_translation_corpus(corpus)
    result = results.results[0]
    assert result.outcome == "accepted"
    assert result.semantic_match is False
    assert result.false_acceptance is True
    assert result.false_refusal is False


def test_instrument_flags_garbled_output_as_false_refusal() -> None:
    # A recorded output that cannot be lowered for a gold-accept prose is a false-refusal:
    # a correct claim was refused because the front-half produced an unusable rewrite.
    corpus = RequirementTranslationCorpus(
        corpus_id="nonvacuity",
        version="0.1",
        cases=[_case("garbled", "not valid controlled text", gold=_AUTH_GOLD, outcome="accepted")],
    )
    result = run_translation_corpus(corpus).results[0]
    assert result.outcome == "refused"
    assert result.false_refusal is True
    assert result.false_acceptance is False


def test_faithful_output_is_neither_false_acceptance_nor_false_refusal() -> None:
    corpus = RequirementTranslationCorpus(
        corpus_id="nonvacuity",
        version="0.1",
        cases=[_case("clean", _AUTH_GOLD, gold=_AUTH_GOLD, outcome="accepted")],
    )
    result = run_translation_corpus(corpus).results[0]
    assert result.semantic_match is True
    assert result.false_acceptance is False
    assert result.false_refusal is False


def test_run_translation_corpus_routes_through_supplied_client_for_calibration() -> None:
    """Per-role calibration routing (scope §5 / ADR 0204 §4): when a drafter client is supplied,
    the corpus is drafted by THAT client — not the case's recorded output — so the FA/FR
    measurement is of the client under calibration.

    Here the case's recorded output is the GOLD (replay would match), but the supplied client
    returns the inverted twin, so the result is a false-acceptance driven by the client —
    proving the routing overrides the recorded output. This is the CI-safe form of the live
    calibration pathway (a recorded client stands in for a live one); the live FA/FR run is
    operator-side.
    """
    from nlreq.llm_client import RecordedLlmClient

    corpus = RequirementTranslationCorpus(
        corpus_id="routing",
        version="0.1",
        cases=[_case("routing", _AUTH_GOLD, gold=_AUTH_GOLD, outcome="accepted")],
    )
    # Replay (no client) → the case's recorded GOLD → a semantic match, no false-acceptance.
    replay = run_translation_corpus(corpus)
    assert replay.results[0].semantic_match is True
    assert replay.results[0].false_acceptance is False
    # Supplied client → the INVERTED twin → a false-acceptance driven by the client, NOT the
    # case's recorded output. Proves the per-role client is the drafter under calibration.
    routed = run_translation_corpus(corpus, client=RecordedLlmClient(_AUTH_INVERTED))
    assert routed.results[0].outcome == "accepted"
    assert routed.results[0].semantic_match is False
    assert routed.results[0].false_acceptance is True


def test_benchmark_translation_llm_client_bad_scheme_exits_2(tmp_path: Path, capsys) -> None:
    """``benchmark-translation --run --llm-client`` routes the corpus through the per-role factory
    (``_resolve_client_scheme``). A bad scheme refuses at exit 2 before any case runs — proving
    the calibration client selection is wired and fails closed (scope §5)."""
    corpus_path = tmp_path / "corpus.json"
    corpus_path.write_text(_load_corpus().model_dump_json())
    exit_code = main([
        "benchmark-translation",
        "--corpus", str(corpus_path),
        "--run",
        "--llm-client", "bogus-scheme-xyz",
    ])
    assert exit_code == 2
    assert "unknown client spec" in capsys.readouterr().err


def _tiny_corpus() -> RequirementTranslationCorpus:
    """A one-case accept-gold corpus for fast, deterministic calibration-provenance tests."""
    return RequirementTranslationCorpus(
        corpus_id="calib-tiny",
        version="0.1",
        cases=[RequirementTranslationCase(
            case_id="c1",
            title="t",
            input_text="Reject an unauthorized withdrawal.",
            input_kind="messy_prose",
            domain="d",
            language="en",
            gold_controlled_text=_AUTH_GOLD,
            recorded_controlled_text=_AUTH_GOLD,
            expected=RequirementTranslationExpected(outcome="accepted"),  # type: ignore[arg-type]
        )],
    )


def test_benchmark_translation_calibration_report_is_self_describing(tmp_path: Path) -> None:
    """``--llm-client`` produces a self-describing ``calibration`` block (role / client_kind /
    prompt_version / transport_source) so the FA/FR tables stand alone without external
    filenames or prose (recommended action #2). Uses a recorded client (CI-safe, no wrapper /
    no API key); the recorded transport records no live model / provider / wrapper."""
    corpus_path = tmp_path / "corpus.json"
    corpus_path.write_text(_tiny_corpus().model_dump_json())
    fixture = tmp_path / "fixture.txt"
    fixture.write_text(_AUTH_GOLD)
    out = tmp_path / "report.json"
    exit_code = main([
        "benchmark-translation",
        "--corpus", str(corpus_path),
        "--run",
        "--llm-client", f"recorded:{fixture}",
        "--out", str(out),
    ])
    assert exit_code in (0, 1)  # FA/FR may be nonzero; the provenance stamping is what is tested
    report = json.loads(out.read_text())
    cal = report["calibration"]
    assert cal is not None
    assert cal["role"] == "drafting"  # default role
    assert cal["client_kind"] == "recorded"
    assert cal["prompt_version"] == _DRAFTING_PROMPT_VERSION
    assert cal["transport_source"] == "override"
    # Recorded transport has no live model / provider / wrapper identity.
    assert cal.get("resolved_model") is None
    assert cal.get("provider") is None
    assert cal.get("wrapper") is None


@pytest.mark.parametrize("role", ["impact", "extraction", "decomposition", "audit"])
def test_benchmark_translation_non_drafting_roles_refused(
    tmp_path: Path, capsys, role: str
) -> None:
    """Regression: only ``drafting`` is calibratable by the translation corpus.

    The corpus measures the drafting front-half (prose -> controlled -> FormalClaim -> FA/FR).
    ``--role impact``/``extraction`` previously STAMPED a non-drafting role + prompt_version onto
    a report that actually measured drafting (false provenance), masked only because every role's
    prompt version was "0.1" (``_DRAFTING_PROMPT_VERSION``/``_IMPACT_PROMPT_VERSION``/
    ``_EXTRACTION_PROMPT_VERSION`` are all "0.1"). They are now refused (exit 2), alongside
    decomposition/audit which were always refused. No calibration artifact claiming a non-drafting
    role can be produced.
    """
    corpus_path = tmp_path / "corpus.json"
    corpus_path.write_text(_tiny_corpus().model_dump_json())
    fixture = tmp_path / "fixture.txt"
    fixture.write_text(_AUTH_GOLD)
    exit_code = main([
        "benchmark-translation",
        "--corpus", str(corpus_path),
        "--run",
        "--llm-client", f"recorded:{fixture}",
        "--role", role,
    ])
    assert exit_code == 2
    assert "not calibratable" in capsys.readouterr().err


def test_benchmark_translation_no_llm_client_has_no_calibration_block(tmp_path: Path) -> None:
    """A plain ``--run`` (recorded replay, no ``--llm-client``) has NO ``calibration`` block —
    byte-stability: non-calibration reports are unchanged (the field is None / excluded)."""
    corpus_path = tmp_path / "corpus.json"
    corpus_path.write_text(_tiny_corpus().model_dump_json())
    out = tmp_path / "report.json"
    exit_code = main([
        "benchmark-translation",
        "--corpus", str(corpus_path),
        "--run",
        "--out", str(out),
    ])
    assert exit_code in (0, 1)
    report = json.loads(out.read_text())
    assert "calibration" not in report or report.get("calibration") is None


# ---------------------------------------------------------------------------
# iter-7: benchmark-translation --results case-set validation (MEDIUM fix)
# ---------------------------------------------------------------------------
# A truncated / duplicated / extra-case ``--results`` file is a structured refusal (exit 2,
# ``nlreq:``), never zeroed FA/FR rates from a partial file — mirrors ``benchmark-role``.
# Previously ``build_translation_benchmark_report`` collapsed results into a dict (duplicates
# overwrote earlier observations), silently omitted missing case ids, and ignored extra ids,
# which could understate FA/FR from malformed evidence files (scope §4 "structured refusal,
# never faked").


def test_cli_benchmark_translation_truncated_results_exits_2(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """A truncated ``--results`` file (missing cases) refuses at exit 2, never zeroed rates."""
    corpus = _tiny_corpus()
    corpus_path = tmp_path / "corpus.json"
    corpus_path.write_text(corpus.model_dump_json())
    # Empty results: zero of one case → missing c1.
    truncated = RequirementTranslationResults(results=[])
    res_path = tmp_path / "truncated.json"
    res_path.write_text(truncated.model_dump_json())
    out = tmp_path / "report.json"
    exit_code = main([
        "benchmark-translation", "--corpus", str(corpus_path),
        "--results", str(res_path), "--out", str(out),
    ])
    assert exit_code == 2
    err = capsys.readouterr().err
    assert "nlreq:" in err
    assert "missing case ids" in err
    assert not out.exists()


def test_cli_benchmark_translation_duplicate_results_exits_2(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """A ``--results`` file with a duplicate case id refuses at exit 2."""
    corpus = _tiny_corpus()
    corpus_path = tmp_path / "corpus.json"
    corpus_path.write_text(corpus.model_dump_json())
    full = run_translation_corpus(corpus)
    duplicated = RequirementTranslationResults(results=[*full.results, full.results[0]])  # c1 twice
    res_path = tmp_path / "duplicated.json"
    res_path.write_text(duplicated.model_dump_json())
    out = tmp_path / "report.json"
    exit_code = main([
        "benchmark-translation", "--corpus", str(corpus_path),
        "--results", str(res_path), "--out", str(out),
    ])
    assert exit_code == 2
    err = capsys.readouterr().err
    assert "nlreq:" in err
    assert "duplicate case ids" in err
    assert not out.exists()


def test_cli_benchmark_translation_extra_results_exits_2(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """A ``--results`` file with a case id not in the corpus refuses at exit 2."""
    corpus = _tiny_corpus()
    corpus_path = tmp_path / "corpus.json"
    corpus_path.write_text(corpus.model_dump_json())
    full = run_translation_corpus(corpus)
    with_extra = RequirementTranslationResults(
        results=[
            *full.results,
            RequirementTranslationCaseResult(case_id="nonexistent", outcome="accepted"),
        ]
    )
    res_path = tmp_path / "extra.json"
    res_path.write_text(with_extra.model_dump_json())
    out = tmp_path / "report.json"
    exit_code = main([
        "benchmark-translation", "--corpus", str(corpus_path),
        "--results", str(res_path), "--out", str(out),
    ])
    assert exit_code == 2
    err = capsys.readouterr().err
    assert "nlreq:" in err
    assert "extra case ids" in err
    assert not out.exists()


def test_release_bar_gate_fails_when_a_domain_exceeds_the_budget() -> None:
    # The CI gate must bite: a planted false-acceptance in one domain, with a per-domain
    # budget of zero, fails the release bar and names the offending domain.
    corpus = RequirementTranslationCorpus(
        corpus_id="gate",
        version="0.1",
        cases=[
            _case("clean", _AUTH_GOLD, gold=_AUTH_GOLD, outcome="accepted", domain="d1"),
            _case("planted", _AUTH_INVERTED, gold=_AUTH_GOLD, outcome="accepted", domain="d1"),
        ],
    )
    report = build_translation_benchmark_report(corpus, run_translation_corpus(corpus))
    assert report.domains[0].false_acceptance_count == 1
    bar = evaluate_translation_benchmark_release_bar(
        report,
        thresholds=RequirementTranslationReleaseThresholds(
            false_acceptance_budget=0,
            per_domain_false_acceptance_budget=0,
            min_semantic_match_rate=0.0,
            required_expected_outcomes=["accepted"],
        ),
    )
    assert bar.result == "failed"
    assert any("d1" in blocker for blocker in bar.blockers)


def test_cli_benchmark_translation_run_release_bar_is_green(tmp_path) -> None:
    out = tmp_path / "release-bar.json"
    exit_code = main(
        [
            "benchmark-translation",
            "--corpus",
            str(CORPUS_PATH),
            "--run",
            "--release-bar",
            "--per-domain-false-acceptance-budget",
            "0",
            "--out",
            str(out),
        ]
    )
    assert exit_code == 0
    assert out.is_file()


def test_corpus_round_trips_through_the_generator() -> None:
    # The committed corpus.json must equal what build_corpus.py emits, so the corpus is
    # reproducible from source and cannot silently drift from the generator.
    import json
    import sys

    sys.path.insert(0, str(CORPUS_PATH.parent))
    try:
        import build_corpus  # type: ignore[import-not-found]
    finally:
        sys.path.pop(0)
    expected = json.loads(
        json.dumps(build_corpus.build_corpus().model_dump(mode="json"), sort_keys=True)
    )
    actual = json.loads(CORPUS_PATH.read_text())
    assert actual == expected, "corpus.json is stale; rerun build_corpus.py"


# The committed calibration reports are the real-evidence artifacts for acceptance #5
# (scope §5 / ADR 0204 §4). Two transports are calibrated live against real model outputs:
#   - the Anthropic SDK transport (live:<model>) on the 66-case English corpus (corpus.json)
#     AND the 63-case multilingual corpus (multilingual.corpus.json, 30 en + 33 pt — both
#     meeting the scope §5 per-language >=30 floor), two candidate models each (haiku, sonnet);
#   - the cross-provider CLI transport (cli:<wrapper>:tiny, ADR 0203 / ADR 0204 §5) on the
#     66-case English corpus via TWO DISTINCT operator wrappers (run-claude → anthropic,
#     run-gpt → openai) — the cross-provider dimension acceptance #5 requires, now executable
#     once the operator landed §6 for run-claude + run-gpt (ADR 0204 §5).
# Each spec carries the structural expectations (languages / client_kind / provider / wrapper)
# AND the exact per-language + per-domain FA/FR counts. The counts are regression-asserted
# against the committed JSON (recommended action #4 — the FA/FR drift fix): a silent edit to a
# committed report, or a stale ADR/TOML prose table, cannot pass green, because the committed
# JSON is the single source of truth and the ADR 0204 / nlreq-models.toml tables mirror these
# exact numbers. Update this map (and ADR 0204 §4 / nlreq-models.toml) together ONLY when a
# report is regenerated.
_CALIBRATION_DIR = CORPUS_PATH.parent / "calibration"
_CALIBRATION_REPORTS = {
    # ── Anthropic SDK transport (live:<model>) — English corpus (en only) ──
    "20260625-drafting-claude-haiku-4-5-20251001.json": {
        "languages": ("en",), "client_kind": "anthropic", "provider": "anthropic",
        "lang_counts": {"en": (54, 8)},
        "domain_counts": {"procurement-approval": (27, 4), "protocol-safety": (27, 4)},
    },
    "20260625-drafting-claude-sonnet-4-5-20250929.json": {
        "languages": ("en",), "client_kind": "anthropic", "provider": "anthropic",
        "lang_counts": {"en": (0, 60)},
        "domain_counts": {"procurement-approval": (0, 30), "protocol-safety": (0, 30)},
    },
    # ── Anthropic SDK transport (live:<model>) — multilingual corpus (en + pt, floor-satisfying) ──
    "20260625-drafting-multilingual-claude-haiku-4-5-20251001.json": {
        "languages": ("en", "pt"), "client_kind": "anthropic", "provider": "anthropic",
        "lang_counts": {"en": (26, 4), "pt": (28, 2)},
        "domain_counts": {"multilingual-spike": (54, 6)},
    },
    "20260625-drafting-multilingual-claude-sonnet-4-5-20250929.json": {
        "languages": ("en", "pt"), "client_kind": "anthropic", "provider": "anthropic",
        "lang_counts": {"en": (0, 30), "pt": (0, 30)},
        "domain_counts": {"multilingual-spike": (0, 60)},
    },
    # ── Cross-provider CLI transport (cli:<wrapper>:tiny) — English corpus, two providers ──
    "20260625-drafting-cli-run-claude-claude-haiku-4-5.json": {
        "languages": ("en",), "client_kind": "cli", "provider": "anthropic",
        "wrapper": "run-claude",
        "lang_counts": {"en": (12, 48)},
        "domain_counts": {"procurement-approval": (3, 27), "protocol-safety": (9, 21)},
    },
    "20260625-drafting-cli-run-gpt-gpt-5.4-mini.json": {
        "languages": ("en",), "client_kind": "cli", "provider": "openai",
        "wrapper": "run-gpt",
        "lang_counts": {"en": (54, 9)},
        "domain_counts": {"procurement-approval": (26, 6), "protocol-safety": (28, 3)},
    },
}


def test_committed_calibration_reports_are_valid_self_describing_evidence() -> None:
    """The committed calibration reports are schema-valid, self-describing, and carry the exact
    committed FA/FR counts (ADR 0204 §4; recommended action #4 — the FA/FR drift fix).

    Each report round-trips through ``RequirementTranslationBenchmarkReport`` (schema validity)
    and carries a self-describing ``calibration`` block whose client_kind / provider / wrapper
    identity match the per-report spec. The Anthropic SDK reports assert client_kind=anthropic /
    provider=anthropic; the cross-provider CLI reports assert client_kind=cli plus the sidecar's
    provider / wrapper / route / wrapper_hash / cli_version (ADR 0203). The resolved_model is
    reflected in the filename (provenance ↔ artifact-name coherence). Per-language coverage is
    the durable contract: the English-corpus reports carry only ``en``; the multilingual-spike
    reports carry BOTH ``en`` and ``pt`` (the Portuguese slice that was previously a below-floor
    spike — now expanded to 33 pt cases, meeting the scope §5 per-language >=30 floor).

    The exact per-language + per-domain FA/FR counts ARE asserted against the committed JSON:
    a committed report is a fixed artifact (a single-run snapshot, but stable on disk until
    regenerated), so asserting its counts regression-guards the source of truth. A stale
    ADR 0204 / nlreq-models.toml prose table cannot pass green — the JSON counts bind the prose,
    and both are updated together on regeneration. The committed finding
    (``result == "failed"``: under drafting-prompt v0.1 no live model is a viable production
    drafter on either transport) is asserted as the calibrated operating-point decision.
    """
    from nlreq.translation_benchmark import RequirementTranslationBenchmarkReport

    assert sorted(p.name for p in _CALIBRATION_DIR.glob("*.json")) == sorted(_CALIBRATION_REPORTS), (
        "calibration report set drifted from the committed evidence; "
        "update this test and ADR 0204 §4 / nlreq-models.toml"
    )
    for name, spec in _CALIBRATION_REPORTS.items():
        report = RequirementTranslationBenchmarkReport.model_validate_json(
            (_CALIBRATION_DIR / name).read_text()
        )
        cal = report.calibration
        assert cal is not None, f"{name} has no calibration block"
        assert cal.role == "drafting", f"{name}: role={cal.role!r}"
        assert cal.client_kind == spec["client_kind"], f"{name}: client_kind={cal.client_kind!r}"
        assert cal.provider == spec["provider"], f"{name}: provider={cal.provider!r}"
        assert cal.prompt_version == _DRAFTING_PROMPT_VERSION, f"{name}: prompt_version={cal.prompt_version!r}"
        assert cal.transport_source == "override", f"{name}: transport_source={cal.transport_source!r}"
        assert cal.resolved_model is not None and cal.resolved_model in name, (
            f"{name}: resolved_model {cal.resolved_model!r} not reflected in filename"
        )
        # The CLI transport records the sidecar's wrapper identity + route (ADR 0203 / 0204 §5);
        # the Anthropic SDK transport has no wrapper (those fields are None / absent).
        if spec["client_kind"] == "cli":
            assert cal.wrapper == spec["wrapper"], f"{name}: wrapper={cal.wrapper!r}"
            assert cal.route == "official", f"{name}: route={cal.route!r}"
            assert cal.wrapper_hash, f"{name}: missing wrapper_hash"
            assert cal.cli_version, f"{name}: missing cli_version"
        languages = {lm.language for lm in report.languages}
        assert languages == set(spec["languages"]), (
            f"{name}: expected languages {spec['languages']}, got {sorted(languages)}"
        )
        # Exact per-language FA/FR counts — the committed JSON is the source of truth
        # (recommended action #4). A stale ADR/TOML prose table cannot pass green.
        for lm in report.languages:
            exp_fa, exp_fr = spec["lang_counts"][lm.language]
            assert lm.false_acceptance_count == exp_fa, (
                f"{name}/{lm.language}: FA={lm.false_acceptance_count} != {exp_fa}"
            )
            assert lm.false_refusal_count == exp_fr, (
                f"{name}/{lm.language}: FR={lm.false_refusal_count} != {exp_fr}"
            )
        # Exact per-domain FA/FR counts (regression-guard the committed domain totals).
        for dm in report.domains:
            exp_fa, exp_fr = spec["domain_counts"][dm.domain]
            assert dm.false_acceptance_count == exp_fa, (
                f"{name}/{dm.domain}: FA={dm.false_acceptance_count} != {exp_fa}"
            )
            assert dm.false_refusal_count == exp_fr, (
                f"{name}/{dm.domain}: FR={dm.false_refusal_count} != {exp_fr}"
            )
        # The committed finding: under drafting-prompt v0.1 no live model is viable on EITHER
        # transport (ADR 0204 §4). Guards the operating-point decision; update only on a prompt
        # revision that regenerates viable reports.
        assert report.result == "failed", f"{name}: expected 'failed' (non-viable live drafter)"


def test_cross_provider_cli_calibration_records_two_distinct_providers() -> None:
    """Acceptance #5 (cross-provider dimension): the two committed CLI-transport calibration
    reports record TWO DISTINCT providers (anthropic via run-claude + openai via run-gpt), two
    distinct resolved model ids, and two distinct wrapper hashes — the cross-provider diversity
    the scope's agreement gate exists to catch, now calibrated live through the §6-eligible
    operator wrappers (ADR 0204 §4/§5). Both are non-viable under drafting-prompt v0.1
    (``result == "failed"``), so no live CLI operating point is released; the diversity is
    recorded regardless, exactly as with the ensemble artifact (acceptance #2).
    """
    from nlreq.translation_benchmark import RequirementTranslationBenchmarkReport

    cli_reports = {
        name: RequirementTranslationBenchmarkReport.model_validate_json(
            (_CALIBRATION_DIR / name).read_text()
        )
        for name in (
            "20260625-drafting-cli-run-claude-claude-haiku-4-5.json",
            "20260625-drafting-cli-run-gpt-gpt-5.4-mini.json",
        )
    }
    providers = {r.calibration.provider for r in cli_reports.values()}
    models = {r.calibration.resolved_model for r in cli_reports.values()}
    wrappers = {r.calibration.wrapper for r in cli_reports.values()}
    hashes = {r.calibration.wrapper_hash for r in cli_reports.values()}
    assert providers == {"anthropic", "openai"}, providers  # two DISTINCT providers
    assert len(models) == 2, models  # two distinct resolved model ids
    assert wrappers == {"run-claude", "run-gpt"}, wrappers
    assert len(hashes) == 2, hashes  # two distinct wrapper hashes
    for r in cli_reports.values():
        assert r.calibration.client_kind == "cli"
        assert r.calibration.route == "official"  # no silent fallback
        assert r.result == "failed"  # non-viable under drafting-prompt v0.1 (not released)
