"""The codec table resolves every spine class, or refuses naming the tie.

This is the test the table may not land without. Its failure mode is the
opposite of the ladder's: an unmapped spine base does not raise, it decodes as a
childless unit — and the export fixpoint PASSES, because an empty value
re-encodes to itself. Measured on a real grammar AST, that turns 51 strings into
0. So the guard is not "does it work on my fixtures" but "does every class the
spine can produce resolve to exactly one row".
"""

from __future__ import annotations

import decimal
import importlib
import inspect
import pkgutil

import pytest

from lexic import ir
from lexic.compile.payload.codec import ROWS, row_for
from lexic.compile.payload.reader import DECODE
from lexic.exceptions import UnsupportedConstructError
from lexic.ir.base import IrSelf
from lexic.ir.nodes import IrLiteral


def _spine_classes() -> list[type]:
    """Every ``IrSelf`` subclass in every ``lexic.ir`` module.

    Enumerated from the package rather than from a hand-written list, so a new
    spine module joins the sweep by existing — a list I maintain is a list that
    stops finding things.
    """
    seen: dict[str, type] = {}
    for info in pkgutil.walk_packages(ir.__path__, "lexic.ir."):
        module = importlib.import_module(info.name)
        for name, value in vars(module).items():
            if inspect.isclass(value) and issubclass(value, IrSelf):
                seen[f"{value.__module__}.{name}"] = value
    return sorted(seen.values(), key=lambda c: f"{c.__module__}.{c.__name__}")


def test_every_spine_class_resolves_to_exactly_one_row() -> None:
    """Order-free: no class ties between two rows, and none is unclaimed.

    A tie is not an error the caller made — it means the table is missing a row,
    and the message says which claims collided so the fix is obvious.
    """
    classes = _spine_classes()
    assert len(classes) > 100, "the sweep stopped finding the spine"
    unresolved: list[str] = []
    for cls in classes:
        try:
            row_for(cls, {})
        except UnsupportedConstructError as exc:
            unresolved.append(f"{cls.__name__}: {exc}")
    assert not unresolved, unresolved


def test_resolution_does_not_depend_on_declaration_order() -> None:
    """The rule is *most derived*, not *first hit*.

    First-hit MRO would answer differently for every scalar, because the spine
    declares ``class IrStr(IrScalar, str)`` and so puts ``IrSelf`` ahead of
    ``str``. The property is that the answer cannot depend on where a row sits.
    """
    memo: dict = {}
    row = row_for(IrLiteral, memo)
    assert row.kind == ROWS[0].kind, "a string leaf must resolve to the string row"


def test_a_type_no_row_claims_refuses() -> None:
    """The raising default — the vocabulary is closed, and says so."""
    with pytest.raises(UnsupportedConstructError, match="not payload"):
        row_for(decimal.Decimal, {})


def test_every_row_names_a_reader_function() -> None:
    """One row declares BOTH directions, so a kind cannot exist on one side.

    This is what the table buys over a ladder: the encoder's branches and the
    reader's used to be two lists kept in step by hand.
    """
    for row in ROWS:
        assert callable(row.decode), row
        if row.kind >= 0:
            assert DECODE[row.kind] is row.decode, row


def test_the_kind_space_is_exactly_the_reader_s() -> None:
    """Every readable kind is written by exactly one row, and vice versa."""
    written = sorted(row.kind for row in ROWS if row.kind >= 0)
    assert written == list(range(len(DECODE)))


def test_the_public_surface_names_no_row_the_table_cannot_resolve() -> None:
    """Whatever ``lexic.ir`` exports, a payload can name."""
    for name in ir.__all__:
        value = getattr(ir, name)
        if inspect.isclass(value) and issubclass(value, IrSelf):
            row_for(value, {})
