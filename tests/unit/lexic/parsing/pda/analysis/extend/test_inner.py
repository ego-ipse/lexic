"""Tests for lexic.parsing.pda.analysis.extend.inner — NON_INITIAL, every
character a string can carry past its first."""

from __future__ import annotations

import pytest

from lexic.compile import compile_text
from lexic.parsing.pda.analysis.extend.inner import rule_non_initials
from lexic.parsing.pda.core.charsets import CharSet
from tests.language_helpers import members


def non_initial(source: str, rule: str = "x") -> CharSet:
    """``rule``'s NON_INITIAL in ``source``, over the codegen grammar."""
    grammar = compile_text(source, cache_key=f"inner-{hash(source)}").codegen_grammar
    return rule_non_initials({str(one.name): one for one in grammar.rules}).found[rule]


@pytest.mark.parametrize(
    ("source", "alphabet", "first_only"),
    [
        ('x ::= "ab"\n', "ab", "a"),
        ('x ::= "b" "a"*\n', "ab", "b"),
        ("x ::= [0-9]+\n", "07", ""),
        ('x ::= "a" | "bc"\n', "abc", "ab"),
        ('x ::= y "c"\ny ::= "a" | "b"\n', "abc", "ab"),
        ('x ::= x "a" | "b"\n', "ab", "b"),
        ('x ::= x "a" | x "b" | "z"\n', "abz", "z"),
        ('x ::= "(" x ")" | "y"\n', "()y", ""),
    ],
    ids=[
        "literal",
        "trailing-loop",
        "run",
        "arms",
        "through-a-rule",
        "left-recursive",
        "several-arms",
        "balanced",
    ],
)
def test_non_initial_holds_every_later_character_and_no_first_only_one(
    source: str, alphabet: str, first_only: str
) -> None:
    """Sound against the LANGUAGE, enumerated: every character a member
    carries past its first position is in NON_INITIAL. ``first_only`` names
    characters the language only ever starts with, which the per-rule reading
    is exact enough to leave out."""
    words = members(source, alphabet, 5)
    assert words, "the enumeration found nothing, so it proves nothing"
    got = non_initial(source)
    later = {char for word in words for char in word[1:]}
    assert all(got.has(char) for char in later), f"{later} not all in NON_INITIAL"
    assert not any(got.has(char) for char in first_only), f"holds one of {first_only!r}"
