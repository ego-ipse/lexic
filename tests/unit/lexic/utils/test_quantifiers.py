"""Unit tests for src/lexic/utils/quantifiers.py"""

from lexic.utils.quantifiers import bounds_to_quantifier


def test_required_singular():
    assert bounds_to_quantifier(1, 1) == ""


def test_optional():
    assert bounds_to_quantifier(0, 1) == "?"


def test_zero_or_more():
    assert bounds_to_quantifier(0, None) == "*"


def test_one_or_more():
    assert bounds_to_quantifier(1, None) == "+"


def test_exact():
    assert bounds_to_quantifier(3, 3) == "{3}"


def test_range():
    assert bounds_to_quantifier(2, 5) == "{2,5}"


def test_min_with_no_max():
    assert bounds_to_quantifier(2, None) == "{2,}"
