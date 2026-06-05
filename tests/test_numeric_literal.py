from __future__ import annotations

from fractions import Fraction

from nlreq.numeric_literal import exact_fraction


def test_large_integers_stay_distinct_unlike_float() -> None:
    """Two consecutive integers past 2**53 must remain distinct. ``float()`` collapses them — the
    trap this helper exists to sidestep — which would make ``a == b`` look satisfiable and a real
    contradiction silently disappear."""
    assert float(9007199254740992) == float(9007199254740993)  # the float trap
    assert exact_fraction(9007199254740992) != exact_fraction(9007199254740993)
    assert exact_fraction(9007199254740993) == Fraction(9007199254740993)


def test_decimal_floats_recover_the_written_value() -> None:
    """Decimal literals the parser lowers to ``float`` are recovered as the decimal that was
    written, not the binary dyadic approximation of it."""
    assert exact_fraction(1.5) == Fraction(3, 2)
    assert exact_fraction(0.1) == Fraction(1, 10)
    assert exact_fraction(-0.25) == Fraction(-1, 4)


def test_integers_and_numeric_strings_parse_exactly() -> None:
    assert exact_fraction(5) == Fraction(5)
    assert exact_fraction(-7) == Fraction(-7)
    assert exact_fraction("9007199254740993") == Fraction(9007199254740993)
    assert exact_fraction("0.1") == Fraction(1, 10)
    assert exact_fraction("1/3") == Fraction(1, 3)
    assert exact_fraction("1e3") == Fraction(1000)


def test_non_numeric_and_non_finite_return_none() -> None:
    """A value that is not a decidable finite number returns None so a caller keeps the comparison
    undecided rather than forcing a value into the encoding."""
    assert exact_fraction("abc") is None
    assert exact_fraction(float("inf")) is None
    assert exact_fraction(float("-inf")) is None
    assert exact_fraction(float("nan")) is None
    assert exact_fraction(True) is None  # bool subclasses int but is not a numeric literal
    assert exact_fraction(None) is None
    assert exact_fraction([1]) is None
