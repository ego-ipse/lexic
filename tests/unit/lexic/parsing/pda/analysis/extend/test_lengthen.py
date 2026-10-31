"""Tests for lexic.parsing.pda.analysis.extend.lengthen — EXTEND, asked through
:func:`rule_extensions` and checked against the language itself, enumerated."""

from __future__ import annotations

import pytest

from lexic.compile import compile_text
from lexic.ir import IrItem, IrRuleRef
from lexic.parsing.lift import lift_optional_nullables
from lexic.parsing.pda.analysis.analysis import GrammarAnalysis
from lexic.parsing.pda.analysis.extend.lengthen import rule_extensions, tails_item
from lexic.parsing.pda.analysis.extend.maps import Confinement
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


def _truth(source: str, alphabet: str, longest: int, rule: str = "x") -> set[str]:
    """Every ``w[0]`` for which ``rule``'s enumerated language holds ``u`` and
    ``uw``."""
    words = members(source, alphabet, longest, rule)
    assert words, "the enumeration found nothing, so it proves nothing"
    return {
        long[len(short)]
        for short in words
        for long in words
        if len(long) > len(short) and long.startswith(short)
    }


_SEP = 'ns ::= sp ":" sp\nsp ::= [ ]*\n'
"""A separator whose trailing run meets the run its value leads with."""

_TAILED = (
    'x ::= "_a" "_a"+\np ::= ws "a" ws\nq ::= ws "b" ws\n'
    'v ::= "a" | ws "b" x? ws "a" ws\nws ::= "_"*\n'
)
"""``v``'s ``x?`` lengthens into ``_a``, leaving the run on the ``a`` its rest
leaves it on."""

_STALE = (
    'x ::= "q" a v\na ::= c\nc ::= ":" sp | ";" d\nd ::= e\ne ::= g\ng ::= h\n'
    'h ::= ("_" "2")?\nv ::= sp "2"\nsp ::= [_]*\n'
)
"""``a`` meets ``v``'s run through ``c``'s first arm two passes before ``d``
grows through its chain, so the first ask at ``a`` reads ``d``'s EXTEND empty
and holds. ``d``'s ``_2`` arrives later, leaving the run on ``v``'s ``2``.
Rules are read in order, the asker first."""


@pytest.mark.parametrize(
    ("source", "alphabet", "fixed"),
    [
        ('x ::= "q" ns v\nv ::= sp "q" sp | sp "1" sp\n' + _SEP, "q: 1", "q:1"),
        ('x ::= m t*\nt ::= sp "," m\nm ::= "q" sp\nsp ::= [ ]*\n', "q, ", "q"),
        ('x ::= sp "q" | sp "1"\nsp ::= [ ]*\n', "q1 ", "q1 "),
    ],
    ids=["shifting-item", "re-splitting-repetition", "arms-sharing-a-run"],
)
def test_a_shift_confined_to_a_run_adds_only_what_the_rest_extends_by(
    source: str, alphabet: str, fixed: str
) -> None:
    """R3, at each of its three sites. Where two readings part inside a run
    the rest leads with, and the rest leaves that run on characters the
    parting item's extensions never leave it on, the longer reading's surplus
    lengthens the rest: EXTEND takes the rest's, not the ALPHABET. Sound
    against the enumerated language, and free of ``fixed``, which the ALPHABET
    fallback held."""
    got = extension(source)
    assert all(got.has(char) for char in _truth(source, alphabet, 7))
    assert not any(got.has(char) for char in fixed), f"holds one of {fixed!r}"


@pytest.mark.parametrize(
    ("source", "rule", "alphabet", "longest", "held"),
    [
        ('x ::= sp "q" | sp "q" "1"\nsp ::= [ ]*\n', "x", "q1 ", 7, "1"),
        ('x ::= "q" ns v\nv ::= sp "q"?\n' + _SEP, "x", "q: ", 7, " q"),
        (
            'x ::= "q" a v\na ::= ":" sp "1"?\nv ::= sp "1"\nsp ::= [ ]*\n',
            "x",
            "q: 1",
            7,
            " 1",
        ),
        ('x ::= "q" ns v\nv ::= " " "q" | sp "1"\n' + _SEP, "x", "q: 1", 7, " 1:q"),
        (_TAILED, "v", "ab_", 7, "a"),
        (
            'x ::= "b" m*\nm ::= sp [ad] "c" ("_" "d")?\nsp ::= [_]*\n',
            "x",
            "abcd_",
            6,
            "c",
        ),
        (_STALE, "x", "q:;2_", 6, "2_"),
    ],
    ids=[
        "arms-meet-past-the-run",
        "rest-vanishes-past-the-run",
        "item-leaves-the-run-on-a-head",
        "run-character-outside-a-run",
        "extension-leaves-the-run-on-a-head",
        "iteration-leaves-the-run-on-a-head",
        "leaves-the-run-only-once-the-maps-stand",
    ],
)
def test_a_shift_that_escapes_its_run_keeps_the_sound_bound(
    source: str, rule: str, alphabet: str, longest: int, held: str
) -> None:
    """Each near miss fails one of R3's conditions, so the boundary is not
    confined and EXTEND keeps every extension: two arms whose strings part
    past the run on the same character, a rest that can end inside the run, a
    parting item that leaves the run where the rest does, and a run character
    the rest spells outside a run; two whose surplus leaves the run on a
    character the rest leaves it on, one through a recursive rule (found by a
    soak) and one between a repetition's iterations; and one whose verdict
    holds on an early pass's maps and fails on the final ones, which only the
    closing re-ask reads. ``held`` is in EXTEND either because the language has
    it or because the fallback must keep it."""
    got = extension(source, rule)
    assert all(got.has(char) for char in _truth(source, alphabet, longest, rule))
    assert all(got.has(char) for char in held), f"missing one of {held!r}"


def test_a_tails_solve_settles_every_key_of_its_cycle() -> None:
    """``a`` and ``b`` read each other's TAILS. A solve started at ``a`` reads
    ``b`` while ``a`` is busy, so ``b``'s first value lacks what ``a``'s own
    arm adds (ANY, from the literal run character). The solve's passes grow it
    to the least fixpoint: the value ``b`` has when solved on its own."""
    source = 'x ::= a b\na ::= "a" ("_" "d")? | "c" b\nb ::= "e" sp a?\nsp ::= [_]*\n'
    compiled = compile_text(source, cache_key="extend-tails-cycle")
    analysis = GrammarAnalysis(lift_optional_nullables(compiled.codegen_grammar))
    run = CharSet.from_chars("_")
    solved = []
    for start in ("a", "b"):
        maps = rule_extensions(analysis)._replace(confined=Confinement.empty())
        tails_item(analysis, maps, IrItem(IrRuleRef(start)), run)
        solved.append(maps.confined.tails[("b", run)])
    assert solved == [CharSet.ANY, CharSet.ANY]
