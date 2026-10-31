"""Tests for lexic.ir.spine.__init__ — the group's share of the ``lexic.ir`` surface.

The marker holds ``SURFACE``, every name the spine group puts on the façade and
the module that defines it; the façade's lazy lookup is built from it. The
façade-wide agreements (the ``TYPE_CHECKING`` block, ``__all__``, resolution)
are pinned in ``tests/unit/lexic/ir/test_init_ir.py``.
"""

from __future__ import annotations

import ast as pyast

from lexic.ir import spine
from tests.paths import PROJECT_ROOT


def test_the_spine_surface_names_only_spine_modules() -> None:
    """The group states where its own names live, and no other group's."""
    strays = {
        n: h for n, h in spine.SURFACE.items() if not h.startswith("lexic.ir.spine.")
    }
    assert not strays


def test_the_spine_surface_records_irnones_home() -> None:
    """One concrete row — the absence singleton lives with the spine bases."""
    assert spine.SURFACE["IrNone"] == "lexic.ir.spine.spine"


def test_the_spine_marker_imports_nothing() -> None:
    """Python runs this marker before any spine submodule, so whatever it imported
    every consumer of the group would pay: the surface is data only."""
    source = (PROJECT_ROOT / "src/lexic/ir/spine/__init__.py").read_text("utf-8")
    spine_imports = [
        node.lineno
        for node in pyast.walk(pyast.parse(source))
        if isinstance(node, (pyast.Import, pyast.ImportFrom))
    ]
    assert not spine_imports
