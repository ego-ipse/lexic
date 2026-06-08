"""Operator-algebra nodes — ``lexic.ir.operators``.

Covers the operator leaf :class:`IrOp` (``_OPS`` dispatch, arity per operator),
the arity bases :class:`MonadicOp`/:class:`DyadicOp`/:class:`VariadicOp` (each
encodes operand count in its ``body`` type), and the fixed-operator nodes
:class:`IrEq`, :class:`IrAnd`, :class:`IrNot`. Node shape is ``(body, op)``
with ``op`` defaulted; ``eval`` is shared on :class:`IrOpNode`.
"""

from __future__ import annotations

import pytest

from lexic.exceptions import UnsupportedConstructError
from lexic.ir.action import IrCallable, IrCompare
from lexic.ir.base import IrAtom, IrInt, IrNone, IrSelf, IrSeq, IrStr, IrTuple
from lexic.ir.operators import (
    DyadicOp,
    IrAnd,
    IrEq,
    IrNot,
    IrOp,
    IrOpNode,
    MonadicOp,
    VariadicOp,
)

# ── IrOp ──────────────────────────────────────────────────────────────


def test_irop_is_irstr_subclass():
    """IrOp is an IrStr (and therefore a str) — the node IS the operator string."""
    op = IrOp(">")
    assert isinstance(op, IrStr)
    assert isinstance(op, str)
    assert op == ">"


def test_irop_eval_applies_gt():
    """IrOp('>').eval with operands (5, 3) returns IrInt(1)."""
    result = IrOp(">").eval(IrNone, IrNone, [IrInt(5), IrInt(3)])
    assert result == IrInt(1)
    assert isinstance(result, IrInt)


def test_irop_eval_applies_lt_false():
    """IrOp('<').eval with operands (3, 5) returns IrInt(1); reversed returns IrInt(0)."""
    assert IrOp("<").eval(IrNone, IrNone, [IrInt(3), IrInt(5)]) == IrInt(1)
    assert IrOp("<").eval(IrNone, IrNone, [IrInt(5), IrInt(3)]) == IrInt(0)


def test_irop_eval_applies_eq():
    """IrOp('==').eval returns IrInt(1) when operands are equal."""
    assert IrOp("==").eval(IrNone, IrNone, [IrInt(7), IrInt(7)]) == IrInt(1)
    assert IrOp("==").eval(IrNone, IrNone, [IrInt(7), IrInt(8)]) == IrInt(0)


def test_irop_eval_applies_not_unary():
    """IrOp('!').eval with a single operand applies operator.not_."""
    assert IrOp("!").eval(IrNone, IrNone, [IrInt(1)]) == IrInt(0)
    assert IrOp("!").eval(IrNone, IrNone, [IrInt(0)]) == IrInt(1)


def test_irop_and_is_variadic_all_fold():
    """IrOp('&') folds operands with ``all`` — any arity, empty is the identity."""
    assert IrOp("&").eval(IrNone, IrNone, [IrInt(1), IrInt(1), IrInt(1)]) == IrInt(1)
    assert IrOp("&").eval(IrNone, IrNone, [IrInt(1), IrInt(0)]) == IrInt(0)
    assert IrOp("&").eval(IrNone, IrNone, []) == IrInt(1)


def test_irop_or_is_variadic_any_fold():
    """IrOp('|') folds operands with ``any`` — any arity, empty is the identity."""
    assert IrOp("|").eval(IrNone, IrNone, [IrInt(0), IrInt(1)]) == IrInt(1)
    assert IrOp("|").eval(IrNone, IrNone, [IrInt(0), IrInt(0)]) == IrInt(0)
    assert IrOp("|").eval(IrNone, IrNone, []) == IrInt(0)


def test_irop_unknown_operator_raises():
    """IrOp with an unrecognised operator string raises UnsupportedConstructError."""
    with pytest.raises(UnsupportedConstructError):
        IrOp("??").eval(IrNone, IrNone, [IrInt(1), IrInt(2)])


def test_irop_repr_is_codegen():
    """repr(IrOp('>')) reproduces the constructor call."""
    assert repr(IrOp(">")) == "IrOp('>')"


# ── Arity bases ───────────────────────────────────────────────────────


def test_iropnode_is_irtuple_and_atom():
    """An operator node is an IrTuple (so a tuple) and an IrAtom."""
    node = DyadicOp(IrTuple(IrInt(5), IrInt(3)), IrOp(">"))
    assert isinstance(node, IrTuple)
    assert isinstance(node, tuple)
    assert isinstance(node, IrAtom)
    assert isinstance(node, IrOpNode)


def test_body_op_are_the_two_fields_in_order():
    """Fields are ``(body, op)``: body at [0], op at [1]."""
    body, op = IrTuple(IrInt(5), IrInt(3)), IrOp(">")
    node = DyadicOp(body, op)
    assert node._fields == ("body", "op")
    assert node.body is node[0] is body
    assert node.op is node[1] is op


def test_monadic_op_eval_applies_unary_operator():
    """MonadicOp wraps its single body operand and applies the operator to it."""
    node = MonadicOp(IrTuple(IrInt(1)), IrOp("!"))
    assert node.body == (IrInt(1),)
    assert node.eval(IrNone, IrNone, ()) == IrInt(0)


def test_dyadic_op_eval_applies_binary_operator():
    """DyadicOp evaluates its two-operand body and applies the operator."""
    node = DyadicOp(IrTuple(IrInt(5), IrInt(3)), IrOp(">"))
    assert tuple(node.body) == (IrInt(5), IrInt(3))
    assert node.eval(IrNone, IrNone, ()) == IrInt(1)


def test_variadic_op_eval_folds_operand_sequence():
    """VariadicOp folds its whole IrSeq body through the operator."""
    node = VariadicOp(IrSeq(IrInt(1), IrInt(1), IrInt(0)), IrOp("&"))
    assert tuple(node.body) == (IrInt(1), IrInt(1), IrInt(0))
    assert node.eval(IrNone, IrNone, ()) == IrInt(0)


def test_dyadic_op_repr_is_codegen():
    """repr(DyadicOp(...)) reproduces the (body, op) constructor call."""
    node = DyadicOp(IrTuple(IrInt(5), IrInt(3)), IrOp(">"))
    assert repr(node) == "DyadicOp(IrTuple(IrInt(5), IrInt(3)), IrOp('>'))"


# ── IrEq ──────────────────────────────────────────────────────────


def test_eqopnode_is_dyadic_with_eq_operator():
    """IrEq is a DyadicOp whose operator defaults to ``IrOp("==")``."""
    node = IrEq(IrTuple(IrInt(7), IrInt(7)))
    assert isinstance(node, DyadicOp)
    assert node.op == IrOp("==")
    assert node._fields == ("body", "op")


def test_eqopnode_equal_operands_yield_one():
    """Equal operands ⇒ IrInt(1)."""
    result = IrEq(IrTuple(IrInt(7), IrInt(7))).eval(IrNone, IrNone, ())
    assert result == IrInt(1)
    assert isinstance(result, IrInt)


def test_eqopnode_unequal_operands_yield_zero():
    """Unequal operands ⇒ IrInt(0)."""
    assert IrEq(IrTuple(IrInt(7), IrInt(8))).eval(IrNone, IrNone, ()) == IrInt(0)


def test_eqopnode_repr_round_trips():
    """repr(IrEq(...)) reproduces the (body, op) constructor call."""
    node = IrEq(IrTuple(IrInt(7), IrInt(7)))
    assert repr(node) == "IrEq(IrTuple(IrInt(7), IrInt(7)), IrOp('=='))"


# ── IrAnd ─────────────────────────────────────────────────────────────


def test_irand_is_variadic_with_and_operator():
    """IrAnd is a VariadicOp whose operator defaults to ``IrOp("&")``."""
    a = IrAnd()
    assert isinstance(a, VariadicOp)
    assert a.op == IrOp("&")
    assert a._fields == ("body", "op")


def test_irand_all_true_yields_one():
    """Every operand truthy ⇒ IrInt(1)."""
    a = IrAnd(
        IrSeq(
            IrCompare(IrInt(1), IrOp("=="), IrInt(1)),
            IrCompare(IrInt(2), IrOp(">"), IrInt(1)),
        )
    )
    result = a.eval(IrNone, IrNone, ())
    assert result == IrInt(1)
    assert isinstance(result, IrInt)


def test_irand_one_false_yields_zero():
    """A single falsy operand ⇒ IrInt(0)."""
    a = IrAnd(
        IrSeq(
            IrCompare(IrInt(1), IrOp("=="), IrInt(1)),
            IrCompare(IrInt(1), IrOp("=="), IrInt(0)),
        )
    )
    assert a.eval(IrNone, IrNone, ()) == IrInt(0)


def test_irand_empty_is_vacuously_true():
    """An empty conjunction is the fold identity ⇒ IrInt(1)."""
    assert IrAnd().eval(IrNone, IrNone, ()) == IrInt(1)


def test_irand_evaluates_every_operand_eagerly():
    """IrAnd folds with ``all`` — every operand is evaluated, no short-circuit."""
    calls: list[int] = []

    def _record(_d: IrSelf, _n: IrSelf, _nc: object) -> IrInt:
        calls.append(1)
        return IrInt(1)

    a = IrAnd(
        IrSeq(
            IrCompare(IrInt(1), IrOp("=="), IrInt(0)),
            IrCallable[IrSelf, IrInt](_record),
        )
    )
    assert a.eval(IrNone, IrNone, ()) == IrInt(0)
    assert calls == [1]


def test_irand_repr_round_trips():
    """repr(IrAnd(...)) reproduces the (body, op) constructor call."""
    a = IrAnd(IrSeq(IrInt(1)))
    assert repr(a) == "IrAnd(IrSeq(IrInt(1)), IrOp('&'))"


# ── IrNot ─────────────────────────────────────────────────────────────


def test_irnot_is_monadic_atom_with_not_operator():
    """IrNot is a MonadicOp and an IrAtom; its operator defaults to ``IrOp("!")``."""
    n = IrNot(IrInt(1))
    assert isinstance(n, MonadicOp)
    assert isinstance(n, IrAtom)
    assert n.op == IrOp("!")
    assert n._fields == ("body", "op")


def test_irnot_eval_negates_truthy_body():
    """IrNot over a truthy operand evals to IrInt(0)."""
    result = IrNot(IrInt(1)).eval(IrNone, IrNone, ())
    assert result == IrInt(0)
    assert isinstance(result, IrInt)


def test_irnot_eval_negates_falsy_body():
    """IrNot over a falsy operand evals to IrInt(1)."""
    assert IrNot(IrInt(0)).eval(IrNone, IrNone, ()) == IrInt(1)


def test_irnot_repr_round_trips():
    """repr(IrNot(...)) reproduces the (body, op) constructor call."""
    assert repr(IrNot(IrInt(1))) == "IrNot(IrInt(1), IrOp('!'))"
