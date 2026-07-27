"""Access — reaching into a node.

Navigation over the substrate: a child by index or name, a field, a length.
Nothing here computes; they only say WHERE.
"""

from __future__ import annotations

from typing import ClassVar, Sequence, cast

from lexic.exceptions import UnsupportedConstructError
from lexic.ir.records import IrNamedTuple, IrTuple
from lexic.ir.scalars import IrInt, IrScalar, IrStr
from lexic.ir.spine import IrLeaf, IrSelf


class IrField(IrNamedTuple[str, type[IrScalar]]):
    """Read a typed attribute from the dispatched node ``n`` and wrap it.

    The read value is wrapped via the **runtime** constructor ``out`` — a
    value-leaf type such as :class:`~lexic.ir.nodes.IrStr` / :class:`IrInt`
    (default ``IrStr``). Read an int with ``IrField("lo", IrInt)``; the default
    ``out=IrStr`` keeps every existing ``IrField("name")`` caller unchanged.

    Cast-free and open: ``out`` is any ``type[IrScalar]`` — callable with the
    payload thanks to :meth:`IrScalar.__new__`, so ``self.out(value)``
    type-checks without a cast and a new ``IrScalar`` subtype needs no change
    here (no enumerated leaf-type union).

    A record-leaf: ``name`` and the class-valued ``out`` are scalar payload
    (``_child_attrs = ()``); the class-aware repr renders ``out`` as a bare name.
    """

    _child_attrs: ClassVar[tuple[str, ...]] = ()
    name: str
    out: type[IrScalar] = IrStr

    def eval(self, _d: IrSelf, n: IrSelf, _nc: Sequence[IrSelf], /) -> IrScalar:
        """Read ``getattr(n, self.name)`` and wrap via ``self.out(value)``.

        :param _d: Dispatcher (unused — no recursion).
        :param n: Node whose attribute to read.
        :param _nc: Pre-walked children (unused).
        :returns: The attribute value wrapped in ``self.out`` (an ``IrScalar``).
        """
        return self.out(getattr(n, self.name))


class IrChild(IrStr):
    """Single dispatched child by name — the node IS the child's field name.

    Resolves the name through ``type(n)._child_attrs`` (record nodes) and
    yields the *dispatched* child. For tuple-shaped nodes whose children
    carry no names, :class:`IrIndex` is the positional primitive this
    resolves to.
    """

    def eval(self, d: IrSelf, n: IrSelf, _nc: Sequence[IrSelf], /) -> IrSelf:
        """Resolve the named child and dispatch it via ``d``.

        :param d: Dispatcher for the sub-dispatch.
        :param n: Node whose child to resolve.
        :param _nc: Arguments (unused — children come from ``n``, never ``nc``).
        :returns: The dispatched child.
        :raises ValueError: if the name is not in ``type(n)._child_attrs``.
        """
        attrs = getattr(type(n), "_child_attrs", ())
        try:
            idx = attrs.index(self)
        except ValueError as exc:
            raise ValueError(
                f"{self!r}: {type(n).__name__} has no such child (known: {attrs})"
            ) from exc
        return d.eval(d, n.children()[idx], IrTuple())


class IrIndex(IrInt):
    """Single dispatched child by position — the node IS the index.

    The positional primitive: tuple-shaped nodes (operator monads,
    collections) have unnamed children, and ``IrIndex(0)`` addresses the
    first directly — the 0th key of a monad like ``IrNot``. Negative
    positions index from the end, as native tuples do.
    """

    def eval(self, d: IrSelf, n: IrSelf, _nc: Sequence[IrSelf], /) -> IrSelf:
        """Resolve the child at this position and dispatch it via ``d``.

        :param d: Dispatcher for the sub-dispatch.
        :param n: Node whose child to resolve.
        :param _nc: Arguments (unused — children come from ``n``, never ``nc``).
        :returns: The dispatched child.
        :raises IndexError: if the position is out of range.
        """
        return d.eval(d, n.children()[self], IrTuple())


class IrAt[Ir_co: IrSelf](IrNamedTuple[int, IrSelf]):
    """Binder — rebind the dispatch focus to a raw child, then evaluate ``body``.

    The algebra's first context-shifting node: every other node evaluates
    against the ``n`` it was dispatched with, but inside an ``IrAt`` body
    ``n`` IS the selected child — ``n.children()[selector]``, raw and
    undispatched, with a fresh empty argument channel. Where :class:`IrIndex`
    yields the *dispatched* child, ``IrAt`` exposes the *raw* child to its
    body — e.g. ``IrAt(0, IrTypeMap(...))`` resolves a guard table against
    an operand's own type.

    ``selector`` is positional scalar payload (negatives index from the end,
    as native tuples do).

    :param Ir_co: the body's result type.
    """

    _child_attrs: ClassVar[tuple[str, ...]] = ("body",)
    selector: int
    body: IrSelf

    def eval(self, d: IrSelf, n: IrSelf, _nc: Sequence[IrSelf], /) -> Ir_co:
        """Evaluate ``body`` with ``n`` rebound to the selected raw child.

        :param d: Dispatcher, forwarded unchanged for sub-dispatch.
        :param n: Node whose raw child becomes the body's focus.
        :param _nc: Arguments (not forwarded — a focus shift starts clean).
        :returns: The body's result against the rebound focus.
        :raises IndexError: If ``selector`` is out of range for ``n.children()``.
        """
        return self.body.eval(d, n.children()[self.selector], IrTuple())


class IrLen(IrLeaf[IrSelf, IrInt]):
    """Element count of the focus — ``IrInt(len(n))``.

    Counts a tuple-shaped node's elements or a str-leaf's characters; the
    natural :class:`IrCompare` operand for arity-branching bodies.
    """

    def eval(self, _d: IrSelf, n: IrSelf, _nc: Sequence[IrSelf], /) -> IrInt:
        """Return the focus's length.

        :raises UnsupportedConstructError: If the focus is unsized.
        """
        if not isinstance(n, (tuple, str)):
            raise UnsupportedConstructError(
                f"IrLen: focus {type(n).__name__!r} has no length"
            )
        return IrInt(len(n))


class IrChildren[Iri: IrSelf, Ir_co: IrSelf = IrSelf](IrNamedTuple):
    """Full tuple of dispatched children of ``n`` (reads ``n.children()``).

    ``Ir_co`` is the dispatcher's per-child result type. The result is the
    whole children sequence — distinct from :class:`IrChild` at the type
    level. ``_bound`` is derived from ``Ir_co`` so :meth:`IrSelf.bind` works.

    A fieldless record-leaf: it has no fields of its own.

    :param Ir_co: the dispatcher's per-child result type.
    """

    def eval(self, d: IrSelf, n: IrSelf, _nc: Sequence[IrSelf], /) -> Ir_co:
        """Resolve the children collection — dispatch each child via ``d``.

        :param d: Dispatcher for the per-child sub-dispatch.
        :param n: Node whose children to resolve.
        :param _nc: Arguments (unused — children come from ``n``, never ``nc``;
            the argument analogue is :class:`IrArgs`).
        :returns: The children sequence, type-checked against ``self.bound``.
        """
        return cast(
            Ir_co, self.bind(IrTuple(*(d.eval(d, c, IrTuple()) for c in n.children())))
        )


class IrArgs(IrNamedTuple):
    """The argument channel, read whole — evaluates to the ``nc`` tuple.

    The argument analogue of :class:`IrChildren`: children come from the
    node, arguments from the caller. A renderer places
    ``IrJoin(parts=IrArgs())`` wherever received marks belong in its surface
    syntax; with no arguments passed it evaluates empty and the join's
    ``empty`` fallback applies.

    A fieldless record-leaf.
    """

    def eval(self, _d: IrSelf, _n: IrSelf, nc: Sequence[IrSelf], /) -> IrTuple:
        """Return the arguments as a tuple node.

        :param _d: Dispatcher (unused).
        :param _n: Node (unused).
        :param nc: The argument channel.
        :returns: ``nc`` as an :class:`IrTuple`.
        """
        return IrTuple(*nc)


class IrArg(IrInt):
    """Single argument by position — the node IS the index into ``nc``.

    The argument-channel analogue of :class:`IrIndex` (which indexes ``n``'s
    children): ``IrArg(0)`` returns the first element of the channel **as-is**,
    undispatched — the arguments are already resolved values (a reducer hands a
    body its reduced children on ``nc``). Negative positions index from the end,
    as native tuples do.
    """

    def eval(self, _d: IrSelf, _n: IrSelf, nc: Sequence[IrSelf], /) -> IrSelf:
        """Return the argument at this position, undispatched.

        :param _d: Dispatcher (unused — arguments are already resolved).
        :param _n: Node (unused — the value comes from ``nc``, never ``n``).
        :param nc: The argument channel.
        :returns: ``nc[self]``.
        :raises IndexError: If the position is out of range.
        """
        return nc[self]
