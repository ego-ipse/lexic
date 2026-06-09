"""Operator-algebra nodes — the operator family, sitting between spine and nodes.

Layering: this module imports only from :mod:`lexic.ir.base` and **never**
from :mod:`lexic.ir.nodes`. That keeps it below ``nodes.py`` in the import
graph, so a concrete grammar atom such as ``IrNot`` can live here and be reused
from ``nodes.py`` without an ``ir.nodes`` ↔ ``ir.operators`` cycle.

Two layers:

- :class:`IrOp` — the operator leaf (the node IS the operator string). Arity is
  the operator's own property: comparisons are binary, ``!`` unary, ``&``/``|``
  variadic folds.
- :class:`IrOpNode` and its three arity bases :class:`MonadicOp`,
  :class:`DyadicOp`, :class:`VariadicOp`. **An operator node IS its operand
  tuple** — operands are the tuple elements, constructed flat
  (``IrEq(a, b)``, ``IrAnd(a, b, c)``, ``IrNot(x)``). Arity is the tuple's own
  parameterisation, so a wrong operand count is a static type error (a
  positional-argument mismatch) rather than a runtime crash. The operator is a
  ``ClassVar`` — type-level, not a field — so concrete nodes (:class:`IrNot`,
  :class:`IrEq`, :class:`IrAnd`) only pin ``op`` and inherit the single shared
  ``eval``.
"""

from __future__ import annotations

import operator
from typing import Callable, ClassVar, Sequence

from lexic.exceptions import UnsupportedConstructError
from lexic.ir.base import IrAtom, IrInt, IrSelf, IrSeq, IrStr, IrTuple

# ── Operator leaf ─────────────────────────────────────────────────────


class IrOp(IrStr):
    """Infix operator leaf — the node IS the operator string (e.g. ``IrOp(">")``).

    No enum: the operator is its own string, keyed directly into ``_OPS`` (an
    ``IrStr`` leaf matches its plain-``str`` key). ``eval`` applies the mapped
    callable to the operands handed in as ``nc`` and returns the truth value as
    ``IrInt(0/1)`` — the consumer (an :class:`IrOpNode`) supplies the operands.

    Arity is the operator's own property: comparisons are binary, ``!`` unary,
    and ``&``/``|`` are variadic logical folds (``all``/``any``). A variadic
    fold over zero operands yields its identity (``all(()) == True``,
    ``any(()) == False``). The number of operands is guaranteed by the operand
    node's shape (see :class:`IrOpNode`), so ``eval`` never validates it.
    """

    _OPS: ClassVar[dict[str, Callable[..., bool]]] = {
        "==": operator.eq,
        "<": operator.lt,
        ">": operator.gt,
        "<=": operator.le,
        ">=": operator.ge,
        "!": operator.not_,
        "&": lambda *xs: all(xs),
        "|": lambda *xs: any(xs),
    }

    def eval(self, _d: IrSelf, _n: IrSelf, nc: Sequence[IrSelf], /) -> IrInt:
        """Apply this operator to the operands in ``nc``.

        :param _d: Dispatcher (unused).
        :param _n: Current node (unused).
        :param nc: The pre-evaluated operands; count matches the operator's arity.
        :returns: ``IrInt(1)`` if the operation holds, else ``IrInt(0)``.
        :raises UnsupportedConstructError: if the operator string is not in ``_OPS``.
        """
        if self not in self._OPS:
            raise UnsupportedConstructError(f"Unknown operator: {self!r}")
        return IrInt(self._OPS[self](*nc))


# ── Operator node — the node IS its operand tuple, op is type-level ───


class IrOpNode(IrAtom):
    """Operator behaviour — the :class:`ClassVar` :attr:`op` plus the shared ``eval``.

    Mixed into one of our tuple types by an arity base, so a concrete operator
    node IS its operand tuple: operands are the elements, in order, and the
    operator is type-level. ``eval`` walks the operand children, evaluates each,
    and applies :attr:`op`.

    Arity is the tuple the arity base mixes in (see :class:`MonadicOp`/
    :class:`DyadicOp`/:class:`VariadicOp`); the operator is fixed by the concrete
    node (:attr:`op`). Construction is flat — ``IrEq(left, right)``.
    """

    op: ClassVar[IrOp]

    def eval(self, d: IrSelf, n: IrSelf, nc: Sequence[IrSelf], /) -> IrInt:
        """Evaluate each operand and apply :attr:`op` to the results.

        :param d: Dispatcher forwarded to each operand's ``eval``.
        :param n: Current node forwarded to each operand's ``eval``.
        :param nc: Pre-walked children forwarded to each operand's ``eval``.
        :returns: ``IrInt(1)`` if the operation holds, else ``IrInt(0)``.
        """
        return self.op.eval(d, n, [o.eval(d, n, nc) for o in self.children()])


class MonadicOp(IrOpNode, IrTuple[IrSelf]):
    """Unary operator node — exactly one operand element."""


class DyadicOp(IrOpNode, IrTuple[IrSelf, IrSelf]):
    """Binary operator node — exactly two operand elements."""


class VariadicOp(IrOpNode, IrSeq[IrSelf]):
    """Variadic operator node — any number of operand elements."""


# ── Fixed-operator nodes ──────────────────────────────────────────────


class IrNot(MonadicOp):
    """Negation atom — a :class:`MonadicOp` over ``IrOp("!")``.

    Construct flat as ``IrNot(operand)``. Being an :class:`IrAtom` it can be
    wrapped by ``IrItem``; the shared ``eval`` applies ``operator.not_`` to the
    single evaluated operand (a truth value or any evaluable operand).
    """

    op: ClassVar[IrOp] = IrOp("!")


class IrEq(DyadicOp):
    """Equality comparison — a :class:`DyadicOp` over ``IrOp("==")``.

    Construct flat as ``IrEq(left, right)``. The shared ``eval`` evaluates both
    operands and returns ``IrInt(1)`` when they compare equal, else ``IrInt(0)``.
    """

    op: ClassVar[IrOp] = IrOp("==")


class IrAnd(VariadicOp):
    """Conjunction — a :class:`VariadicOp` over ``IrOp("&")``.

    Construct flat as ``IrAnd(p, q, …)``. The operator folds the truthiness of
    every evaluated operand via ``all`` and yields ``IrInt(0/1)``. The empty
    conjunction is the fold identity, ``IrInt(1)``.
    """

    op: ClassVar[IrOp] = IrOp("&")
