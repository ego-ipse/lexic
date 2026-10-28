"""Tests for lexic.parsing.pda.analysis.predicates — per-node predicates and
their dispatch tables.

``FIRST``/``HARD``/``FOLLOW_FEED``/``SEQ_ATOM`` need a live ``GrammarAnalysis``
to drive them and are exercised through it in
``tests/unit/lexic/parsing/pda/analysis/test_analysis.py``; this file targets
the table usable standalone: ``STOPSET_ATOM`` (a pure per-type predicate
needing no dispatcher context). Nullability is the grammar's own fact
(``IrAst.nullable``), pinned in ``tests/unit/lexic/ir/grammar/test_nodes.py``.
``EXTEND`` is asked through :func:`rule_extensions` and checked against the
language itself, enumerated.
"""

from __future__ import annotations

import math
from itertools import product

import pytest

from lexic.compile import compile_text
from lexic.exceptions import UnsupportedConstructError
from lexic.ir import (
    IrCharClass,
    IrChr,
    IrLiteral,
    IrRuleRef,
)
from lexic.parsing.lift import lift_optional_nullables
from lexic.parsing.pda.analysis.analysis import GrammarAnalysis
from lexic.parsing.pda.analysis.predicates import (
    STOPSET_ATOM,
    rule_extensions,
    rule_non_initials,
    rule_spans,
)
from lexic.parsing.pda.core.charsets import CharSet


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


# ── NON_INITIAL — what can stand anywhere but first ───────────────────────


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


# ── SPAN — how short and how long a match can be ──────────────────────────


def span_of(source: str, rule: str = "x") -> tuple[float, float]:
    """``rule``'s span in ``source``, over the grammar the PDA analyses."""
    compiled = compile_text(source, cache_key=f"span-{hash(source)}")
    grammar = lift_optional_nullables(compiled.codegen_grammar)
    return rule_spans({str(one.name): one for one in grammar.rules})[rule]


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        ('x ::= "abc"\n', (3.0, 3.0)),
        ("x ::= [a-z]\n", (1.0, 1.0)),
        ('x ::= "ab" "c"?\n', (2.0, 3.0)),
        ("x ::= [a-z]{2,4}\n", (2.0, 4.0)),
        ('x ::= "a" | "bcd"\n', (1.0, 3.0)),
        ("x ::= [a-z]*\n", (0.0, math.inf)),
        ('x ::= "(" x ")" | "y"\n', (1.0, math.inf)),
    ],
    ids=["literal", "class", "optional", "bounded", "arms", "unbounded", "recursion"],
)
def test_span_is_the_shortest_and_longest_match(
    source: str, expected: tuple[float, float]
) -> None:
    """Fewest and most characters a match of ``x`` can take."""
    assert span_of(source) == expected


def test_a_cycle_of_rules_is_unbounded_in_every_rule_it_reaches() -> None:
    """``a → b → c → a``: each round one rule rises, so widening must reach
    all three, not stop at whichever rose last — and must not undo itself."""
    source = 'a ::= "x" b | "y"\nb ::= "x" c | "y"\nc ::= "x" a | "y"\n'
    for rule in ("a", "b", "c"):
        assert span_of(source, rule) == (1.0, math.inf), rule


def test_an_unmeasured_rule_under_a_zero_count_does_not_poison_the_low_end() -> None:
    """``a*`` before ``a`` is measured: ``inf`` times a count of zero is NaN,
    which ``min`` never lowers. A zero count contributes nothing instead."""
    source = 'root ::= a* "x"\na ::= "y" a?\n'
    for rule in ("root", "a"):
        low, high = span_of(source, rule)
        assert not (math.isnan(low) or math.isnan(high)), rule
        assert (low, high) == (1.0, math.inf), rule


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
