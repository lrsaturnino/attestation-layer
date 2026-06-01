from __future__ import annotations

from pathlib import PurePosixPath
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, RootModel, model_validator


BENCHMARK_CORPUS_SCHEMA_VERSION = "0.1"


BenchmarkDecision = Literal["accepted", "refused", "unknown"]


class BenchmarkExpectedOutcome(BaseModel):
    model_config = ConfigDict(extra="forbid")

    decision: BenchmarkDecision
    failure_mode: str | None = None
    counterexample_expected: bool = False


class BenchmarkCase(BaseModel):
    model_config = ConfigDict(extra="forbid")

    case_id: str
    title: str
    description: str
    artifacts: dict[str, list[str]] = Field(default_factory=dict)
    tags: list[str] = Field(default_factory=list)
    expected: BenchmarkExpectedOutcome

    @model_validator(mode="after")
    def validate_artifact_paths(self) -> BenchmarkCase:
        for paths in self.artifacts.values():
            for path in paths:
                _validate_relative_path(path)
        return self


class BenchmarkCorpus(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["0.1"] = BENCHMARK_CORPUS_SCHEMA_VERSION
    corpus_id: str
    version: str
    cases: list[BenchmarkCase] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_unique_cases(self) -> BenchmarkCorpus:
        case_ids = [case.case_id for case in self.cases]
        if len(case_ids) != len(set(case_ids)):
            raise ValueError("benchmark case ids must be unique")
        return self


class BenchmarkCaseResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    case_id: str
    decision: BenchmarkDecision
    runtime_ms: int = Field(default=0, ge=0)
    counterexample_count: int = Field(default=0, ge=0)
    notes: list[str] = Field(default_factory=list)


class BenchmarkResultsArtifact(RootModel[list[BenchmarkCaseResult]]):
    pass


class BenchmarkObservation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    case_id: str
    expected_decision: BenchmarkDecision
    observed_decision: BenchmarkDecision | None = None
    status: Literal[
        "matched",
        "missing",
        "false_closure",
        "false_refusal",
        "unknown_mismatch",
    ]
    runtime_ms: int = 0
    counterexample_count: int = 0
    notes: list[str] = Field(default_factory=list)


class BenchmarkRunReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["0.1"] = BENCHMARK_CORPUS_SCHEMA_VERSION
    corpus_id: str
    version: str
    result: Literal["passed", "failed"]
    total_cases: int
    matched_cases: int
    closure_rate: float
    false_closure_rate: float
    false_refusal_rate: float
    counterexample_quality: float | None = None
    runtime_ms_total: int
    observations: list[BenchmarkObservation] = Field(default_factory=list)


def build_benchmark_run_report(
    corpus: BenchmarkCorpus,
    results: list[BenchmarkCaseResult],
) -> BenchmarkRunReport:
    results_by_id = {result.case_id: result for result in results}
    observations = [
        _observation(case, results_by_id.get(case.case_id)) for case in corpus.cases
    ]
    total = len(corpus.cases)
    matched = sum(1 for item in observations if item.status == "matched")
    false_closures = sum(1 for item in observations if item.status == "false_closure")
    false_refusals = sum(1 for item in observations if item.status == "false_refusal")
    closures = sum(1 for item in observations if item.observed_decision == "accepted")
    runtime_total = sum(item.runtime_ms for item in observations)
    counterexample_quality = _counterexample_quality(corpus, results_by_id)
    failed = (
        matched != total
        or false_closures > 0
        or any(item.status == "missing" for item in observations)
    )
    return BenchmarkRunReport(
        corpus_id=corpus.corpus_id,
        version=corpus.version,
        result="failed" if failed else "passed",
        total_cases=total,
        matched_cases=matched,
        closure_rate=_ratio(closures, total),
        false_closure_rate=_ratio(false_closures, total),
        false_refusal_rate=_ratio(false_refusals, total),
        counterexample_quality=counterexample_quality,
        runtime_ms_total=runtime_total,
        observations=observations,
    )


def _observation(
    case: BenchmarkCase,
    result: BenchmarkCaseResult | None,
) -> BenchmarkObservation:
    if result is None:
        return BenchmarkObservation(
            case_id=case.case_id,
            expected_decision=case.expected.decision,
            status="missing",
            notes=["no observed benchmark result supplied"],
        )
    status = _status_for_decision(case.expected.decision, result.decision)
    return BenchmarkObservation(
        case_id=case.case_id,
        expected_decision=case.expected.decision,
        observed_decision=result.decision,
        status=status,
        runtime_ms=result.runtime_ms,
        counterexample_count=result.counterexample_count,
        notes=result.notes,
    )


def _status_for_decision(
    expected: BenchmarkDecision, observed: BenchmarkDecision
) -> str:
    if expected == observed:
        return "matched"
    if observed == "accepted" and expected != "accepted":
        return "false_closure"
    if observed == "refused" and expected == "accepted":
        return "false_refusal"
    return "unknown_mismatch"


def _counterexample_quality(
    corpus: BenchmarkCorpus,
    results_by_id: dict[str, BenchmarkCaseResult],
) -> float | None:
    expected_cases = [
        case for case in corpus.cases if case.expected.counterexample_expected
    ]
    if not expected_cases:
        return None
    produced = sum(
        1
        for case in expected_cases
        if (result := results_by_id.get(case.case_id)) is not None
        and result.counterexample_count > 0
    )
    return _ratio(produced, len(expected_cases))


def _ratio(numerator: int, denominator: int) -> float:
    if denominator == 0:
        return 0.0
    return numerator / denominator


def _validate_relative_path(path: str) -> None:
    parsed = PurePosixPath(path)
    if parsed.is_absolute() or ".." in parsed.parts:
        raise ValueError("benchmark artifact paths must be corpus-root-relative")
