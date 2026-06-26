from __future__ import annotations

from pathlib import PurePosixPath
from typing import TYPE_CHECKING, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

if TYPE_CHECKING:
    # Imported only for type-checking to avoid a runtime cycle; the live drafter is passed in
    # by the caller (the per-role factory, for calibration — scope §5 / ADR 0204 §4).
    from .llm_client import LlmClient


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
    # Domain label for the per-domain false-acceptance/false-refusal breakdown (PA-9).
    # Optional so the pre-PA-9 seed corpora (domain-less) keep validating; cases without
    # a domain are simply absent from the per-domain section of the report.
    domain: str | None = None
    # Source language of input_text, recorded in provenance for the per-language slice
    # (PA-11). Reuses the intake `language` vocabulary ("en", "pt", ...); defaults to en.
    language: str = "en"
    # The human-approved controlled rewrite (the "approved-controlled" of the
    # (prose, approved-controlled, gold-IR) triple). The gold IR — and thus the gold
    # FormalClaim signature the harness scores against — is DERIVED from this by the
    # deterministic DSL v3 parser, so no separate gold-IR file is needed. None for cases
    # whose gold outcome is a refusal (there is no correct claim to accept).
    gold_controlled_text: str | None = None
    # The controlled text a recorded model run produced for input_text, replayed verbatim
    # through RecordedLlmClient. Equals gold_controlled_text for a faithful rewrite; differs
    # for a planted drafting error (wrong claim / inverted premise / garbled). Falls back to
    # gold_controlled_text, then to input_text for already-controlled cases.
    recorded_controlled_text: str | None = None
    expected: RequirementTranslationExpected

    @model_validator(mode="after")
    def validate_expected_path(self) -> RequirementTranslationCase:
        if self.expected.expected_ir_path is not None:
            parsed = PurePosixPath(self.expected.expected_ir_path)
            if parsed.is_absolute() or ".." in parsed.parts:
                raise ValueError("expected_ir_path must be corpus-root-relative")
        return self

    def recorded_output(self) -> str:
        """The controlled text to replay through RecordedLlmClient for this case."""
        if self.recorded_controlled_text is not None:
            return self.recorded_controlled_text
        if self.gold_controlled_text is not None:
            return self.gold_controlled_text
        if self.input_kind == "controlled":
            return self.input_text
        raise ValueError(
            f"case {self.case_id!r} has no recorded_controlled_text, gold_controlled_text, "
            "or controlled input_text to replay"
        )


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
    false_refusal: bool = False
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
        "false_refusal",
        "outcome_mismatch",
    ]
    notes: list[str] = Field(default_factory=list)


class TranslationDomainMetrics(BaseModel):
    """Per-domain false-acceptance / false-refusal breakdown (PA-9).

    Both rates are reported separately and never collapsed into a single
    "accuracy": false-acceptance (a wrong claim accepted) and false-refusal
    (a correct claim refused) trade off against each other and must be read
    independently.
    """

    model_config = ConfigDict(extra="forbid")

    domain: str
    total_cases: int
    semantic_match_rate: float
    false_acceptance_count: int
    false_acceptance_rate: float
    false_refusal_count: int
    false_refusal_rate: float


class TranslationLanguageMetrics(BaseModel):
    """Per-language false-acceptance / false-refusal breakdown (PA-11).

    "NL-agnostic" may be claimed for a language only when its recorded rates are within
    the English budget on the spike; otherwise the claim is scoped to the languages that
    pass. Both rates are reported, never collapsed into one accuracy.
    """

    model_config = ConfigDict(extra="forbid")

    language: str
    total_cases: int
    semantic_match_rate: float
    false_acceptance_count: int
    false_acceptance_rate: float
    false_refusal_count: int
    false_refusal_rate: float


class CalibrationProvenance(BaseModel):
    """Self-describing per-role / per-model calibration provenance (scope §5, ADR 0204 §4).

    Stamped onto a ``RequirementTranslationBenchmarkReport`` when ``--llm-client`` calibrates a
    role, so the false-acceptance / false-refusal tables are self-describing by role / client
    kind / provider / resolved model / wrapper identity / prompt version — no reliance on
    external filenames or prose (recommended action #2). All transport-specific fields are
    optional so a partial provenance (e.g. anthropic with no wrapper) is honest rather than
    fabricated; ``jsonutil.to_jsonable`` serializes with ``exclude_none=True``, so absent fields
    are omitted and a non-calibration report (``calibration=None``) is byte-identical to before.
    """

    model_config = ConfigDict(extra="forbid")

    # The role under calibration (drafting / impact / extraction — the LlmClient-protocol roles
    # the translation corpus can drive). Required: a calibration report MUST state its role.
    role: str
    # The transport kind: anthropic | cli | recorded. Required.
    client_kind: str
    # The provider that answered (``anthropic`` for the SDK transport; the sidecar provider for
    # cli). None for recorded.
    provider: str | None = None
    # The exact model id that answered — the sidecar-resolved id for cli (NEVER the tier), the
    # configured/default model for anthropic. None for recorded.
    resolved_model: str | None = None
    # CLI-transport wrapper identity (ADR 0203). None for anthropic/recorded.
    wrapper: str | None = None
    wrapper_hash: str | None = None
    route: str | None = None
    cli_version: str | None = None
    # The role's prompt-template version stamp (shared across transports, ADR 0203).
    prompt_version: str | None = None
    # The ladder rung that resolved (override / env / config-file / default).
    transport_source: str | None = None


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
    false_acceptance_count: int = 0
    false_acceptance_rate: float
    false_refusal_count: int = 0
    false_refusal_rate: float = 0.0
    clarification_quality: float | None = None
    refusal_correctness: float | None = None
    runtime_ms_total: int
    # Per-domain breakdown of both rates (PA-9). Empty for domain-less corpora.
    domains: list[TranslationDomainMetrics] = Field(default_factory=list)
    # Per-language breakdown of both rates (PA-11). Single "en" entry for monolingual corpora.
    languages: list[TranslationLanguageMetrics] = Field(default_factory=list)
    # Self-describing calibration provenance (scope §5, ADR 0204 §4). None for a plain
    # --run (recorded replay) or a --results read — only set when --llm-client calibrates a
    # role, so non-calibration reports are byte-identical to before (exclude_none).
    calibration: CalibrationProvenance | None = None
    observations: list[RequirementTranslationObservation] = Field(default_factory=list)


class RequirementTranslationReleaseThresholds(BaseModel):
    model_config = ConfigDict(extra="forbid")

    false_acceptance_budget: int = Field(default=0, ge=0)
    # When set, EACH domain's false-acceptance count must be within this budget — a
    # per-domain gate so one domain cannot hide a regression behind another's headroom
    # (PA-9.T3). None disables the per-domain check (corpus-wide budget still applies).
    per_domain_false_acceptance_budget: int | None = Field(default=None, ge=0)
    false_refusal_budget: int | None = Field(default=None, ge=0)
    min_semantic_match_rate: float = Field(default=1.0, ge=0.0, le=1.0)
    min_clarification_quality: float | None = Field(default=None, ge=0.0, le=1.0)
    min_refusal_correctness: float | None = Field(default=None, ge=0.0, le=1.0)
    required_expected_outcomes: list[TranslationOutcome] = Field(
        default_factory=lambda: ["accepted", "clarification", "refused", "needs_review"]
    )


class RequirementTranslationReleaseBarReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["0.1"] = TRANSLATION_BENCHMARK_SCHEMA_VERSION
    result: Literal["passed", "failed"]
    benchmark_report_hash: str
    thresholds: RequirementTranslationReleaseThresholds
    blockers: list[str] = Field(default_factory=list)
    covered_expected_outcomes: list[TranslationOutcome] = Field(default_factory=list)


def _validate_translation_results_against_corpus(
    corpus: RequirementTranslationCorpus,
    results: RequirementTranslationResults,
) -> None:
    """Ensure exactly one scored result per corpus case (no missing/duplicate/extra).

    Without this guard, ``build_translation_benchmark_report`` collapses results into a dict
    keyed by ``case_id`` (duplicates overwrite earlier observations), silently omits missing
    case ids, and ignores extra ids — so a truncated or duplicated results file would report
    zeroed FA/FR rates while missing most cases (weak evidence hygiene for committed
    calibration tables). Mirrors ``role_calibration._validate_results_against_corpus``. Raises
    ``ValueError`` (surfaced by the CLI as exit 2 with ``nlreq:``) on any mismatch.
    """
    case_ids = [case.case_id for case in corpus.cases]
    result_ids = [result.case_id for result in results.results]
    seen: set[str] = set()
    dupes: list[str] = []
    for rid in result_ids:
        if rid in seen:
            dupes.append(rid)
        seen.add(rid)
    if dupes:
        raise ValueError(
            f"translation-benchmark results have duplicate case ids: {sorted(set(dupes))}; "
            "exactly one observation per corpus case is required"
        )
    expected = set(case_ids)
    actual = set(result_ids)
    missing = sorted(expected - actual)
    extra = sorted(actual - expected)
    if missing or extra:
        problems: list[str] = []
        if missing:
            problems.append(f"missing case ids {missing}")
        if extra:
            problems.append(f"extra case ids {extra} (not in corpus)")
        raise ValueError(
            f"translation-benchmark results do not match the corpus "
            f"({len(case_ids)} corpus cases, {len(result_ids)} results): {'; '.join(problems)}; "
            "exactly one observation per corpus case is required — supply a complete results "
            "file or run --run (a truncated file must not report zeroed FA/FR rates)"
        )


def build_translation_benchmark_report(
    corpus: RequirementTranslationCorpus,
    results: RequirementTranslationResults,
    *,
    calibration: CalibrationProvenance | None = None,
) -> RequirementTranslationBenchmarkReport:
    _validate_translation_results_against_corpus(corpus, results)
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
    false_refusal = sum(1 for result in corpus_results if result.false_refusal)
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
        false_acceptance_count=false_acceptance,
        false_acceptance_rate=_ratio(false_acceptance, total),
        false_refusal_count=false_refusal,
        false_refusal_rate=_ratio(false_refusal, total),
        clarification_quality=_quality(clarification_cases, result_by_id),
        refusal_correctness=_refusal_correctness(refusal_cases, result_by_id),
        runtime_ms_total=runtime,
        domains=_domain_metrics(corpus, result_by_id),
        languages=_language_metrics(corpus, result_by_id),
        calibration=calibration,
        observations=observations,
    )


def _group_rate_counts(
    cases: list[RequirementTranslationCase],
    result_by_id: dict[str, RequirementTranslationCaseResult],
) -> tuple[int, int, int, int]:
    """Return (total, semantic_match, false_acceptance, false_refusal) over a case group."""
    results = [
        result for case in cases if (result := result_by_id.get(case.case_id)) is not None
    ]
    return (
        len(cases),
        sum(1 for result in results if result.semantic_match),
        sum(1 for result in results if result.false_acceptance),
        sum(1 for result in results if result.false_refusal),
    )


def _domain_metrics(
    corpus: RequirementTranslationCorpus,
    result_by_id: dict[str, RequirementTranslationCaseResult],
) -> list[TranslationDomainMetrics]:
    """Group both rates by case.domain. Domain-less cases are omitted (no domain bucket)."""
    domains: list[str] = []
    for case in corpus.cases:
        if case.domain is not None and case.domain not in domains:
            domains.append(case.domain)
    metrics: list[TranslationDomainMetrics] = []
    for domain in domains:
        cases = [case for case in corpus.cases if case.domain == domain]
        total, semantic, false_acceptance, false_refusal = _group_rate_counts(cases, result_by_id)
        metrics.append(
            TranslationDomainMetrics(
                domain=domain,
                total_cases=total,
                semantic_match_rate=_ratio(semantic, total),
                false_acceptance_count=false_acceptance,
                false_acceptance_rate=_ratio(false_acceptance, total),
                false_refusal_count=false_refusal,
                false_refusal_rate=_ratio(false_refusal, total),
            )
        )
    return metrics


def _language_metrics(
    corpus: RequirementTranslationCorpus,
    result_by_id: dict[str, RequirementTranslationCaseResult],
) -> list[TranslationLanguageMetrics]:
    """Group both rates by case.language (PA-11), in first-seen order."""
    languages: list[str] = []
    for case in corpus.cases:
        if case.language not in languages:
            languages.append(case.language)
    metrics: list[TranslationLanguageMetrics] = []
    for language in languages:
        cases = [case for case in corpus.cases if case.language == language]
        total, semantic, false_acceptance, false_refusal = _group_rate_counts(cases, result_by_id)
        metrics.append(
            TranslationLanguageMetrics(
                language=language,
                total_cases=total,
                semantic_match_rate=_ratio(semantic, total),
                false_acceptance_count=false_acceptance,
                false_acceptance_rate=_ratio(false_acceptance, total),
                false_refusal_count=false_refusal,
                false_refusal_rate=_ratio(false_refusal, total),
            )
        )
    return metrics


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
    elif result.false_refusal:
        status = "false_refusal"
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


def evaluate_translation_benchmark_release_bar(
    report: RequirementTranslationBenchmarkReport,
    *,
    thresholds: RequirementTranslationReleaseThresholds | None = None,
) -> RequirementTranslationReleaseBarReport:
    effective_thresholds = thresholds or RequirementTranslationReleaseThresholds()
    blockers: list[str] = []
    if report.false_acceptance_count > effective_thresholds.false_acceptance_budget:
        blockers.append(
            "false semantic acceptance budget exceeded: "
            f"{report.false_acceptance_count} > {effective_thresholds.false_acceptance_budget}"
        )
    if effective_thresholds.per_domain_false_acceptance_budget is not None:
        for domain in report.domains:
            if domain.false_acceptance_count > effective_thresholds.per_domain_false_acceptance_budget:
                blockers.append(
                    f"false semantic acceptance budget exceeded in domain {domain.domain!r}: "
                    f"{domain.false_acceptance_count} > "
                    f"{effective_thresholds.per_domain_false_acceptance_budget}"
                )
    if (
        effective_thresholds.false_refusal_budget is not None
        and report.false_refusal_count > effective_thresholds.false_refusal_budget
    ):
        blockers.append(
            "false semantic refusal budget exceeded: "
            f"{report.false_refusal_count} > {effective_thresholds.false_refusal_budget}"
        )
    if report.semantic_match_rate < effective_thresholds.min_semantic_match_rate:
        blockers.append(
            "semantic match rate below release threshold: "
            f"{report.semantic_match_rate:.3f} < {effective_thresholds.min_semantic_match_rate:.3f}"
        )
    if (
        effective_thresholds.min_clarification_quality is not None
        and (report.clarification_quality or 0.0) < effective_thresholds.min_clarification_quality
    ):
        blockers.append("clarification quality below release threshold")
    if (
        effective_thresholds.min_refusal_correctness is not None
        and (report.refusal_correctness or 0.0) < effective_thresholds.min_refusal_correctness
    ):
        blockers.append("refusal correctness below release threshold")
    covered = sorted({item.expected_outcome for item in report.observations})
    missing_outcomes = [
        outcome for outcome in effective_thresholds.required_expected_outcomes if outcome not in covered
    ]
    if missing_outcomes:
        blockers.append(f"benchmark corpus missing required expected outcomes: {', '.join(missing_outcomes)}")
    return RequirementTranslationReleaseBarReport(
        result="failed" if blockers or report.result == "failed" else "passed",
        benchmark_report_hash=_report_hash(report),
        thresholds=effective_thresholds,
        blockers=blockers,
        covered_expected_outcomes=covered,  # type: ignore[arg-type]
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


def _report_hash(report: RequirementTranslationBenchmarkReport) -> str:
    from .jsonutil import sha256_json

    return sha256_json(report)


# --- PA-9 corpus runner ----------------------------------------------------------------
#
# Measures the LLM front-half (PA-4 drafting + PA-5 translation) over a labeled corpus,
# OFFLINE and deterministically: each case's recorded model output is replayed through
# RecordedLlmClient and run prose -> draft -> translate -> FormalClaim. This scores the
# pipeline gate's quality OVER THE RECORDED OUTPUTS — it is NOT an empirical LLM error
# rate (that is the separate, budgeted live-LLM suite). Both rates are reported, never a
# single "accuracy":
#   false_acceptance  = the pipeline accepted a claim it should not have — either the
#                       gold outcome was a refusal, or the accepted claim's signature
#                       diverges from the gold claim (wrong class / inverted or invented
#                       premise). Equality uses the alpha/commutative-normalised
#                       FormalClaim signature, so cosmetic id/title/order differences do
#                       not count as divergence.
#   false_refusal     = the pipeline refused (or needs-review) a claim the gold says
#                       should have been accepted.
_DEFAULT_INTAKE_TIMESTAMP = "2026-01-01T00:00:00Z"


def evaluate_translation_case(
    case: RequirementTranslationCase,
    *,
    intake_timestamp: str = _DEFAULT_INTAKE_TIMESTAMP,
    client: LlmClient | None = None,
) -> RequirementTranslationCaseResult:
    from .formal_claim import formal_claim_signature
    from .intake import (
        create_free_form_intake,
        cross_language_clarification,
        draft_controlled_rewrite_with_llm,
    )
    from .llm_client import RecordedLlmClient
    from .semantic_translation import (
        refuse_low_confidence_cross_language,
        translate_controlled_requirement_to_formal_claim,
    )

    gold_signature = _gold_claim_signature(case)

    # When a live client is supplied (per-role calibration, scope §5 / ADR 0204 §4), the drafter
    # IS that client — the corpus measures ITS false-acceptance / false-refusal against the gold,
    # routing through the per-role factory so the transport under calibration is the configured
    # one. Without a client, the case's recorded output is replayed offline (CI-safe, byte-stable).
    if client is not None:
        drafter = client
    else:
        drafter = RecordedLlmClient(case.recorded_output())

    # Route through the PA-4 drafting path so the prose -> controlled inference is exercised
    # exactly as production would. The intake records the source language (PA-11) which steers
    # the drafter. With no ``client`` the case's recorded output is replayed offline; with a
    # ``client`` the live (factory-built) drafter is under calibration (scope §5).
    intake = create_free_form_intake(
        intake_id=f"intake-{case.case_id}",
        original_text=case.input_text,
        submitted_at=intake_timestamp,
        language=case.language,
    )
    proposal = draft_controlled_rewrite_with_llm(
        intake=intake,
        client=drafter,
        proposal_id=f"proposal-{case.case_id}",
        timestamp=intake_timestamp,
        model="recorded",
        language=case.language,
    )
    # PA-11: a low-confidence cross-language draft refuses with a clarification rather than
    # letting a guessed rewrite reach the parser.
    clarify_fragment = cross_language_clarification(proposal.proposed_controlled_text)
    if clarify_fragment is not None:
        translation = refuse_low_confidence_cross_language(
            requirement_id=f"REQ-{case.case_id}",
            language=case.language,
            fragment=clarify_fragment,
            prose=case.input_text,
        )
    else:
        translation = translate_controlled_requirement_to_formal_claim(
            controlled_text=proposal.proposed_controlled_text,
            requirement_id=f"REQ-{case.case_id}",
            title=case.title,
        )

    accepted = translation.result == "accepted"
    claim = (
        translation.formal_claim_report.formal_claim
        if translation.formal_claim_report is not None
        else None
    )
    semantic_match = False
    semantic_profile: str | None = None
    if accepted and claim is not None:
        semantic_profile = claim.semantics_profile
        observed_signature = formal_claim_signature(
            claim, alpha_identifiers=False, commutative=True
        )
        semantic_match = gold_signature is not None and observed_signature == gold_signature

    gold_is_accept = case.expected.outcome == "accepted"
    false_acceptance = accepted and not (gold_is_accept and semantic_match)
    false_refusal = (not accepted) and gold_is_accept

    return RequirementTranslationCaseResult(
        case_id=case.case_id,
        outcome=translation.result,
        syntactically_valid=translation.syntactically_valid,
        semantic_match=semantic_match,
        ambiguous=bool(translation.ambiguity_findings),
        false_acceptance=false_acceptance,
        false_refusal=false_refusal,
        formal_claim_hash=translation.formal_claim_hash,
        semantic_profile=semantic_profile,
        clarification_questions=translation.clarification_questions,
        refusal_code=translation.refusal_code,
    )


def run_translation_corpus(
    corpus: RequirementTranslationCorpus,
    *,
    intake_timestamp: str = _DEFAULT_INTAKE_TIMESTAMP,
    client: LlmClient | None = None,
) -> RequirementTranslationResults:
    """Run every corpus case through the offline front-half and collect scored results.

    When ``client`` is supplied (per-role calibration, scope §5 / ADR 0204 §4), each case is
    drafted by that client instead of its recorded output, so the corpus measures the client's
    false-acceptance / false-refusal against the gold. Routing through a factory-built client is
    what makes the per-role, per-model calibration executable across providers; the live FA/FR
    run itself is operator-side (it needs the §6 sidecar + provider auth, neither CI-safe).
    """
    return RequirementTranslationResults(
        results=[
            evaluate_translation_case(case, intake_timestamp=intake_timestamp, client=client)
            for case in corpus.cases
        ]
    )


def _gold_claim_signature(case: RequirementTranslationCase) -> str | None:
    """Derive the gold FormalClaim signature from the approved-controlled text.

    The gold IR is the deterministic DSL v3 parse of gold_controlled_text, so there is
    no separately maintained gold-IR file to drift. Returns None when the case declares
    no gold (a refusal-gold case) or the approved text does not lower to a claim.
    """
    if case.gold_controlled_text is None:
        return None
    from .dsl_v3 import DslV3ParseError, DslV3Parser
    from .formal_claim import build_formal_claim, formal_claim_signature

    try:
        ir = DslV3Parser().parse_ir(
            case.gold_controlled_text,
            requirement_id=f"GOLD-{case.case_id}",
            title=case.title,
        )
    except DslV3ParseError:
        return None
    report = build_formal_claim(ir)
    if report.formal_claim is None:
        return None
    return formal_claim_signature(report.formal_claim, alpha_identifiers=False, commutative=True)
