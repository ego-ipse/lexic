"""Control — what runs, and in what order.

The flow of an action body: piping, branching, iteration, and the two
short-circuits. ``IrReturn`` carries its own exception because the short-circuit
is intrinsic to the node rather than to a driver.
"""

from __future__ import annotations

from typing import ClassVar, Sequence

from lexic.exceptions import UnsupportedConstructError
from lexic.ir.spine.records import IrNamedTuple, IrTuple
from lexic.ir.spine.scalars import IrStr
from lexic.ir.spine.spine import IrLeaf, IrNode, IrNone, IrSelf


class _Return(BaseException):
    """Control-flow exception raised by :class:`IrReturn`.

    Inherits :class:`BaseException` (not :class:`Exception`) so
    procedural bodies that wrap their work in
    ``except Exception:`` cannot swallow it.
    """

    def __init__(self, value: object) -> None:
        """Initialise with the value to surface to the dispatcher.

        :param value: The value carried out to the catching dispatcher.
        """
        super().__init__()
        self.value = value


class IrEach[Ir_co: IrSelf](IrNamedTuple[IrSelf]):
    """Map ``body`` over the focus's elements — an ``IrTuple`` of the results.

    The variadic sibling of :class:`IrAt`: ``n`` is rebound to each element in
    turn (a tuple-shaped node's elements; a str-leaf's characters, each lifted
    to :class:`~lexic.ir.base.IrStr`), and like every focus shift the body
    starts with a clean argument channel.
    """

    _child_attrs: ClassVar[tuple[str, ...]] = ("body",)
    body: IrSelf

    def eval(self, d: IrSelf, n: IrSelf, _nc: Sequence[IrSelf], /) -> IrTuple:
        """Evaluate ``body`` once per element of the focus.

        :param d: Dispatcher, forwarded unchanged for sub-dispatch.
        :param n: The tuple-shaped or str-leaf focus to iterate.
        :param _nc: Arguments (not forwarded — a focus shift starts clean).
        :returns: The per-element results as an :class:`IrTuple`.
        :raises UnsupportedConstructError: If the focus has no elements to map.
        """
        if isinstance(n, tuple):
            elements: tuple[IrSelf, ...] = tuple(n)
        elif isinstance(n, str):
            elements = tuple(IrStr(c) for c in str(n))
        else:
            raise UnsupportedConstructError(
                f"IrEach: focus {type(n).__name__!r} has no elements"
            )
        return IrTuple(*(self.body.eval(d, e, IrTuple()) for e in elements))


class IrPipe(IrNamedTuple[IrSelf, IrSelf]):
    """Rebind the focus to a computed value, then evaluate ``body``.

    Evaluates ``source``, then evaluates ``body`` with that result as ``n`` (the
    argument channel carries through). The focus-shift onto a *computed* node —
    where :class:`IrAt` shifts onto a raw child by index. ``IrPipe(IrArg(0),
    IrField("name"))`` reads ``name`` off the first argument.
    """

    _child_attrs: ClassVar[tuple[str, ...]] = ("source", "body")
    source: IrSelf
    body: IrSelf

    def eval(self, d: IrSelf, n: IrSelf, nc: Sequence[IrSelf], /) -> IrSelf:
        """Evaluate ``body`` with ``n`` rebound to ``source``'s result."""
        return self.body.eval(d, self.source.eval(d, n, nc), nc)


class IrCond[Ir_co: IrSelf](IrNamedTuple[IrSelf, IrSelf, IrSelf]):
    """If ``test`` evaluates truthy, evaluate ``then_op``; else ``else_op``.

    ``test`` is any node whose ``eval`` yields a truthy/falsy value (e.g.
    :class:`IrCompare`, :class:`IrAnd`). Typed ``IrSelf`` (not ``IrNode``) for
    the same reason as :class:`IrCompare`'s operands — ``IrNode``'s ``Ir_co`` is
    invariant, which rejects value operands like ``IrField``. Both branches
    share ``Ir_co``.

    :param Ir_co: the shared result type of both branches.
    """

    _child_attrs: ClassVar[tuple[str, ...]] = ("test", "then_op", "else_op")
    test: IrSelf
    then_op: IrSelf
    else_op: IrSelf

    def eval(self, d: IrSelf, n: IrSelf, nc: Sequence[IrSelf], /) -> Ir_co:
        """Branch on the truthiness of ``self.test.eval(d, n, nc)``.

        :param d: Dispatcher forwarded to the test and the chosen branch.
        :param n: Current node forwarded to the test and the chosen branch.
        :param nc: Pre-walked children forwarded onward.
        :returns: The chosen branch's result.
        """
        branch = self.then_op if self.test.eval(d, n, nc) else self.else_op
        return branch.eval(d, n, nc)


class IrThis(IrLeaf[IrSelf, IrSelf]):
    """Identity body — evaluates to the dispatched node ``n`` as-is.

    Use when an action matches and the dispatcher's return-shape contract
    is satisfied by the dispatched node itself. Equivalent to Python's
    ``lambda d, n, nc: n``.
    """

    def eval(self, _d: IrSelf, n: IrSelf, _nc: Sequence[IrSelf], /) -> IrSelf:
        """Return the dispatched node ``n``.

        :param _d: Dispatcher (unused).
        :param n: Node to return as-is.
        :param _nc: Pre-walked children (unused).
        :returns: The dispatched node ``n``.
        """
        return n


class IrPass(IrLeaf[IrSelf, IrSelf]):
    """No-op body — evaluates to :data:`IrNone` without recursing.

    Use when an action matches but neither a value nor a child walk is
    desired. Equivalent to Python's ``pass``. Not the default for
    :class:`~lexic.ir.action.walk.IrVisitor` — that role belongs to
    :class:`IrWalk`.
    """

    def eval(self, _d: IrSelf, _n: IrSelf, _nc: Sequence[IrSelf], /) -> IrSelf:
        """Return :data:`IrNone`.

        :param _d: Dispatcher (unused).
        :param _n: Node (unused).
        :param _nc: Pre-walked children (unused).
        :returns: :data:`IrNone`.
        """
        return IrNone


class IrReturn[Ir_co: IrSelf](IrNode[IrSelf, Ir_co], _Return):
    """Short-circuit IR node that IS-A control-flow exception.

    ``IrReturn`` mixes :class:`IrNode` (structural IR contract) with
    :class:`_Return` (BaseException machinery). Both are object-based — unlike a
    tuple, they coexist with ``BaseException``'s instance layout — so it is a
    plain :class:`IrNode` leaf, not an :class:`IrNamedTuple`. ``eval`` raises
    ``self``; the dispatcher catches the instance and surfaces ``self.value`` or
    the instance itself. Equality is by identity (``BaseException`` semantics).

    :param Ir_co: the type of the carried value.
    """

    lazy_eval: bool

    def __init__(self, value: object = IrThis(), lazy_eval: bool = True) -> None:
        """Carry ``value`` and initialise the ``BaseException`` machinery.

        :param value: Value to surface — defaults to the dispatched node (via
            :class:`IrThis`) when none is given.
        :param lazy_eval: When ``True``, an ``IrSelf`` value is ``eval``\\ ed
            before the exception unwinds.
        """
        _Return.__init__(self, value)
        self.lazy_eval = lazy_eval

    def eval(self, d: IrSelf, n: IrSelf, nc: Sequence[IrSelf], /) -> Ir_co:
        """Raise ``self`` — unwinds to the dispatcher's catch.

        :param _d: Dispatcher (unused).
        :param _n: Node (unused).
        :param _nc: Pre-walked children (unused).
        :returns: Never returns normally.
        :raises IrReturn: Always — raises ``self``.
        """

        if self.lazy_eval and isinstance(self.value, IrSelf):
            raise self.__class__(self.value.eval(d, n, nc))
        raise self
