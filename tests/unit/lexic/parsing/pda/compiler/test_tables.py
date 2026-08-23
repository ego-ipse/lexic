"""Tests for lexic.parsing.pda.compiler.tables — PdaTables, the compiled
predictive-parser artifact.

The clone table's own shape (islands, cloning residue) is pinned in depth in
``tests/unit/lexic/parsing/pda/compiler/test_clones.py``; this file targets
``PdaTables``'s own accessor surface: ``islands``, ``island_tables``'s cache,
``island_delegates``, and ``reset_delegate_cache``.
"""

from __future__ import annotations

from lexic.parsing.earley.kernel.tables.records import ParserTables
from lexic.parsing.pda.compiler.program.flatten import PdaProgram
from tests.unit.lexic.parsing.pda.compiler.test_clones import pda_from_text

LEFT_RECURSIVE = 'root ::= x\nx ::= x "a" | "b"\n'


def test_program_and_clones_are_populated_after_compilation():
    """A trivial grammar still yields a real program and a non-empty clone table."""
    pda = pda_from_text('root ::= "x"\n')
    assert isinstance(pda.program, PdaProgram)
    assert pda.clones  # at least the root clone


def test_islands_is_the_island_follow_key_set():
    """``islands`` is derived from ``island_follow``, not stored separately."""
    pda = pda_from_text(LEFT_RECURSIVE)
    assert pda.islands == frozenset(pda.island_follow.keys())
    assert "x" in pda.islands


def test_island_tables_returns_a_parser_tables_instance():
    """The Earley sub-parser tables for an island rule."""
    pda = pda_from_text(LEFT_RECURSIVE)
    tables = pda.island_tables("x")
    assert isinstance(tables, ParserTables)


def test_island_tables_is_memoised_by_identity_per_name():
    """Repeat calls for the same name return the identical object."""
    pda = pda_from_text(LEFT_RECURSIVE)
    first = pda.island_tables("x")
    second = pda.island_tables("x")
    assert first is second


def test_island_tables_differs_by_packing_tier():
    """Different packing tiers compile distinct tables, even for the same rule."""
    pda = pda_from_text(LEFT_RECURSIVE)
    small = pda.island_tables("x", bits=8)
    default = pda.island_tables("x")
    assert small is not default


def test_island_delegates_is_empty_when_nothing_delegates():
    """An island with no delegable interior clones returns an empty dict."""
    pda = pda_from_text('root ::= "x"\n')
    assert pda.island_delegates("nonexistent") == {}


def test_reset_delegate_cache_does_not_raise():
    """The cache-reset seam is safe to call even after populating the cache."""
    pda = pda_from_text(LEFT_RECURSIVE)
    pda.island_delegates("x")
    pda.reset_delegate_cache()  # must not raise, whether or not anything delegated
