from __future__ import annotations

import math
from fractions import Fraction

__all__ = ["exact_fraction", "numeric_bounds_conflict"]


def exact_fraction(value: object) -> Fraction | None:
    """The exact rational value of a numeric operand, or None if it is not a finite number.

    The IR lowers integer literals to ``int`` (arbitrary precision) and decimal literals to
    ``float``. Deciding a comparison through ``float(value)`` silently rounds any integer past
    2**53 — ``float(9007199254740993) == float(9007199254740992)`` is ``True`` — so a ground-false
    comparison looks satisfiable and a real contradiction disappears. This converts each literal to
    an exact :class:`~fractions.Fraction` instead, so equality and ordering are decided at full
    precision regardless of magnitude:

      - ``int``   -> exact, any magnitude (``bool`` is rejected: it is not a numeric literal even
        though it subclasses ``int``).
      - ``float`` -> the decimal it was written as, recovered from its shortest round-tripping repr
        (``1.5`` -> ``3/2``, ``0.1`` -> ``1/10``); ``nan`` / ``inf`` are not finite numbers -> None.
      - ``str``   -> parsed as exact integer / decimal / rational / exponent text; non-numeric -> None.

    Returning None means "not a decidable number" — callers keep the comparison undecided rather
    than forcing a value into the encoding, never silently approving it.
    """
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return Fraction(value)
    if isinstance(value, float):
        if not math.isfinite(value):
            return None
        text = str(value)  # shortest repr that round-trips: 0.1 -> "0.1", recovering the decimal
    elif isinstance(value, str):
        text = value
    else:
        return None
    try:
        return Fraction(text)
    except (ValueError, ZeroDivisionError):
        return None


def numeric_bounds_conflict(
    lower_bounds: list[tuple[Fraction, bool]],
    upper_bounds: list[tuple[Fraction, bool]],
) -> bool:
    """True when a set of lower and upper bounds on one numeric value cannot all hold.

    Each bound is ``(value, inclusive)``: a lower bound ``x >= v`` is ``(v, True)`` and ``x > v`` is
    ``(v, False)``; an upper bound ``x <= v`` is ``(v, True)`` and ``x < v`` is ``(v, False)``. The
    binding constraints are the strongest lower bound (largest value, an exclusive ``>`` winning ties
    over an inclusive ``>=``) and the strongest upper bound (smallest value, exclusive ``<`` winning
    ties). They bound a non-empty interval iff the lower value is below the upper, or the two values
    are equal and both bounds are inclusive — anything else is an empty interval, i.e. a conflict.
    Comparison is exact (:class:`~fractions.Fraction`), so a conflict between large-integer bounds is
    not lost to float rounding. Callers pass only decidable bounds (see :func:`exact_fraction`); an
    empty ``lower_bounds`` or ``upper_bounds`` is not a conflict and is filtered out before calling.
    """
    strongest_lower = max(lower_bounds, key=lambda item: (item[0], not item[1]))
    strongest_upper = min(upper_bounds, key=lambda item: (item[0], item[1]))
    if strongest_lower[0] > strongest_upper[0]:
        return True
    if strongest_lower[0] == strongest_upper[0] and (
        not strongest_lower[1] or not strongest_upper[1]
    ):
        return True
    return False
