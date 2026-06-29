"""Parse forest — the shared packed parse forest (SPPF) and its reducible views.

Following Scott (2008, *SPPF-Style Parsing From Earley Recognisers*), the chart's
family table IS a shared packed parse forest. This module gives it node shapes
and lets it be read either as a single derivation or as all of them:

- :class:`ParseTree` — ONE derivation: a non-terminal symbol over a span, with
  its children (sub-trees, or :class:`~lexic.ir.nodes.IrLiteral` leaves for
  consumed characters). The reducible output a
  :class:`~lexic.parsing_2.reduce.Reducer` folds. Unchanged from the
  single-derivation era.
- :class:`SppfNode` — a shared, packed forest handle for a dotted item over a
  span: the pure-data pair ``(item, end)``. Its packed families are
  ``chart.links[(item, end)]`` (each a predecessor / consumed-child pair), read on
  demand by the operation nodes — so the same handle always exposes the same
  families (sharing) without a rebuilt DAG, and ``> 1`` family ⇒ the node is
  **ambiguous**. The handle is intrinsically **binary** (one predecessor + one
  child per family), so the forest is binarised by construction — an intermediate
  node IS a dotted item ``A -> α·β`` over its span — and stays polynomial under
  ambiguity. Like every engine record it carries no methods of its own.

  Nullable rules need care: the predictor's Aycock-Horspool advance and the
  matching empty completion describe the same empty-span derivation, so both
  reference the same ``SppfNode(EarleyItem(ref, arm, len(arm), col), col)`` per
  empty-deriving arm and dedup to one family (see
  :class:`~lexic.parsing_2.ops.Predict`).

Enumeration is **lazy**: a handle's kid-sequence prefixes and its derivation
trees are :class:`IrStream` sequences driven on demand, so an ambiguous forest is
never fully materialised to read the first (or first two) derivations. Behaviour
lives on the operation nodes and the stream-source nodes, recursion flows through
``eval`` and the source nodes' ``__iter__``:

- :class:`Prefixes.eval` returns the memoised :class:`IrStream` of **kid-sequence
  prefixes** a dotted item packs — for dot 0 the single empty prefix, otherwise the
  lazy product (driven by :class:`FamilyPrefixes`) over family choices, each
  family's predecessor prefixes, and each consumed child's derivations.
- :data:`CHILD_TREES` / :data:`CHILD_STREAMS` are the child-kind seams: a terminal
  leaf is its own sole derivation; a completed sub-:class:`SppfNode` wraps each of
  its prefixes into a :class:`ParseTree` (eagerly via :class:`Derivations`, lazily
  via :data:`DERIVATION_STREAM`).
- :class:`Derivations.eval` realises a completed handle's derivations eagerly (all
  of them); :data:`DERIVATION_STREAM` is the lazy counterpart;
  :class:`BuildTree.eval` is the strict single-derivation façade — taking only the
  first two derivations and **raising**
  :exc:`~lexic.exceptions.UnsupportedConstructError` on ambiguous input (a lone
  :class:`ParseTree` cannot honestly represent it).

A :class:`ForestCtx` cursor carries the chart and a prefix memo so each
``(item, end)`` is expanded once (sharing) and cyclic recursion terminates.
"""

from __future__ import annotations

from typing import ClassVar, Iterable, Iterator, Self, Sequence, cast

from lexic.exceptions import UnsupportedConstructError
from lexic.ir.action import IrAction
from lexic.ir.base import (
    IrLeaf,
    IrNamedTuple,
    IrNone,
    IrNoneType,
    IrSelf,
    IrSeq,
    IrTuple,
)
from lexic.ir.mapping import IrMultiMap, IrTypeMap
from lexic.ir.nodes import IrLiteral, IrRuleRef
from lexic.parsing_2.chart import Chart
from lexic.parsing_2.item import EarleyItem

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


class SppfNode(IrNamedTuple[EarleyItem, int]):
    """A shared, packed forest handle for a dotted item over its span — pure data.

    The handle IS the pair ``(item, end)``; its packed families are
    ``chart.links[(item, end)]``, read by the operation nodes (:class:`Prefixes`,
    :class:`Derivations`), not by the record. Like :class:`EarleyItem` and
    :class:`~lexic.parsing_2.chart.Link` it carries no methods beyond ``__new__`` —
    derived values (the families, the dot, ambiguity) are computed inline in the
    ``eval`` bodies that need them. Scalar payload only (``_child_attrs = ()``):
    families come from the chart, never an IR-children walk.

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


class ForestCtx(IrMultiMap[tuple[EarleyItem, int], "IrStream[IrSeq]"]):
    """Per-read forest cursor — IS-A :class:`~lexic.ir.mapping.IrMultiMap`.

    Maps each ``(item, end)`` handle to its prefix :class:`IrStream`, and carries
    the chart as a second tuple element. It is the **mutable** forest-read cursor
    (the mutable-chart exception, like :class:`~lexic.parsing_2.ops.ParseCtx`):
    each handle's prefix :class:`IrStream` is filed **once** (a single-valued use
    of the multi-map), so a cyclic re-entry resolves to the same stream — whose
    ``DRIVING`` state terminates the cycle — and a shared sub-handle is expanded
    once. The cursor rides the argument channel ``nc`` exactly as :class:`ParseCtx`
    does; it is engine state, never walked.

    A tuple subtype cannot carry an extra instance slot, so ``chart`` rides tuple
    slot 1, past the :class:`IrMultiMap` backing dict at slot 0. Every inherited
    map dunder (``__contains__`` / ``__getitem__`` / ``__iadd__``) reads only slot
    0 via ``_table``, so the 2-tuple is transparent to them.

    JUSTIFIED: the directive prefers the class itself be an ``IrMultiMap`` over a
    plain ``dict`` attr for a per-read mutable cursor — so the memo IS the map
    surface (``key in ctx`` / ``ctx[key]`` / ``ctx += (key, stream)``) rather than
    a ``ctx.memo`` dict. The single-valued filing keeps the sharing invariant: a
    handle's bucket holds exactly one stream, read as ``ctx[key][0]``.

    :ivar chart: The chart holding the family table (tuple slot 1).
    """

    __slots__ = ()

    def __new__(cls, chart: Chart) -> Self:
        """Build the cursor: backing dict at slot 0, ``chart`` at slot 1.

        :param chart: The chart holding the family table.
        :returns: A fresh, empty forest cursor over ``chart``.
        """
        return tuple.__new__(cls, ({}, chart))

    @property
    def chart(self) -> Chart:
        """The chart this read walks — tuple slot 1, past the backing dict."""
        return cast(Chart, tuple.__getitem__(self, 1))


class IrStream[T: IrSelf](IrLeaf[IrSelf, IrSelf]):
    """A replayable lazy sequence of ``T`` — a buffered, single-drive view.

    Drives its ``_source`` (an iterable ``T`` node) **once**, buffering each
    element so later consumers replay it without re-driving. ``nc`` is never
    threaded here — the source node already holds its own context. ``T`` is the
    element type, so a prefix stream is an ``IrStream[IrSeq]`` and a derivation
    stream an ``IrStream[ParseTree]`` — the element type is recovered statically
    (an :class:`~lexic.ir.base.IrSeq` prefix can be unpacked, a
    :class:`ParseTree` consumed) instead of erasing to :class:`~lexic.ir.base.IrSelf`.

    JUSTIFIED DEVIATION from "prefer :class:`~lexic.ir.mapping.IrMultiMap`": this
    is a **keyless lazy sequence**, not a multi-valued map; the immutable
    ``tuple``/:class:`~lexic.ir.base.IrSeq` tiers cannot hold a growing buffer, so
    it follows the mutable ``__slots__``-leaf precedent (:class:`ForestCtx`,
    :class:`~lexic.parsing_2.ops.ParseCtx`, :class:`~lexic.parsing_2.chart.Column`).
    Behaviour is on :meth:`__iter__` only (an allowed dunder) — no free methods.

    **Partial-consumption invariant:** a driving consumer must run the stream to
    exhaustion or abandon the WHOLE forest read. A partially-consumed stream must
    not be re-iterated by an *independent* consumer: its suspended ``DRIVING``
    state would be misread as a genuine cycle and replay the cycle sentinel. Every
    current caller honours this — short-circuits take the first one or two
    derivations then discard the stream, eager realisers exhaust it.

    :ivar _buffer: Elements driven so far, replayed on re-iteration.
    :ivar _source: The iterable ``T`` node driven once — an
        :class:`~lexic.ir.base.IrSeq` or a source node (:class:`FamilyPrefixes`,
        :class:`DerivationTrees`).
    :ivar _state: One of :data:`_FRESH` / :data:`_DRIVING` / :data:`_DONE`.
    :ivar _on_cycle: What to replay on a re-entrant (cyclic) iteration — the
        empty-prefix sentinel ``(IrSeq(),)`` for a prefix stream (reproducing the
        eager ``IrSeq(IrSeq())`` seed), empty for a stream that is never re-entered.
    """

    __slots__ = ("_buffer", "_source", "_state", "_on_cycle")

    _buffer: list[T]
    _source: Iterable[T]
    _state: int
    _on_cycle: tuple[T, ...]

    def __init__(self, source: Iterable[T], on_cycle: tuple[T, ...] = ()) -> None:
        """Wrap ``source`` as an undriven, empty stream.

        :param source: An iterable ``T`` node (an :class:`~lexic.ir.base.IrSeq` or
            a source node defining ``__iter__``), driven once on first iteration.
        :param on_cycle: The sentinel to replay on a cyclic re-entry (default
            none); a prefix stream passes ``(IrSeq(),)`` to terminate cycles.
        """
        self._buffer = []
        self._source = source
        self._state = _FRESH
        self._on_cycle = on_cycle

    def __iter__(self) -> Iterator[T]:
        """Replay the buffer, driving the source once if not yet done.

        ``DONE`` replays the full buffer; ``DRIVING`` (a re-entry) is a genuine
        cycle and replays :attr:`_on_cycle` without touching the source; ``FRESH``
        drives the source once, buffering each element.

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
        for element in self._source:
            self._buffer.append(element)
            yield element
        self._state = _DONE


class FamilyPrefixes(IrLeaf[IrSelf, IrSelf]):
    """Source for a dot>0 handle's prefix :class:`IrStream` — the lazy family product.

    A transient cursor-like leaf (mutable ``__slots__`` precedent, like
    :class:`~lexic.parsing_2.ops.ParseCtx`): carries the handle, the forest cursor,
    and the parser so :meth:`__iter__` can drive the product without a closure. Per
    packed family it yields each predecessor prefix extended by each consumed
    child — the Cartesian product, in source order, computed lazily.

    :ivar _node: The :class:`SppfNode` handle to expand.
    :ivar _ctx: The forest cursor (chart + prefix memo).
    :ivar _parser: The dispatcher, forwarded to child / predecessor expansion.
    """

    __slots__ = ("_node", "_ctx", "_parser")

    _node: SppfNode
    _ctx: ForestCtx
    _parser: IrSelf

    def __init__(self, node: SppfNode, ctx: ForestCtx, parser: IrSelf) -> None:
        """Bind the handle, cursor, and parser for one lazy expansion.

        :param node: The :class:`SppfNode` handle to expand.
        :param ctx: The forest cursor.
        :param parser: The dispatcher forwarded to sub-expansion.
        """
        self._node = node
        self._ctx = ctx
        self._parser = parser

    def __iter__(self) -> Iterator[IrSeq]:
        """Yield each kid-sequence prefix the handle packs, lazily.

        :returns: An iterator of :class:`~lexic.ir.base.IrSeq` prefixes.
        """
        ctx_nc = IrTuple(self._ctx)
        key = (self._node.item, self._node.end)
        for link in self._ctx.chart.links[key]:
            predecessor = PREFIXES.eval(
                self._parser,
                SppfNode(link.predecessor, link.predecessor_end),
                ctx_nc,
            )
            children = CHILD_STREAMS.eval(self._parser, link.child, ctx_nc)
            for prefix in predecessor:
                for child in children:
                    yield IrSeq(*prefix, child)


class DerivationTrees(IrLeaf[IrSelf, IrSelf]):
    """Source for a handle's :class:`ParseTree` :class:`IrStream`.

    A transient cursor-like leaf (mutable ``__slots__`` precedent): wraps each of a
    handle's prefixes into a :class:`ParseTree` under the rule's symbol, lazily —
    so an ambiguous handle's derivations are produced one at a time, never all
    materialised. Carries the handle, the cursor, the parser, and the symbol.

    :ivar _node: The completed :class:`SppfNode` handle.
    :ivar _ctx: The forest cursor.
    :ivar _parser: The dispatcher, forwarded to prefix expansion.
    :ivar _symbol: The rule symbol each derivation derives.
    """

    __slots__ = ("_node", "_ctx", "_parser", "_symbol")

    _node: SppfNode
    _ctx: ForestCtx
    _parser: IrSelf
    _symbol: IrRuleRef

    def __init__(
        self, node: SppfNode, ctx: ForestCtx, parser: IrSelf, symbol: IrRuleRef
    ) -> None:
        """Bind the handle, cursor, parser, and symbol for lazy derivation.

        :param node: The completed :class:`SppfNode` handle.
        :param ctx: The forest cursor.
        :param parser: The dispatcher forwarded to prefix expansion.
        :param symbol: The rule symbol each derivation derives.
        """
        self._node = node
        self._ctx = ctx
        self._parser = parser
        self._symbol = symbol

    def __iter__(self) -> Iterator[ParseTree]:
        """Yield one :class:`ParseTree` per prefix the handle packs, lazily.

        :returns: An iterator of :class:`ParseTree` derivations.
        """
        for kids in PREFIXES.eval(self._parser, self._node, IrTuple(self._ctx)):
            yield ParseTree(self._symbol, kids)


class Prefixes(IrLeaf[IrSelf, IrSelf]):
    """Return the lazy :class:`IrStream` of kid-sequence prefixes a handle packs.

    Invoked directly via :data:`PREFIXES`: ``n`` is the :class:`SppfNode` handle;
    ``nc`` is ``(chart,)`` on entry or ``(ForestCtx,)`` on recursion — the cursor
    carries the chart and the prefix memo. Dot 0 is the single empty prefix;
    otherwise the stream's source (:class:`FamilyPrefixes`) drives the lazy product
    over each family's predecessor prefixes and consumed-child derivations. The
    stream is memoised on the cursor and filed **before** the source is driven, so
    a shared sub-handle expands once and a cyclic re-entry replays the same stream
    (whose ``DRIVING`` state terminates the cycle).
    """

    def eval(self, d: IrSelf, n: IrSelf, nc: Sequence[IrSelf], /) -> IrStream[IrSeq]:
        """Return handle ``n``'s memoised prefix :class:`IrStream`.

        :param d: Dispatcher, forwarded to the family source.
        :param n: The :class:`SppfNode` handle to expand.
        :param nc: ``(chart | ForestCtx,)``.
        :returns: The handle's prefix :class:`IrStream` (each element an
            :class:`~lexic.ir.base.IrSeq` prefix).
        """
        node = cast(SppfNode, n)
        head = nc[0]
        ctx = head if isinstance(head, ForestCtx) else ForestCtx(cast(Chart, head))
        key = (node.item, node.end)
        if key in ctx:
            return cast("IrStream[IrSeq]", ctx[key][0])
        source: Iterable[IrSeq] = (
            IrSeq(IrSeq()) if node.item.dot == 0 else FamilyPrefixes(node, ctx, d)
        )
        # on_cycle reproduces the eager IrSeq(IrSeq()) seed: a re-entrant prefix
        # stream replays one empty prefix, terminating the cycle.
        stream: IrStream[IrSeq] = IrStream(source, (IrSeq(),))
        ctx += (key, stream)  # file before any drive: cyclic re-entry replays it
        return stream


class DerivationStream(IrLeaf[IrSelf, IrSelf]):
    """Return the lazy :class:`IrStream` of a completed handle's derivation trees.

    Invoked directly via :data:`DERIVATION_STREAM`: ``n`` is a completed
    :class:`SppfNode`; ``nc`` is ``(chart,)`` or ``(ForestCtx,)``. Establishes the
    :class:`ForestCtx` once (so a top-level caller seeds the cursor) then wraps
    each prefix into a :class:`ParseTree` lazily via :class:`DerivationTrees`. The
    single lazy source both short-circuits (``parse`` / ``is_ambiguous``) and the
    eager :class:`Derivations` enumeration consume.
    """

    def eval(
        self, d: IrSelf, n: IrSelf, nc: Sequence[IrSelf], /
    ) -> IrStream[ParseTree]:
        """Return handle ``n``'s lazy :class:`ParseTree` :class:`IrStream`.

        :param d: Dispatcher, forwarded to prefix expansion.
        :param n: The completed :class:`SppfNode` handle.
        :param nc: ``(chart | ForestCtx,)``.
        :returns: The handle's :class:`ParseTree` stream.
        """
        head = nc[0]
        ctx = head if isinstance(head, ForestCtx) else ForestCtx(cast(Chart, head))
        symbol = cast(SppfNode, n).item.rule_name
        return IrStream(DerivationTrees(cast(SppfNode, n), ctx, d, symbol))


class Derivations(IrLeaf[IrSelf, IrSelf]):
    """Realise a completed handle's prefixes into ALL :class:`ParseTree` trees.

    Invoked directly via :data:`DERIVATIONS`: ``n`` is a completed
    :class:`SppfNode`; ``nc`` is ``(chart,)`` or ``(ForestCtx,)``. Eagerly drains
    the lazy :data:`DERIVATION_STREAM` into an :class:`~lexic.ir.base.IrSeq` — so
    an ambiguous handle yields every derivation, an unambiguous one exactly the
    single derivation. The public way to recover ALL derivations of a parse.
    """

    def eval(self, d: IrSelf, n: IrSelf, nc: Sequence[IrSelf], /) -> IrSeq:
        """Enumerate every :class:`ParseTree` the handle ``n`` packs.

        :param d: Dispatcher, forwarded to the lazy stream.
        :param n: The completed :class:`SppfNode` handle.
        :param nc: ``(chart | ForestCtx,)``.
        :returns: An :class:`~lexic.ir.base.IrSeq` of :class:`ParseTree` derivations.
        """
        return IrSeq(*DERIVATION_STREAM.eval(d, n, nc))


class ChildTrees(IrLeaf[IrSelf, IrSelf]):
    """Eager child-kind seam for a completed sub-:class:`SppfNode` in a family.

    The non-leaf arm of :data:`CHILD_TREES`: a sub-rule child wraps each of its own
    prefixes into a :class:`ParseTree` (via :data:`DERIVATIONS`) — so the parent
    appends a completed sub-tree and the sub-tree's own ambiguity is surfaced. A
    terminal leaf is handled by the leaf arm (:class:`Whole`), contributing itself.
    """

    def eval(self, d: IrSelf, n: IrSelf, nc: Sequence[IrSelf], /) -> IrSeq:
        """Wrap sub-node ``n``'s prefixes into :class:`ParseTree` derivations.

        :param d: Dispatcher, forwarded to the sub-node's prefix expansion.
        :param n: The consumed :class:`SppfNode` child.
        :param nc: ``(ForestCtx,)`` — the cursor to forward.
        :returns: The sub-node's :class:`ParseTree` derivations.
        """
        return DERIVATIONS.eval(d, n, nc)


class ChildStream(IrLeaf[IrSelf, IrSelf]):
    """Lazy child-kind seam for a completed sub-:class:`SppfNode` in a family.

    The non-leaf arm of :data:`CHILD_STREAMS`, consumed inside
    :class:`FamilyPrefixes`: a sub-rule child yields its :class:`ParseTree`
    derivations lazily (via :data:`DERIVATION_STREAM`), so a shared sub-handle's
    derivations are produced on demand rather than realised eagerly. A terminal
    leaf is handled by the leaf arm (:class:`Whole`).
    """

    def eval(
        self, d: IrSelf, n: IrSelf, nc: Sequence[IrSelf], /
    ) -> IrStream[ParseTree]:
        """Return sub-node ``n``'s lazy :class:`ParseTree` stream.

        :param d: Dispatcher, forwarded to the sub-node's prefix expansion.
        :param n: The consumed :class:`SppfNode` child.
        :param nc: ``(ForestCtx,)`` — the cursor to forward.
        :returns: The sub-node's :class:`ParseTree` :class:`IrStream`.
        """
        return DERIVATION_STREAM.eval(d, n, nc)


class LiteralStream(IrLeaf[IrSelf, IrSelf]):
    """Lazy terminal child-kind seam — a consumed :class:`~lexic.ir.nodes.IrLiteral`.

    The non-recursing arm of :data:`CHILD_STREAMS`: a consumed terminal is its own
    sole derivation, wrapped in a one-element :class:`IrStream` so the lazy child
    seam is uniformly stream-valued (each :data:`CHILD_STREAMS` arm yields an
    :class:`IrStream`, so :class:`FamilyPrefixes` iterates the result without
    erasing to :class:`~lexic.ir.base.IrSelf`). The single-element source means the
    leaf contributes itself once — never split into characters. Nullable (empty)
    derivations are NOT terminals: an empty-span completion is a shared
    :class:`SppfNode`, flowing through the :class:`ChildStream` arm instead.
    """

    def eval(
        self, _d: IrSelf, n: IrSelf, _nc: Sequence[IrSelf], /
    ) -> IrStream[IrLiteral]:
        """Contribute the whole child ``n`` as a one-element :class:`IrStream`.

        :param _d: Dispatcher (unused).
        :param n: The consumed terminal :class:`~lexic.ir.nodes.IrLiteral` leaf.
        :param _nc: Arguments (unused).
        :returns: A one-element :class:`IrStream` over ``n``.
        """
        return IrStream(IrSeq(cast(IrLiteral, n)))


class Whole(IrLeaf[IrSelf, IrSelf]):
    """Eager terminal child-kind seam — a consumed :class:`~lexic.ir.nodes.IrLiteral`.

    The non-recursing arm of :data:`CHILD_TREES`. A consumed terminal
    :class:`~lexic.ir.nodes.IrLiteral` is its own sole derivation, contributed as a
    one-element :class:`~lexic.ir.base.IrSeq` so the eager family product treats it
    as a single alternative (iterating a leaf's own string would otherwise split it
    into characters). The lazy seam's terminal arm is :class:`LiteralStream`.
    Nullable (empty) derivations are NOT terminals: both the predictor's
    Aycock-Horspool advance and the completer record an empty-span completion as a
    shared :class:`SppfNode`, so they flow through the :class:`ChildTrees` arm like
    any other completed sub-rule.
    """

    def eval(self, _d: IrSelf, n: IrSelf, _nc: Sequence[IrSelf], /) -> IrSeq:
        """Contribute the whole child ``n`` as its one derivation.

        :param _d: Dispatcher (unused).
        :param n: The consumed terminal :class:`~lexic.ir.nodes.IrLiteral` leaf.
        :param _nc: Arguments (unused).
        :returns: ``IrSeq(n)`` — the child as its sole derivation.
        """
        return IrSeq(n)


class BuildTree(IrLeaf[IrSelf, IrSelf]):
    """Single-derivation façade — the ONE derivation the root handle packs (strict).

    Invoked directly via :data:`BUILD_TREE`: ``n`` is the (typically complete)
    :class:`EarleyItem`; the argument channel carries ``(chart, IrInt(end))``. The
    approved single-result policy: a single :class:`ParseTree` cannot honestly
    represent ambiguity, so a root handle packing more than one derivation
    **raises** rather than silently picking one. It takes only the **first two**
    derivations from the lazy :data:`DERIVATION_STREAM` — never the full
    (potentially exponential) enumeration — so detecting ambiguity is cheap. For
    unambiguous input the handle packs exactly one derivation, matching the
    pre-SPPF behaviour. To recover ALL derivations of an ambiguous input, build the
    :class:`SppfNode` and apply :data:`DERIVATIONS` (the
    :func:`~lexic.parsing_2.engine.derivations` entry).
    """

    def eval(self, d: IrSelf, n: IrSelf, nc: Sequence[IrSelf], /) -> IrSelf:
        """Return the sole :class:`ParseTree` the root ``(item, end)`` packs.

        :param d: Dispatcher, forwarded to the lazy stream.
        :param n: The :class:`EarleyItem` to reconstruct.
        :param nc: ``(chart, IrInt(end))``.
        :returns: The single :class:`ParseTree` derivation for the item.
        :raises UnsupportedConstructError: If the handle packs no derivation, or
            more than one (ambiguous input).
        """
        node = SppfNode(cast(EarleyItem, n), int(cast(int, nc[1])))
        stream = DERIVATION_STREAM.eval(d, node, IrTuple(nc[0]))
        first = IrNone
        for index, tree in enumerate(stream):
            if index == 0:
                first = tree
                continue
            raise UnsupportedConstructError(  # a second derivation ⇒ ambiguous
                f"parsing_2: ambiguous input — more than one derivation of "
                f"{node.item.rule_name!r}; use the forest enumeration entry "
                "(parse_forest / derivations) instead"
            )
        if isinstance(first, IrNoneType):
            raise UnsupportedConstructError(
                f"parsing_2: no derivation of {node.item.rule_name!r}"
            )
        return first


PREFIXES = Prefixes()
"""Shared :class:`Prefixes` instance — prefix-stream construction is stateless."""

DERIVATIONS = Derivations()
"""Shared :class:`Derivations` instance — eager enumeration is stateless."""

DERIVATION_STREAM = DerivationStream()
"""Shared :class:`DerivationStream` instance — lazy enumeration is stateless."""

BUILD_TREE = BuildTree()
"""Shared :class:`BuildTree` instance — single-derivation extraction is stateless."""


CHILD_TREES: IrTypeMap[IrSeq] = IrTypeMap(
    IrAction(SppfNode, ChildTrees()),
    IrAction(IrLiteral, Whole()),
)
"""Eager child-kind dispatch over a family's consumed child: a completed sub-node —
including an empty-span nullable completion — wraps to its own :class:`ParseTree`
derivations (:class:`ChildTrees`); a consumed terminal
:class:`~lexic.ir.nodes.IrLiteral` is its sole derivation (:class:`Whole`). Kept for
direct/test callers; :data:`CHILD_STREAMS` is the lazy seam the family product uses."""


CHILD_STREAMS: IrTypeMap[IrStream] = IrTypeMap(
    IrAction(SppfNode, ChildStream()),
    IrAction(IrLiteral, LiteralStream()),
)
"""Lazy child-kind dispatch consumed inside :class:`FamilyPrefixes` — uniformly
:class:`IrStream`-valued, so the family product iterates each arm's result without
erasing to :class:`~lexic.ir.base.IrSelf`. A completed sub-node yields its
:class:`ParseTree` derivations lazily (:class:`ChildStream` →
:data:`DERIVATION_STREAM`); a consumed terminal
:class:`~lexic.ir.nodes.IrLiteral` is its sole derivation as a one-element stream
(:class:`LiteralStream`)."""
