"""Operator-algebra nodes — the operator family, sitting between spine and nodes.

Layering: this module imports only from :mod:`lexic.ir.base` and **never**
from :mod:`lexic.ir.nodes`. That keeps it below ``nodes.py`` in the import
graph, so a concrete grammar atom such as ``IrNot`` (defined in ``nodes.py``)
can subclass :class:`IrOpNode` here without an ``ir.nodes`` ↔ ``ir.operators``
cycle.

Two complementary shapes for "an operator applied to operands" live here:

- :class:`IrOpNode` — the **shape-agnostic contract** (option B). It fixes the
  operator (``op``) and the evaluation rule (apply ``op`` to the evaluated
  operands) but leaves *how operands are stored* to the subclass via the
  abstract :meth:`IrOpNode.operands`. A record node like ``IrNot`` (one
  ``body`` field) can satisfy it without changing shape.
- :class:`IrOpTuple` — the **tuple realization** (option A). The node IS its
  operand tuple; :meth:`operands` returns ``self``. The natural base for a
  variadic operator like a conjunction.

``IrOpTuple`` IS-AN ``IrOpNode``, so the contract is the single source of the
evaluation rule and the tuple form is just one storage choice under it.
"""

from __future__ import annotations

import operator
from abc import abstractmethod
from typing import Callable, ClassVar, Sequence

from lexic.exceptions import UnsupportedConstructError
from lexic.ir.base import IrInt, IrNode, IrSelf, IrStr, IrTuple

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


# ── Operator node

class IrOpNode(IrTuple[IrOp, ...], IrNode):
    """
    """

    op: IrOp

