"""Per-role calibration harnesses for the four non-drafting LLM roles (scope §5, ADR 0204 §4).

The translation benchmark corpus (``translation_benchmark.py``) measures ONLY the drafting
front-half (prose -> controlled -> FormalClaim -> FA/FR). Each of the other four roles has a
different input/output/gold-standard shape, so it cannot be calibrated by that corpus. This
module supplies the role-specific corpora, runners, and scorers that close acceptance #5's
"per-role" dimension for decomposition / impact / extraction / audit:

* **decomposition** — input: approved controlled text; the decomposer re-expresses it as DSL v3
  -> IR. Gold = the FormalClaim signature derived from the controlled text (a faithful
  re-expression reproduces it). FA = a valid claim whose signature diverges (mis-re-expression
  accepted). FR = the decomposer produced an IR that does not lower to a claim (a lowerable
  requirement refused at the claim level) or raised an unparseable re-expression.
* **audit** — input: (controlled text, IR summary); the auditor returns an AuditVerdict. Gold =
  the correct verdict. FA = the auditor passed a faulty decomposition (missed an invented premise
  / missing clause). FR = the auditor failed a correct decomposition (false alarm).
* **impact** — input: (prose, symbols, candidate modules); the estimator returns a module set.
  Gold = the authoritative affected set. FA = the estimate named a module NOT in gold (over-claim
  / false impact). FR = the estimate missed a module IN gold (under-claim / missed impact). These
  are the precision/recall analogues of FA/FR for a set-valued role.
* **extraction** — input: (module, code presentation); the extractor returns candidate invariants.
  Gold = the correct invariant set. FA = the extractor proposed an invariant NOT in gold
  (invented). FR = the extractor missed an invariant IN gold.

Design invariants (mirroring ``translation_benchmark.py``):

* **Offline + deterministic by default.** With no live client, each case's ``recorded_*`` planted
  output is replayed through the role's recorded client, so the harness is CI-safe and
  byte-stable. This is the *discriminator* run: planted FA/FR cases yield non-zero FA/FR (the
  non-vacuity proof that the instrument discriminates), faithful cases yield zero. It is NOT a
  live-model measurement — that is the operator-side ``--llm-client`` pathway, exactly as with
  drafting (the live FA/FR run needs provider auth / the §6 sidecar and is not CI-safe).
* **Per-role client routing through the factory.** ``--llm-client <scheme>`` builds the role's
  client via ``build_client_for_role`` (the same ladder as drafting), so the transport under
  calibration is the configured one. The report carries a self-describing ``calibration`` block
  (role / client_kind / provider / resolved model / wrapper identity / prompt version) so the
  FA/FR tables stand alone without external filenames or prose.
* **Refusals are structured, never faked.** A bad scheme / missing config refuses at exit 2
  (``nlreq:``); a CLI transport that violates the pure-completion contract refuses via
  ``CliTransportError``. The scorer never silently accepts an unverifiable output.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Literal, Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .audit_client import AuditVerdict
from .translation_benchmark import CalibrationProvenance

# Shared schema version for the role-calibration corpus + report artifacts.
ROLE_CALIBRATION_SCHEMA_VERSION = "0.1"

# The four non-drafting roles this module calibrates. (drafting is calibrated by
# ``translation_benchmark.py``; importing ``Role`` here would create a cycle through the client
# constructors, so the role vocabulary is mirrored as a literal union for the corpus/report.)
CalibrationRole = Literal["decomposition", "impact", "extraction", "audit"]
FaultKind = Literal["faithful", "false_acceptance", "false_refusal"]


class ModelOutputFailure(Exception):
    """A live role client contacted the model but its output could not be turned into a usable
    role result (e.g. unparseable decomposition text).

    This is the ONLY exception family the role-calibration scorer treats as a scoreable
    false-refusal: the model DID answer, but the answer was unusable, which for a lowerable /
    correct input is a conservative FR. A client or test double may raise it directly to signal
    unusable model output; ``_run_case`` also wraps a ``DslV3ParseError`` (an unparseable
    decomposition re-expression) into it. Transport/config/environment/client infrastructure
    failures (``CliTransportError``, ``EnvironmentError``, ``ImportError``, SDK errors) are NOT
    model-output failures — they never reached a scoreable answer — so ``_run_case`` propagates
    them as ``CalibrationRunError`` (exit 2, no report), never a silent false-refusal.
    """


class CalibrationRunError(Exception):
    """A role-calibration run could not reach a scoreable outcome on a case.

    Raised by ``_run_case`` (and propagated by ``run_role_calibration``) when a live client
    raises a transport/config/environment/infrastructure failure that is NOT model behavior —
    i.e. the call never produced a usable model output to score (a missing API key, a missing
    SDK, an auth/network/rate-limit SDK error, or any other non-model-output client failure).
    ``benchmark-role`` converts it to exit 2 with ``nlreq:`` and writes NO report: a measurement
    that could not run must not be recorded as false-refusal evidence (scope §4 "structured
    refusal, never faked"). ``CliTransportError`` (a CLI-transport contract violation) propagates
    separately with its own provenance-hazard message but the same exit-2-no-report outcome —
    both mean 'the run is unverifiable, refuse.'
    """


# ---------------------------------------------------------------------------
# Per-case result + report (shared across the four roles)
# ---------------------------------------------------------------------------


class RoleCalibrationCaseResult(BaseModel):
    """One case's scored outcome under a role-calibration run.

    ``matched`` / ``false_acceptance`` / ``false_refusal`` are not mutually exclusive for the
    set-valued roles (impact / extraction): a partial-overlap estimate is both an over-claim (FA)
    and an under-claim (FR). For the verdict/signature roles (decomposition / audit) they are
    mutually exclusive. ``matched`` is True only when neither FA nor FR fired.
    """

    model_config = ConfigDict(extra="forbid")

    case_id: str
    fault_kind: FaultKind
    matched: bool = False
    false_acceptance: bool = False
    false_refusal: bool = False
    notes: list[str] = Field(default_factory=list)


class RoleCalibrationSubgroupMetrics(BaseModel):
    """Per-subgroup (domain or language) FA/FR breakdown.

    Both rates are reported separately and never collapsed into one "accuracy" — false-acceptance
    and false-refusal trade off against each other and must be read independently, exactly as in
    the drafting report.
    """

    model_config = ConfigDict(extra="forbid")

    label: str
    total_cases: int
    matched_count: int
    false_acceptance_count: int
    false_acceptance_rate: float
    false_refusal_count: int
    false_refusal_rate: float


class RoleCalibrationReport(BaseModel):
    """Self-describing per-role FA/FR calibration report.

    ``result`` is ``"passed"`` only when every case matched (FA=0 AND FR=0). A discriminator run
    over a planted-error corpus is EXPECTED to be ``"failed"`` — that non-zero FA/FR is the
    non-vacuity proof that the harness discriminates (a constant-zero instrument would pass
    vacuously). The committed discriminator reports therefore read as ``"failed"`` by design.
    ``calibration`` is None for a plain recorded ``--run`` (byte-stable, like the drafting release
    corpus) and populated only for a ``--llm-client`` calibration run.
    """

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["0.1"] = ROLE_CALIBRATION_SCHEMA_VERSION
    role: CalibrationRole
    corpus_id: str
    version: str
    result: Literal["passed", "failed"]
    total_cases: int
    matched_cases: int
    false_acceptance_count: int = 0
    false_acceptance_rate: float
    false_refusal_count: int = 0
    false_refusal_rate: float = 0.0
    domains: list[RoleCalibrationSubgroupMetrics] = Field(default_factory=list)
    languages: list[RoleCalibrationSubgroupMetrics] = Field(default_factory=list)
    calibration: CalibrationProvenance | None = None
    observations: list[RoleCalibrationCaseResult] = Field(default_factory=list)


class RoleCalibrationResults(BaseModel):
    """Pre-computed role-calibration case results (the ``--results`` input shape).

    Mirrors ``RequirementTranslationResults``: a schema-versioned wrapper around a list of
    per-case results so a calibration can be computed once and reported separately.
    """

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["0.1"] = ROLE_CALIBRATION_SCHEMA_VERSION
    role: CalibrationRole
    results: list[RoleCalibrationCaseResult]


# ---------------------------------------------------------------------------
# Per-role case + corpus types
# ---------------------------------------------------------------------------


class _CaseBase(BaseModel):
    """Shared fields for every role-calibration case.

    ``domain`` drives the per-domain FA/FR breakdown; ``language`` drives the per-language
    breakdown (defaults to ``en``, the intake vocabulary). ``fault_kind`` declares the planted
    fault so the scorer's expectation is explicit in the corpus (a discriminator corpus is
    self-documenting: a reader sees which cases are meant to FA / FR / match).
    """

    model_config = ConfigDict(extra="forbid")

    case_id: str
    title: str
    domain: str
    language: str = "en"
    fault_kind: FaultKind


class DecompositionCalibrationCase(_CaseBase):
    """A decomposition-calibration case.

    ``controlled_text`` is the APPROVED DSL v3 input the decomposer re-expresses. The gold
    FormalClaim signature is DERIVED from it (a faithful re-expression reproduces it), so no
    separate gold-signature field is needed (mirrors drafting's gold-IR derivation).
    ``recorded_dsl_text`` is the planted decomposer re-expression replayed in the recorded
    discriminator. ``fault_kind="false_refusal"`` means the planted re-expression must NOT lower
    to a claim (the harness marks its IR unsupported so ``build_formal_claim`` refuses); a live
    decomposer analogously refuses by emitting unparseable text or an unsupported IR.
    """

    controlled_text: str
    recorded_dsl_text: str


class AuditCalibrationCase(_CaseBase):
    """An audit-calibration case.

    ``controlled_text`` + ``ir_summary`` are the auditor's inputs. ``gold_verdict`` is the
    correct verdict (``passed`` for a faithful IR summary; ``failed`` for one with an invented
    premise / missing clause). ``recorded_verdict`` is the planted auditor response replayed in
    the recorded discriminator.
    """

    controlled_text: str
    ir_summary: str
    gold_verdict: Literal["passed", "failed"]
    # The planted auditor response, validated as a real ``AuditVerdict`` (its model_validator
    # derives ``verdict`` from ``covers_all_clauses`` / ``invented_premises``), so the corpus is
    # self-describing and the scorer can read ``.verdict`` directly.
    recorded_verdict: AuditVerdict


class ImpactCalibrationCase(_CaseBase):
    """An impact-calibration case.

    ``prose`` / ``symbols`` / ``candidate_modules`` are the estimator's inputs.
    ``gold_affected_modules`` is the authoritative affected set. ``recorded_estimate`` is the
    planted raw JSON estimate replayed in the recorded discriminator.
    """

    prose: str
    symbols: list[str] = Field(default_factory=list)
    candidate_modules: list[str] = Field(default_factory=list)
    gold_affected_modules: list[str]
    recorded_estimate: str


class ExtractionCalibrationCase(_CaseBase):
    """An extraction-calibration case.

    ``module_id`` / ``code_presentation`` / ``language`` are the extractor's inputs.
    ``gold_invariants`` is the correct invariant set (``{name, tla}``). ``recorded_estimate`` is
    the planted raw JSON extraction replayed in the recorded discriminator.
    """

    module_id: str
    code_presentation: str
    gold_invariants: list[dict[str, str]] = Field(default_factory=list)
    recorded_estimate: str


# Shared corpus wrapper (schema version + id + version + unique case ids) is defined below via
# ``_CorpusBase``; the four role-specific corpora follow.


class _CorpusBase(BaseModel):
    """Shared corpus wrapper: schema version + id + version + unique case ids."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["0.1"] = ROLE_CALIBRATION_SCHEMA_VERSION
    corpus_id: str
    version: str


class DecompositionCalibrationCorpus(_CorpusBase):
    cases: list[DecompositionCalibrationCase]

    @model_validator(mode="after")
    def _unique_ids(self) -> "DecompositionCalibrationCorpus":
        _check_unique_ids(self.cases)
        return self


class AuditCalibrationCorpus(_CorpusBase):
    cases: list[AuditCalibrationCase]

    @model_validator(mode="after")
    def _unique_ids(self) -> "AuditCalibrationCorpus":
        _check_unique_ids(self.cases)
        return self


class ImpactCalibrationCorpus(_CorpusBase):
    cases: list[ImpactCalibrationCase]

    @model_validator(mode="after")
    def _unique_ids(self) -> "ImpactCalibrationCorpus":
        _check_unique_ids(self.cases)
        return self


class ExtractionCalibrationCorpus(_CorpusBase):
    cases: list[ExtractionCalibrationCase]

    @model_validator(mode="after")
    def _unique_ids(self) -> "ExtractionCalibrationCorpus":
        _check_unique_ids(self.cases)
        return self


def _check_unique_ids(cases: list[Any]) -> None:
    ids = [getattr(c, "case_id") for c in cases]
    if len(ids) != len(set(ids)):
        raise ValueError("role-calibration corpus case ids must be unique")


# ---------------------------------------------------------------------------
# Runner + scorer
# ---------------------------------------------------------------------------


@runtime_checkable
class _DecompositionClient(Protocol):
    def decompose_controlled_to_ir(
        self, controlled_text: str, requirement_id: str, title: str
    ) -> Any: ...


@runtime_checkable
class _AuditClient(Protocol):
    def audit_decomposition(self, controlled_text: str, ir_summary: str) -> Any: ...


@runtime_checkable
class _LlmClient(Protocol):
    def estimate_impacted_modules(
        self, *, prose: str, symbols: list[str], candidate_modules: list[str]
    ) -> str: ...

    def extract_spec_invariants(
        self, *, module_id: str, code_presentation: str, language: str = "en"
    ) -> str: ...


def _gold_decomposition_signature(case: DecompositionCalibrationCase) -> str | None:
    """Derive the gold FormalClaim signature from the controlled text (a faithful re-expression
    reproduces it). None when the controlled text does not lower (not expected for an approved
    text, but handled conservatively)."""
    from .dsl_v3 import DslV3Parser
    from .formal_claim import build_formal_claim, formal_claim_signature

    try:
        ir = DslV3Parser().parse_ir(
            case.controlled_text, requirement_id=f"GOLD-{case.case_id}", title=case.title
        )
    except Exception:
        return None
    report = build_formal_claim(ir)
    if report.formal_claim is None:
        return None
    return formal_claim_signature(report.formal_claim, alpha_identifiers=False, commutative=True)


def _decomposition_recorded_client(case: DecompositionCalibrationCase) -> Any:
    """Build the per-case recorded decomposer from the planted DSL v3 re-expression.

    ``fault_kind="false_refusal"`` marks the planted re-expression as one that must NOT lower:
    its IR's ``requirement_class`` metadata is set to an unsupported value so
    ``build_formal_claim`` refuses (simulating a decomposer that re-expressed into an unsupported
    construct). A live decomposer analogously refuses by emitting unparseable text or an
    unsupported IR — both are FR for a lowerable input.
    """
    from .decomposition_client import RecordedDecompositionClient
    from .dsl_v3 import DslV3Parser

    ir = DslV3Parser().parse_ir(
        case.recorded_dsl_text, requirement_id=f"REC-{case.case_id}", title=case.title
    )
    if case.fault_kind == "false_refusal":
        # Mark the IR's claim class unsupported so the lowering refuses — the decomposer produced
        # an IR that cannot become a claim (FR for a lowerable input).
        ir = ir.model_copy(deep=True)
        ir.semantic_ir.metadata["requirement_class"] = "nlreq-calibration-unsupported"
    return RecordedDecompositionClient(fixture=ir, candidate_id=f"recorded-{case.case_id}")


def _score_decomposition(
    case: DecompositionCalibrationCase, outcome: Any, gold_sig: str | None
) -> RoleCalibrationCaseResult:
    notes: list[str] = []
    if isinstance(outcome, ModelOutputFailure):
        # The decomposer's model output was unusable (an unparseable live re-expression) — no
        # usable IR → a conservative FR. Only ModelOutputFailure is scoreable; infrastructure
        # failures never reach here (they propagate as CalibrationRunError before scoring).
        return RoleCalibrationCaseResult(
            case_id=case.case_id,
            fault_kind=case.fault_kind,
            false_refusal=True,
            notes=[f"decomposer model-output failure: {outcome!r}"],
        )
    from .formal_claim import build_formal_claim, formal_claim_signature

    report = build_formal_claim(outcome.requirement)
    if report.formal_claim is None:
        # The decomposer's IR does not lower to a claim → FR for a lowerable input.
        notes.append(f"decomposition IR refused lowering: {report.refusal_code}")
        return RoleCalibrationCaseResult(
            case_id=case.case_id, fault_kind=case.fault_kind, false_refusal=True, notes=notes
        )
    observed_sig = formal_claim_signature(
        report.formal_claim, alpha_identifiers=False, commutative=True
    )
    if gold_sig is not None and observed_sig == gold_sig:
        return RoleCalibrationCaseResult(
            case_id=case.case_id, fault_kind=case.fault_kind, matched=True, notes=notes
        )
    notes.append("decomposition lowered to a divergent FormalClaim signature")
    return RoleCalibrationCaseResult(
        case_id=case.case_id, fault_kind=case.fault_kind, false_acceptance=True, notes=notes
    )


def _audit_recorded_client(case: AuditCalibrationCase) -> Any:
    from .audit_client import RecordedAuditClient

    return RecordedAuditClient(fixture=case.recorded_verdict)


def _score_audit(case: AuditCalibrationCase, outcome: Any) -> RoleCalibrationCaseResult:
    if isinstance(outcome, ModelOutputFailure):
        return RoleCalibrationCaseResult(
            case_id=case.case_id,
            fault_kind=case.fault_kind,
            false_refusal=True,
            notes=[f"auditor model-output failure: {outcome!r}"],
        )
    observed = outcome.verdict
    if observed == case.gold_verdict:
        return RoleCalibrationCaseResult(
            case_id=case.case_id, fault_kind=case.fault_kind, matched=True
        )
    if observed == "passed" and case.gold_verdict == "failed":
        # The auditor passed a faulty decomposition (missed an invented premise / missing clause).
        return RoleCalibrationCaseResult(
            case_id=case.case_id, fault_kind=case.fault_kind, false_acceptance=True
        )
    # observed == "failed" and gold == "passed": the auditor false-alarmed a correct decomposition.
    return RoleCalibrationCaseResult(
        case_id=case.case_id, fault_kind=case.fault_kind, false_refusal=True
    )


def _impact_recorded_client(case: ImpactCalibrationCase) -> Any:
    from .llm_client import RecordedLlmClient

    return RecordedLlmClient(case.recorded_estimate)


def _score_impact(case: ImpactCalibrationCase, outcome: Any) -> RoleCalibrationCaseResult:
    from .llm_client import parse_impact_estimate

    if isinstance(outcome, ModelOutputFailure):
        return RoleCalibrationCaseResult(
            case_id=case.case_id,
            fault_kind=case.fault_kind,
            false_refusal=True,
            notes=[f"impact estimator model-output failure: {outcome!r}"],
        )
    estimated = set(parse_impact_estimate(outcome))
    gold = set(case.gold_affected_modules)
    over = estimated - gold  # named a module NOT in gold (false impact / over-claim)
    under = gold - estimated  # missed a module IN gold (missed impact / under-claim)
    notes: list[str] = []
    if over:
        notes.append(f"over-claimed modules: {sorted(over)}")
    if under:
        notes.append(f"missed modules: {sorted(under)}")
    return RoleCalibrationCaseResult(
        case_id=case.case_id,
        fault_kind=case.fault_kind,
        matched=not over and not under,
        false_acceptance=bool(over),
        false_refusal=bool(under),
        notes=notes,
    )


def _extraction_recorded_client(case: ExtractionCalibrationCase) -> Any:
    from .llm_client import RecordedLlmClient

    return RecordedLlmClient(case.recorded_estimate)


def _score_extraction(case: ExtractionCalibrationCase, outcome: Any) -> RoleCalibrationCaseResult:
    from .spec_extraction import parse_spec_extraction

    if isinstance(outcome, ModelOutputFailure):
        return RoleCalibrationCaseResult(
            case_id=case.case_id,
            fault_kind=case.fault_kind,
            false_refusal=True,
            notes=[f"extractor model-output failure: {outcome!r}"],
        )
    proposed = {(inv.name, inv.tla) for inv in parse_spec_extraction(outcome).invariants}
    gold = {(item["name"], item["tla"]) for item in case.gold_invariants}
    invented = proposed - gold  # proposed an invariant NOT in gold
    missed = gold - proposed  # missed an invariant IN gold
    notes: list[str] = []
    if invented:
        notes.append(f"invented invariants: {sorted(invented)}")
    if missed:
        notes.append(f"missed invariants: {sorted(missed)}")
    return RoleCalibrationCaseResult(
        case_id=case.case_id,
        fault_kind=case.fault_kind,
        matched=not invented and not missed,
        false_acceptance=bool(invented),
        false_refusal=bool(missed),
        notes=notes,
    )


def _run_case(role: CalibrationRole, case: Any, client: Any) -> Any:
    """Invoke the role's client method for one case, returning the raw outcome.

    Three failure families, three treatments (scope §4 "structured refusal, never faked"):

    * **Model-output failure** — the live model DID answer but the answer was unusable (an
      unparseable decomposition re-expression raised as ``DslV3ParseError``, or an explicit
      ``ModelOutputFailure`` a client/test-double raises for unusable output). This is a
      conservative *false-refusal*: captured and returned (the scorer records FR), never a
      crash. ``DslV3ParseError`` is wrapped into ``ModelOutputFailure`` here so the scorer's
      single ``isinstance(outcome, ModelOutputFailure)`` guard handles both shapes.
    * **CLI-transport failure** (``CliTransportError``: missing sidecar, route mismatch, tools
      active, non-zero exit, wrapper-hash drift) — unverifiable-origin evidence, NOT model
      behavior: propagated out of ``run_role_calibration`` so the CLI converts it to exit 2,
      never a silent false-refusal in the report.
    * **Infrastructure failure** — every OTHER exception (missing API key / SDK, an
      auth/network/rate-limit SDK error, ``OSError``, ``ImportError``, ...): the call never
      reached a scoreable model output, so it is raised as ``CalibrationRunError`` (propagates
      to the CLI → exit 2, NO report), never a silent false-refusal and never a crash in the
      scorer (which would otherwise call ``outcome.requirement`` / ``outcome.verdict`` /
      ``parse_impact_estimate(outcome).strip()`` on the bare exception object).

    Recorded clients never raise any of these. Except-clause order matters:
    ``CliTransportError`` and ``DslV3ParseError`` both subclass ``ValueError``, so they must
    precede the generic ``except Exception``; ``ModelOutputFailure`` is a plain ``Exception``
    and is caught explicitly before it.
    """
    from .cli_llm_client import CliTransportError
    from .dsl_v3 import DslV3ParseError

    try:
        if role == "decomposition":
            return client.decompose_controlled_to_ir(
                case.controlled_text, requirement_id=f"REQ-{case.case_id}", title=case.title
            )
        if role == "audit":
            return client.audit_decomposition(
                controlled_text=case.controlled_text, ir_summary=case.ir_summary
            )
        if role == "impact":
            return client.estimate_impacted_modules(
                prose=case.prose, symbols=case.symbols, candidate_modules=case.candidate_modules
            )
        if role == "extraction":
            return client.extract_spec_invariants(
                module_id=case.module_id,
                code_presentation=case.code_presentation,
                language=case.language,
            )
    except CliTransportError:
        # Transport-origin failures are unverifiable-origin evidence, not scoreable model
        # failures: propagate so the CLI surfaces them as exit 2 (structured refusal), never a
        # false-refusal in the calibration report (scope §4). Must precede ``except Exception``
        # because ``CliTransportError`` subclasses ``ValueError``.
        raise
    except ModelOutputFailure as exc:
        # An explicit model-output failure (a live client / test-double signalling unusable
        # model output): the model DID answer but the answer was unusable → a conservative
        # false-refusal the scorer records, never a crash or an infrastructure refusal.
        return exc
    except DslV3ParseError as exc:
        # An unparseable decomposition re-expression: the live decomposer emitted text the DSL
        # v3 parser could not turn into an IR. The model DID answer, so this is a model-output
        # failure (conservative FR), NOT an infrastructure failure — wrap it so the scorer
        # records a false-refusal instead of raising ``CalibrationRunError``. Only the
        # decomposition dispatch parses DSL v3, so this clause is unreachable for the other
        # roles; ``DslV3ParseError`` subclasses ``ValueError``, so it must precede
        # ``except Exception``.
        failure = ModelOutputFailure(
            f"unparseable decomposition re-expression for case {case.case_id!r}: {exc}"
        )
        failure.__cause__ = exc  # preserve the parser error for diagnostics without `raise ... from`
        return failure
    except Exception as exc:  # noqa: BLE001 — infra failure → structured refusal, never scored.
        # Transport/config/environment/client infrastructure failure (missing API key / SDK,
        # an auth/network/rate-limit SDK error, ``OSError``, ``ImportError``, ...): the call
        # never reached a scoreable model output, so it must surface as a structured refusal
        # (exit 2, no report), never a silent false-refusal buried in the calibration evidence
        # (scope §4 "structured refusal, never faked").
        raise CalibrationRunError(
            f"role-calibration case {case.case_id!r} could not reach a scoreable outcome "
            f"({type(exc).__name__}: {exc})"
        ) from exc
    raise ValueError(f"unknown calibration role {role!r}")


def _score_case(role: CalibrationRole, case: Any, outcome: Any) -> RoleCalibrationCaseResult:
    if role == "decomposition":
        return _score_decomposition(case, outcome, _gold_decomposition_signature(case))
    if role == "audit":
        return _score_audit(case, outcome)
    if role == "impact":
        return _score_impact(case, outcome)
    if role == "extraction":
        return _score_extraction(case, outcome)
    raise ValueError(f"unknown calibration role {role!r}")


def _recorded_client_for_case(role: CalibrationRole, case: Any) -> Any:
    """Build the per-case recorded client from the case's planted output (the discriminator)."""
    if role == "decomposition":
        return _decomposition_recorded_client(case)
    if role == "audit":
        return _audit_recorded_client(case)
    if role == "impact":
        return _impact_recorded_client(case)
    if role == "extraction":
        return _extraction_recorded_client(case)
    raise ValueError(f"unknown calibration role {role!r}")


def run_role_calibration(
    role: CalibrationRole,
    cases: list[Any],
    *,
    client: Any = None,
) -> list[RoleCalibrationCaseResult]:
    """Run every case through the role's client and score it against gold.

    When ``client`` is None (the recorded discriminator), each case is driven by a per-case
    recorded client built from the case's planted ``recorded_*`` output — CI-safe, deterministic,
    and the non-vacuity proof that the harness discriminates. When ``client`` is supplied (the
    per-role factory output for ``--llm-client``), every case is driven by THAT client — the live
    calibration pathway (operator-side; needs provider auth / the §6 sidecar).

    A ``CliTransportError`` raised by a live cli client on any case PROPAGATES out of this
    function (it is not captured/scored): a transport-origin failure is unverifiable-origin
    evidence that must become a structured refusal (``benchmark-role`` exit 2), never a silent
    false-refusal in the report. A non-CLI infrastructure failure (missing API key / SDK, an
    auth/network/rate-limit SDK error, ``OSError``, ``ImportError``) likewise PROPAGATES as
    ``CalibrationRunError`` (raised by ``_run_case``): a run that could not reach a scoreable
    outcome on a case must refuse entirely (exit 2, no partial report), never a silent
    false-refusal. Model-output failures (an explicit ``ModelOutputFailure``, an unparseable
    decomposition re-expression, a non-lowering IR) remain captured and scored as conservative
    false-refusals.
    """
    results: list[RoleCalibrationCaseResult] = []
    for case in cases:
        case_client = client if client is not None else _recorded_client_for_case(role, case)
        outcome = _run_case(role, case, case_client)
        results.append(_score_case(role, case, outcome))
    return results


# ---------------------------------------------------------------------------
# Report builder
# ---------------------------------------------------------------------------


def _ratio(numerator: int, denominator: int) -> float:
    return numerator / denominator if denominator else 0.0


def _subgroup_metrics(
    cases: list[Any],
    results: list[RoleCalibrationCaseResult],
    *,
    key: str,
) -> list[RoleCalibrationSubgroupMetrics]:
    """Group FA/FR by a case attribute (``domain`` or ``language``), in first-seen order."""
    labels: list[str] = []
    for case in cases:
        value = getattr(case, key)
        if value not in labels:
            labels.append(value)
    metrics: list[RoleCalibrationSubgroupMetrics] = []
    by_id = {r.case_id: r for r in results}
    for label in labels:
        group_cases = [c for c in cases if getattr(c, key) == label]
        group_results = [by_id[c.case_id] for c in group_cases if c.case_id in by_id]
        total = len(group_cases)
        matched = sum(1 for r in group_results if r.matched)
        fa = sum(1 for r in group_results if r.false_acceptance)
        fr = sum(1 for r in group_results if r.false_refusal)
        metrics.append(
            RoleCalibrationSubgroupMetrics(
                label=label,
                total_cases=total,
                matched_count=matched,
                false_acceptance_count=fa,
                false_acceptance_rate=_ratio(fa, total),
                false_refusal_count=fr,
                false_refusal_rate=_ratio(fr, total),
            )
        )
    return metrics


def _validate_results_against_corpus(
    cases: list[Any], results: list[RoleCalibrationCaseResult]
) -> None:
    """Ensure exactly one scored observation per corpus case (no missing/duplicate/extra).

    A truncated or duplicated results file would otherwise sum only the supplied observations
    and could report ``false_acceptance_count=0`` / ``false_refusal_count=0`` while missing most
    cases — weak evidence hygiene for committed calibration tables. Missing cases must be
    explicit observations (or a structured refusal at the CLI), not silent zeros. Raises
    ``ValueError`` (a ``ValueError`` subclass, so the CLI's ``except ValueError`` surfaces it as
    exit 2 with ``nlreq:``) on any mismatch: duplicates, missing case ids, or extra case ids not
    in the corpus.
    """
    case_ids = [getattr(c, "case_id") for c in cases]
    result_ids = [r.case_id for r in results]
    seen: set[str] = set()
    dupes: list[str] = []
    for rid in result_ids:
        if rid in seen:
            dupes.append(rid)
        seen.add(rid)
    if dupes:
        raise ValueError(
            f"role-calibration results have duplicate case ids: {sorted(set(dupes))}; "
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
            f"role-calibration results do not match the corpus "
            f"({len(case_ids)} corpus cases, {len(result_ids)} results): {'; '.join(problems)}; "
            "exactly one observation per corpus case is required — supply a complete results "
            "file or run --run (a truncated file must not report zeroed FA/FR rates)"
        )


def build_role_calibration_report(
    role: CalibrationRole,
    corpus: Any,
    results: list[RoleCalibrationCaseResult],
    *,
    calibration: CalibrationProvenance | None = None,
) -> RoleCalibrationReport:
    """Assemble the self-describing per-role FA/FR report from scored case results.

    Validates ``results`` against the corpus first (``_validate_results_against_corpus``): a
    partial or duplicated results list is a structured refusal, never zeroed FA/FR rates.
    """
    cases = corpus.cases
    _validate_results_against_corpus(cases, results)
    total = len(cases)
    matched = sum(1 for r in results if r.matched)
    fa = sum(1 for r in results if r.false_acceptance)
    fr = sum(1 for r in results if r.false_refusal)
    return RoleCalibrationReport(
        role=role,
        corpus_id=corpus.corpus_id,
        version=corpus.version,
        result="passed" if (fa == 0 and fr == 0 and matched == total) else "failed",
        total_cases=total,
        matched_cases=matched,
        false_acceptance_count=fa,
        false_acceptance_rate=_ratio(fa, total),
        false_refusal_count=fr,
        false_refusal_rate=_ratio(fr, total),
        domains=_subgroup_metrics(cases, results, key="domain"),
        languages=_subgroup_metrics(cases, results, key="language"),
        calibration=calibration,
        observations=results,
    )


# ---------------------------------------------------------------------------
# Corpus loading (dispatch on role)
# ---------------------------------------------------------------------------

_CORPUS_MODELS = {
    "decomposition": DecompositionCalibrationCorpus,
    "audit": AuditCalibrationCorpus,
    "impact": ImpactCalibrationCorpus,
    "extraction": ExtractionCalibrationCorpus,
}


def load_role_corpus(role: CalibrationRole, path: Any) -> Any:
    """Load and validate a role-calibration corpus for ``role`` from JSON.

    Raises ``ValueError`` for an unknown role (the CLI surfaces it as a structured refusal).
    The ``audit`` role's ``recorded_verdict`` is validated into a real ``AuditVerdict`` by the
    case model itself (pydantic BaseModel field), so no manual coercion is needed here.
    """
    if role not in _CORPUS_MODELS:
        raise ValueError(
            f"unknown calibration role {role!r} (expected one of {sorted(_CORPUS_MODELS)})"
        )
    model = _CORPUS_MODELS[role]
    data = json.loads(Path(path).read_text())
    return model.model_validate(data)
