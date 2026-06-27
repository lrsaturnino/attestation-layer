from __future__ import annotations

from .models import EvidenceObject, FinalStatus, PinningProvenance, StatusDecision


# The explicit set of statuses that represent a HUMAN acceptance — never a machine pinning.
# This replaces the former ``status.startswith("ACCEPTED")`` prefix checks at the six consumer
# sites (``adoption.py``, ``continuous.py``, ``agent_workflow.py``) so that a machine-pinned status
# (``MACHINE_PINNED_PENDING_REVIEW``, which deliberately does NOT start with "ACCEPTED") can never
# be silently treated as human-accepted, AND a future ACCEPTED-prefixed machine status could not
# slip through a prefix check. Membership is compared against an explicit frozenset, not a prefix
# (ADR 0206; acceptance #3).
HUMAN_ACCEPTED_STATUSES: frozenset[str] = frozenset(
    {
        FinalStatus.ACCEPTED_WITH_EVIDENCE.value,
        FinalStatus.ACCEPTED_FOR_IMPLEMENTATION_WITH_REVIEW.value,
    }
)


def is_human_accepted(status: object) -> bool:
    """Whether ``status`` represents a HUMAN acceptance — never a machine pinning.

    Only the two human-accepted ``FinalStatus`` values count (``ACCEPTED_WITH_EVIDENCE`` and
    ``ACCEPTED_FOR_IMPLEMENTATION_WITH_REVIEW``). A machine-pinned status
    (``MACHINE_PINNED_PENDING_REVIEW``) is deliberately NOT in this set, so the six former
    ``startswith("ACCEPTED")`` consumers never silently treat a machine-pinned package as
    human-accepted. Accepts a ``FinalStatus`` member or a plain string (the two shapes the
    consumers see — enum members from in-memory decisions, strings from JSON-loaded packages);
    any other type (e.g. ``None``) is not human-accepted.
    """
    if isinstance(status, FinalStatus):
        return status.value in HUMAN_ACCEPTED_STATUSES
    return isinstance(status, str) and status in HUMAN_ACCEPTED_STATUSES


def decide_status(
    evidence: EvidenceObject, pinning: PinningProvenance | None = None
) -> StatusDecision:
    """Pure status decision from evidence state, optionally consulting pinning provenance.

    The ``pinning`` record is a separate provenance axis from evidence: it records WHO pinned the
    controlled meaning, not WHAT tool produced evidence. When a package is machine-pinned
    (``pinning.kind == "machine_agreement"``) it resolves to ``MACHINE_PINNED_PENDING_REVIEW`` — a
    status that does NOT start with ``ACCEPTED`` — in BOTH non-refusal branches (the all-evidence-
    satisfied branch and the evidence-gap / pending-review branch), so the six former prefix-check
    consumers never silently treat it as human-accepted. Deterministic evidence-level requirements
    are unchanged: machine pinning never substitutes for a proof level, so a machine-pinned package
    with an ambiguous / unbound / unsupported / failed / timeout / needs-coverage signal still
    refuses exactly as a human-reviewed package would, and a machine-pinned package with an evidence
    or review gap still surfaces that gap in ``next_actions`` — but it resolves to
    ``MACHINE_PINNED_PENDING_REVIEW`` (never to an ``ACCEPTED``-prefixed status), so acceptance #3
    holds unconditionally: a machine-pinned package is never resolved to a status that starts with
    ``ACCEPTED``. With ``pinning=None`` (the default), behavior is byte-identical to the
    pre-machine-pinning pipeline: every rule stays on the human path (acceptance #1).
    """
    machine_pinned = pinning is not None and pinning.kind == "machine_agreement"
    if evidence.ambiguous or evidence.ambiguous_symbols:
        if evidence.ambiguous_symbols:
            ambiguous = ", ".join(evidence.ambiguous_symbols)
            first_ambiguous = evidence.ambiguous_symbols[0]
            return StatusDecision(
                status=FinalStatus.REFUSED_AMBIGUOUS,
                reason=f"Ambiguous symbols: {ambiguous}.",
                next_actions=["Choose one binding for each ambiguous symbol or rewrite the requirement."],
                source_span=evidence.ambiguous_symbol_spans.get(first_ambiguous),
            )
        return StatusDecision(
            status=FinalStatus.REFUSED_AMBIGUOUS,
            reason="Requirement is ambiguous.",
            next_actions=["Rewrite the controlled requirement to remove ambiguity."],
        )
    if evidence.unbound_symbols:
        missing = ", ".join(evidence.unbound_symbols)
        first_missing = evidence.unbound_symbols[0]
        return StatusDecision(
            status=FinalStatus.REFUSED_UNBOUND_SYMBOLS,
            reason=f"Unbound symbols: {missing}.",
            next_actions=["Add bindings for missing symbols or rewrite using approved vocabulary."],
            source_span=evidence.unbound_symbol_spans.get(first_missing),
        )
    if evidence.unsupported_claims:
        claims = ", ".join(evidence.unsupported_claims)
        return StatusDecision(
            status=FinalStatus.REFUSED_UNSUPPORTED_CLAIM,
            reason=f"Unsupported claims: {claims}.",
            next_actions=["Rewrite using supported Phase 0 claim kinds."],
        )
    if evidence.failed_checks:
        failed = ", ".join(evidence.failed_checks)
        return StatusDecision(
            status=FinalStatus.REFUSED_FAILED_CHECK,
            reason=f"Failed checks: {failed}.",
            next_actions=["Inspect backend evidence and revise the requirement or assumptions."],
        )
    if evidence.timeouts:
        timeouts = ", ".join(evidence.timeouts)
        return StatusDecision(
            status=FinalStatus.REFUSED_TIMEOUT,
            reason=f"Timed out checks: {timeouts}.",
            next_actions=["Reduce scope, increase budget, or lower required evidence."],
        )
    if evidence.needs_spec_coverage:
        return StatusDecision(
            status=FinalStatus.NEEDS_SPEC_COVERAGE,
            reason="Requirement touches a target with insufficient spec coverage.",
            next_actions=["Add or review spec coverage for the target."],
        )

    missing_evidence = [
        claim.id
        for claim in evidence.claims
        if claim.achieved_evidence is None or claim.achieved_evidence != claim.required_evidence
    ]
    if missing_evidence or evidence.pending_reviews:
        actions = []
        if missing_evidence:
            actions.append(f"Provide required evidence for claims: {', '.join(missing_evidence)}.")
        if evidence.pending_reviews:
            actions.append(f"Resolve pending reviews: {', '.join(evidence.pending_reviews)}.")
        # A machine-pinned package never resolves to an ACCEPTED-prefixed status (acceptance #3):
        # route the evidence/review gap to the machine-pinned bucket while still surfacing the
        # gap in ``next_actions`` — machine pinning never substitutes for a deterministic proof
        # level, so the gap is not hidden, only the status is non-ACCEPTED.
        if machine_pinned:
            actions.append(
                "A human may review this machine-pinned rule to promote it to human_review "
                "(promotion is upward only; a human review never reverts to machine pinning)."
            )
            return StatusDecision(
                status=FinalStatus.MACHINE_PINNED_PENDING_REVIEW,
                reason=(
                    "Machine-pinned package has evidence or review gaps; machine pinning never "
                    "substitutes for a deterministic proof level. Pending human review."
                ),
                next_actions=actions,
            )
        return StatusDecision(
            status=FinalStatus.ACCEPTED_FOR_IMPLEMENTATION_WITH_REVIEW,
            reason="Package is structurally usable but has evidence or review gaps.",
            next_actions=actions,
        )

    # All required evidence levels are satisfied. A machine-pinned package (whose controlled
    # meaning was pinned by a cross-provider ensemble) resolves to a status that does NOT start
    # with "ACCEPTED", so it is never silently treated as human-accepted by the former
    # prefix-check consumers (acceptance #3). The deterministic evidence bar is unchanged —
    # machine pinning never substitutes for a proof level; it only records who pinned the meaning.
    if machine_pinned:
        return StatusDecision(
            status=FinalStatus.MACHINE_PINNED_PENDING_REVIEW,
            reason=(
                "All required evidence levels are satisfied and the controlled meaning was "
                "machine-pinned by a cross-provider ensemble; pending human review."
            ),
            next_actions=[
                "A human may review this machine-pinned rule to promote it to human_review "
                "(promotion is upward only; a human review never reverts to machine pinning)."
            ],
        )

    return StatusDecision(
        status=FinalStatus.ACCEPTED_WITH_EVIDENCE,
        reason="All required evidence levels are satisfied.",
    )
