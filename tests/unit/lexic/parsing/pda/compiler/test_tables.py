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
from tests.unit.lexic.parsing.pda.compiler.test_clones import (
    pda_from_text,
    specs_from_text,
)

LEFT_RECURSIVE = 'root ::= x\nx ::= y "a" | "b"\ny ::= x\n'
"""INDIRECT left recursion — `x` reaches itself through `y`.

Direct left recursion no longer islands: the fold rewrites `A ::= A β | γ` to
`(γ)(β)*` and builds the model back
(:mod:`lexic.parsing.pda.compiler.leftrec.rewrite`). What still islands is the
recursion the fold refuses, and this is the smallest such shape — a fixture for
island behaviour has to be one the fold does not take, or it pins nothing."""


def test_program_and_clones_are_populated_after_compilation():
    """A trivial grammar still yields a real program, and real clones behind it."""
    pda = pda_from_text('root ::= "x"\n')
    assert isinstance(pda.program, PdaProgram)
    assert specs_from_text('root ::= "x"\n').clones  # at least the root clone


def test_the_artefact_does_not_carry_the_authored_clone_specs():
    """The specs are a compile-time intermediate and do not survive lowering.

    Holding them beside the program kept a fifth to two fifths of the
    artefact's GC-tracked population alive with nothing reading it, so the
    absence is the point and belongs in a test rather than only in a docstring.
    """
    pda = pda_from_text('root ::= "x"\n')
    assert not hasattr(pda, "clones")
    assert "clones" not in type(pda).__slots__


def test_islands_is_the_compilers_island_set():
    """``islands`` is the compiler's residue, carried as a plain set.

    It used to be the key set of a per-island FOLLOW map. The values of that
    map were the seam's two-ends evidence and are now wrong for the job — the
    set a two-ends check needs is what the island's REFERENCES are followed
    by — so the evidence moved onto the reference and the map became a dict
    nothing read the values of.
    """
    pda = pda_from_text(LEFT_RECURSIVE)
    assert not hasattr(pda, "island_follow")
    assert isinstance(pda.islands, frozenset)
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
