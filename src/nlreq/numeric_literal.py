from __future__ import annotations

import math
from fractions import Fraction

__all__ = ["exact_fraction"]


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
