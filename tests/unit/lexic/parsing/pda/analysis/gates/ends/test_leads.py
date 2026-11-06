"""Tests for lexic.parsing.pda.analysis.gates.ends.leads — what a follower leads
with before the character that ends a run, and whether that is closed.

Each follower below is solved for one run class and its lead read for ``;``:
the kind says whether a gate may stop short of ``;`` by the lead's ``j``. The
counterexamples are the shapes where stopping at the minimum would prune the
only reading that parses — they must come out MIXED, which no gate stops for.
"""

from __future__ import annotations

import pytest

from lexic.compile import compile_text
from lexic.parsing.lift import lift_optional_nullables
from lexic.parsing.pda.analysis.gates.ends.leads import (
    FIXED,
    FREE,
    FULL,
    MIXED,
    Lead,
    Reach,
    RunLeads,
    closed,
    lead_windows,
    merge,
)
from lexic.parsing.pda.analysis.gates.ends.sites import RunIndex
from lexic.parsing.pda.compiler.program.gating import flat_window, window_admits
from lexic.parsing.pda.core.charsets import CharSet

AZ = CharSet(frozenset("abcdefghijklmnopqrstuvwxyz"))
AZ09 = CharSet(frozenset("abcdefghijklmnopqrstuvwxyz0123456789"))
SEMI = CharSet.from_chars(";")


def _lead(follower: str, run: CharSet) -> Lead:
    """Rule ``head``'s own lead for ``run``, in a grammar holding ``follower``."""
    grammar = lift_optional_nullables(
        compile_text(f"root ::= head\n{follower}").codegen_grammar
    )
    rules = {str(rule.name): rule for rule in grammar.rules}
    callees = RunIndex(rules, "root", False).callees
    return RunLeads(rules, callees, run).rule("head").lead


def _semi(lead: Lead) -> Reach:
    """The reach of ``;`` in ``lead``."""
    found = [reach for chars, reach in lead.marks if chars.has(";")]
    assert len(found) == 1, lead
    return found[0]


@pytest.mark.parametrize(
    ("follower", "run", "reach"),
    [
        ('head ::= [a-z]+ ";"\n', AZ, Reach(1, FREE)),
        ('head ::= [a-z] [a-z]* ";"\n', AZ, Reach(1, FREE)),
        ('head ::= [a-z] [a-z] ";"\n', AZ, Reach(2, FULL)),
        ('head ::= "ab" ";"\n', AZ, Reach(2, FIXED)),
        ('head ::= ";"\n', AZ, Reach(0, FULL)),
    ],
    ids=["plus", "one-then-star", "two-classes", "literal", "bare"],
)
def test_a_closed_follower_keeps_its_exact_reach(
    follower: str, run: CharSet, reach: Reach
) -> None:
    """Every derivation reaching ``;`` does so at one ``j``, or after every
    class string of length ``j`` or more."""
    lead = _lead(follower, run)
    assert _semi(lead) == reach
    assert closed(lead)


@pytest.mark.parametrize(
    ("follower", "run", "j"),
    [
        ('head ::= [a-z]* "x" ";"\n', AZ, 1),
        ('head ::= [0-9] [a-z]* ";"\n', AZ09, 1),
        ('head ::= [0-9] ";" | [a-z] [a-z] ";"\n', AZ09, 1),
        ('head ::= [a-z] ";" "!" | [a-z] [a-z] ";" "?"\n', AZ, 1),
        ('head ::= x? ";"\nx ::= [a-z]\n', AZ, 0),
    ],
    ids=["star-then-x", "digit-then-star", "two-lengths", "two-tails", "optional"],
)
def test_an_unclosed_follower_is_mixed_never_its_minimum(
    follower: str, run: CharSet, j: int
) -> None:
    """A restricted prefix of varying length, or ``;`` reached at two lengths,
    is MIXED: leaving its minimum would prune a reading that parses — on
    ``q5ab;`` the digit-led one needs ``5ab``, and on ``qab;?`` the two-tailed
    one needs ``ab``."""
    lead = _lead(follower, run)
    assert _semi(lead) == Reach(j, MIXED)
    assert not closed(lead)
    assert lead_windows(run, lead) is None


def test_two_derivations_at_one_length_stay_closed() -> None:
    """Two ways to reach ``;`` at the same ``j`` agree on where the run stops."""
    a = Lead(((SEMI, Reach(1, FULL)),), None)
    b = Lead(((SEMI, Reach(1, FIXED)),), None)
    assert _semi(merge(a, b)) == Reach(1, FULL)


def test_two_derivations_at_two_lengths_are_mixed_at_the_shorter() -> None:
    """``;`` after one character in one follower and two in another."""
    a = Lead(((SEMI, Reach(1, FULL)),), None)
    b = Lead(((SEMI, Reach(2, FULL)),), None)
    assert _semi(merge(a, b)) == Reach(1, MIXED)


def _admits(windows: tuple[tuple[CharSet, ...], ...], text: str, pos: int) -> bool:
    """Whether the loop gate built from ``windows`` takes ``text[pos]``."""
    return window_admits(text, pos, tuple(flat_window(win) for win in windows))


def test_the_gate_leaves_exactly_the_closed_reach_before_its_character() -> None:
    """``;`` at FREE(1): every run character is taken but the last before ``;``;
    a run ending at ``,`` or at the end of the input is taken whole."""
    comma = CharSet.from_chars(",")
    lead = Lead(((SEMI, Reach(1, FREE)), (comma, Reach(0, FULL))), Reach(0, FULL))
    windows = lead_windows(AZ, lead)
    assert windows is not None
    assert [_admits(windows, "abc;", pos) for pos in range(3)] == [True, True, False]
    assert all(_admits(windows, "abc,", pos) for pos in range(3))
    assert all(_admits(windows, "abc", pos) for pos in range(3))


def test_the_gate_is_as_wide_as_the_largest_closed_reach() -> None:
    """No width is fixed: ``;`` at FULL(3) reads four characters."""
    windows = lead_windows(AZ, Lead(((SEMI, Reach(3, FULL)),), None))
    assert windows is not None
    assert max(len(win) for win in windows) == 4
    assert [_admits(windows, "abcde;", pos) for pos in range(3)] == [True, True, False]


def test_a_lead_no_follower_needs_any_of_the_run_from_builds_no_gate() -> None:
    """Every ending character at ``j = 0``: the run is taken whole."""
    assert lead_windows(AZ, Lead(((SEMI, Reach(0, FULL)),), Reach(0, FULL))) is None
    assert lead_windows(AZ, None) is None
