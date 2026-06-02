from __future__ import annotations

from pathlib import PurePosixPath
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


TRANSLATION_BENCHMARK_SCHEMA_VERSION = "0.1"


TranslationOutcome = Literal["accepted", "clarification", "refused", "needs_review"]


class RequirementTranslationExpected(BaseModel):
    model_config = ConfigDict(extra="forbid")

    outcome: TranslationOutcome
    expected_ir_path: str | None = None
    expected_clarification_questions: list[str] = Field(default_factory=list)
    expected_refusal_code: str | None = None


class RequirementTranslationCase(BaseModel):
    model_config = ConfigDict(extra="forbid")

    case_id: str
    title: str
    input_text: str
    input_kind: Literal["controlled", "messy_prose", "ambiguous_prose", "incomplete_prose", "multilingual", "adversarial"]
    tags: list[str] = Field(default_factory=list)
    expected: RequirementTranslationExpected

    @model_validator(mode="after")
    def validate_expected_path(self) -> RequirementTranslationCase:
        if self.expected.expected_ir_path is not None:
            parsed = PurePosixPath(self.expected.expected_ir_path)
            if parsed.is_absolute() or ".." in parsed.parts:
                raise ValueError("expected_ir_path must be corpus-root-relative")
        return self


class RequirementTranslationCorpus(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["0.1"] = TRANSLATION_BENCHMARK_SCHEMA_VERSION
    corpus_id: str
    version: str
    cases: list[RequirementTranslationCase]

    @model_validator(mode="after")
    def validate_unique_cases(self) -> RequirementTranslationCorpus:
        ids = [case.case_id for case in self.cases]
        if len(ids) != len(set(ids)):
            raise ValueError("translation corpus case ids must be unique")
        return self


class RequirementTranslationCaseResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    case_id: str
    outcome: TranslationOutcome
    syntactically_valid: bool = False
    semantic_match: bool = False
    ambiguous: bool = False
    false_acceptance: bool = False
    needs_review_reason: str | None = None
    formal_claim_hash: str | None = None
    semantic_profile: str | None = None
    clarification_questions: list[str] = Field(default_factory=list)
    refusal_code: str | None = None
    runtime_ms: int = Field(default=0, ge=0)


class RequirementTranslationResults(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["0.1"] = TRANSLATION_BENCHMARK_SCHEMA_VERSION
    results: list[RequirementTranslationCaseResult]


class RequirementTranslationObservation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    case_id: str
    expected_outcome: TranslationOutcome
    observed_outcome: TranslationOutcome | None = None
    status: Literal[
        "matched",
        "missing",
        "semantic_mismatch",
        "clarification_mismatch",
        "refusal_mismatch",
        "review_mismatch",
        "false_acceptance",
        "outcome_mismatch",
    ]
    notes: list[str] = Field(default_factory=list)


class RequirementTranslationBenchmarkReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["0.1"] = TRANSLATION_BENCHMARK_SCHEMA_VERSION
    corpus_id: str
    version: str
    result: Literal["passed", "failed"]
    total_cases: int
    matched_cases: int
    syntactic_validity_rate: float
    semantic_match_rate: float
    ambiguity_rate: float
    needs_review_rate: float
    false_acceptance_rate: float
    clarification_quality: float | None = None
    refusal_correctness: float | None = None
    runtime_ms_total: int
    observations: list[RequirementTranslationObservation] = Field(default_factory=list)


def build_translation_benchmark_report(
    corpus: RequirementTranslationCorpus,
    results: RequirementTranslationResults,
) -> RequirementTranslationBenchmarkReport:
    result_by_id = {result.case_id: result for result in results.results}
    observations = [_observe(case, result_by_id.get(case.case_id)) for case in corpus.cases]
    corpus_results = [
        result
        for case in corpus.cases
        if (result := result_by_id.get(case.case_id)) is not None
    ]
    total = len(corpus.cases)
    matched = sum(1 for item in observations if item.status == "matched")
    syntactic = sum(1 for result in corpus_results if result.syntactically_valid)
    semantic = sum(1 for result in corpus_results if result.semantic_match)
    ambiguous = sum(1 for result in corpus_results if result.ambiguous)
    needs_review = sum(1 for result in corpus_results if result.outcome == "needs_review")
    false_acceptance = sum(1 for result in corpus_results if result.false_acceptance)
    clarification_cases = [case for case in corpus.cases if case.expected.outcome == "clarification"]
    refusal_cases = [case for case in corpus.cases if case.expected.outcome == "refused"]
    runtime = sum(result.runtime_ms for result in corpus_results)
    return RequirementTranslationBenchmarkReport(
        corpus_id=corpus.corpus_id,
        version=corpus.version,
        result="passed" if matched == total and false_acceptance == 0 else "failed",
        total_cases=total,
        matched_cases=matched,
        syntactic_validity_rate=_ratio(syntactic, total),
        semantic_match_rate=_ratio(semantic, total),
        ambiguity_rate=_ratio(ambiguous, total),
        needs_review_rate=_ratio(needs_review, total),
        false_acceptance_rate=_ratio(false_acceptance, total),
        clarification_quality=_quality(clarification_cases, result_by_id),
        refusal_correctness=_refusal_correctness(refusal_cases, result_by_id),
        runtime_ms_total=runtime,
        observations=observations,
    )


def _observe(
    case: RequirementTranslationCase,
    result: RequirementTranslationCaseResult | None,
) -> RequirementTranslationObservation:
    if result is None:
        return RequirementTranslationObservation(
            case_id=case.case_id,
            expected_outcome=case.expected.outcome,
            status="missing",
            notes=["no observed translation result supplied"],
        )
    if result.false_acceptance:
        status = "false_acceptance"
    elif result.outcome != case.expected.outcome:
        status = "outcome_mismatch"
    elif case.expected.outcome == "accepted" and not result.semantic_match:
        status = "semantic_mismatch"
    elif case.expected.outcome == "clarification" and not _questions_match(case, result):
        status = "clarification_mismatch"
    elif case.expected.outcome == "refused" and case.expected.expected_refusal_code != result.refusal_code:
        status = "refusal_mismatch"
    elif case.expected.outcome == "needs_review" and not result.needs_review_reason:
        status = "review_mismatch"
    else:
        status = "matched"
    return RequirementTranslationObservation(
        case_id=case.case_id,
        expected_outcome=case.expected.outcome,
        observed_outcome=result.outcome,
        status=status,  # type: ignore[arg-type]
    )


def _questions_match(case: RequirementTranslationCase, result: RequirementTranslationCaseResult) -> bool:
    expected = {item.lower().strip() for item in case.expected.expected_clarification_questions}
    observed = {item.lower().strip() for item in result.clarification_questions}
    return expected.issubset(observed)


def _quality(
    cases: list[RequirementTranslationCase],
    results: dict[str, RequirementTranslationCaseResult],
) -> float | None:
    if not cases:
        return None
    return _ratio(
        sum(
            1
            for case in cases
            if (result := results.get(case.case_id)) is not None
            and _questions_match(case, result)
        ),
        len(cases),
    )


def _refusal_correctness(
    cases: list[RequirementTranslationCase],
    results: dict[str, RequirementTranslationCaseResult],
) -> float | None:
    if not cases:
        return None
    correct = sum(
        1
        for case in cases
        if (result := results.get(case.case_id)) is not None
        and result.refusal_code == case.expected.expected_refusal_code
    )
    return _ratio(correct, len(cases))


def _ratio(numerator: int, denominator: int) -> float:
    if denominator == 0:
        return 0.0
    return numerator / denominator
