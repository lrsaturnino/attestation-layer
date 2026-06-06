"""Cross-requirement contradiction detection over typed ``FormalClaim`` fragments.

The single-requirement checker (:mod:`nlreq.requirement_self_consistency`) decides one requirement
against itself: everything inside one ``and`` conjunction co-occurs by construction, so opposite or
disjoint fragments there are genuine contradictions. This module decides a *set* of requirements
against each other, where co-occurrence is no longer free — two requirements only contradict in a
state their premises can both reach.

So the unit of comparison here is the *obligation*, not the premise. Two rules with opposite
premises (``actor is authorized`` vs ``actor is not authorized``) are the two halves of a complete,
consistent specification, not a contradiction: they never both fire. A real cross-requirement
contradiction is two obligations that must both hold — premises provably co-occurring on a shared
scope — yet cannot. The checker is deliberately conservative: a false positive blocks a satisfiable
set, which is worse than a miss a formal backend can still catch downstream, so when co-occurrence
cannot be proven the pair is left unflagged.

Detection runs over the typed fragments of :func:`nlreq.formal_claim.build_formal_claim` and reports
only the minimal conflicting core (the two binding fragments) with their source spans.
"""

from __future__ import annotations

from fractions import Fraction
from typing import TYPE_CHECKING, Literal, NamedTuple

from pydantic import BaseModel, ConfigDict, Field

from .models import SourceSpan
from .numeric_literal import exact_fraction, numeric_bounds_conflict

if TYPE_CHECKING:
    # Annotation-only: FormalClaim's module transitively imports system_checker, which imports this
    # module. The fragments are read by attribute access, never constructed here, so the type is
    # needed only for static checking — importing it at runtime would close an import cycle.
    from .formal_claim import FormalClaim, FormalClaimFragment


CROSS_REQUIREMENT_CONSISTENCY_SCHEMA_VERSION = "0.1"
CROSS_REQUIREMENT_TAXONOMY_VERSION = "pa7-0.1"


# The classes the deterministic set checker can decide soundly over typed FormalClaim fragments.
# A reported finding is always one of these; the broader catalogue (including the classes that the
# v3 grammar cannot express, see :func:`build_cross_requirement_contradiction_taxonomy`) is
# documentation, not an emit surface.
CrossRequirementContradictionType = Literal[
    "numeric_range_disjointness",
    "mutual_exclusion",
    "action_order_conflict",
]


class RequirementContradiction(BaseModel):
    model_config = ConfigDict(extra="forbid")

    contradiction_type: CrossRequirementContradictionType
    requirement_ids: list[str]
    # The canonical form of each of the two conflicting fragments, in the same order as the
    # requirement_ids / source_spans they came from.
    fragments: list[str]
    # Always the spans of the two binding fragments, so a contradiction is never reported without
    # being tied back to the offending source text (no bare "the set is inconsistent"). Required and
    # non-empty: a candidate whose fragments carry no span is dropped rather than reported spanless.
    source_spans: list[SourceSpan] = Field(min_length=1)


class CrossRequirementContradictionClass(BaseModel):
    model_config = ConfigDict(extra="forbid")

    contradiction_type: str
    description: str
    # True when the deterministic set checker emits this class; False when it is catalogued but not
    # decided here (either the v3 grammar cannot express the conflict, or it is the co-occurrence
    # gate rather than a standalone finding). ``reason`` records which, so "not detected" is never
    # silent acceptance of a real contradiction.
    detected: bool
    reason: str


class CrossRequirementContradictionTaxonomy(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["0.1"] = CROSS_REQUIREMENT_CONSISTENCY_SCHEMA_VERSION
    taxonomy_version: Literal["pa7-0.1"] = CROSS_REQUIREMENT_TAXONOMY_VERSION
    classes: list[CrossRequirementContradictionClass]


def build_cross_requirement_contradiction_taxonomy() -> CrossRequirementContradictionTaxonomy:
    """The seven contradiction classes the set checker reasons about, and how each is handled.

    Three are decided deterministically over obligation fragments (numeric-range disjointness,
    mutual exclusion, action/order conflict). The remaining four are catalogued with the reason they
    are not emitted as standalone findings: ``conditional_overlap`` is the co-occurrence gate the
    other three are checked under; ``negation``, ``quantifier_scope_conflict`` and
    ``temporal_conflict`` describe conflicts the v3 grammar cannot express across requirements, so
    there is no real contradiction for the set checker to miss.
    """
    return CrossRequirementContradictionTaxonomy(
        classes=[
            CrossRequirementContradictionClass(
                contradiction_type="negation",
                description="A requirement obligation and its direct logical negation are both required.",
                detected=False,
                reason=(
                    "The v3 obligation grammar has no negatable boolean obligation, so direct "
                    "negation between two requirements' obligations is not separately expressible. "
                    "Opposite premises (authorized vs not_authorized) are mutually exclusive "
                    "conditions that never co-occur and so are not contradictions; a boolean-valued "
                    "obligation conflict surfaces as mutual_exclusion."
                ),
            ),
            CrossRequirementContradictionClass(
                contradiction_type="mutual_exclusion",
                description="Two requirements force the same post-state variable to incompatible values.",
                detected=True,
                reason=(
                    "Decided over post_state obligation fragments that pin the same variable to "
                    "different values on a shared scope with co-occurring premises."
                ),
            ),
            CrossRequirementContradictionClass(
                contradiction_type="conditional_overlap",
                description="Requirements with overlapping conditions impose conflicting obligations.",
                detected=False,
                reason=(
                    "Conditional overlap is the co-occurrence gate every other class is checked "
                    "under, not a standalone finding: obligations are only compared when the two "
                    "requirements' premises provably co-occur (identical, or both unconditional) on "
                    "a shared scope. Requirements whose premises cannot co-occur are reported "
                    "consistent rather than flagged."
                ),
            ),
            CrossRequirementContradictionClass(
                contradiction_type="quantifier_scope_conflict",
                description="Conflicting requirements quantified over incompatible scopes.",
                detected=False,
                reason=(
                    "The v3 scope grammar binds a single flat scope name with no nesting or "
                    "subsumption, so there is no quantifier alternation to conflict. Obligations on "
                    "different scopes address different state and are reported consistent."
                ),
            ),
            CrossRequirementContradictionClass(
                contradiction_type="numeric_range_disjointness",
                description="Two requirements bound the same value to an empty numeric interval.",
                detected=True,
                reason=(
                    "Decided over state_invariant obligation bounds on a shared scope with "
                    "co-occurring premises; only the binding lower/upper pair is reported."
                ),
            ),
            CrossRequirementContradictionClass(
                contradiction_type="temporal_conflict",
                description="Two requirements impose incompatible temporal bounds on the same response.",
                detected=False,
                reason=(
                    "The v3 temporal grammar ('within N') expresses only an upper bound, so two "
                    "temporal obligations can always both hold (the tighter bound wins) and never "
                    "conflict across requirements. A non-positive bound is a single-requirement "
                    "temporal_impossibility, not a set-level conflict."
                ),
            ),
            CrossRequirementContradictionClass(
                contradiction_type="action_order_conflict",
                description="Two requirements require the same action to both succeed and be rejected.",
                detected=True,
                reason=(
                    "Decided over success vs rejection_order obligation fragments naming the same "
                    "action on a shared scope with co-occurring premises."
                ),
            ),
        ]
    )


def detect_cross_requirement_contradictions(
    claims: list[FormalClaim],
) -> list[RequirementContradiction]:
    """Every deterministic cross-requirement contradiction across a set of lowered claims.

    Each unordered pair is checked once. The pair is compared only when its premises provably
    co-occur on a shared scope (:func:`_premises_co_occur`); when the gate is open the three sound
    obligation-level detectors run. Findings carry only the two binding fragments and their spans.
    """
    contradictions: list[RequirementContradiction] = []
    for first in range(len(claims)):
        for second in range(first + 1, len(claims)):
            left, right = claims[first], claims[second]
            if not _premises_co_occur(left, right):
                continue
            contradictions.extend(_numeric_range_disjointness(left, right))
            contradictions.extend(_mutual_exclusion(left, right))
            contradictions.extend(_action_order_conflict(left, right))
    return contradictions


def _premises_co_occur(left: FormalClaim, right: FormalClaim) -> bool:
    """True when both requirements provably apply in the same reachable state.

    Conservative on purpose. Co-occurrence is provable exactly when the two claims share a scope and
    impose the same condition: equal premise signatures, which includes the both-unconditional case
    (two empty premise sets). When the premises differ we cannot prove they ever hold together —
    disjoint conditions never both fire — so the pair is declined rather than risk a false positive
    on a satisfiable set. (A genuinely co-occurring but non-identical premise pair, e.g. one
    unconditional and one conditional, is a deliberate miss left to the formal backend.)
    """
    if _scope_signature(left) != _scope_signature(right):
        return False
    return _premise_signature(left) == _premise_signature(right)


def _scope_signature(claim: FormalClaim) -> tuple[str, ...]:
    return tuple(sorted(fragment.canonical for fragment in claim.scope))


def _premise_signature(claim: FormalClaim) -> tuple[str, ...]:
    return tuple(sorted(fragment.canonical for fragment in claim.premises))


class _Bound(NamedTuple):
    fragment: FormalClaimFragment
    value: Fraction
    inclusive: bool


def _numeric_range_disjointness(
    left: FormalClaim, right: FormalClaim
) -> list[RequirementContradiction]:
    """Flag a variable whose obligation bounds across the two requirements bound an empty interval.

    Only cross-requirement conflicts are reported (a lower bound in one requirement above an upper
    bound in the other on the same variable); a lower-vs-upper conflict contained within a single
    requirement is that requirement's own self-consistency concern. The report names only the
    binding pair — the strongest lower and strongest upper — so a third, compatible bound on the
    same variable is never blamed.
    """
    left_bounds = _invariant_bounds_by_variable(left)
    right_bounds = _invariant_bounds_by_variable(right)
    findings: list[RequirementContradiction] = []
    for variable in sorted(set(left_bounds) & set(right_bounds)):
        for lower_claim, lowers, upper_claim, uppers in (
            (left, left_bounds[variable][0], right, right_bounds[variable][1]),
            (right, right_bounds[variable][0], left, left_bounds[variable][1]),
        ):
            conflict = _binding_conflict(lowers, uppers)
            if conflict is None:
                continue
            lower_fragment, upper_fragment = conflict
            finding = _pair_finding(
                "numeric_range_disjointness",
                lower_claim,
                lower_fragment,
                upper_claim,
                upper_fragment,
            )
            if finding is not None:
                findings.append(finding)
    return findings


def _invariant_bounds_by_variable(
    claim: FormalClaim,
) -> dict[str, tuple[list[_Bound], list[_Bound]]]:
    """Lower and upper numeric bounds per variable from this claim's ``state_invariant`` obligations.

    Only the canonical ``keep <identifier> <comparison> <number>`` shape contributes a bound;
    ``gt``/``gte`` are lower bounds, ``lt``/``lte`` upper bounds, with ``gte``/``lte`` inclusive. A
    non-numeric or undecidable literal yields no bound and is left out rather than guessed. Values
    are read at exact rational precision so a large-integer conflict is not lost to float rounding.
    """
    bounds: dict[str, tuple[list[_Bound], list[_Bound]]] = {}
    for fragment in claim.obligations:
        if fragment.kind != "state_invariant" or fragment.operator not in {"lt", "lte", "gt", "gte"}:
            continue
        if len(fragment.operands) < 2 or fragment.operands[0].kind != "identifier":
            continue
        value = exact_fraction(fragment.operands[1].value)
        if value is None:
            continue
        variable = str(fragment.operands[0].value)
        lowers, uppers = bounds.setdefault(variable, ([], []))
        bound = _Bound(fragment=fragment, value=value, inclusive=fragment.operator in {"gte", "lte"})
        if fragment.operator in {"gt", "gte"}:
            lowers.append(bound)
        else:
            uppers.append(bound)
    return bounds


def _binding_conflict(
    lowers: list[_Bound], uppers: list[_Bound]
) -> tuple[FormalClaimFragment, FormalClaimFragment] | None:
    """The strongest lower and strongest upper bound, if together they bound an empty interval.

    The binding constraints are the largest lower (an exclusive ``>`` winning a tie over ``>=``) and
    the smallest upper (an exclusive ``<`` winning a tie). Emptiness is decided exactly by
    :func:`numeric_bounds_conflict`. Returning just this pair keeps the reported core minimal.
    """
    if not lowers or not uppers:
        return None
    strongest_lower = max(lowers, key=lambda bound: (bound.value, not bound.inclusive))
    strongest_upper = min(uppers, key=lambda bound: (bound.value, bound.inclusive))
    if numeric_bounds_conflict(
        [(strongest_lower.value, strongest_lower.inclusive)],
        [(strongest_upper.value, strongest_upper.inclusive)],
    ):
        return strongest_lower.fragment, strongest_upper.fragment
    return None


def _mutual_exclusion(
    left: FormalClaim, right: FormalClaim
) -> list[RequirementContradiction]:
    """Flag a post-state variable that the two requirements pin to different values.

    A variable cannot hold two values at once, so two ``state <var> must be <value>`` obligations on
    the same variable with different values cannot both be met under co-occurring premises.
    """
    left_states = _post_states_by_variable(left)
    right_states = _post_states_by_variable(right)
    findings: list[RequirementContradiction] = []
    for variable in sorted(set(left_states) & set(right_states)):
        for left_fragment, left_value in left_states[variable]:
            for right_fragment, right_value in right_states[variable]:
                if left_value == right_value:
                    continue
                finding = _pair_finding(
                    "mutual_exclusion", left, left_fragment, right, right_fragment
                )
                if finding is not None:
                    findings.append(finding)
    return findings


def _post_states_by_variable(
    claim: FormalClaim,
) -> dict[str, list[tuple[FormalClaimFragment, tuple[str, str]]]]:
    """Per-variable ``post_state`` obligations, each paired with its canonical (kind, value) value.

    The value is keyed by its operand kind and text so ``status == active`` and ``status == frozen``
    differ while two identical assignments do not.
    """
    states: dict[str, list[tuple[FormalClaimFragment, tuple[str, str]]]] = {}
    for fragment in claim.obligations:
        if fragment.kind != "post_state" or len(fragment.operands) < 2:
            continue
        if fragment.operands[0].kind != "identifier":
            continue
        variable = str(fragment.operands[0].value)
        value = (fragment.operands[1].kind, str(fragment.operands[1].value))
        states.setdefault(variable, []).append((fragment, value))
    return states


def _action_order_conflict(
    left: FormalClaim, right: FormalClaim
) -> list[RequirementContradiction]:
    """Flag an action one requirement must complete successfully and another must reject.

    Success and rejection are exclusive outcomes of the same action, so a ``must succeed`` obligation
    in one requirement and a ``must reject before ...`` obligation naming the same action in the
    other cannot both be met under co-occurring premises.
    """
    findings: list[RequirementContradiction] = []
    for success_claim, reject_claim in ((left, right), (right, left)):
        successes = _successes(success_claim)
        rejections = _rejections(reject_claim)
        for success_fragment, action in successes:
            for reject_fragment, rejected_action in rejections:
                if action != rejected_action:
                    continue
                finding = _pair_finding(
                    "action_order_conflict",
                    success_claim,
                    success_fragment,
                    reject_claim,
                    reject_fragment,
                )
                if finding is not None:
                    findings.append(finding)
    return findings


def _successes(claim: FormalClaim) -> list[tuple[FormalClaimFragment, str]]:
    return [
        (fragment, str(fragment.operands[0].value))
        for fragment in claim.obligations
        if fragment.kind == "success" and fragment.operands
    ]


def _rejections(claim: FormalClaim) -> list[tuple[FormalClaimFragment, str]]:
    return [
        (fragment, str(fragment.operands[0].value))
        for fragment in claim.obligations
        if fragment.kind == "rejection_order" and fragment.operands
    ]


def _pair_finding(
    contradiction_type: CrossRequirementContradictionType,
    first_claim: FormalClaim,
    first_fragment: FormalClaimFragment,
    second_claim: FormalClaim,
    second_fragment: FormalClaimFragment,
) -> RequirementContradiction | None:
    """A contradiction over exactly two fragments, or ``None`` if either cannot be tied to source.

    A detected contradiction must point at the offending text, so a fragment with no source span is
    dropped here rather than reported spanless.
    """
    spans = [*first_fragment.source_spans, *second_fragment.source_spans]
    if not first_fragment.source_spans or not second_fragment.source_spans:
        return None
    return RequirementContradiction(
        contradiction_type=contradiction_type,
        requirement_ids=[first_claim.requirement_id, second_claim.requirement_id],
        fragments=[first_fragment.canonical, second_fragment.canonical],
        source_spans=spans,
    )
