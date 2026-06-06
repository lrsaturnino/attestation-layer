from __future__ import annotations

from z3 import (
    ArithRef,
    Bool,
    BoolRef,
    Const,
    DeclareSort,
    Distinct,
    ExprRef,
    Not,
    Or,
    Real,
    RealVal,
    SortRef,
    Solver,
    sat,
    unsat,
)

from .formal_claim import FormalClaim, FormalClaimFragment, FormalClaimOperand
from .jsonutil import sha256_text
from .models import BackendResult, EvidenceLevel
from .numeric_literal import exact_fraction
from .premise_consistency import is_set_literal_membership, premise_consistency_overlap_key

# Evidence honesty: a fragment that was *not checked here* carries no evidence level. This covers
# both an "unsupported" predicate/order fragment (needs a model checker) and a "needs_review"
# fragment that could not enter the joint encoding (a non-arithmetic comparison, an opaque named-set
# membership, or a sort clash). Claiming CONSISTENCY_CHECKED for a premise the solver never saw would
# overstate the evidence — the honest level is None. _producer_blockers skips results with
# evidence_level=None, so an unchecked route stays cleanly open rather than tripping a spurious
# producer-mapping blocker (smt-theories is registered for SMT_CHECKED only).
_UNCHECKED_EVIDENCE: EvidenceLevel | None = None


FORMAL_CLAIM_SMT_VERSION = "0.1"

# The producer id every result here carries (PB-7). This is the theory-aware z3 backend — Int/Real
# linear arithmetic plus an uninterpreted member sort — registered in proof_closure distinctly from
# the propositional ``core_smt`` (nlreq.smt). Tagging the theory discharge with its own producer id
# is what lets proof closure route comparison/membership premises to it without conflating them with
# the propositional encoder that drops those ops.
SMT_THEORIES_BACKEND_ID = "smt-theories"

# The Z3 logic the premise consistency check runs in: quantifier-free linear real arithmetic.
# The IR declares no sorts for identifiers, so the reals are the honest (most permissive) domain —
# an UNSAT over the reals is a genuine contradiction in any numeric interpretation, and the
# satisfiability claim is reported as "consistent over QF_LRA", never as a stronger integer result.
_SMT_LOGIC = "QF_LRA"

# Comparison operators the linear-arithmetic encoder understands. Membership "in" is not one of
# them: a set-literal membership encodes into a finite sort of distinct named members (see
# _encode_set_membership), and an opaque named-set membership has no concrete collection to encode
# and stays a model-level check.
_COMPARISON_OPS = frozenset({"eq", "neq", "lt", "lte", "gt", "gte"})


def smt_check_formal_claim_predicate_fragments(claim: FormalClaim) -> list[BackendResult]:
    """SMT-check FormalClaim fragments, returning explicit results for every checkable kind.

    Evidence honesty contract:
      - Comparison fragments (premises): checked together by a claim-level Z3 linear-arithmetic
        consistency query — see ``_premise_consistency``. The conjunction of the numeric
        premises being satisfiable discharges each at SMT_CHECKED (the antecedent is realizable and
        internally consistent); being unsatisfiable marks them invalid (a contradictory antecedent
        a single boolean-only or per-fragment query cannot detect). A lone symbolic comparison is
        vacuous in isolation, so the check is deliberately claim-level, not per-fragment.
      - Comparison obligations lower to ``state_invariant`` (invariance over S's transitions), not
        ``comparison``; proving them needs the system model S, so they are NOT discharged here —
        they route to the S ∧ R model check (Apalache). Z3 only checks the premise antecedent.
      - Predicate fragments: named uninterpreted predicates require model-level checking
        (Apalache/Pillar B). Emits "unsupported" so their routes become "blocked" in the proof
        object (explicit reason) rather than silently "open".
      - Membership fragments: a set-literal membership (``x is in {A, B}``) carries its members as
        concrete operands, so it joins the claim-level premise-consistency query as a disjunction of
        equalities over distinct named members and discharges at SMT_CHECKED — a disjoint-set antecedent
        (``x in {A}`` and ``x in {B}``) is a catchable contradiction. An opaque named-set membership
        (``x is in S``) has no concrete collection to encode, so it was not checked: it emits
        needs_review with no evidence level and the route stays open.
      - rejection_order fragments: bounded-reachability ordering requires a model checker
        (Apalache). Emits "unsupported" so routes become "blocked".

    covered_fragment_ids is set on every result so proof_closure can match formal_claim-routed
    premises by fragment ID.
    """
    results = list(_premise_consistency(claim.premises))
    for fragment in [*claim.premises, *claim.obligations]:
        if fragment.kind == "membership" and is_set_literal_membership(fragment):
            # Set-literal membership is enumerated into the joint premise-consistency query above,
            # not re-checked vacuously per fragment; skip it here so it is not double-emitted.
            continue
        if fragment.kind in {"predicate", "rejection_order", "membership"}:
            results.append(_check_fragment(fragment))
    return results


def smt_check_formal_claim_premise_consistency(claim: FormalClaim) -> list[BackendResult]:
    """Check only the premise-consistency question with z3, one result per contributing premise.

    This is the exact question cvc5 answers in ``cvc5_check_formal_claim_premises`` — the joint
    satisfiability of a claim's comparison and set-literal-membership premises — and nothing else
    (no predicate/rejection_order fragments). Exposing it as a public function gives the
    cross-backend agreement registry a z3 backend that poses the *same* question as the cvc5 backend,
    so their verdicts are directly comparable. Returns an empty list when the claim poses no such
    question (no contributing premise).
    """
    return _premise_consistency(claim.premises)


def premises_jointly_satisfiable(premises: list[FormalClaimFragment]) -> bool | None:
    """Whether the conjunction of these premise fragments can hold together in one model.

    This is the cross-requirement *co-occurrence* decision (PA-7 conditional overlap): two
    requirements impose conflicting obligations only in a state where both their premises hold, so
    the obligation comparison is gated on the conjunction of both premise sets being satisfiable.
    Unlike :func:`_premise_consistency` (comparisons + set-literal membership only), this also
    encodes ``predicate`` premises, because the gate's soundness depends on it: opposite
    authorization premises (``approved`` vs ``not_approved``) must be UNSAT together — they are the
    two halves of a complete specification that never co-occur — or a disjoint pair would be flagged
    as co-occurring. All three premise kinds enter one Z3 model so a cross-premise contradiction is
    caught:

      - ``predicate`` encodes propositionally, with the ``not_`` prefix as boolean negation (same
        base name and arguments share one atom; ``approved(a)`` and ``not_approved(a)`` are an atom
        and its negation), mirroring :func:`nlreq.smt._atom_name`;
      - ``comparison`` encodes into shared linear real arithmetic (``x > 10`` AND ``x < 5`` is UNSAT);
      - set-literal ``membership`` encodes over a shared uninterpreted member sort with pairwise
        ``Distinct`` members (``x in {A}`` AND ``x in {B}`` is UNSAT).

    Returns:
      - ``True``  — every premise was encoded and the conjunction is SAT (the premises provably
        co-occur). An empty premise list is ``True`` (an unconditional antecedent always holds).
      - ``False`` — the encoded constraints alone are UNSAT, so the whole conjunction is UNSAT
        regardless of any premise that did not encode (the premises provably cannot co-occur).
      - ``None``  — the encoded constraints are SAT but at least one premise could not be encoded
        (an opaque named-set membership, or a non-arithmetic comparison): co-occurrence is
        undecidable here and the caller must fall back to a conservative gate rather than guess.

    Identifiers are shared by name across all premises, so the same scope-bound variable (``actor``,
    a numeric ``amount``) in two requirements is the same atom/variable — that is what makes a
    cross-requirement contradiction detectable at all.
    """
    solver = Solver()
    real_vars: dict[str, ArithRef] = {}
    bool_atoms: dict[tuple[str, tuple[str, ...]], BoolRef] = {}
    fully_encoded = True
    set_memberships: list[FormalClaimFragment] = []

    for fragment in premises:
        if fragment.kind == "predicate":
            solver.add(_encode_predicate(fragment, bool_atoms))
        elif fragment.kind == "comparison":
            constraint = _encode_comparison(fragment, real_vars)
            if constraint is None:
                # A non-arithmetic comparison (string operand) is not encodable; the conjunction
                # cannot be proven SAT without it, so co-occurrence stays undecidable.
                fully_encoded = False
                continue
            solver.add(constraint)
        elif fragment.kind == "membership" and is_set_literal_membership(fragment):
            # Encoded after the comparison loop so real_vars is populated: a set-literal membership
            # whose element is also a numeric operand cannot share a model and is left unencodable.
            set_memberships.append(fragment)
        else:
            # scope/action never appear as premises; an opaque named-set membership has no
            # enumerable contents, so the conjunction cannot be proven SAT here.
            fully_encoded = False

    if set_memberships:
        member_names = sorted(
            {str(operand.value) for fragment in set_memberships for operand in fragment.operands[1:]}
        )
        member_sort = DeclareSort("FormalClaimMember")
        const_by_name = {name: Const(name, member_sort) for name in member_names}
        if len(const_by_name) >= 2:
            solver.add(Distinct(list(const_by_name.values())))
        element_vars: dict[str, ExprRef] = {}
        for fragment in set_memberships:
            constraint = _encode_set_membership(
                fragment, member_sort, const_by_name, element_vars, real_vars
            )
            if constraint is None:
                fully_encoded = False
                continue
            solver.add(constraint)

    if solver.check() == unsat:
        return False
    return True if fully_encoded else None


def _encode_predicate(
    fragment: FormalClaimFragment, atoms: dict[tuple[str, tuple[str, ...]], BoolRef]
) -> BoolRef:
    """A boolean atom for an authorization/approval premise, negated for a ``not_`` predicate.

    The ``not_`` prefix is the DSL's negation convention (see :func:`nlreq.smt._atom_name`): a
    ``not_approved`` premise is the negation of the ``approved`` atom over the same arguments, so the
    two are UNSAT together. Premises sharing a base name and arguments share one atom, so the same
    condition stated in two requirements is the same variable and an opposite-premise pair is a
    catchable contradiction.
    """
    name = fragment.predicate or ""
    negated = name.startswith("not_")
    base = name[len("not_") :] if negated else name
    args = tuple(str(operand.value) for operand in fragment.operands)
    key = (base, args)
    if key not in atoms:
        atoms[key] = Bool("pred_" + "_".join([base, *args]))
    atom = atoms[key]
    return Not(atom) if negated else atom


def _premise_consistency(premises: list[FormalClaimFragment]) -> list[BackendResult]:
    """Discharge premise comparison and set-literal-membership fragments by one joint Z3 query.

    A lone symbolic premise proves nothing (``x > rhs`` and ``x in {A, B}`` are each trivially
    satisfiable), but the *conjunction* of the premises does: it is the requirement's antecedent.
    Checking that conjunction for satisfiability gives a real, non-vacuous SMT result:

      - comparison fragments encode into linear real arithmetic, sharing real variables across
        fragments so a cross-fragment numeric contradiction (``x > y`` AND ``y > x``) is caught;
      - set-literal membership fragments (``x is in {A, B}``) encode over a finite sort whose named
        members are asserted pairwise distinct, sharing an element variable across fragments so a
        disjoint-set contradiction (``x in {A}`` AND ``x in {B}``) is caught.

    SAT  -> every contributing premise is encodable and mutually consistent: status "valid",
            SMT_CHECKED. UNSAT -> the premises contradict one another, so the antecedent can never
            hold: status "invalid", SMT_CHECKED.

    One result is emitted per contributing fragment (each covering exactly its own fragment_id) so
    proof_closure can discharge or block each premise route individually while the verdict comes
    from the joint model. A fragment that cannot enter the joint encoding — a non-arithmetic
    comparison, or a membership whose element is also used as a numeric operand (an identifier
    cannot be both a real and a member value in one model) — is returned needs_review so its route
    stays open rather than being forced under a guessed sort.
    """
    comparisons = [fragment for fragment in premises if fragment.kind == "comparison"]
    set_memberships = [
        fragment
        for fragment in premises
        if fragment.kind == "membership" and is_set_literal_membership(fragment)
    ]
    if not comparisons and not set_memberships:
        return []

    solver = Solver()
    real_vars: dict[str, ArithRef] = {}
    encoded: list[FormalClaimFragment] = []
    unencodable: list[tuple[FormalClaimFragment, str]] = []
    constraint_texts: list[str] = []

    for fragment in comparisons:
        constraint = _encode_comparison(fragment, real_vars)
        if constraint is None:
            unencodable.append((fragment, _UNENCODABLE_COMPARISON_REASON))
            continue
        solver.add(constraint)
        encoded.append(fragment)
        constraint_texts.append(str(constraint))

    # All named members across every set-literal membership share one uninterpreted sort, each a
    # named constant of that sort. ``Distinct`` over the members makes them pairwise unequal — enum
    # semantics — which is what turns ``x in {A}`` AND ``x in {B}`` into an UNSAT antecedent (an
    # uninterpreted constant is not distinct from another by default, so the assertion is required).
    # The element of each membership is a separate constant of that sort. A fresh ``DeclareSort`` of
    # the same name is idempotent in Z3's context, so repeated queries do not re-declare a sort
    # (unlike ``EnumSort``, whose constructors collide on the second declaration).
    member_names = sorted(
        {str(operand.value) for fragment in set_memberships for operand in fragment.operands[1:]}
    )
    if member_names:
        member_sort = DeclareSort("FormalClaimMember")
        const_by_name = {name: Const(name, member_sort) for name in member_names}
        if len(const_by_name) >= 2:
            distinct = Distinct(list(const_by_name.values()))
            solver.add(distinct)
            constraint_texts.append(str(distinct))
        element_vars: dict[str, ExprRef] = {}
        for fragment in set_memberships:
            constraint = _encode_set_membership(
                fragment, member_sort, const_by_name, element_vars, real_vars
            )
            if constraint is None:
                unencodable.append((fragment, _UNENCODABLE_MEMBERSHIP_REASON))
                continue
            solver.add(constraint)
            encoded.append(fragment)
            constraint_texts.append(str(constraint))

    # The shared, solver-independent identity of this premise-consistency question (PB-6.T3). cvc5
    # computes the same key from the same claim, so the cross-backend agreement check can pair the
    # two verdicts. ``query_hash`` below is the z3-specific encoded form (the constraint strings) and
    # stays as metadata — the agreement compares the verdict, not the encoding.
    overlap_key = premise_consistency_overlap_key(premises)
    results: list[BackendResult] = []
    if encoded:
        outcome = solver.check()
        status = "valid" if outcome == sat else "invalid"
        logic = _query_logic(encoded)
        # Order-independent reproducibility key for the joint query the verdict came from.
        query_hash = sha256_text(f"{logic}\n" + "\n".join(sorted(constraint_texts)))
        participating = sorted(fragment.fragment_id for fragment in encoded)
        for fragment in encoded:
            results.append(
                BackendResult(
                    backend=SMT_THEORIES_BACKEND_ID,
                    status=status,
                    evidence_level=EvidenceLevel.SMT_CHECKED,
                    details={
                        "covered_fragment_ids": [fragment.fragment_id],
                        "check": "premise_consistency",
                        "tool_version": FORMAL_CLAIM_SMT_VERSION,
                        "smt_logic": logic,
                        "z3_result": str(outcome),
                        "premise_constraint_fragment_ids": participating,
                        "query_hash": query_hash,
                        "overlap_key": overlap_key,
                        # Tell the agreement check to judge this result on its verdict, not on
                        # encoder incidentals (logic label, bounds): the question is decidable.
                        "agreement_compare": "verdict",
                    },
                )
            )
    for fragment, reason in unencodable:
        results.append(
            BackendResult(
                backend=SMT_THEORIES_BACKEND_ID,
                status="needs_review",
                # No evidence level: an unencodable premise never entered the solver, so it was not
                # checked. None keeps the route open without claiming a consistency result (and
                # without tripping the SMT_CHECKED-only producer mapping) — see _UNCHECKED_EVIDENCE.
                evidence_level=_UNCHECKED_EVIDENCE,
                details={
                    "covered_fragment_ids": [fragment.fragment_id],
                    "check": "premise_consistency:unencodable",
                    "tool_version": FORMAL_CLAIM_SMT_VERSION,
                    "reason": reason,
                },
            )
        )
    return results


_UNENCODABLE_COMPARISON_REASON = (
    "comparison operand is not encodable into linear arithmetic "
    "(a string operand or fewer than two operands); route stays open"
)
_UNENCODABLE_MEMBERSHIP_REASON = (
    "set-literal membership element is also used as a numeric operand in this claim; an identifier "
    "cannot be both a real and a member value in one model, so the route stays open"
)


def _encode_set_membership(
    fragment: FormalClaimFragment,
    member_sort: SortRef,
    const_by_name: dict[str, ExprRef],
    element_vars: dict[str, ExprRef],
    real_vars: dict[str, ArithRef],
) -> ExprRef | None:
    """A Z3 constraint ``element in {members}`` for a set-literal membership, or None.

    ``x in {A, B}`` becomes ``x == A \\/ x == B`` over the uninterpreted member sort whose named
    members the caller has asserted pairwise distinct, so a disjoint-set contradiction is caught.
    Returns None when any identifier in the fragment — the element or a named member — is already a
    real variable in this query (used as a numeric comparison operand): an identifier cannot be both
    a real and a member value in one model, and encoding it as both would silently treat the two
    occurrences as unrelated, so the caller leaves the route open rather than force a guessed sort.
    """
    operand_names = [str(operand.value) for operand in fragment.operands]
    if any(name in real_vars for name in operand_names):
        return None
    element_name = operand_names[0]
    member_consts = [const_by_name[name] for name in operand_names[1:]]
    if not member_consts:
        return None
    if element_name not in element_vars:
        element_vars[element_name] = Const(f"element_{element_name}", member_sort)
    element = element_vars[element_name]
    if len(member_consts) == 1:
        return element == member_consts[0]
    return Or([element == member for member in member_consts])


def _query_logic(encoded: list[FormalClaimFragment]) -> str:
    """The honest SMT logic label for a joint query, by the fragment kinds it actually encoded.

    Comparisons are linear real arithmetic (``QF_LRA``); set-literal membership adds an
    uninterpreted member sort with equality and ``Distinct`` (``UF``). The label is reproducibility
    metadata only — the solver runs unconstrained — so it must report what was encoded rather than a
    fixed constant.
    """
    has_comparison = any(fragment.kind == "comparison" for fragment in encoded)
    has_membership = any(fragment.kind == "membership" for fragment in encoded)
    if has_comparison and has_membership:
        return "QF_UFLRA"
    if has_membership:
        return "QF_UF"
    return _SMT_LOGIC


def _encode_comparison(
    fragment: FormalClaimFragment, variables: dict[str, ArithRef]
) -> BoolRef | None:
    """A Z3 linear-arithmetic constraint for a comparison fragment, or None if not encodable.

    Numbers map to real literals and identifiers to shared real variables, so the same identifier
    in two fragments is the same variable and a cross-fragment contradiction is caught. A string
    operand, an unknown operator, or fewer than two operands makes the comparison non-arithmetic
    (returns None), and the caller keeps that route open rather than forcing it into the reals.
    """
    if fragment.operator not in _COMPARISON_OPS or len(fragment.operands) < 2:
        return None
    lhs = _encode_operand(fragment.operands[0], variables)
    rhs = _encode_operand(fragment.operands[1], variables)
    if lhs is None or rhs is None:
        return None
    operator = fragment.operator
    if operator == "eq":
        return lhs == rhs
    if operator == "neq":
        return lhs != rhs
    if operator == "lt":
        return lhs < rhs
    if operator == "lte":
        return lhs <= rhs
    if operator == "gt":
        return lhs > rhs
    return lhs >= rhs  # gte


def _encode_operand(
    operand: FormalClaimOperand, variables: dict[str, ArithRef]
) -> ArithRef | None:
    """An exact Z3 real for a number operand, a shared real variable for an identifier, else None.

    Number literals are encoded at full precision via :func:`exact_fraction` (never through
    ``float()``, which rounds integers past 2**53 and would mask a ground-false comparison such as
    ``9007199254740992 = 9007199254740993``); a non-finite literal (``inf`` / ``nan``) is not linear
    arithmetic and returns None. String operands (kind ``string``) return None and make the whole
    comparison unencodable — encoding them as reals would invent an ordering the requirement never
    stated.
    """
    if operand.kind == "number":
        fraction = exact_fraction(operand.value)
        if fraction is None:
            return None
        # An exact rational as Z3's "numerator/denominator" numeral — the literal enters the solver
        # at the precision it was written, so equality and ordering are decided exactly.
        return RealVal(f"{fraction.numerator}/{fraction.denominator}")
    if operand.kind == "identifier":
        name = str(operand.value)
        if name not in variables:
            variables[name] = Real(f"v_{name}")
        return variables[name]
    return None


def _check_fragment(fragment: FormalClaimFragment) -> BackendResult:
    if fragment.kind == "predicate":
        # Named uninterpreted predicates require Apalache/Pillar B model-level checking.
        # Returning "unsupported" causes proof_closure to set the premise status to
        # "blocked" with an explicit reason rather than leaving it silently "open".
        # evidence_level=None so _producer_blockers skips this result and emits no spurious
        # producer-mapping blocker (smt-theories is only registered for SMT_CHECKED).
        span_text = fragment.source_spans[0].text if fragment.source_spans else fragment.canonical
        return BackendResult(
            backend=SMT_THEORIES_BACKEND_ID,
            status="unsupported",
            evidence_level=_UNCHECKED_EVIDENCE,
            details={
                "covered_fragment_ids": [fragment.fragment_id],
                "check": "fragment_satisfiability:predicate",
                "tool_version": FORMAL_CLAIM_SMT_VERSION,
                "reason": (
                    f"uninterpreted predicate '{span_text}' has no fragment-level SMT content "
                    "(a free boolean is trivially SAT); checkable only at the requirement level "
                    "via S∧R composition in system_checker — not a fragment-level Z3 query"
                ),
            },
        )
    if fragment.kind == "rejection_order":
        # Bounded-reachability ordering requires a model checker (Apalache).
        # Return with backend="apalache" to match the routed_backend so proof_closure can
        # find this result and set the premise to "blocked" (not silently "open").
        span_text = fragment.source_spans[0].text if fragment.source_spans else fragment.canonical
        return BackendResult(
            backend="apalache",
            status="unsupported",
            evidence_level=_UNCHECKED_EVIDENCE,
            details={
                "covered_fragment_ids": [fragment.fragment_id],
                "check": "fragment_satisfiability:rejection_order",
                "tool_version": FORMAL_CLAIM_SMT_VERSION,
                "reason": f"rejection_order '{span_text}' bounded-reachability requires Apalache binary; not available",
            },
        )
    # membership (opaque named set, e.g. `x is in S`) — its set is a single opaque identifier with
    # no enumerable contents, so a fragment-level query is vacuous (a set-literal membership with
    # concrete members is enumerated by _premise_consistency and never reaches here). needs_review
    # keeps the route open rather than discharging it falsely; no evidence level, because nothing was
    # checked (an opaque set cannot be encoded here) — see _UNCHECKED_EVIDENCE.
    return BackendResult(
        backend=SMT_THEORIES_BACKEND_ID,
        status="needs_review",
        evidence_level=_UNCHECKED_EVIDENCE,
        details={
            "covered_fragment_ids": [fragment.fragment_id],
            "check": f"fragment_satisfiability:{fragment.kind}",
            "tool_version": FORMAL_CLAIM_SMT_VERSION,
        },
    )
