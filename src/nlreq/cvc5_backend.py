"""Independent cvc5 projection of the FormalClaim premise-consistency question (PB-6.T2).

This is the second formal backend behind the same question ``formal_claim_smt`` answers with the
in-process z3 API: *is the conjunction of a claim's comparison and set-literal-membership premises
satisfiable?* (i.e. is the requirement's antecedent realizable, or does it contradict itself?).

The point of a *second* backend is a non-vacuous cross-backend agreement check (PB-6.T3): two
complete solvers always agree on identical formulas over a decidable theory, so the value is not
catching solver bugs — it is catching *encoder* divergence. That only works if the two encoders are
genuinely independent and share nothing but the ``FormalClaim`` as source of truth. So this module
encodes from the claim directly, and deliberately differs from the z3 path where it can:

  - comparisons lower into linear real arithmetic, sharing one real variable per identifier so a
    cross-fragment numeric contradiction (``x > y`` AND ``y > x``) is caught — same theory as z3
    (there is only one honest way to put ``x > 5`` into the reals);
  - set-literal memberships (``x is in {A, B}``) lower through cvc5's NATIVE finite-set theory
    (``set.member`` / ``set.insert`` / ``set.singleton`` over an uninterpreted member sort whose
    named members are asserted pairwise ``distinct``) — NOT the z3 path's
    ``DeclareSort`` + ``Distinct`` + disjunction-of-equalities. The membership encoding is where the
    independence has teeth: a bug translating ``x ∈ {A, B}`` to one form does not replicate to the
    other, so a planted divergence shows up as opposite verdicts.

Verdict contract mirrors ``formal_claim_smt._premise_consistency`` so the two backends are directly
comparable on the same question: SAT → ``valid`` (premises mutually consistent), UNSAT → ``invalid``
(premises contradict), both at ``SMT_CHECKED``; one result per contributing fragment, each covering
exactly its own ``fragment_id``. A fragment that cannot enter the joint encoding (a non-arithmetic
comparison, or a membership whose element/member is also a numeric operand — an identifier cannot be
both a real and a member value in one model) is returned ``needs_review`` so its route stays open
rather than being forced under a guessed sort.

Honest degradation: cvc5 is an OPTIONAL dependency (run tests with ``uv run --with cvc5``; install
the ``cvc5`` extra to enable it in a checkout). When cvc5 is not importable, the check emits
``unsupported`` results carrying no evidence level — never an ``SMT_CHECKED`` claim without a real
cvc5 run.
"""

from __future__ import annotations

from .formal_claim import FormalClaim, FormalClaimFragment, FormalClaimOperand
from .jsonutil import sha256_text
from .models import BackendResult, EvidenceLevel
from .numeric_literal import exact_fraction

try:  # cvc5 is an optional dependency — see module docstring.
    import cvc5
    from cvc5 import Kind

    _CVC5_IMPORT_ERROR: str | None = None
except Exception as exc:  # pragma: no cover - exercised only in cvc5-absent environments
    cvc5 = None  # type: ignore[assignment]
    Kind = None  # type: ignore[assignment]
    _CVC5_IMPORT_ERROR = repr(exc)


# Stable backend identifier — the producer id registered in proof_closure and the BackendResult.backend
# every result carries, so proof closure can route to and match cvc5 results distinctly from core_smt.
CVC5_BACKEND_ID = "cvc5"
CVC5_BACKEND_VERSION = "0.1"

# The comparison operators the linear-arithmetic encoder understands; membership "in" is handled
# separately through the finite-set theory, not here (it has no arithmetic meaning).
_COMPARISON_OPS = frozenset({"eq", "neq", "lt", "lte", "gt", "gte"})

_UNENCODABLE_COMPARISON_REASON = (
    "comparison operand is not encodable into linear arithmetic "
    "(a string operand or fewer than two operands); route stays open"
)
_UNENCODABLE_MEMBERSHIP_REASON = (
    "set-literal membership element or member is also used as a numeric operand in this claim; an "
    "identifier cannot be both a real and a member value in one model, so the route stays open"
)
_CVC5_ABSENT_REASON = (
    "cvc5 is not installed in this environment; install the optional 'cvc5' dependency "
    "(or run under `uv run --with cvc5`) to enable the second formal backend"
)
_CVC5_UNKNOWN_REASON = (
    "cvc5 returned 'unknown' for the joint premise query — not a decided sat/unsat verdict, so the "
    "route stays open rather than claiming a checked result"
)


def cvc5_available() -> bool:
    """Whether the cvc5 solver is importable in this environment."""
    return cvc5 is not None


def cvc5_tool_version() -> str | None:
    """The installed cvc5 version recorded with every run, or None when cvc5 is absent."""
    if cvc5 is None:
        return None
    return getattr(cvc5, "__version__", None)


def cvc5_check_formal_claim_premises(claim: FormalClaim) -> list[BackendResult]:
    """Check a claim's premise-consistency question with cvc5, returning one result per premise.

    Contributing premises are comparison fragments and set-literal-membership fragments (the same
    fragments ``formal_claim_smt._premise_consistency`` contributes). The joint satisfiability of
    their conjunction is the verdict; each contributing fragment gets its own result so proof
    closure can discharge or block its route individually. Returns an empty list when the claim has
    no contributing premise (there is no question to ask), and ``unsupported`` results — never a
    checked verdict — when cvc5 is unavailable.
    """
    comparisons = [fragment for fragment in claim.premises if fragment.kind == "comparison"]
    set_memberships = [
        fragment
        for fragment in claim.premises
        if fragment.kind == "membership" and _is_set_literal_membership(fragment)
    ]
    contributing = [*comparisons, *set_memberships]
    if not contributing:
        return []
    if not cvc5_available():
        return [_absent_result(fragment) for fragment in contributing]
    return _check_with_cvc5(comparisons, set_memberships)


def _check_with_cvc5(
    comparisons: list[FormalClaimFragment],
    set_memberships: list[FormalClaimFragment],
) -> list[BackendResult]:
    solver = cvc5.Solver()
    # ALL admits linear real arithmetic, uninterpreted sorts, and the finite-set theory together —
    # the three this encoder uses. The honest per-result label records what was actually encoded.
    solver.setLogic("ALL")
    real_sort = solver.getRealSort()

    real_vars: dict[str, object] = {}
    encoded: list[FormalClaimFragment] = []
    unencodable: list[tuple[FormalClaimFragment, str]] = []

    for fragment in comparisons:
        term = _encode_comparison(solver, fragment, real_sort, real_vars)
        if term is None:
            unencodable.append((fragment, _UNENCODABLE_COMPARISON_REASON))
            continue
        solver.assertFormula(term)
        encoded.append(fragment)

    # All named members across every set-literal membership share one uninterpreted sort and are
    # asserted pairwise distinct — that distinctness is what turns `x in {A}` AND `x in {B}` into an
    # UNSAT antecedent (uninterpreted constants are not unequal by default). Comparisons are encoded
    # first so the membership encoder can see, via `real_vars`, any identifier already bound to a
    # real and refuse the sort clash rather than silently model the two occurrences as unrelated.
    member_names = sorted(
        {str(operand.value) for fragment in set_memberships for operand in fragment.operands[1:]}
    )
    if member_names:
        member_sort = solver.mkUninterpretedSort("FormalClaimMember")
        member_const = {name: solver.mkConst(member_sort, name) for name in member_names}
        if len(member_const) >= 2:
            solver.assertFormula(solver.mkTerm(Kind.DISTINCT, *member_const.values()))
        element_consts: dict[str, object] = {}
        for fragment in set_memberships:
            term = _encode_set_membership(
                solver, fragment, member_sort, member_const, element_consts, real_vars
            )
            if term is None:
                unencodable.append((fragment, _UNENCODABLE_MEMBERSHIP_REASON))
                continue
            solver.assertFormula(term)
            encoded.append(fragment)

    results: list[BackendResult] = []
    if encoded:
        outcome = solver.checkSat()
        if outcome.isUnknown():
            # cvc5 could not decide the query — never report a sat/unsat verdict it did not produce.
            results.extend(_unknown_result(fragment) for fragment in encoded)
        else:
            status = "valid" if outcome.isSat() else "invalid"
            logic = _encoded_logic(encoded)
            participating = sorted(fragment.fragment_id for fragment in encoded)
            question_hash = _question_hash(encoded, logic)
            cvc5_result = str(outcome)
            results.extend(
                _checked_result(fragment, status, logic, cvc5_result, participating, question_hash)
                for fragment in encoded
            )
    results.extend(_unencodable_result(fragment, reason) for fragment, reason in unencodable)
    return results


def _is_set_literal_membership(fragment: FormalClaimFragment) -> bool:
    """Whether a membership fragment enumerates concrete members (``x is in {A, B}``).

    Mirrors the ``metadata['membership'] == 'set_literal'`` marker set at lowering (dsl_v3 →
    formal_claim) and shared by the z3 path: a set-literal membership carries its members as concrete
    operands after the element, while an opaque named-set membership (``x is in S``) lacks the marker
    and has no enumerable contents to encode.
    """
    return fragment.metadata.get("membership") == "set_literal" and len(fragment.operands) >= 2


def _encode_comparison(
    solver: object,
    fragment: FormalClaimFragment,
    real_sort: object,
    real_vars: dict[str, object],
) -> object | None:
    """A cvc5 linear-arithmetic term for a comparison fragment, or None if not encodable.

    Numbers map to exact rational literals and identifiers to shared real constants, so the same
    identifier across two fragments is the same constant and a cross-fragment contradiction is
    caught. A string operand, an unknown operator, or fewer than two operands makes the comparison
    non-arithmetic (returns None), and the caller keeps that route open.
    """
    if fragment.operator not in _COMPARISON_OPS or len(fragment.operands) < 2:
        return None
    lhs = _encode_operand(solver, fragment.operands[0], real_sort, real_vars)
    rhs = _encode_operand(solver, fragment.operands[1], real_sort, real_vars)
    if lhs is None or rhs is None:
        return None
    kind = {
        "eq": Kind.EQUAL,
        "neq": Kind.DISTINCT,
        "lt": Kind.LT,
        "lte": Kind.LEQ,
        "gt": Kind.GT,
        "gte": Kind.GEQ,
    }[fragment.operator]
    return solver.mkTerm(kind, lhs, rhs)


def _encode_operand(
    solver: object,
    operand: FormalClaimOperand,
    real_sort: object,
    real_vars: dict[str, object],
) -> object | None:
    """An exact cvc5 rational for a number, a shared real constant for an identifier, else None.

    Number literals are encoded at full precision through :func:`exact_fraction` (never ``float()``,
    which rounds integers past 2**53 and would mask a ground-false comparison such as
    ``9007199254740992 = 9007199254740993``) as a cvc5 ``num/den`` rational. A non-finite literal
    (``inf`` / ``nan``) is not linear arithmetic and returns None. String operands return None and
    make the whole comparison unencodable — ordering them as reals would invent an ordering the
    requirement never stated.
    """
    if operand.kind == "number":
        fraction = exact_fraction(operand.value)
        if fraction is None:
            return None
        return solver.mkReal(f"{fraction.numerator}/{fraction.denominator}")
    if operand.kind == "identifier":
        name = str(operand.value)
        if name not in real_vars:
            real_vars[name] = solver.mkConst(real_sort, f"v_{name}")
        return real_vars[name]
    return None


def _encode_set_membership(
    solver: object,
    fragment: FormalClaimFragment,
    member_sort: object,
    member_const: dict[str, object],
    element_consts: dict[str, object],
    real_vars: dict[str, object],
) -> object | None:
    """A cvc5 ``set.member(element, {members})`` term over the finite-set theory, or None.

    ``x in {A, B}`` becomes ``set.member(x, set.insert(A, set.singleton(B)))`` over the uninterpreted
    member sort whose named members the caller has asserted pairwise distinct — so a disjoint-set
    contradiction is caught. Returns None when any identifier in the fragment is already a real
    variable in this query (used as a numeric comparison operand): an identifier cannot be both a
    real and a member value in one model, so the caller leaves the route open rather than force a
    guessed sort.
    """
    operand_names = [str(operand.value) for operand in fragment.operands]
    if any(name in real_vars for name in operand_names):
        return None
    element_name = operand_names[0]
    member_terms = [member_const[name] for name in operand_names[1:]]
    if not member_terms:
        return None
    if element_name not in element_consts:
        element_consts[element_name] = solver.mkConst(member_sort, f"element_{element_name}")
    element = element_consts[element_name]
    return solver.mkTerm(Kind.SET_MEMBER, element, _set_literal(solver, member_terms))


def _set_literal(solver: object, member_terms: list[object]) -> object:
    """Build the finite set ``{m0, ..., mN}`` from member terms via chained single-element inserts.

    Starts from ``set.singleton(mN)`` and inserts each remaining member one at a time. Single-element
    insert is the primitive verified against cvc5; chaining it avoids depending on a variadic
    ``set.insert`` arity.
    """
    result = solver.mkTerm(Kind.SET_SINGLETON, member_terms[-1])
    for term in reversed(member_terms[:-1]):
        result = solver.mkTerm(Kind.SET_INSERT, term, result)
    return result


def _encoded_logic(encoded: list[FormalClaimFragment]) -> str:
    """A label for what this query actually encoded — comparisons (LRA), memberships (finite sets).

    cvc5 runs under ``ALL``; this label is reproducibility metadata describing the encoded fragment
    kinds, not the solver's configured logic. It deliberately may differ from the z3 path's label
    for the same question (z3 encodes membership in pure UF, cvc5 in the finite-set theory) — the
    cross-backend agreement check (PB-6.T3) compares verdicts, treating such labels as metadata.
    """
    has_comparison = any(fragment.kind == "comparison" for fragment in encoded)
    has_membership = any(fragment.kind == "membership" for fragment in encoded)
    if has_comparison and has_membership:
        return "FS_LRA"
    if has_membership:
        return "FS"
    return "LRA"


def _fragment_signature(fragment: FormalClaimFragment) -> str:
    """A backend-independent signature of a fragment's encoded meaning (kind, operator, operands).

    Derived from the ``FormalClaim`` rather than any cvc5 term, so it is the same identity the z3
    path could compute for the same fragment — the natural key for pairing the two backends'
    verdicts on one shared question in the agreement check.
    """
    operands = ",".join(f"{operand.kind}:{operand.value}" for operand in fragment.operands)
    return f"{fragment.kind}|{fragment.operator}|{operands}"


def _question_hash(encoded: list[FormalClaimFragment], logic: str) -> str:
    signatures = sorted(_fragment_signature(fragment) for fragment in encoded)
    return sha256_text(f"{logic}\n" + "\n".join(signatures))


def _checked_result(
    fragment: FormalClaimFragment,
    status: str,
    logic: str,
    cvc5_result: str,
    participating: list[str],
    question_hash: str,
) -> BackendResult:
    return BackendResult(
        backend=CVC5_BACKEND_ID,
        status=status,
        evidence_level=EvidenceLevel.SMT_CHECKED,
        details={
            "covered_fragment_ids": [fragment.fragment_id],
            "check": "premise_consistency",
            "tool": "cvc5",
            "tool_version": cvc5_tool_version(),
            "encoded_logic": logic,
            "cvc5_result": cvc5_result,
            "premise_constraint_fragment_ids": participating,
            "question_hash": question_hash,
        },
    )


def _unencodable_result(fragment: FormalClaimFragment, reason: str) -> BackendResult:
    return BackendResult(
        backend=CVC5_BACKEND_ID,
        status="needs_review",
        evidence_level=EvidenceLevel.CONSISTENCY_CHECKED,
        details={
            "covered_fragment_ids": [fragment.fragment_id],
            "check": "premise_consistency:unencodable",
            "tool": "cvc5",
            "tool_version": cvc5_tool_version(),
            "reason": reason,
        },
    )


def _unknown_result(fragment: FormalClaimFragment) -> BackendResult:
    return BackendResult(
        backend=CVC5_BACKEND_ID,
        status="needs_review",
        evidence_level=EvidenceLevel.CONSISTENCY_CHECKED,
        details={
            "covered_fragment_ids": [fragment.fragment_id],
            "check": "premise_consistency:unknown",
            "tool": "cvc5",
            "tool_version": cvc5_tool_version(),
            "reason": _CVC5_UNKNOWN_REASON,
        },
    )


def _absent_result(fragment: FormalClaimFragment) -> BackendResult:
    """An honest 'cvc5 not available' result: unsupported, no evidence level.

    Carries ``covered_fragment_ids`` so proof closure still routes it (the premise stays open under
    an explicit reason rather than silently vanishing), and ``evidence_level=None`` so it can never
    be read as a checked SMT result.
    """
    reason = _CVC5_ABSENT_REASON
    if _CVC5_IMPORT_ERROR is not None:
        reason = f"{reason} (import error: {_CVC5_IMPORT_ERROR})"
    return BackendResult(
        backend=CVC5_BACKEND_ID,
        status="unsupported",
        evidence_level=None,
        details={
            "covered_fragment_ids": [fragment.fragment_id],
            "check": "premise_consistency:cvc5_unavailable",
            "tool": "cvc5",
            "tool_version": None,
            "reason": reason,
        },
    )
