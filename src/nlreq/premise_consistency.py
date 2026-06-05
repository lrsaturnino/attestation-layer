"""The shared, solver-independent identity of a FormalClaim premise-consistency question (PB-6.T3).

Two independent backends answer the same question — *is the conjunction of a claim's comparison and
set-literal-membership premises satisfiable?* — through deliberately different encoders: z3 in
``formal_claim_smt`` (uninterpreted sort + ``Distinct`` + disjunction of equalities) and cvc5 in
``cvc5_backend`` (native finite-set theory). The cross-backend agreement check (PB-6.T3) only has
teeth if the two results can be *paired on the same question* and then judged on their *verdict*, not
on encoder-specific incidentals (the z3 constraint strings, the cvc5 ``set.member`` terms, or the
``QF_UFLRA`` vs ``FS_LRA`` logic label they each record).

This module is that pairing key. The identity is derived from the ``FormalClaim`` fragments alone —
each contributing fragment's ``kind|operator|operands`` — with no solver term and no logic label, so
z3 and cvc5 compute the *same* ``overlap_key`` for the same claim by construction. It deliberately
imports neither backend (both backends import *it*), keeping it the single source of truth for which
premises contribute and how the question is identified, so the two encoders cannot drift apart on
*what* they were asked.
"""

from __future__ import annotations

from .formal_claim import FormalClaimFragment
from .jsonutil import sha256_text


def is_set_literal_membership(fragment: FormalClaimFragment) -> bool:
    """Whether a membership fragment enumerates concrete members (``x is in {A, B}``).

    A set-literal membership is marked at lowering (``metadata['membership'] == 'set_literal'``) and
    carries its members as concrete operands after the element. An opaque named-set membership
    (``x is in S``) lacks the marker — its set is a single opaque identifier with no enumerable
    contents — so it poses no finite consistency question and does not contribute here. This is the
    single predicate both SMT backends share, so they cannot disagree on which memberships count.
    """
    return fragment.metadata.get("membership") == "set_literal" and len(fragment.operands) >= 2


def contributing_premises(premises: list[FormalClaimFragment]) -> list[FormalClaimFragment]:
    """The premise fragments that pose the joint satisfiability question, comparisons before sets.

    Both SMT backends ask the same question over the same fragments: every comparison plus every
    set-literal membership. Ordering comparisons first then memberships matches the order each
    backend asserts them; the overlap key sorts fragment signatures, so the verdict is independent of
    this order regardless.
    """
    comparisons = [fragment for fragment in premises if fragment.kind == "comparison"]
    set_memberships = [
        fragment
        for fragment in premises
        if fragment.kind == "membership" and is_set_literal_membership(fragment)
    ]
    return [*comparisons, *set_memberships]


def premise_consistency_fragment_signature(fragment: FormalClaimFragment) -> str:
    """A backend-independent signature of a fragment's encoded meaning (kind, operator, operands).

    Derived from the ``FormalClaim`` rather than any solver term, so z3 and cvc5 compute the same
    signature for the same fragment — the atom of the shared question identity.
    """
    operands = ",".join(f"{operand.kind}:{operand.value}" for operand in fragment.operands)
    return f"{fragment.kind}|{fragment.operator}|{operands}"


def premise_consistency_overlap_key(premises: list[FormalClaimFragment]) -> str | None:
    """The shared identity of the premise-consistency question these premises pose, or None.

    Hashes the sorted signatures of the contributing premises (comparisons + set-literal
    memberships) — no solver term, no logic label — so the two backends emit an identical
    ``overlap_key`` for the same claim and the agreement check can pair their verdicts. Returns None
    when no premise contributes: there is no consistency question to ask, hence nothing to pair.
    """
    contributing = contributing_premises(premises)
    if not contributing:
        return None
    signatures = sorted(premise_consistency_fragment_signature(fragment) for fragment in contributing)
    return sha256_text("premise_consistency\n" + "\n".join(signatures))
