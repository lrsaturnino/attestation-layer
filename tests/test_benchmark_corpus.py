from pathlib import Path

from nlreq.benchmark_corpus import (
    BenchmarkCaseResult,
    BenchmarkCorpus,
    BenchmarkResultsArtifact,
    build_benchmark_run_report,
)
from nlreq.cli import main
from nlreq.jsonutil import read_json


CORPUS_ROOT = Path("benchmarks/verification-power")


def test_public_benchmark_corpus_paths_and_expected_cases_exist() -> None:
    corpus = BenchmarkCorpus.model_validate_json((CORPUS_ROOT / "corpus.json").read_text())

    assert {case.case_id for case in corpus.cases} == {
        "positive-closure",
        "counterexample",
        "parser-disagreement",
        "stale-spec",
        "trace-mismatch",
        "timeout",
        "backend-disagreement",
    }
    assert any(case.expected.counterexample_expected for case in corpus.cases)
    for case in corpus.cases:
        for paths in case.artifacts.values():
            for path in paths:
                assert (CORPUS_ROOT / path).is_file()


def test_benchmark_run_report_tracks_quality_metrics() -> None:
    corpus = BenchmarkCorpus.model_validate_json((CORPUS_ROOT / "corpus.json").read_text())
    results = BenchmarkResultsArtifact.model_validate_json(
        (CORPUS_ROOT / "observed-results.example.json").read_text()
    ).root

    report = build_benchmark_run_report(corpus, results)

    assert report.result == "passed"
    assert report.total_cases == 7
    assert report.matched_cases == 7
    assert report.closure_rate == 1 / 7
    assert report.false_closure_rate == 0
    assert report.counterexample_quality == 1.0
    assert report.runtime_ms_total == 1362


def test_benchmark_run_report_flags_false_closures() -> None:
    corpus = BenchmarkCorpus.model_validate_json((CORPUS_ROOT / "corpus.json").read_text())
    results = [
        BenchmarkCaseResult(case_id=case.case_id, decision=case.expected.decision)
        for case in corpus.cases
    ]
    results[1] = BenchmarkCaseResult(case_id="counterexample", decision="accepted")

    report = build_benchmark_run_report(corpus, results)

    assert report.result == "failed"
    assert report.false_closure_rate == 1 / 7
    assert report.observations[1].status == "false_closure"


def test_benchmark_corpus_cli_writes_report(tmp_path: Path, capsys) -> None:
    out = tmp_path / "benchmark-report.json"

    exit_code = main(
        [
            "benchmark-corpus",
            "--corpus",
            str(CORPUS_ROOT / "corpus.json"),
            "--results",
            str(CORPUS_ROOT / "observed-results.example.json"),
            "--out",
            str(out),
        ]
    )

    output = capsys.readouterr().out

    assert exit_code == 0
    assert "Benchmark corpus report:" in output
    assert read_json(out)["result"] == "passed"
