"""The FormalClaim premise-consistency backend surface and its cross-backend agreement gate (PB-6).

The existing ``FormalBackend`` protocol (``formal_backend.py``) is the wrong abstraction for this
question: it takes a ``RequirementIRV2``, lowers it to a TLA+ module, and runs a subprocess model
checker. The premise-consistency question is different in kind — it consumes an already-lowered
``FormalClaim`` and runs an in-process SMT solver to decide whether the conjunction of a claim's
comparison and set-literal-membership premises is satisfiable. So rather than force two in-process
SMT backends through the model-checker shape, this module defines a small, parallel backend surface
over the already-versioned ``FormalClaim`` (request) and ``BackendResult`` (response) types:

  - :class:`FormalClaimConsistencyBackend` — the protocol: ``check(claim) -> list[BackendResult]``.
  - two registered backends posing the *same* question through independent encoders: ``smt-theories``
    (z3, ``formal_claim_smt``) and ``cvc5`` (``cvc5_backend``), discoverable via
    :func:`formal_claim_consistency_backends` / :func:`formal_claim_consistency_backend_for_id`.
  - :func:`build_premise_consistency_agreement` — runs the registered backends on one claim and
    judges their verdicts with the verdict-first agreement gate (PB-6.T3): they share a
    solver-independent ``overlap_key`` for the question and must reach the same valid/invalid answer;
    an opposite-verdict divergence blocks, while logic label / evidence metadata / encoded form
    differences do not.

This module imports the backends and the agreement gate but nothing imports it, so it stays clear of
the ``formal_claim`` -> ``proof_closure`` -> ``backend_agreement`` import chain.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from .backend_agreement import (
    BackendAgreementPolicy,
    BackendAgreementReport,
    build_backend_agreement_report,
)
from .cvc5_backend import CVC5_BACKEND_ID, cvc5_check_formal_claim_premises
from .formal_claim import FormalClaim
from .formal_claim_smt import SMT_THEORIES_BACKEND_ID, smt_check_formal_claim_premise_consistency
from .models import BackendResult, EvidenceLevel
from .premise_consistency import contributing_premises, premise_consistency_overlap_key


# The backend surface is versioned by the types it carries: the request is a FormalClaim
# (FORMAL_CLAIM_SCHEMA_VERSION) and the response is a list of BackendResult (the backend-results
# schema). This constant version-stamps the protocol/registry contract itself.
FORMAL_CLAIM_BACKEND_VERSION = "0.1"


@runtime_checkable
class FormalClaimConsistencyBackend(Protocol):
    """A backend that decides the premise-consistency question for a ``FormalClaim``.

    ``check`` returns one ``BackendResult`` per contributing premise (each covering its own
    ``fragment_id``), a decided ``valid``/``invalid`` verdict at ``SMT_CHECKED`` when the joint query
    is decided, and an honest non-checked result (``needs_review``/``unsupported`` with no evidence
    level) for any premise it could not encode or when the solver is unavailable.
    """

    backend_id: str

    def check(self, claim: FormalClaim) -> list[BackendResult]:
        ...


class SmtTheoriesConsistencyBackend:
    """z3 premise-consistency backend (``formal_claim_smt``), registered as ``smt-theories``."""

    backend_id = SMT_THEORIES_BACKEND_ID

    def check(self, claim: FormalClaim) -> list[BackendResult]:
        return smt_check_formal_claim_premise_consistency(claim)


class Cvc5ConsistencyBackend:
    """cvc5 premise-consistency backend (``cvc5_backend``), registered as ``cvc5``.

    Independent of the z3 encoder (native finite-set theory vs uninterpreted sort + ``Distinct``);
    degrades to ``unsupported`` results carrying no evidence level when cvc5 is not installed.
    """

    backend_id = CVC5_BACKEND_ID

    def check(self, claim: FormalClaim) -> list[BackendResult]:
        return cvc5_check_formal_claim_premises(claim)


def formal_claim_consistency_backends() -> list[FormalClaimConsistencyBackend]:
    """The registered FormalClaim premise-consistency backends, in a stable order.

    Both pose the same question through independent encoders, so cross-backend agreement over their
    verdicts is a real check on encoder divergence, not solver bugs.
    """
    return [SmtTheoriesConsistencyBackend(), Cvc5ConsistencyBackend()]


def formal_claim_consistency_backend_for_id(backend_id: str) -> FormalClaimConsistencyBackend:
    """The registered premise-consistency backend with ``backend_id``, or raise ``ValueError``."""
    for backend in formal_claim_consistency_backends():
        if backend.backend_id == backend_id:
            return backend
    raise ValueError(f"unknown formal-claim consistency backend: {backend_id}")


def build_premise_consistency_agreement(
    claim: FormalClaim,
    *,
    policy: BackendAgreementPolicy = "blocking",
    backends: list[FormalClaimConsistencyBackend] | None = None,
) -> BackendAgreementReport:
    """Run the registered backends on ``claim`` and judge their verdicts (verdict-first, PB-6.T3).

    Each backend's per-premise results are collapsed to one per-backend verdict on the shared
    question (they all carry the joint query's single verdict), keyed by the solver-independent
    ``overlap_key``. The verdict-first agreement gate then blocks only on an opposite-verdict
    divergence between backends — a real encoder disagreement — and treats logic label, evidence
    metadata, and encoded form as non-semantic. When a backend cannot decide the question (e.g. cvc5
    is not installed), it contributes a non-deciding observation and the pair is reported as
    non-overlap rather than a false disagreement.
    """
    selected = backends if backends is not None else formal_claim_consistency_backends()
    overlap_key = premise_consistency_overlap_key(claim.premises)
    collapsed = [
        _collapse_backend_verdict(backend, claim, overlap_key) for backend in selected
    ]
    return build_backend_agreement_report(collapsed, policy=policy, mode="verdict")


def _collapse_backend_verdict(
    backend: FormalClaimConsistencyBackend,
    claim: FormalClaim,
    overlap_key: str | None,
) -> BackendResult:
    """Collapse a backend's per-premise results to one verdict observation on the shared question.

    The shared question is the conjunction of *every* contributing premise — the comparison and
    set-literal-membership fragments :func:`contributing_premises` selects, the same set the
    ``overlap_key`` is hashed over. A backend has decided that question only when it discharged
    *every* contributing premise at ``SMT_CHECKED`` with a single ``valid``/``invalid`` verdict from
    the joint query. If any contributing fragment came back ``needs_review``/``unsupported`` (it could
    not be encoded, or the solver was unavailable) — or is missing from the results entirely — the
    backend answered only part of the question; collapsing that to a whole-question verdict would
    turn partial encoding into a false agreement (e.g. ``amount in {APPROVED} and amount >= 5``: the
    comparison checks ``valid`` while the membership is an unencodable sort clash, yet the antecedent
    as a whole was never decided). A partial or empty result is therefore non-deciding: it carries
    the degradation status (``unsupported`` if the tool was absent, else ``needs_review``), no
    evidence level, and lists the undecided contributing fragment IDs, so the agreement gate pairs it
    as non_overlap rather than a verdict.
    """
    results = backend.check(claim)

    # The full premise set that poses the shared question — the authoritative contributing set the
    # overlap_key is computed over, so a fragment the backend dropped entirely still counts as
    # undecided rather than silently vanishing from the coverage check.
    contributing_ids = {fragment.fragment_id for fragment in contributing_premises(claim.premises)}
    # The contributing fragments this backend actually decided at SMT_CHECKED with a verdict.
    decided_results = [
        result
        for result in results
        if result.evidence_level == EvidenceLevel.SMT_CHECKED
        and result.status in {"valid", "invalid"}
    ]
    decided_ids = {
        fragment_id
        for result in decided_results
        for fragment_id in result.details.get("covered_fragment_ids", [])
    }
    checked_verdicts = {result.status for result in decided_results}
    undecided_ids = sorted(contributing_ids - decided_ids)

    # Decided only when there IS a question and every contributing premise reached one verdict.
    fully_decided = bool(contributing_ids) and not undecided_ids and len(checked_verdicts) == 1
    if fully_decided:
        status = next(iter(checked_verdicts))
        evidence_level: EvidenceLevel | None = EvidenceLevel.SMT_CHECKED
        decided = True
    else:
        # Either the backend decided no verdict, decided only part of the question, or — defensively
        # — returned a split that a single joint query should never produce. Report a non-deciding
        # status so the pair is non_overlap, never a false whole-question verdict.
        status = "unsupported" if _any_unsupported(results) else "needs_review"
        evidence_level = None
        decided = False
    return BackendResult(
        backend=backend.backend_id,
        status=status,  # type: ignore[arg-type]
        evidence_level=evidence_level,
        details={
            "check": "premise_consistency:agreement",
            "overlap_key": overlap_key,
            # Judge this collapsed result on its verdict, not on encoder incidentals.
            "agreement_compare": "verdict",
            # Only the contributing premises actually discharged at SMT_CHECKED — partial coverage is
            # never reported as whole-question coverage.
            "covered_fragment_ids": sorted(decided_ids & contributing_ids),
            # Contributing premises this backend did not decide; non-empty here is exactly why the
            # result is non-deciding.
            "undecided_fragment_ids": undecided_ids,
            "decided": decided,
            "result_count": len(results),
        },
    )


def _any_unsupported(results: list[BackendResult]) -> bool:
    return any(result.status == "unsupported" for result in results)
