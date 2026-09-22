"""Tests for lexic.parsing.pda.analysis.predicates — per-node predicates and
their dispatch tables.

``FIRST``/``HARD``/``FOLLOW_FEED``/``SEQ_ATOM`` need a live ``GrammarAnalysis``
to drive them and are exercised through it in
``tests/unit/lexic/parsing/pda/analysis/test_analysis.py``; this file targets
the two tables usable standalone: ``nullable_names`` (self-contained, its own
fixpoint solver) and ``STOPSET_ATOM`` (a pure per-type predicate needing no
dispatcher context). ``EXTEND`` is asked through :func:`rule_extensions` and
checked against the language itself, enumerated.
"""

from __future__ import annotations

from itertools import product

import pytest

from lexic.compile import compile_text
from lexic.exceptions import UnsupportedConstructError
from lexic.ir import (
    IrAlternation,
    IrCharClass,
    IrChr,
    IrItem,
    IrLiteral,
    IrQuantifier,
    IrRule,
    IrRuleRef,
    IrSequence,
)
from lexic.parsing.lift import lift_optional_nullables
from lexic.parsing.pda.analysis.analysis import GrammarAnalysis
from lexic.parsing.pda.analysis.predicates import (
    STOPSET_ATOM,
    nullable_names,
    rule_extensions,
)
from lexic.parsing.pda.core.charsets import CharSet


def test_nullable_names_finds_an_empty_literal_arm():
    """A rule whose sole arm is the empty literal derives the empty string."""
    rules = [IrRule("r", IrAlternation(IrSequence(IrItem(IrLiteral("")))))]
    assert nullable_names(rules) == frozenset({"r"})


def test_nullable_names_excludes_a_rule_with_only_non_empty_arms():
    """A rule with no all-nullable arm is not in the result."""
    rules = [IrRule("r", IrAlternation(IrSequence(IrItem(IrLiteral("x")))))]
    assert nullable_names(rules) == frozenset()


def test_nullable_names_an_optional_item_makes_its_arm_nullable():
    """A ``lo == 0`` item makes its whole arm nullable even with non-empty text."""
    rules = [
        IrRule(
            "r",
            IrAlternation(IrSequence(IrItem(IrLiteral("x"), IrQuantifier(0, 1)))),
        )
    ]
    assert nullable_names(rules) == frozenset({"r"})


def test_nullable_names_propagates_through_a_ruleref_chain():
    """``root`` is nullable because ``mid`` is, transitively — the fixpoint's
    own reason to exist over a one-pass check."""
    rules = [
        IrRule("root", IrAlternation(IrSequence(IrItem(IrRuleRef("mid"))))),
        IrRule("mid", IrAlternation(IrSequence(IrItem(IrLiteral(""))))),
    ]
    assert nullable_names(rules) == frozenset({"root", "mid"})


def test_nullable_names_any_arm_nullable_makes_the_whole_alternation_nullable():
    """One nullable arm among several non-nullable ones is enough."""
    rules = [
        IrRule(
            "r",
            IrAlternation(
                IrSequence(IrItem(IrLiteral("x"))),
                IrSequence(IrItem(IrLiteral(""))),
            ),
        )
    ]
    assert nullable_names(rules) == frozenset({"r"})


def test_stopset_atom_is_true_only_for_a_single_char_loop_atom():
    """Only a char class is a single-char loop atom — a literal or ref is not."""
    charclass = IrCharClass(IrChr("a"))
    assert STOPSET_ATOM.resolve(charclass).eval(None, charclass, ()) is True

    literal = IrLiteral("x")
    assert STOPSET_ATOM.resolve(literal).eval(None, literal, ()) is False

    ref = IrRuleRef("r")
    assert STOPSET_ATOM.resolve(ref).eval(None, ref, ()) is False


# ── EXTEND — what can lengthen a complete match ───────────────────────────


def extension(source: str, rule: str = "x") -> CharSet:
    """``rule``'s EXTEND in ``source``, over the grammar the PDA analyses."""
    compiled = compile_text(source, cache_key=f"extend-{hash(source)}")
    analysis = GrammarAnalysis(lift_optional_nullables(compiled.codegen_grammar))
    return rule_extensions(analysis).found[rule]


def members(source: str, alphabet: str, longest: int) -> set[str]:
    """Every string over ``alphabet`` up to ``longest`` that ``source`` derives,
    by asking the parser — an ambiguous member is a member all the same."""
    compiled = compile_text(source, cache_key=f"members-{hash(source)}")
    found: set[str] = set()
    for size in range(longest + 1):
        for chars in product(alphabet, repeat=size):
            text = "".join(chars)
            try:
                compiled.parse(text)
            except UnsupportedConstructError as refused:
                if "ambiguous" not in str(refused) and "two ways" not in str(refused):
                    continue
            found.add(text)
    return found


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
    ],
)
def test_extend_holds_what_lengthens_a_match_and_nothing_that_cannot(
    source: str, grows: str, fixed: str
) -> None:
    """Each character that can lengthen a complete match is in EXTEND, and a
    construct whose matches are closed has none. EXTEND over-approximates —
    arms sharing a first character take the longer arm's whole ALPHABET — so
    ``fixed`` names only characters no approximation may hold."""
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
    ],
    ids=["loop", "arm-chain", "optional-tail", "recursive", "left-recursive"],
)
def test_extend_covers_every_extension_the_language_has(
    source: str, alphabet: str
) -> None:
    """Sound against the LANGUAGE, enumerated: for every ``u`` and ``uw`` the
    parser accepts, ``w``'s first character is in EXTEND."""
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
