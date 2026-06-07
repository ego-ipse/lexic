"""Operator-algebra nodes — IrOp and IrOpNode (``lexic.ir.operators``).

Covers the operator leaf and heterogeneous operator-applied-to-operands node:
``IrOp`` string leaf with ``_OPS`` dispatch, ``IrOpNode`` with positional ``op``
accessor, ``operands()``, ``eval``, and codegen ``repr``.
"""

from __future__ import annotations

import pytest

from lexic.exceptions import UnsupportedConstructError
from lexic.ir.base import IrInt, IrNone, IrStr, IrTuple
from lexic.ir.operators import IrOp, IrOpNode

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


def test_irop_unknown_operator_raises():
    """IrOp with an unrecognised operator string raises UnsupportedConstructError."""
    with pytest.raises(UnsupportedConstructError):
        IrOp("??").eval(IrNone, IrNone, [IrInt(1), IrInt(2)])


def test_irop_repr_is_codegen():
    """repr(IrOp('>')) reproduces the constructor call."""
    assert repr(IrOp(">")) == "IrOp('>')"


# ── IrOpNode ──────────────────────────────────────────────────────────


def test_iropnode_is_irtuple_subclass():
    """IrOpNode is an IrTuple subclass (and therefore a tuple)."""
    node = IrOpNode(IrOp("!"), IrInt(1))
    assert isinstance(node, IrTuple)
    assert isinstance(node, tuple)


def test_iropnode_op_is_element_zero():
    """IrOpNode.op property returns element [0], which is the IrOp head."""
    op = IrOp(">")
    node = IrOpNode(op, IrInt(5), IrInt(3))
    assert node.op is node[0]
    assert node.op is op


def test_iropnode_operands_is_tail():
    """IrOpNode.operands() returns elements [1:] as a tuple."""
    a, b = IrInt(5), IrInt(3)
    node = IrOpNode(IrOp(">"), a, b)
    assert node.operands() == (a, b)


def test_iropnode_eval_not_returns_ir_int_zero():
    """IrOpNode('!', IrInt(1)).eval returns IrInt(0) — negation of truthy value."""
    node = IrOpNode(IrOp("!"), IrInt(1))
    result = node.eval(IrNone, IrNone, ())
    assert result == IrInt(0)
    assert isinstance(result, IrInt)


def test_iropnode_eval_gt_returns_ir_int_one():
    """IrOpNode('>', IrInt(5), IrInt(3)).eval returns IrInt(1)."""
    node = IrOpNode(IrOp(">"), IrInt(5), IrInt(3))
    result = node.eval(IrNone, IrNone, ())
    assert result == IrInt(1)


def test_iropnode_eval_lt_false():
    """IrOpNode('<', IrInt(5), IrInt(3)).eval returns IrInt(0)."""
    node = IrOpNode(IrOp("<"), IrInt(5), IrInt(3))
    result = node.eval(IrNone, IrNone, ())
    assert result == IrInt(0)


def test_iropnode_repr_is_codegen():
    """repr(IrOpNode(...)) reproduces the constructor call."""
    node = IrOpNode(IrOp("!"), IrInt(1))
    assert repr(node) == "IrOpNode(IrOp('!'), IrInt(1))"


def test_iropnode_unary_not_of_zero_is_one():
    """IrOpNode('!', IrInt(0)).eval → IrInt(1) — negation of falsy value."""
    node = IrOpNode(IrOp("!"), IrInt(0))
    assert node.eval(IrNone, IrNone, ()) == IrInt(1)
