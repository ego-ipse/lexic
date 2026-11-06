"""Tests for lexic.parsing.pda.analysis.extend.runs — runs, read off the grammar
alone: what a run is, what leads past one, and when two arms part on one."""

from __future__ import annotations

import pytest

from lexic.compile import compile_text
from lexic.ir import IrItem
from lexic.parsing.lift import lift_optional_nullables
from lexic.parsing.pda.analysis.analysis import GrammarAnalysis
from lexic.parsing.pda.analysis.extend.maps import Confinement
from lexic.parsing.pda.analysis.extend.runs import (
    apart,
    heads,
    is_run,
    leading_run,
    led,
    run_chars,
)
from lexic.parsing.pda.core.charsets import CharSet

SPACE = CharSet.from_chars(" ")


def _analysis(source: str) -> GrammarAnalysis:
    compiled = compile_text(source, cache_key=f"runs-{hash(source)}")
    return GrammarAnalysis(lift_optional_nullables(compiled.codegen_grammar))


def _arm(analysis: GrammarAnalysis, rule: str = "x", at: int = 0) -> tuple[IrItem, ...]:
    return tuple(analysis.rules[rule].body[at])


@pytest.mark.parametrize(
    ("source", "runs"),
    [
        ("x ::= [ ]* [a]\n", (True, False)),
        ('x ::= " "* "ab"*\n', (True, False)),
        ("x ::= [ ]+ [ ]?\n", (False, False)),
        ('x ::= sp "a"\nsp ::= [ ]*\n', (True, False)),
        ('x ::= sp "a"\nsp ::= [ ]* [a]\n', (False, False)),
    ],
    ids=[
        "class",
        "one-char-literal",
        "bounded-below-or-above",
        "unit-rule",
        "longer-rule",
    ],
)
def test_a_run_is_an_unbounded_optional_single_set(
    source: str, runs: tuple[bool, ...]
) -> None:
    """``C*`` over one character set is a run, directly or as a unit rule's
    sole item; a longer literal, a lower bound, an upper bound or a rule with
    more than one item is not."""
    analysis = _analysis(source)
    assert tuple(is_run(analysis, item) for item in _arm(analysis)) == runs


def test_the_run_characters_are_every_run_s_and_no_other() -> None:
    """Only the characters some run holds: ``q`` stands in no run."""
    analysis = _analysis('x ::= sp "q" tab\nsp ::= [ ]*\ntab ::= [\\t]*\n')
    assert run_chars(analysis, Confinement.empty()) == CharSet.from_chars(" ", "\t")


def test_a_leading_run_is_read_through_vanishing_items_and_arms() -> None:
    """The runs a string can begin with, read past nullable items and into each
    arm; ``None`` once a string beginning in K begins with no run."""
    analysis = _analysis(
        'x ::= "q"? v\nv ::= sp "1" | sp "2"\nsp ::= [ ]*\ny ::= " " "1"\n'
    )
    memo = Confinement.empty()
    assert leading_run(analysis, memo, _arm(analysis), SPACE) == SPACE
    assert leading_run(analysis, memo, _arm(analysis, "y"), SPACE) is None


@pytest.mark.parametrize(
    ("source", "is_led"),
    [
        ('x ::= sp ":" sp v\nv ::= "1"\nsp ::= [ ]*\n', True),
        ('x ::= sp "1"?\nsp ::= [ ]*\n', False),
        ('x ::= w "1"\nw ::= sp "2" | sp "3"\nsp ::= [ ]*\n', True),
        ('x ::= w "1"\nw ::= sp "2" | " " "3"\nsp ::= [ ]*\n', False),
        ('x ::= w? sp\nw ::= sp "2"\nsp ::= [ ]*\n', False),
    ],
    ids=[
        "run-then-mark",
        "may-end-in-run",
        "every-arm",
        "arm-spells-run-alone",
        "absent-arm",
    ],
)
def test_led_asks_a_droppable_run_then_a_character_past_it(
    source: str, is_led: bool
) -> None:
    """Every string beginning in the run is a run prefix then a character
    outside it: never a string ending inside the run, never a run character
    spelled outside a run, read into every arm and past an absent one."""
    analysis = _analysis(source)
    assert led(analysis, Confinement.empty(), _arm(analysis), SPACE) is is_led


def test_heads_are_the_first_characters_past_the_run() -> None:
    """A string's first character outside the run: past the run where it
    begins in it, its own where it does not, from every arm."""
    analysis = _analysis('x ::= w "9"\nw ::= sp ":" | "1" | sp? "2"\nsp ::= [ ]*\n')
    assert heads(
        analysis, Confinement.empty(), _arm(analysis), SPACE
    ) == CharSet.from_chars(*":12")


@pytest.mark.parametrize(
    ("source", "parts"),
    [
        ('x ::= sp "q" | sp "1"\nsp ::= [ ]*\n', True),
        ('x ::= sp "q" | sp "q" "1"\nsp ::= [ ]*\n', False),
        ('x ::= sp "q" | " " "1"\nsp ::= [ ]*\n', False),
        ('x ::= "a" "q" | "a" "1"\n', False),
    ],
    ids=["distinct-heads", "shared-head", "unled-arm", "no-run"],
)
def test_two_arms_part_on_a_shared_run_only_by_distinct_heads(
    source: str, parts: bool
) -> None:
    """Arms sharing a first character part only when the share is a run both
    are led by and the characters past it never meet."""
    analysis = _analysis(source)
    one, other = _arm(analysis, at=0), _arm(analysis, at=1)
    assert apart(analysis, Confinement.empty(), one, other) is parts


def test_apart_is_kept_by_the_arms_themselves() -> None:
    """The kept answer pins its arms: an equal arm at another identity is read
    afresh, never served another pair's answer."""
    analysis = _analysis('x ::= sp "q" | sp "1"\nsp ::= [ ]*\n')
    memo = Confinement.empty()
    one, other = _arm(analysis, at=0), _arm(analysis, at=1)
    assert apart(analysis, memo, one, other)
    assert memo.apart[(id(one), id(other))] == (one, other, True)
