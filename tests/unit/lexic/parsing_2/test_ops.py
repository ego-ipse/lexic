"""Tests for lexic.parsing_2.ops — Predict/Scan/Complete and EARLEY_OPS.

API changes:

- ``ParseCtx.nullable`` is now an ``IrSeq`` (was ``frozenset``).  The test that
  constructed ``ParseCtx`` with a ``frozenset`` is updated to pass ``IrSeq()``.
"""

from __future__ import annotations

from lexic.ir.base import IrNone, IrSeq
from lexic.ir.mapping import IrMap, IrTypeMap
from lexic.ir.nodes import IrCharClass, IrLiteral, IrRange, IrRuleRef, IrSequence
from lexic.parsing_2.chart import Chart
from lexic.parsing_2.item import EarleyItem
from lexic.parsing_2.ops import EARLEY_OPS, Complete, ParseCtx, Predict, Scan

# ── EARLEY_OPS dispatch table ─────────────────────────────────────────


def test_earley_ops_is_ir_type_map():
    """EARLEY_OPS is an IrTypeMap."""
    assert isinstance(EARLEY_OPS, IrTypeMap)


def test_earley_ops_irruleref_resolves_to_predict():
    """IrRuleRef symbol → Predict."""
    assert isinstance(EARLEY_OPS.resolve(IrRuleRef("x")), Predict)


def test_earley_ops_irliteral_resolves_to_scan():
    """IrLiteral symbol → Scan."""
    assert isinstance(EARLEY_OPS.resolve(IrLiteral("a")), Scan)


def test_earley_ops_ircharclass_resolves_to_scan():
    """IrCharClass symbol → Scan."""
    assert isinstance(EARLEY_OPS.resolve(IrCharClass(IrRange("a", "z"))), Scan)


def test_earley_ops_irrange_resolves_to_scan():
    """IrRange symbol → Scan."""
    assert isinstance(EARLEY_OPS.resolve(IrRange("a", "z")), Scan)


def test_earley_ops_irnone_resolves_to_complete():
    """IrNone (IrNoneType) symbol → Complete (dot-past-end sentinel)."""
    assert isinstance(EARLEY_OPS.resolve(IrNone), Complete)


# ── ParseCtx fields ───────────────────────────────────────────────────


def test_parse_ctx_has_nullable_field():
    """ParseCtx declares a 'nullable' field for Aycock-Horspool."""
    annotations = getattr(ParseCtx, "__annotations__", {})
    assert "nullable" in annotations


def test_parse_ctx_child_attrs_is_empty():
    """ParseCtx walks no children — context is engine state, not grammar.

    ``nullable`` is now an ``IrSeq`` (was ``frozenset``).
    """
    ctx = ParseCtx(
        Chart(),
        IrMap(),
        "",
        0,
        EarleyItem(IrRuleRef("r"), IrSequence(), 0, 0),
        IrSeq(),
    )
    assert not ctx.children()
