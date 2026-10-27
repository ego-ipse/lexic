"""Tests for lexic.ir.grammar.__init__ — the group's share of the ``lexic.ir`` surface.

The marker holds ``SURFACE``, every name the grammar group puts on the façade and
the module that defines it; the façade's lazy lookup is built from it. The
façade-wide agreements (the ``TYPE_CHECKING`` block, ``__all__``, resolution)
are pinned in ``tests/unit/lexic/ir/test_init_ir.py``.
"""

from __future__ import annotations

import ast as pyast

from lexic.ir import grammar
from tests.paths import PROJECT_ROOT


def test_the_grammar_surface_names_only_grammar_modules() -> None:
    """The group states where its own names live, and no other group's."""
    strays = {
        n: h
        for n, h in grammar.SURFACE.items()
        if not h.startswith("lexic.ir.grammar.")
    }
    assert not strays


def test_the_grammar_surface_records_irranges_home() -> None:
    """One concrete row — a range lives with the character-set node."""
    assert grammar.SURFACE["IrRange"] == "lexic.ir.grammar.charclass"


def test_the_grammar_marker_imports_nothing() -> None:
    """Python runs this marker before any grammar submodule, so whatever it imported
    every consumer of the group would pay: the surface is data only."""
    source = (PROJECT_ROOT / "src/lexic/ir/grammar/__init__.py").read_text("utf-8")
    grammar_imports = [
        node.lineno
        for node in pyast.walk(pyast.parse(source))
        if isinstance(node, (pyast.Import, pyast.ImportFrom))
    ]
    assert not grammar_imports
