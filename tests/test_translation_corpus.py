"""PA-9 labeled translation corpus + per-domain metrics + CI gate.

The committed corpus is the release bar: running it offline through the recorded
front-half must yield zero false-acceptance and zero false-refusal per domain. The
non-vacuity tests prove the instrument actually discriminates — a planted wrong-but-
parseable output is flagged as false-acceptance, a garbled output as false-refusal —
so the zeros on the release corpus are a real signal, not a constant.
"""

from __future__ import annotations

from pathlib import Path

from nlreq.cli import main
from nlreq.translation_benchmark import (
    RequirementTranslationCase,
    RequirementTranslationCorpus,
    RequirementTranslationExpected,
    RequirementTranslationReleaseThresholds,
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
