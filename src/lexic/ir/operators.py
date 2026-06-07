"""Operator-algebra nodes — the operator family, sitting between spine and nodes.

Layering: this module imports only from :mod:`lexic.ir.base` and **never**
from :mod:`lexic.ir.nodes`. That keeps it below ``nodes.py`` in the import
graph, so a concrete grammar atom such as ``IrNot`` (defined in ``nodes.py``)
can subclass :class:`IrOpNode` here without an ``ir.nodes`` ↔ ``ir.operators``
cycle.

Contents:

- :class:`IrOp` — the operator leaf (the node IS the operator string).
- :class:`IrOpNode` — an operator applied to operands, stored as the
  heterogeneous tuple ``(op, *operands)``: ``op`` is element ``[0]``
  (positionally type-checked as an :class:`IrOp`), the operands are the
  variadic tail. ``eval`` evaluates the operands and applies ``op``.
"""

from __future__ import annotations

import operator
from typing import Callable, ClassVar, Sequence

from lexic.exceptions import UnsupportedConstructError
from lexic.ir.base import IrInt, IrSelf, IrStr, IrTuple

# ── Operator leaf ─────────────────────────────────────────────────────


class IrOp(IrStr):
    """Infix operator leaf — the node IS the operator string (e.g. ``IrOp(">")``).

    No enum: the operator is its own string, keyed directly into ``_OPS`` (an
    ``IrStr`` leaf matches its plain-``str`` key). ``eval`` applies the mapped
    builtin to the operands handed in as ``nc`` and returns the truth value as
    ``IrInt(0/1)`` — the consumer (e.g. :class:`IrOpNode`, ``IrCompare``)
    supplies the operands.
    """

    _OPS: ClassVar[dict[str, Callable[..., bool]]] = {
        "==": operator.eq,
        "<": operator.lt,
        ">": operator.gt,
        "<=": operator.le,
        ">=": operator.ge,
        "!": operator.not_,
        "&": operator.and_,
        "|": operator.or_,
    }

    def eval(self, _d: IrSelf, _n: IrSelf, nc: Sequence[IrSelf], /) -> IrInt:
        """Apply this operator to the operands in ``nc``.

        :param _d: Dispatcher (unused).
        :param _n: Current node (unused).
        :param nc: The pre-evaluated operands (one for unary, two for binary).
        :returns: ``IrInt(1)`` if the operation holds, else ``IrInt(0)``.
        :raises UnsupportedConstructError: if the operator string is not in ``_OPS``.
        """
        if self not in self._OPS:
            raise UnsupportedConstructError(f"Unknown operator: {self!r}")
        return IrInt(self._OPS[self](*nc))


# ── Operator node — heterogeneous (op, *operands) ─────────────────────


class IrOpNode(IrTuple[IrOp, *tuple[IrSelf, ...]]):
    """Operator applied to operands — the node IS the tuple ``(op, *operands)``.

    A heterogeneous :class:`~lexic.ir.base.IrTuple` whose head element is the
    :class:`IrOp` (positionally type-checked at ``[0]``) and whose tail is the
    variadic operands. ``eval`` evaluates each operand and applies ``op``.
    Construct as ``IrOpNode(IrOp("!"), operand)`` or
    ``IrOpNode(IrOp("&"), p, q)``.

    Both a conjunction and a future record atom like ``IrNot`` can be expressed
    as operator nodes over this shape.
    """

    __slots__ = ()

    @property
    def op(self) -> IrOp:
        """The operator — element ``[0]`` of the tuple.

        :returns: The :class:`IrOp` head.
        """
        return self[0]

    def operands(self) -> tuple[IrSelf, ...]:
        """The operand nodes — elements ``[1:]``.

        :returns: The operand tail.
        """
        return self[1:]

    def eval(self, d: IrSelf, n: IrSelf, nc: Sequence[IrSelf], /) -> IrInt:
        """Evaluate each operand and apply :attr:`op`.

        :param d: Dispatcher forwarded to each operand's ``eval``.
        :param n: Current node forwarded to each operand's ``eval``.
        :param nc: Pre-walked children forwarded to each operand's ``eval``.
        :returns: ``IrInt(1)`` if the operation holds, else ``IrInt(0)``.
        """
        return self.op.eval(d, n, [o.eval(d, n, nc) for o in self.operands()])
