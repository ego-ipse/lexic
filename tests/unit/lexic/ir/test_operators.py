"""Operator-algebra nodes — ``lexic.ir.operators``.

Covers the operator leaf :class:`IrOp` (``_OPS`` dispatch, arity per operator),
the arity bases :class:`MonadicOp`/:class:`DyadicOp`/:class:`VariadicOp` (the
node IS its operand tuple), and the fixed-operator nodes :class:`IrEq`,
:class:`IrAnd`, :class:`IrNot`. Operands are constructed flat; ``op`` is a
type-level ``ClassVar`` and ``eval`` is shared on :class:`IrOpNode`.
"""

from __future__ import annotations

import pytest

from lexic.exceptions import UnsupportedConstructError
from lexic.ir.action import IrCompare
from lexic.ir.base import IrAtom, IrCallable, IrInt, IrNone, IrSelf, IrStr, IrTuple
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


class _Gt(DyadicOp):
    """Test-only binary operator node over ``>`` — a reusable DyadicOp shape."""

    __slots__ = ()
    op = IrOp(">")


def test_op_node_is_irtuple_and_atom():
    """An operator node is an IrTuple (so a tuple), an IrAtom, and an IrOpNode."""
    node = _Gt(IrInt(5), IrInt(3))
    assert isinstance(node, IrTuple)
    assert isinstance(node, tuple)
    assert isinstance(node, IrAtom)
    assert isinstance(node, IrOpNode)


def test_operands_are_the_flat_tuple_elements():
    """The node IS its operand tuple: operands are elements [0], [1], …"""
    node = _Gt(IrInt(5), IrInt(3))
    assert tuple(node) == (IrInt(5), IrInt(3))
    assert node[0] == IrInt(5)
    assert node[1] == IrInt(3)


def test_op_is_a_classvar_not_an_element():
    """``op`` is type-level — reachable on the class and instance, not a tuple element."""
    assert _Gt.op == IrOp(">")
    assert _Gt(IrInt(5), IrInt(3)).op == IrOp(">")
    assert tuple(_Gt(IrInt(5), IrInt(3))) == (IrInt(5), IrInt(3))


def test_dyadic_shape_eval_applies_its_operator():
    """A DyadicOp evaluates its two operands and applies its operator."""
    assert _Gt(IrInt(5), IrInt(3)).eval(IrNone, IrNone, ()) == IrInt(1)
    assert _Gt(IrInt(3), IrInt(5)).eval(IrNone, IrNone, ()) == IrInt(0)


def test_op_node_repr_is_flat_codegen():
    """repr lists only the operands (op is type-level, not an element)."""
    assert repr(_Gt(IrInt(5), IrInt(3))) == "_Gt(IrInt(5), IrInt(3))"


# ── IrNot (MonadicOp) ─────────────────────────────────────────────────


def test_irnot_is_monadic_atom_with_not_operator():
    """IrNot is a MonadicOp and an IrAtom; its operator is ``IrOp("!")``."""
    n = IrNot(IrInt(1))
    assert isinstance(n, MonadicOp)
    assert isinstance(n, IrAtom)
    assert n.op == IrOp("!")


def test_irnot_eval_negates_truthy_operand():
    """IrNot over a truthy operand evals to IrInt(0)."""
    result = IrNot(IrInt(1)).eval(IrNone, IrNone, ())
    assert result == IrInt(0)
    assert isinstance(result, IrInt)


def test_irnot_eval_negates_falsy_operand():
    """IrNot over a falsy operand evals to IrInt(1)."""
    assert IrNot(IrInt(0)).eval(IrNone, IrNone, ()) == IrInt(1)


def test_irnot_repr_round_trips():
    """repr(IrNot(...)) reproduces the flat constructor call."""
    assert repr(IrNot(IrInt(1))) == "IrNot(IrInt(1))"


# ── IrEq (DyadicOp) ───────────────────────────────────────────────────


def test_ireq_is_dyadic_with_eq_operator():
    """IrEq is a DyadicOp whose operator is ``IrOp("==")``."""
    node = IrEq(IrInt(7), IrInt(7))
    assert isinstance(node, DyadicOp)
    assert node.op == IrOp("==")


def test_ireq_equal_operands_yield_one():
    """Equal operands ⇒ IrInt(1)."""
    result = IrEq(IrInt(7), IrInt(7)).eval(IrNone, IrNone, ())
    assert result == IrInt(1)
    assert isinstance(result, IrInt)


def test_ireq_unequal_operands_yield_zero():
    """Unequal operands ⇒ IrInt(0)."""
    assert IrEq(IrInt(7), IrInt(8)).eval(IrNone, IrNone, ()) == IrInt(0)


def test_ireq_repr_round_trips():
    """repr(IrEq(...)) reproduces the flat constructor call."""
    assert repr(IrEq(IrInt(7), IrInt(7))) == "IrEq(IrInt(7), IrInt(7))"


# ── IrAnd (VariadicOp) ────────────────────────────────────────────────


def test_irand_is_variadic_with_and_operator():
    """IrAnd is a VariadicOp whose operator is ``IrOp("&")``."""
    a = IrAnd()
    assert isinstance(a, VariadicOp)
    assert a.op == IrOp("&")


def test_irand_all_true_yields_one():
    """Every operand truthy ⇒ IrInt(1)."""
    a = IrAnd(
        IrCompare(IrInt(1), IrOp("=="), IrInt(1)),
        IrCompare(IrInt(2), IrOp(">"), IrInt(1)),
    )
    result = a.eval(IrNone, IrNone, ())
    assert result == IrInt(1)
    assert isinstance(result, IrInt)


def test_irand_one_false_yields_zero():
    """A single falsy operand ⇒ IrInt(0)."""
    a = IrAnd(
        IrCompare(IrInt(1), IrOp("=="), IrInt(1)),
        IrCompare(IrInt(1), IrOp("=="), IrInt(0)),
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
        IrCompare(IrInt(1), IrOp("=="), IrInt(0)),
        IrCallable[IrSelf, IrInt](_record),
    )
    assert a.eval(IrNone, IrNone, ()) == IrInt(0)
    assert calls == [1]


def test_irand_repr_round_trips():
    """repr(IrAnd(...)) reproduces the flat constructor call."""
    assert repr(IrAnd(IrInt(1))) == "IrAnd(IrInt(1))"
