"""Tests for regex_portable: literal_to_regex_pattern, PORTABLE_FEATURES, validate_portable."""

from __future__ import annotations

import pytest

from lexic.exceptions import UnsupportedConstructError
from lexic.ir.regex_portable import (
    PORTABLE_FEATURES,
    features_used,
    literal_to_regex_pattern,
    validate_portable,
)

# ── literal_to_regex_pattern ──────────────────────────────────────────


@pytest.mark.parametrize(
    "value,expected",
    [
        ("abc", "abc"),
        ("a.b", r"a\.b"),
        ("a*b", r"a\*b"),
        ("a+b", r"a\+b"),
        ("a?b", r"a\?b"),
        ("a^b", r"a\^b"),
        ("a$b", r"a\$b"),
        ("[x]", r"\[x\]"),
        ("(x)", r"\(x\)"),
        ("{1}", r"\{1\}"),
        ("a|b", r"a\|b"),
        ("a/b", r"a\/b"),
        ("a\\b", r"a\\b"),
        ("a\nb", r"a\nb"),
        ("a\rb", r"a\rb"),
        ("a\tb", r"a\tb"),
        ("", ""),
    ],
)
def test_literal_to_regex_pattern_escaping(value: str, expected: str) -> None:
    """literal_to_regex_pattern escapes metacharacters correctly."""
    assert literal_to_regex_pattern(value) == expected


def test_literal_to_regex_pattern_plain_chars_unchanged() -> None:
    """Plain alphanumeric characters are returned unchanged."""
    assert literal_to_regex_pattern("hello123") == "hello123"


# ── PORTABLE_FEATURES ────────────────────────────────────────────────


def test_portable_features_is_frozenset() -> None:
    """PORTABLE_FEATURES is a frozenset."""
    assert isinstance(PORTABLE_FEATURES, frozenset)


# ── validate_portable ────────────────────────────────────────────────


def test_validate_portable_accepts_literal() -> None:
    """A plain literal regex passes validation."""
    validate_portable("abc")  # no exception


def test_validate_portable_accepts_char_class() -> None:
    """A character class regex passes validation."""
    validate_portable("[a-z]")  # no exception


def test_validate_portable_accepts_negated_class() -> None:
    """A negated character class passes validation."""
    validate_portable("[^a-z]")  # no exception


def test_validate_portable_accepts_quantifiers() -> None:
    """Quantified patterns pass validation."""
    validate_portable("a*")
    validate_portable("a+")
    validate_portable("a?")
    validate_portable("a{2,4}")


def test_validate_portable_accepts_alternation() -> None:
    """Alternation passes validation."""
    validate_portable("a|b|c")


def test_validate_portable_accepts_non_capturing_group() -> None:
    """Non-capturing group passes validation."""
    validate_portable("(?:abc)")


def test_validate_portable_rejects_anchor_start() -> None:
    """An anchor at the start of the pattern raises UnsupportedConstructError."""
    with pytest.raises(UnsupportedConstructError, match="anchor"):
        validate_portable("^abc")


def test_validate_portable_rejects_anchor_end() -> None:
    """An anchor at the end of the pattern raises UnsupportedConstructError."""
    with pytest.raises(UnsupportedConstructError, match="anchor"):
        validate_portable("abc$")


def test_validate_portable_rejects_capturing_group() -> None:
    """A capturing group raises UnsupportedConstructError."""
    with pytest.raises(UnsupportedConstructError, match="capturing group"):
        validate_portable("(abc)")


def test_validate_portable_rejects_backreference() -> None:
    """A backreference raises UnsupportedConstructError.

    Note: the capturing group check fires before the backreference check,
    so the error message mentions the capturing group.
    """
    with pytest.raises(UnsupportedConstructError):
        validate_portable(r"(a)\1")


# ── features_used ────────────────────────────────────────────────────


def test_features_used_literal_only() -> None:
    """A plain literal uses only the 'literal' feature."""
    assert features_used("abc") == frozenset({"literal"})


def test_features_used_char_class() -> None:
    """A character class reports 'char_class'."""
    assert "char_class" in features_used("[a-z]")


def test_features_used_negated_class() -> None:
    """A negated character class reports 'negated_class'."""
    assert "negated_class" in features_used("[^a-z]")


def test_features_used_quantifier() -> None:
    """A quantified pattern reports 'quantifier'."""
    assert "quantifier" in features_used("a*")


def test_features_used_alternation() -> None:
    """An alternation reports 'alternation'.

    Python's re module optimises single-char alternation (``a|b``) into a
    char class, so multi-char arms are used to exercise the BRANCH op.
    """
    assert "alternation" in features_used("ab|cd")


def test_features_used_non_capturing_group_in_portable_features() -> None:
    """'non_capturing_group' is listed in PORTABLE_FEATURES.

    Python's re module inlines ``(?:...)`` groups at the parse level, so plain
    non-capturing groups do not produce the SUBPATTERN op that ``features_used``
    looks for.  The feature is therefore declared portable but not emitted for
    simple ``(?:...)`` patterns.
    """
    assert "non_capturing_group" in PORTABLE_FEATURES


def test_features_used_returns_frozenset() -> None:
    """features_used returns a frozenset."""
    result = features_used("abc")
    assert isinstance(result, frozenset)
