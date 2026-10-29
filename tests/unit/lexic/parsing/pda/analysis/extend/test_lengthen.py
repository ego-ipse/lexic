"""Tests for lexic.parsing.pda.analysis.extend.lengthen — EXTEND, asked through
:func:`rule_extensions` and checked against the language itself, enumerated."""

from __future__ import annotations

import pytest

from lexic.compile import compile_text
from lexic.parsing.lift import lift_optional_nullables
from lexic.parsing.pda.analysis.analysis import GrammarAnalysis
from lexic.parsing.pda.analysis.extend.lengthen import rule_extensions
from lexic.parsing.pda.core.charsets import CharSet
from tests.language_helpers import members


def extension(source: str, rule: str = "x") -> CharSet:
    """``rule``'s EXTEND in ``source``, over the grammar the PDA analyses."""
    compiled = compile_text(source, cache_key=f"extend-{hash(source)}")
    analysis = GrammarAnalysis(lift_optional_nullables(compiled.codegen_grammar))
    return rule_extensions(analysis).found[rule]


@pytest.mark.parametrize(
    ("source", "grows", "fixed"),
    [
        ('x ::= "ab"\n', "", "ab"),
        ('x ::= "b" "a"*\n', "a", "b"),
        ("x ::= [0-9]+\n", "07", "a"),
        ('x ::= "b" | "ba"\n', "a", "c"),
        ('x ::= "\\"" [a-z]* "\\""\n', "", 'a"'),
        ('x ::= "(" x ")" | "y"\n', "", "()y"),
        ('x ::= "a"? "a"\n', "a", "b"),
        ('x ::= y y\ny ::= "a" | "aa"\n', "a", "b"),
        ('x ::= ([a-b] "z")? [a-b] [0-1]\n', "", "abz01"),
        ('x ::= "q" [a-b]* [a-b]\n', "ab", "q"),
        ("x ::= [a-b]? [a-b] [0-1]\n", "", "ab01"),
    ],
    ids=[
        "literal",
        "trailing-loop",
        "run",
        "arm-prefix",
        "closed-string",
        "balanced",
        "unsettled-seq",
        "unsettled-repeat",
        "unshifting-seq",
        "shift-bound",
        "short-surplus",
    ],
)
def test_extend_holds_what_lengthens_a_match_and_nothing_that_cannot(
    source: str, grows: str, fixed: str
) -> None:
    """Each character that can lengthen a complete match is in EXTEND, and a
    construct whose matches are closed has none. EXTEND over-approximates —
    arms sharing a first character take the longer arm's whole ALPHABET — so
    ``fixed`` names only characters no approximation may hold. Where an item's
    EXTEND meets what follows, the boundary shifts only if what follows can
    begin with the item's surplus then itself (``unshifting-seq``: a ``z``
    cannot begin a digit; ``short-surplus``: nor a letter), and a shift reaches
    back no further than its own item (``shift-bound``: ``q`` is never past
    one)."""
    got = extension(source)
    assert all(got.has(char) for char in grows), f"missing one of {grows!r}"
    assert not any(got.has(char) for char in fixed), f"holds one of {fixed!r}"


@pytest.mark.parametrize(
    ("source", "alphabet"),
    [
        ('x ::= "b" "a"*\n', "ab"),
        ('x ::= "b" | "ba" | "bab"\n', "ab"),
        ('x ::= y "c"?\ny ::= "a" | "ac"\n', "ac"),
        ('x ::= "(" x ")" | "y" x?\n', "()y"),
        ('x ::= x "a" | "b"\n', "ab"),
        ('x ::= ([a-b] "z")? [a-b] [0-1]\n', "abz01"),
        ('x ::= "q" [a-b]* [a-b]\n', "qab"),
        ('x ::= ([a-b] "z")? [a-b] "z"? [0-1]\n', "abz01"),
        ('x ::= y [b-c]\ny ::= "a" | "ab"\n', "abc"),
        ('x ::= [a-c]* "b" "a"+\n', "abc"),
        ('x ::= y* "b"\ny ::= "a" "ab"?\n', "ab"),
        ('x ::= ([a-b] "z")? [a-b] [0-1]* [0-1]\n', "abz01"),
        ("x ::= [b-c]? x?\n", "bc"),
        ('x ::= "a"* "ab"?\n', "ab"),
    ],
    ids=[
        "loop",
        "arm-chain",
        "optional-tail",
        "recursive",
        "left-recursive",
        "unshifting-seq",
        "shift-bound",
        "shifting-seq",
        "lengthening-item",
        "several-more",
        "re-split",
        "two-shifts",
        "unknown-window",
        "vanishing-rest",
    ],
)
def test_extend_covers_every_extension_the_language_has(
    source: str, alphabet: str
) -> None:
    """Sound against the LANGUAGE, enumerated: for every ``u`` and ``uw`` the
    parser accepts, ``w``'s first character is in EXTEND. The later cases each
    shift a boundary only through one part of the surplus test: an item's own
    lengthening, several further occurrences, occurrences that split otherwise
    (``"a" "ab"`` against ``"aab"``), a second shifting item read at its own
    position past one that cannot shift, a window the solver cannot see (a
    recursion it re-enters), and a rest that can vanish."""
    words = members(source, alphabet, 6)
    assert words, "the enumeration found nothing, so it proves nothing"
    seen = {
        long[len(short)]
        for short in words
        for long in words
        if len(long) > len(short) and long.startswith(short)
    }
    got = extension(source)
    assert all(got.has(char) for char in seen), f"{seen} not all in EXTEND"


def test_extend_is_built_once_per_analysis_and_shared() -> None:
    """Every reader of one analysis gets the SAME EXTEND: the second ask returns
    the first's maps, and they hold the fixpoint, not an empty start."""
    grammar = compile_text(
        'root ::= unit+\nunit ::= [a-z]+ "!"\n', cache_key="pred-extend-once"
    ).codegen_grammar
    analysis = GrammarAnalysis(lift_optional_nullables(grammar))
    first = rule_extensions(analysis)
    assert rule_extensions(analysis) is first
    assert first.found["root"].has("a")
