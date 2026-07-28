"""Tests for the table primitives — packing tiers, atom expansion, run terminals."""

from __future__ import annotations

import pytest

from lexic.exceptions import UnsupportedConstructError
from lexic.ir import (
    IrAlternation,
    IrAst,
    IrCharClass,
    IrChr,
    IrLiteral,
    IrNot,
    IrRange,
    IrRule,
    IrRuleRef,
    IrSeq,
    IrSequence,
)
from lexic.parsing.earley.kernel.tables.atoms import (
    TIERS,
    RunTerm,
    atom_accepts,
    expand_atom,
    tier_for,
)
from lexic.parsing.earley.kernel.tables.builder import build_tables
from lexic.parsing.earley.kernel.tables.records import (
    RUN_STR,
)


def test_atom_accepts_literal_matches_same_char():
    """A single-char IrLiteral accepts its own char."""
    assert atom_accepts(IrLiteral("x"), "x")


def test_atom_accepts_literal_rejects_other_char():
    """A single-char IrLiteral rejects a different char."""
    assert not atom_accepts(IrLiteral("x"), "y")


def test_atom_accepts_charclass_range_matches():
    """A range char-class accepts a char within bounds."""
    atom = IrCharClass(IrRange(IrChr("a"), IrChr("z")))
    assert atom_accepts(atom, "m")


def test_atom_accepts_charclass_range_rejects_outside():
    """A range char-class rejects a char outside bounds."""
    atom = IrCharClass(IrRange(IrChr("a"), IrChr("z")))
    assert not atom_accepts(atom, "0")


def test_atom_accepts_charclass_single_chr_matches():
    """A char-class with a bare IrChr element accepts that exact char."""
    atom = IrCharClass(IrChr("q"))
    assert atom_accepts(atom, "q")


def test_atom_accepts_charclass_single_chr_rejects_other():
    """A char-class with a bare IrChr element rejects any other char."""
    atom = IrCharClass(IrChr("q"))
    assert not atom_accepts(atom, "r")


def test_atom_accepts_negated_charclass_matches_char_outside_set():
    """A negated char-class accepts a char that is not in the inner set."""
    atom = IrNot(IrCharClass(IrChr('"')))
    assert atom_accepts(atom, "a")


def test_atom_accepts_negated_charclass_rejects_char_in_set():
    """A negated char-class rejects a char that is in the inner set."""
    atom = IrNot(IrCharClass(IrChr('"')))
    assert not atom_accepts(atom, '"')


def test_atom_accepts_negated_range_matches_char_outside_range():
    """A negated range accepts a char outside the inner range."""
    atom = IrNot(IrCharClass(IrRange(IrChr("a"), IrChr("z"))))
    assert atom_accepts(atom, "0")


def test_atom_accepts_negated_range_rejects_char_in_range():
    """A negated range rejects a char inside the inner range."""
    atom = IrNot(IrCharClass(IrRange(IrChr("a"), IrChr("z"))))
    assert not atom_accepts(atom, "m")


def test_atom_accepts_negated_non_charclass_raises():
    """An IrNot over anything but an IrCharClass raises."""
    with pytest.raises(UnsupportedConstructError):
        atom_accepts(IrNot(IrRuleRef("x")), "a")


def test_expand_atom_single_char_literal_returns_its_char():
    """A single-char IrLiteral expands to a one-char frozenset."""
    assert expand_atom(IrLiteral("a")) == frozenset("a")


def test_expand_atom_multichar_literal_returns_none():
    """A literal longer than one char is not a char-unit — poisoned."""
    assert expand_atom(IrLiteral("ab")) is None


def test_expand_atom_charclass_with_ranges_returns_charset():
    """A range char-class expands to every char in the range."""
    atom = IrCharClass(IrRange(IrChr("a"), IrChr("c")))
    assert expand_atom(atom) == frozenset("abc")


def test_expand_atom_charclass_with_bare_chr_returns_charset():
    """A char-class with a bare IrChr element expands to that one char."""
    atom = IrCharClass(IrChr("q"))
    assert expand_atom(atom) == frozenset("q")


def test_expand_atom_over_cap_range_poisons():
    """A range wider than the expansion cap poisons to None."""
    atom = IrCharClass(IrRange(IrChr(chr(0)), IrChr(chr(0x2000))))
    assert expand_atom(atom) is None


def test_expand_atom_ruleref_is_not_a_terminal_atom():
    """An IrRuleRef is never a char-unit — poisoned regardless of shape."""
    assert expand_atom(IrRuleRef("digit")) is None


def test_expand_atom_negated_charclass_poisons():
    """A negated char-class is not a positive char-unit — poisoned to None."""
    assert expand_atom(IrNot(IrCharClass(IrChr('"')))) is None


def test_run_term_arm_gate_is_the_run_charset():
    """A collapsed run-terminal arm's gate is the run's own charset."""
    run = RunTerm(frozenset("ab"), 1, RUN_STR)
    placeholder = IrRule("s", IrAlternation(IrSequence()))
    g = IrAst(rules=IrSeq(placeholder), start="s")
    tables = build_tables(g, runs={"s": (run, False)})
    s_rid = tables.decode.rule_ids["s"]
    ((_shifted, _sym, gate),) = tables.codes.rule_seed_gates[s_rid]
    assert gate == frozenset("ab")


def test_tier_for_picks_the_smallest_covering_tier():
    """tier_for returns the first TIERS entry with length < 2**bits."""
    assert tier_for(0) == TIERS[0]
    assert tier_for(2 ** TIERS[0] - 1) == TIERS[0]
    assert tier_for(2 ** TIERS[0]) == TIERS[1]


def test_tier_for_backstop_is_the_last_tier():
    """Beyond every tier's capacity the LAST tier returns — the kernel
    capacity raise stays the backstop."""
    assert tier_for(2 ** TIERS[-1]) == TIERS[-1]
    assert tier_for(2 ** (TIERS[-1] + 1)) == TIERS[-1]
