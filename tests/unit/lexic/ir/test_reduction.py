"""Tests for lexic.ir.reduction — declarative reduction data and contribution
policies.

The compile-layer fold that drives these against real parses lives in
``tests/unit/lexic/compile/reduce/test_fold.py``; this file pins the four
policy singletons and ``Reducer.body`` in isolation.
"""

from __future__ import annotations

from lexic.ir import IR_DEFAULT, IrMap, IrRuleRef, IrStr, IrTuple
from lexic.ir.reduction import (
    DROP,
    KEEP_RAW,
    KEEP_REDUCED,
    YIELD,
    Drop,
    KeepRaw,
    KeepReduced,
    Reducer,
    Yield,
)


def test_drop_contributes_nothing():
    """DROP's channel is always empty."""
    assert DROP.eval(DROP, IrStr("x"), ()) == IrTuple()


def test_keep_raw_contributes_the_node_unchanged():
    """KEEP_RAW passes the node through as its one-element channel."""
    node = IrStr("x")
    assert KEEP_RAW.eval(KEEP_RAW, node, ()) == IrTuple(node)


def test_keep_reduced_dispatches_through_the_outer_dispatcher():
    """``KEEP_REDUCED`` calls back into ``d.eval`` rather than returning the
    node as-is — it channels the DISPATCHER'S interpretation."""
    reducer = Reducer(actions=IrMap(IrTuple(IR_DEFAULT, IrStr("interpreted"))))
    node = IrStr("x")
    assert KEEP_REDUCED.eval(reducer, node, ()) == IrTuple(IrStr("interpreted"))


def test_yield_returns_the_str_view_of_the_node():
    """YIELD returns the node's text view, wrapped in IrStr."""
    assert YIELD.eval(YIELD, IrStr("hello"), ()) == IrStr("hello")


def test_the_singletons_are_true_singletons():
    """Each policy class always returns the same module-level instance."""
    assert Drop() is DROP
    assert KeepRaw() is KEEP_RAW
    assert KeepReduced() is KEEP_REDUCED
    assert Yield() is YIELD


def test_reducer_body_returns_the_explicit_action_for_a_mapped_symbol():
    """A symbol present in ``actions`` returns its mapped body."""
    reducer = Reducer(
        actions=IrMap(IrTuple(IrRuleRef("digit"), IrStr("mapped"))), default=YIELD
    )
    assert reducer.body(IrRuleRef("digit")) == IrStr("mapped")


def test_reducer_body_falls_back_to_default_for_an_unmapped_symbol():
    """A symbol absent from ``actions`` falls back to ``default``."""
    reducer = Reducer(actions=IrMap(), default=DROP)
    assert reducer.body(IrRuleRef("unmapped")) is DROP


def test_reducer_defaults_are_keep_reduced_noise_and_keep_raw_literal():
    """The class-level defaults ``Reducer`` declares when a caller supplies
    neither ``noise`` nor ``literal``."""
    reducer = Reducer(actions=IrMap())
    assert reducer.noise == IrMap(IrTuple(IR_DEFAULT, KEEP_REDUCED))
    assert reducer.literal is KEEP_RAW
