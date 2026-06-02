from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from .benchmark_corpus import BenchmarkCaseResult, BenchmarkCorpus, build_benchmark_run_report
from .jsonutil import sha256_json


BENCHMARK_REPORT_SCHEMA_VERSION = "0.1"
BENCHMARK_REPORT_TOOL_VERSION = "0.1"
EXTENDED_BENCHMARK_SCHEMA_VERSION = "0.1"

EXTENDED_BENCHMARK_REQUIRED_DIMENSIONS: tuple[str, ...] = (
    "semantic_translation",
    "formal_system",
    "trace_grounding",
    "adapter_evidence",
    "release_gate",
    "false_closure",
    "false_refusal",
    "runtime",
    "counterexample_quality",
)


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


class ExtendedBenchmarkDimensionResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    dimension: str
    total_cases: int = 0
    passed_cases: int = 0
    failed_cases: int = 0
    score: float = 0.0
    threshold: float = 1.0
    passed: bool = True
    findings: list[str] = Field(default_factory=list)


class ExtendedBenchmarkEvaluationReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["0.1"] = EXTENDED_BENCHMARK_SCHEMA_VERSION
    corpus_id: str
    version: str
    result: Literal["passed", "failed"]
    base_report_hash: str
    required_dimensions: list[str] = Field(default_factory=list)
    dimensions: list[ExtendedBenchmarkDimensionResult] = Field(default_factory=list)
    missing_dimensions: list[str] = Field(default_factory=list)
    failed_dimensions: list[str] = Field(default_factory=list)
    release_thresholds: dict[str, float] = Field(default_factory=dict)
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


def build_extended_benchmark_evaluation_report(
    base: BenchmarkEvaluationReport,
    dimensions: list[ExtendedBenchmarkDimensionResult],
    *,
    required_dimensions: tuple[str, ...] | list[str] = EXTENDED_BENCHMARK_REQUIRED_DIMENSIONS,
    release_thresholds: dict[str, float] | None = None,
) -> ExtendedBenchmarkEvaluationReport:
    release_thresholds = release_thresholds or {}
    by_dimension = {dimension.dimension: dimension for dimension in dimensions}
    missing_dimensions = sorted(set(required_dimensions) - set(by_dimension))
    normalized_dimensions = [
        _apply_dimension_threshold(dimension, release_thresholds.get(dimension.dimension))
        for dimension in dimensions
    ]
    failed_dimensions = sorted(
        dimension.dimension for dimension in normalized_dimensions if not dimension.passed
    )
    failed = bool(
        base.result != "passed"
        or missing_dimensions
        or failed_dimensions
    )
    return ExtendedBenchmarkEvaluationReport(
        corpus_id=base.corpus_id,
        version=base.version,
        result="failed" if failed else "passed",
        base_report_hash=sha256_json(base),
        required_dimensions=list(required_dimensions),
        dimensions=normalized_dimensions,
        missing_dimensions=missing_dimensions,
        failed_dimensions=failed_dimensions,
        release_thresholds=release_thresholds,
        input_hashes={
            "base_report": sha256_json(base),
            "dimensions": sha256_json(dimensions),
            "required_dimensions": sha256_json(list(required_dimensions)),
            "release_thresholds": sha256_json(release_thresholds),
        },
    )


def _apply_dimension_threshold(
    dimension: ExtendedBenchmarkDimensionResult,
    threshold: float | None,
) -> ExtendedBenchmarkDimensionResult:
    if threshold is None:
        return dimension
    passed = dimension.score >= threshold and dimension.passed
    findings = list(dimension.findings)
    if not passed and dimension.score < threshold:
        findings.append(
            f"{dimension.dimension} score {dimension.score} is below release threshold {threshold}"
        )
    return dimension.model_copy(
        update={
            "threshold": threshold,
            "passed": passed,
            "findings": findings,
        }
    )
