"""Parse forest — the shared packed parse forest (SPPF) and its reducible views.

Following Scott (2008, *SPPF-Style Parsing From Earley Recognisers*), the chart's
family table IS a shared packed parse forest. This module gives it node shapes
and enumerates its derivations:

- :class:`ParseTree` — ONE derivation: a non-terminal symbol over a span, with
  its children (sub-trees, or :class:`~lexic.ir.nodes.IrLiteral` leaves for
  consumed characters). The reducible output a
  :class:`~lexic.parsing.earley.reduce.Reducer` folds.
- :class:`SppfNode` — a shared, packed forest handle for a dotted item over a
  span: the pure-data pair ``(item, end)``. Its packed families are
  ``chart.links[(item, end)]`` (each a predecessor / consumed-child pair), read on
  demand — the same handle always exposes the same families (sharing), ``> 1``
  family ⇒ the node is **ambiguous**. The handle is intrinsically **binary** (one
  predecessor + one child per family), so the forest is binarised by construction
  and stays polynomial under ambiguity.

**Enumeration is lazy and depth-safe.** A node's derivations are a lazy product
over its families, each family's predecessor prefixes, and each consumed child's
derivations. Right-recursive grammars make that product arbitrarily deep, so the
walk must not recurse through the Python call stack (a native nested-generator
walk overflows at ~300 levels). Instead the walk is **trampolined**: the
per-node generators (:class:`NodeDerivs`, :class:`PrefixSource`,
:class:`ChildDerivs` — their behaviour lives on ``__iter__``) do not iterate
their children directly; they yield :data:`ADVANCE` / :data:`EMIT` commands to
the :class:`Trampoline` driver, which keeps the active pull-chain on an explicit
Python list. Suspended generators live as locals in their parent generator's
frame, so the driver's list holds only the live spine — depth lives in a list,
never the C stack.

A :class:`ForestCtx` cursor carries the chart and the set of **open** handles
(those whose prefixes are mid-production); a re-entrant prefix request on an open
handle is a genuine (nullable) cycle and emits the single empty prefix, which
terminates it.

Public readers:

- :class:`DerivationStream.eval` (:data:`DERIVATION_STREAM`) — a node's lazy
  :class:`IrStream` of :class:`ParseTree` derivations (buffered, replayable).
- :class:`Derivations.eval` (:data:`DERIVATIONS`) — all of them, eagerly, as an
  :class:`~lexic.ir.base.IrSeq`.
- :class:`BuildTree.eval` (:data:`BUILD_TREE`) — the strict single-derivation
  façade, taking only the first two derivations and **raising**
  :exc:`~lexic.exceptions.UnsupportedConstructError` on ambiguous input.
"""

from __future__ import annotations

from typing import ClassVar, Iterable, Iterator, Self, Sequence, cast

from lexic.exceptions import UnsupportedConstructError
from lexic.ir.base import (
    IrLeaf,
    IrNamedTuple,
    IrNone,
    IrNoneType,
    IrSelf,
    IrSeq,
    IrTuple,
)
from lexic.ir.nodes import IrLiteral, IrRuleRef
from lexic.parsing.earley.chart import Chart, EarleyItem
from lexic.parsing.earley.trampoline import ADVANCE, EMIT, EXHAUSTED, Trampoline

_FRESH, _DRIVING, _DONE = 0, 1, 2
"""Replay states of an :class:`IrStream` — fresh (never driven), driving
(re-entry signals a genuine empty-span cycle), done (buffer fully populated)."""


class ParseTree(IrNamedTuple[IrRuleRef, IrSeq]):
    """A derivation node: ``symbol`` matched over the ``kids`` in order.

    ``kids`` are the dispatched part (sub-:class:`ParseTree` nodes and consumed
    :class:`~lexic.ir.nodes.IrLiteral` leaves); ``symbol`` is scalar payload
    naming the rule, the key a reduction table looks up. The field is ``kids``
    (not ``children``) to avoid shadowing the :meth:`IrNamedTuple.children`
    protocol method — ``_child_attrs`` still routes the walk through it.

    :ivar symbol: The rule this node derives.
    :ivar kids: The matched sub-derivations / terminals, in source order.
    """

    _child_attrs: ClassVar[tuple[str, ...]] = ("kids",)
    symbol: IrRuleRef
    kids: IrSeq

    def __new__(cls, symbol: IrRuleRef, kids: IrSeq) -> Self:
        """Fast positional constructor — skips the generic IrNamedTuple path.

        :param symbol: The rule this node derives.
        :param kids: The matched sub-derivations / terminals, in source order.
        :returns: A new :class:`ParseTree`.
        """
        return tuple.__new__(cls, (symbol, kids))


class PayloadLeaf(IrLeaf[IrSelf, IrSelf]):
    """A pre-folded family child spliced in by island-interior delegation.

    When the PDA delegates a conflict-free rule's interior, its sub-run yields a
    finished payload (a model instance on the instance path, or a reduced IR
    fragment on the reduce path) plus the consumed span text. The kernel injects
    a completed item for the delegated rule and records, on the waiter it
    advances, a family whose consumed child IS this leaf — the same slot a
    scanned character occupies. It therefore decodes as a normal terminal-like
    family child (:class:`ChildDerivs` / :meth:`~lexic.parsing.earley.kernel
    .Kernel._child` / :class:`~lexic.parsing.earley.kernel.FastTree`), and the
    :class:`~lexic.parsing.fold.ModelFold` / :class:`~lexic.parsing.earley.reduce
    .Reducer` pass its :attr:`payload` straight through as an already-folded
    child (mirroring the PDA-side island splice). Not a :class:`ParseTree` and
    not an :class:`~lexic.ir.nodes.IrLiteral`, so every kid-walk that
    discriminates on those two leaves it alone.

    :ivar payload: The pre-built value — a model instance / reduced IR fragment
        (``None`` for a nullable empty match).
    :ivar text: The consumed span text (read by ``text`` / ``gtext`` folds and
        the reduce ``YIELD`` walk).
    """

    __slots__ = ("payload", "text")

    payload: object
    text: str

    def __init__(self, payload: object, text: str) -> None:
        """:param payload: the pre-built value; :param text: its consumed span."""
        self.payload = payload
        self.text = text


class SppfNode(IrNamedTuple[EarleyItem, int]):
    """A shared, packed forest handle for a dotted item over its span — pure data.

    The handle IS the pair ``(item, end)``; its packed families are
    ``chart.links[(item, end)]``, read by the enumeration generators, not by the
    record. Like :class:`EarleyItem` it carries no methods beyond ``__new__``.
    Scalar payload only (``_child_attrs = ()``): families come from the chart,
    never an IR-children walk.

    :ivar item: The dotted (usually completed) item.
    :ivar end: The column the item ends at.
    """

    _child_attrs: ClassVar[tuple[str, ...]] = ()
    item: EarleyItem
    end: int

    def __new__(cls, item: EarleyItem, end: int) -> Self:
        """Fast positional constructor.

        :param item: The dotted (usually completed) item.
        :param end: The column the item ends at.
        :returns: A new :class:`SppfNode`.
        """
        return tuple.__new__(cls, (item, end))


class ForestCtx(IrLeaf[IrSelf, IrSelf]):
    """Per-read forest cursor — the chart plus the open-handle cycle guard.

    The **mutable** forest-read cursor (the mutable-chart exception, like
    :class:`~lexic.parsing.earley.kernel.KernelState`): :attr:`open` holds the
    ``(item, end)`` handles whose prefixes are currently being produced. A
    re-entrant :class:`PrefixSource` on an open handle is a genuine empty-span
    (nullable) cycle and emits the single empty prefix to terminate it. A handle
    is added to :attr:`open` before its families are walked and discarded after —
    so an *exhausted* handle can be legitimately re-entered (sharing), only a
    *mid-production* one is treated as a cycle.

    :attr:`open` is a set (membership + ``discard``), so it rides a slot rather
    than an :class:`~lexic.ir.mapping.IrMultiMap` — the same set-shaped-state
    precedent as :attr:`~lexic.parsing.earley.chart.Column.predicted`. Behaviour stays
    on the generator nodes; the cursor only holds state.

    :ivar chart: The chart holding the family table.
    :ivar open: The handles whose prefixes are mid-production.
    """

    __slots__ = ("chart", "open")

    chart: Chart
    open: set[tuple[EarleyItem, int]]

    def __init__(self, chart: Chart) -> None:
        """Build the cursor over ``chart`` with no open handles.

        :param chart: The chart holding the family table.
        """
        self.chart = chart
        self.open = set()


class IrStream[T: IrSelf](IrLeaf[IrSelf, IrSelf]):
    """A replayable lazy sequence of ``T`` — a buffered, single-drive view.

    Drives its ``_source`` (an iterable ``T`` node) **once**, buffering each
    element so later consumers replay it without re-driving. ``T`` is the element
    type, so a derivation stream is an ``IrStream[ParseTree]``. Behaviour is on
    :meth:`__iter__` only (an allowed dunder).

    **Partial-consumption invariant:** a driving consumer must run the stream to
    exhaustion or abandon it; a partially-consumed stream must not be re-iterated
    by an *independent* consumer (its suspended ``DRIVING`` state would be misread
    as a cycle). Every current caller honours this — short-circuits take the first
    one or two elements then discard, eager realisers exhaust it.

    :ivar _buffer: Elements driven so far, replayed on re-iteration.
    :ivar _source: The iterable ``T`` node driven once.
    :ivar _state: One of :data:`_FRESH` / :data:`_DRIVING` / :data:`_DONE`.
    :ivar _on_cycle: What to replay on a re-entrant (cyclic) iteration.
    """

    __slots__ = ("_buffer", "_source", "_state", "_on_cycle")

    _buffer: list[T]
    _source: object
    _state: int
    _on_cycle: tuple[T, ...]

    def __init__(self, source: object, on_cycle: tuple[T, ...] = ()) -> None:
        """Wrap ``source`` as an undriven, empty stream.

        :param source: An iterable ``T`` node, driven once on first iteration.
        :param on_cycle: The sentinel to replay on a cyclic re-entry (default none).
        """
        self._buffer = []
        self._source = source
        self._state = _FRESH
        self._on_cycle = on_cycle

    def __iter__(self) -> Iterator[T]:
        """Replay the buffer, driving the source once if not yet done.

        ``DONE`` replays the full buffer; ``DRIVING`` (a re-entry) replays
        :attr:`_on_cycle`; ``FRESH`` drives the source once, buffering each element.

        :returns: An iterator over the stream's elements.
        """
        if self._state == _DONE:
            yield from self._buffer
            return
        if self._state == _DRIVING:
            yield from self._on_cycle
            return
        self._state = _DRIVING
        yield from self._buffer
        for element in iter(cast(Iterable[T], self._source)):
            self._buffer.append(element)
            yield element
        self._state = _DONE


# ── Trampolined derivation generators ─────────────────────────────────
# Each generator's behaviour is its __iter__; instead of iterating a child
# generator directly (which would grow the C stack per spine level), it creates
# the child once and yields (ADVANCE, child) / (EMIT, value) commands to the
# Trampoline driver. The driver feeds back each child value, or EXHAUSTED.


class NodeDerivs(IrLeaf[IrSelf, IrSelf]):
    """Trampoline generator: a completed handle's :class:`ParseTree` derivations.

    Wraps each of the handle's prefixes into a :class:`ParseTree` under the rule's
    symbol — one derivation per prefix, lazily.

    :ivar _node: The completed :class:`SppfNode` handle.
    :ivar _ctx: The forest cursor (chart + open-handle guard).
    """

    __slots__ = ("_node", "_ctx")

    _node: SppfNode
    _ctx: ForestCtx

    def __init__(self, node: SppfNode, ctx: ForestCtx) -> None:
        """:param node: the completed handle; :param ctx: the forest cursor."""
        self._node = node
        self._ctx = ctx

    def __iter__(self) -> Iterator[tuple[object, object]]:
        """Yield ``(EMIT, ParseTree)`` per prefix, via the trampoline.

        :returns: A command iterator the :class:`Trampoline` drives.
        """
        symbol = IrRuleRef(self._node.item[0])
        prefixes = iter(PrefixSource(self._node, self._ctx))
        kids = yield (ADVANCE, prefixes)
        while kids is not EXHAUSTED:
            yield (EMIT, ParseTree(symbol, cast(IrSeq, kids)))
            kids = yield (ADVANCE, prefixes)


class PrefixSource(IrLeaf[IrSelf, IrSelf]):
    """Trampoline generator: a handle's kid-sequence prefixes.

    Dot 0 is the single empty prefix; otherwise the lazy product over each packed
    family of (predecessor prefix) × (consumed-child derivation), in source order.
    A re-entrant request on an *open* handle (in :attr:`ForestCtx.open`) is a
    nullable cycle and emits one empty prefix to terminate.

    :ivar _node: The :class:`SppfNode` handle to expand.
    :ivar _ctx: The forest cursor.
    """

    __slots__ = ("_node", "_ctx")

    _node: SppfNode
    _ctx: ForestCtx

    def __init__(self, node: SppfNode, ctx: ForestCtx) -> None:
        """:param node: the handle to expand; :param ctx: the forest cursor."""
        self._node = node
        self._ctx = ctx

    def __iter__(self) -> Iterator[tuple[object, object]]:
        """Yield ``(EMIT, IrSeq)`` per prefix, via the trampoline.

        :returns: A command iterator the :class:`Trampoline` drives.
        """
        node = self._node
        if node.item[2] == 0:  # dot 0 — the empty prefix
            yield (EMIT, IrSeq())
            return
        ctx = self._ctx
        key = (node.item, node.end)
        if key in ctx.open:  # re-entrant open handle ⇒ empty-span cycle
            yield (EMIT, IrSeq())
            return
        chart = ctx.chart
        ctx.open.add(key)
        for link in chart.links[key]:
            predecessor = iter(PrefixSource(SppfNode(link[0], link[1]), ctx))
            prefix = yield (ADVANCE, predecessor)
            while prefix is not EXHAUSTED:
                children = iter(ChildDerivs(link[2], ctx))
                child = yield (ADVANCE, children)
                while child is not EXHAUSTED:
                    yield (EMIT, IrSeq(*cast(IrSeq, prefix), child))
                    child = yield (ADVANCE, children)
                prefix = yield (ADVANCE, predecessor)
        ctx.open.discard(key)


class ChildDerivs(IrLeaf[IrSelf, IrSelf]):
    """Trampoline generator: the derivations of one family's consumed child.

    A terminal :class:`~lexic.ir.nodes.IrLiteral` is its own sole derivation; a
    completed sub-:class:`SppfNode` yields its own :class:`ParseTree` derivations
    (recursing through the trampoline, never the C stack).

    :ivar _child: The consumed child — an :class:`~lexic.ir.nodes.IrLiteral` leaf
        or a sub-:class:`SppfNode`.
    :ivar _ctx: The forest cursor.
    """

    __slots__ = ("_child", "_ctx")

    _child: IrSelf
    _ctx: ForestCtx

    def __init__(self, child: IrSelf, ctx: ForestCtx) -> None:
        """:param child: the consumed child; :param ctx: the forest cursor."""
        self._child = child
        self._ctx = ctx

    def __iter__(self) -> Iterator[tuple[object, object]]:
        """Yield ``(EMIT, …)`` for each child derivation, via the trampoline.

        :returns: A command iterator the :class:`Trampoline` drives.
        """
        child = self._child
        if isinstance(child, (IrLiteral, PayloadLeaf)):
            # terminal leaf / delegated payload — its own sole derivation
            yield (EMIT, child)
            return
        derivs = iter(NodeDerivs(cast(SppfNode, child), self._ctx))
        tree = yield (ADVANCE, derivs)
        while tree is not EXHAUSTED:
            yield (EMIT, tree)
            tree = yield (ADVANCE, derivs)


def _forest_ctx(head: IrSelf) -> ForestCtx:
    """Recover the :class:`ForestCtx` from an ``nc`` head (chart or cursor).

    :param head: ``nc[0]`` — a :class:`~lexic.parsing.earley.chart.Chart` (top-level
        call) or an established :class:`ForestCtx`.
    :returns: The forest cursor to enumerate with.
    """
    return head if isinstance(head, ForestCtx) else ForestCtx(cast(Chart, head))


class DerivationStream(IrLeaf[IrSelf, IrSelf]):
    """Return the lazy :class:`IrStream` of a completed handle's derivation trees.

    Invoked directly via :data:`DERIVATION_STREAM`: ``n`` is a completed
    :class:`SppfNode`; ``nc`` is ``(chart,)`` or ``(ForestCtx,)``. Establishes the
    cursor, then wraps the depth-safe :class:`Trampoline` over :class:`NodeDerivs`
    in an :class:`IrStream` so the derivations buffer and replay. Both the
    short-circuiting readers (``parse`` / ``is_ambiguous``) and the eager
    :class:`Derivations` consume this single lazy source.
    """

    def eval(
        self, _d: IrSelf, n: IrSelf, nc: Sequence[IrSelf], /
    ) -> IrStream[ParseTree]:
        """Return handle ``n``'s lazy :class:`ParseTree` :class:`IrStream`.

        :param _d: Dispatcher (unused — recursion is trampolined, not dispatched).
        :param n: The completed :class:`SppfNode` handle.
        :param nc: ``(chart | ForestCtx,)``.
        :returns: The handle's :class:`ParseTree` stream.
        """
        ctx = _forest_ctx(nc[0])
        return IrStream(Trampoline(NodeDerivs(cast(SppfNode, n), ctx)))


class Derivations(IrLeaf[IrSelf, IrSelf]):
    """Realise a completed handle's prefixes into ALL :class:`ParseTree` trees.

    Invoked directly via :data:`DERIVATIONS`: ``n`` is a completed
    :class:`SppfNode`; ``nc`` is ``(chart,)`` or ``(ForestCtx,)``. Eagerly drains
    the lazy :data:`DERIVATION_STREAM` into an :class:`~lexic.ir.base.IrSeq`. The
    public way to recover ALL derivations of a parse.
    """

    def eval(self, d: IrSelf, n: IrSelf, nc: Sequence[IrSelf], /) -> IrSeq:
        """Enumerate every :class:`ParseTree` the handle ``n`` packs.

        :param d: Dispatcher, forwarded to the lazy stream.
        :param n: The completed :class:`SppfNode` handle.
        :param nc: ``(chart | ForestCtx,)``.
        :returns: An :class:`~lexic.ir.base.IrSeq` of :class:`ParseTree` derivations.
        """
        return IrSeq(*DERIVATION_STREAM.eval(d, n, nc))


class BuildTree(IrLeaf[IrSelf, IrSelf]):
    """Single-derivation façade — the ONE derivation the root handle packs (strict).

    Invoked directly via :data:`BUILD_TREE`: ``n`` is the accepting
    :class:`SppfNode`; ``nc`` is ``(chart,)``. A single :class:`ParseTree` cannot
    honestly represent ambiguity, so a handle packing more than one derivation
    **raises** rather than silently picking one.

    This is the trampolined strict reader over a decoded chart. The common
    unambiguous case never reaches it — :class:`~lexic.parsing.earley.kernel.FastTree`
    builds the tree from the packed links first, and only a fast-path miss
    (ambiguity) decodes the chart and falls back here.
    """

    def eval(self, d: IrSelf, n: IrSelf, nc: Sequence[IrSelf], /) -> IrSelf:
        """Return the sole :class:`ParseTree` the root ``n`` packs.

        :param d: Dispatcher, forwarded to the lazy stream.
        :param n: The accepting :class:`SppfNode` to reconstruct.
        :param nc: ``(chart,)``.
        :returns: The single :class:`ParseTree` derivation for the handle.
        :raises UnsupportedConstructError: If the handle packs no derivation, or
            more than one (ambiguous input).
        """
        node = cast(SppfNode, n)
        stream = DERIVATION_STREAM.eval(d, node, IrTuple(nc[0]))
        first: IrSelf = IrNone
        for index, tree in enumerate(stream):
            if index == 0:
                first = tree
                continue
            raise UnsupportedConstructError(  # a second derivation ⇒ ambiguous
                f"parsing: ambiguous input — more than one derivation of "
                f"{node.item[0]!r}; use the forest enumeration entry "
                "(parse_forest / derivations) instead"
            )
        if isinstance(first, IrNoneType):
            raise UnsupportedConstructError(
                f"parsing: no derivation of {node.item[0]!r}"
            )
        return first


DERIVATIONS = Derivations()
"""Shared :class:`Derivations` instance — eager enumeration is stateless."""

DERIVATION_STREAM = DerivationStream()
"""Shared :class:`DerivationStream` instance — lazy enumeration is stateless."""

BUILD_TREE = BuildTree()
"""Shared :class:`BuildTree` instance — single-derivation extraction is stateless."""
