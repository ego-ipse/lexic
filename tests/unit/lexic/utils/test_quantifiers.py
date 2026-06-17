"""Unit tests for src/lexic/utils/quantifiers.py"""

from lexic.ir.base import IrNone
from lexic.utils.quantifiers import bounds_to_quantifier


def test_required_singular():
    """(1,1) maps to empty string."""
    assert bounds_to_quantifier(1, 1) == ""


def test_optional():
    """(0,1) maps to '?'."""
    assert bounds_to_quantifier(0, 1) == "?"


def test_zero_or_more():
    """(0,None) maps to '*'."""
    assert bounds_to_quantifier(0, IrNone) == "*"


def test_one_or_more():
    """(1,None) maps to '+'."""
    assert bounds_to_quantifier(1, IrNone) == "+"


def test_exact():
    """(n,n) maps to '{n}'."""
    assert bounds_to_quantifier(3, 3) == "{3}"


def test_range():
    """(min,max) maps to '{min,max}'."""
    assert bounds_to_quantifier(2, 5) == "{2,5}"


def test_min_with_no_max():
    """(min,None) maps to '{min,}'."""
    assert bounds_to_quantifier(2, IrNone) == "{2,}"
