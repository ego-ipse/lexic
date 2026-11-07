"""Tests for the table primitives — packing tiers, atom expansion, run terminals."""

from __future__ import annotations

import pytest

from lexic.exceptions import UnsupportedConstructError
from lexic.ir import (
    IrAlphabet,
    IrAlternation,
    IrAst,
    IrCharClass,
    IrChr,
    IrLiteral,
    IrNone,
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
    Spans,
    atom_accepts,
    atom_unit,
    expand_atom,
    may_begin_within,
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


# ── may_begin_within: the run proof's question, on unit classes ───────

A_TO_Z = IrCharClass(IrRange(IrChr("a"), IrChr("z")))


def _unit(chars: str) -> IrCharClass:
    return IrCharClass.from_intervals((ord(c), ord(c)) for c in chars)


def test_a_class_meets_a_unit_at_either_bound():
    """``[a-z]`` meets ``{z}`` and ``{a}`` at its edges and misses ``{`, {}``."""
    assert may_begin_within(A_TO_Z, _unit("z"))
    assert may_begin_within(A_TO_Z, _unit("a"))
    assert not may_begin_within(A_TO_Z, _unit("`{"))


def test_a_negated_class_meets_what_its_inner_class_leaves_out():
    """``[^a-z]`` misses a unit inside a-z and meets one partly or wholly outside."""
    negated = IrNot(A_TO_Z)
    assert not may_begin_within(negated, _unit("az"))
    assert may_begin_within(negated, _unit("a0"))
    assert may_begin_within(negated, _unit("09"))


def test_a_wide_class_is_asked_by_its_bounds_not_its_members():
    """U+0100..U+10FFFF holds ``ā`` and not ``z``: no member is ever listed."""
    wide = IrCharClass(IrRange(IrChr(chr(0x100)), IrChr(chr(0x10FFFF))))
    assert may_begin_within(wide, _unit("\u0101"))
    assert not may_begin_within(wide, _unit("z"))


def test_a_co_finite_unit_is_met_by_anything_but_its_exclusions():
    """``[^"]`` as the unit: a quote follower misses it, a letter meets it."""
    unit = IrCharClass(IrChr('"')).complement()
    assert not may_begin_within(IrLiteral('"x'), unit)
    assert may_begin_within(IrLiteral("x"), unit)
    assert may_begin_within(IrNot(_unit('"')), unit)


def test_a_literal_meets_by_its_first_character_and_the_empty_one_never():
    """``"-x"`` begins with ``-``; ``"x-"`` does not; ``""`` begins with nothing."""
    dash = _unit("-")
    assert may_begin_within(IrLiteral("-x"), dash)
    assert not may_begin_within(IrLiteral("x-"), dash)
    assert not may_begin_within(IrLiteral(""), dash)


def test_a_token_may_begin_with_anything_though_the_char_scan_skips_it():
    """The run proof answers yes where the scan filter answers no."""
    token = IrAlphabet("tokens", IrLiteral("x"))
    assert may_begin_within(token, _unit("q"))
    assert not atom_accepts(token, "x")


def test_a_run_terminal_has_no_row_and_raises():
    """A RunTerm only appears in a collapsed layout, which no run proof reads."""
    run = RunTerm(frozenset("a"), 1, RUN_STR)
    with pytest.raises(UnsupportedConstructError):
        may_begin_within(run, _unit("a"))


# ── atom_unit and the run terminal's two polarities ───────────────────


def test_atom_unit_reads_a_negated_class_as_its_complement():
    """``[^"]`` is every code point but the quote; a char literal is itself."""
    unit = atom_unit(IrNot(IrCharClass(IrChr('"'))))
    assert isinstance(unit, IrCharClass)
    assert not unit.holds(ord('"')) and unit.holds(0) and unit.holds(0x10FFFF)
    assert atom_unit(IrLiteral("x")) == _unit("x")


def test_atom_unit_refuses_a_longer_literal_and_a_token():
    """Neither is a one-character unit."""
    assert atom_unit(IrLiteral("xy")) is IrNone
    assert atom_unit(IrAlphabet("tokens", IrLiteral("x"))) is IrNone


def test_a_run_over_a_co_finite_unit_lists_its_exclusions():
    """``[^"]``'s run keeps the one excluded quote, negated, and accepts by it."""
    run = RunTerm.over(IrCharClass(IrChr('"')).complement(), RUN_STR)
    assert (run.charset, run.negated) == (frozenset('"'), True)
    assert atom_accepts(run, "x")
    assert not atom_accepts(run, '"')


def test_a_run_over_a_narrow_unit_lists_its_members():
    """``[a-c]``'s run keeps its three members, positive."""
    run = RunTerm.over(_unit("abc"), RUN_STR)
    assert (run.charset, run.negated) == (frozenset("abc"), False)
    assert atom_accepts(run, "b") and not atom_accepts(run, "d")


def test_a_unit_too_large_on_both_sides_runs_on_its_ranges():
    """U+0000..U+7FFFF and its complement both exceed the listing cap, so the
    run tests membership by its bounds and lists no first characters."""
    half = IrCharClass(IrRange(IrChr(0), IrChr(0x7FFFF)), IrChr(0x90000))
    run = RunTerm.over(half, RUN_STR)
    assert run.charset == Spans(((0, 0x7FFFF), (0x90000, 0x90000)))
    assert chr(0) in run.charset and chr(0x7FFFF) in run.charset
    assert chr(0x80000) not in run.charset and chr(0x90000) in run.charset
    assert chr(0x90001) not in run.charset
    assert run.first_chars is None and not run.negated


def test_only_a_positive_listed_run_names_its_first_characters():
    """A narrow run lists them; a negated one has too many to list."""
    assert RunTerm.over(_unit("ab"), RUN_STR).first_chars == frozenset("ab")
    negated = RunTerm.over(IrCharClass(IrChr('"')).complement(), RUN_STR)
    assert negated.first_chars is None
