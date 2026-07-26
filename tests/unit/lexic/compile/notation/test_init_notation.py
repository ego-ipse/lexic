"""Tests for ``lexic.compile.notation.__init__``: the package surface.

The defect this pins: the package called itself "the notation surface" and bound
nothing, so its docstring advertised three things no import could reach.
"""

from __future__ import annotations

import re

from lexic.compile import notation
from lexic.compile.notation.emit import emit_ir as _emit_ir
from lexic.compile.notation.loader import load_flavour as _load_flavour
from lexic.compile.notation.parse import load_ir as _load_ir
from lexic.ir.base import IrStr, IrTuple

_DOC_NAME = re.compile(r"``([A-Za-z_][A-Za-z0-9_]*)``")


def test_module_has_all() -> None:
    """The package declares its surface."""
    assert hasattr(notation, "__all__")


def test_all_names_importable() -> None:
    """Every name in ``__all__`` is bound."""
    for name in notation.__all__:
        assert hasattr(notation, name), f"lexic.compile.notation is missing {name!r}"


def test_docstring_advertises_exactly_the_surface() -> None:
    """Every ``name`` the docstring quotes is in ``__all__``, and vice versa.

    A docstring naming a symbol the module does not bind is the whole B5 defect,
    and the only way it stays fixed is if the two are pinned to each other. The
    quoting convention is what makes this checkable: a symbol is written in
    double backticks, prose is not.
    """
    quoted = set(_DOC_NAME.findall(notation.__doc__ or ""))
    assert quoted == set(notation.__all__)


def test_surface_binds_both_halves_and_the_manifest_loader() -> None:
    """The three things the package is named for resolve to the real functions."""
    assert notation.load_ir is _load_ir
    assert notation.emit_ir is _emit_ir
    assert notation.load_flavour is _load_flavour


def test_surface_round_trips_through_itself() -> None:
    """The two halves are inverses, reached through the package alone."""
    value = IrTuple(IrStr("a"), (IrStr("b"),))
    assert notation.load_ir(notation.emit_ir(value)) == value
