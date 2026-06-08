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
  :class:`DyadicOp`, :class:`VariadicOp`. **Arity is encoded in the ``body``
  field type**, so a wrong operand count is a static type error rather than a
  runtime crash: ``DyadicOp`` holds an ``IrTuple[IrSelf, IrSelf]`` (exactly
  two), ``MonadicOp`` a single ``IrSelf``, ``VariadicOp`` an ``IrSeq`` (any).
  Concrete operator nodes (:class:`IrEq`, :class:`IrAnd`, :class:`IrNot`)
  fix the operator and inherit ``eval``.
"""

from __future__ import annotations

import operator
from typing import Callable, ClassVar, Sequence

from lexic.exceptions import UnsupportedConstructError
from lexic.ir.base import IrAtom, IrInt, IrNamedTuple, IrSelf, IrSeq, IrStr, IrTuple

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


# ── Operator node — (body, op), arity carried by the body type ────────


class IrOpNode[T: IrTuple](IrNamedTuple[T, IrOp], IrAtom):
    """An operator applied to its operands — IS-AN :class:`IrAtom`.

    The node is the named tuple ``(body, op)``: ``body`` holds the operands and
    ``op`` is the :class:`IrOp` applied to them. ``op`` comes second so a
    concrete subclass can pin it with a default while ``body`` stays required.

    Arity lives in ``T`` — the static type of ``body`` — so an off-arity
    construction is a type error, not a runtime crash. Subclasses fix the shape
    of ``T`` (see :class:`MonadicOp`/:class:`DyadicOp`/:class:`VariadicOp`) and
    supply :meth:`operands`; ``eval`` is shared.
    """

    __slots__ = ()
    body: T
    op: IrOp

    def eval(self, d: IrSelf, n: IrSelf, nc: Sequence[IrSelf], /) -> IrInt:
        """Evaluate each operand and apply :attr:`op` to the results.

        :param d: Dispatcher forwarded to each operand's ``eval``.
        :param n: Current node forwarded to each operand's ``eval``.
        :param nc: Pre-walked children forwarded to each operand's ``eval``.
        :returns: ``IrInt(1)`` if the operation holds, else ``IrInt(0)``.
        """
        return self.op.eval(d, n, [o.eval(d, n, nc) for o in self.body])


# The sort of thing that wars are fought over.
type Monad[T: IrSelf] = T
type Dyad[T: IrSelf] = IrTuple[T, T]
type Variad[T: IrSelf] = IrSeq[T]


class MonadicOp(IrOpNode[Monad]):
    """Unary operator node — ``body`` is a single operand."""

    __slots__ = ()
    body: Monad
    op: IrOp

    def eval(self, d: IrSelf, n: IrSelf, nc: Sequence[IrSelf], /) -> IrInt:
        """Evaluate each operand and apply :attr:`op` to the results."""
        return self.op.eval(d, n, [self.body.eval(d, n, nc)])


class DyadicOp(IrOpNode[Dyad]):
    """Binary operator node — ``body`` is an exactly-two operand tuple."""

    __slots__ = ()
    body: Dyad
    op: IrOp


class VariadicOp(IrOpNode[Variad]):
    """Variadic operator node — ``body`` is an :class:`IrSeq` of any length."""

    __slots__ = ()
    body: Variad
    op: IrOp


# ── Fixed-operator nodes ──────────────────────────────────────────────


class IrNot(MonadicOp):
    """Negation atom — a :class:`MonadicOp` over ``IrOp("!")``.

    Construct as ``IrNot(operand)``; ``op`` defaults to ``!``. Being an
    :class:`IrAtom` it can be wrapped by ``IrItem``; inherited ``eval`` applies
    ``operator.not_`` to the single evaluated ``body`` (a truth value or any
    evaluable operand).
    """

    __slots__ = ()
    body: Monad
    op: IrOp = IrOp("!")


class IrEq(DyadicOp):
    """Equality comparison — a :class:`DyadicOp` over ``IrOp("==")``.

    Construct as ``IrEq(IrTuple(left, right))``; ``op`` defaults to ``==``.
    Inherited ``eval`` evaluates both operands and returns ``IrInt(1)`` when
    they compare equal, else ``IrInt(0)``.
    """

    __slots__ = ()
    body: Dyad
    op: IrOp = IrOp("==")


class IrAnd(VariadicOp):
    """Conjunction — a :class:`VariadicOp` over ``IrOp("&")``.

    Construct as ``IrAnd(IrSeq(p, q, …))``; ``op`` defaults to ``&``. The
    operator folds the truthiness of every evaluated operand via ``all`` and
    yields ``IrInt(0/1)``. The empty conjunction is the fold identity,
    ``IrInt(1)``.
    """

    __slots__ = ()
    body: Variad = IrSeq()
    op: IrOp = IrOp("&")
