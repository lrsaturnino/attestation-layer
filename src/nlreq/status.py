from __future__ import annotations

from .models import EvidenceObject, FinalStatus, StatusDecision


def decide_status(evidence: EvidenceObject) -> StatusDecision:
    """Pure status decision from evidence state."""
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
        return StatusDecision(
            status=FinalStatus.ACCEPTED_FOR_IMPLEMENTATION_WITH_REVIEW,
            reason="Package is structurally usable but has evidence or review gaps.",
            next_actions=actions,
        )

    return StatusDecision(
        status=FinalStatus.ACCEPTED_WITH_EVIDENCE,
        reason="All required evidence levels are satisfied.",
    )
