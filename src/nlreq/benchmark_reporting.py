from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from .benchmark_corpus import BenchmarkCaseResult, BenchmarkCorpus, build_benchmark_run_report
from .jsonutil import sha256_json


BENCHMARK_REPORT_SCHEMA_VERSION = "0.1"
BENCHMARK_REPORT_TOOL_VERSION = "0.1"


class BenchmarkMetric(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    value: float
    budget: float | None = None
    passed: bool = True


class BenchmarkEvaluationReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["0.1"] = BENCHMARK_REPORT_SCHEMA_VERSION
    corpus_id: str
    version: str
    result: Literal["passed", "failed"]
    total_cases: int
    metrics: list[BenchmarkMetric] = Field(default_factory=list)
    category_counts: dict[str, int] = Field(default_factory=dict)
    base_report_hash: str
    input_hashes: dict[str, str] = Field(default_factory=dict)
    tool: str = "nlreq.benchmark_reporting"
    tool_version: str = BENCHMARK_REPORT_TOOL_VERSION


def build_benchmark_evaluation_report(
    corpus: BenchmarkCorpus,
    results: list[BenchmarkCaseResult],
    *,
    false_closure_budget: float = 0.0,
) -> BenchmarkEvaluationReport:
    base = build_benchmark_run_report(corpus, results)
    category_counts: dict[str, int] = {}
    for case in corpus.cases:
        for tag in case.tags:
            category_counts[tag] = category_counts.get(tag, 0) + 1
    metrics = [
        BenchmarkMetric(
            name="closure_rate",
            value=base.closure_rate,
        ),
        BenchmarkMetric(
            name="false_closure_rate",
            value=base.false_closure_rate,
            budget=false_closure_budget,
            passed=base.false_closure_rate <= false_closure_budget,
        ),
        BenchmarkMetric(
            name="false_refusal_rate",
            value=base.false_refusal_rate,
        ),
        BenchmarkMetric(
            name="runtime_ms_total",
            value=float(base.runtime_ms_total),
        ),
    ]
    failed = base.result == "failed" or any(not metric.passed for metric in metrics)
    return BenchmarkEvaluationReport(
        corpus_id=corpus.corpus_id,
        version=corpus.version,
        result="failed" if failed else "passed",
        total_cases=base.total_cases,
        metrics=metrics,
        category_counts=category_counts,
        base_report_hash=sha256_json(base),
        input_hashes={
            "corpus": sha256_json(corpus),
            "results": sha256_json(results),
        },
    )
