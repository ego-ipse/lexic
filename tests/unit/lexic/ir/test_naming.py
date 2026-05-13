"""Tests for ir.naming — CHARCLASS_NAMES and LITERAL_NAMES lookup tables."""

from lexic.ir.naming import CHARCLASS_NAMES, LITERAL_NAMES


def test_charclass_names_digit():
    assert CHARCLASS_NAMES["[0-9]"] == "digit"


def test_charclass_names_lower():
    assert CHARCLASS_NAMES["[a-z]"] == "lower"


def test_charclass_names_upper():
    assert CHARCLASS_NAMES["[A-Z]"] == "upper"


def test_charclass_names_letter():
    assert CHARCLASS_NAMES["[a-zA-Z]"] == "letter"


def test_charclass_names_hex():
    assert CHARCLASS_NAMES["[0-9a-fA-F]"] == "hex"


def test_charclass_names_alnum():
    assert CHARCLASS_NAMES["[a-zA-Z_0-9]"] == "alnum"


def test_literal_names_sign():
    assert LITERAL_NAMES["-"] == "sign"
    assert LITERAL_NAMES["+"] == "sign"


def test_literal_names_dot():
    assert LITERAL_NAMES["."] == "dot"


def test_literal_names_comma():
    assert LITERAL_NAMES[","] == "comma"


def test_literal_names_eq():
    assert LITERAL_NAMES["="] == "eq"


def test_charclass_names_is_dict():
    assert isinstance(CHARCLASS_NAMES, dict)
    assert len(CHARCLASS_NAMES) >= 6


def test_literal_names_is_dict():
    assert isinstance(LITERAL_NAMES, dict)
    assert len(LITERAL_NAMES) >= 4
