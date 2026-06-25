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

Behaviour lives on the operation nodes, recursion flows through ``eval``:

- :class:`Prefixes.eval` yields the **kid-sequence prefixes** a dotted item packs
  — for dot 0 the single empty prefix, otherwise the Cartesian product over family
  choices, each family's predecessor prefixes, and each consumed child's
  derivations. It computes the family read and dot inline (as every engine ``eval``
  body does), recursing on itself for the predecessor.
- :data:`CHILD_TREES` is the child-kind seam: a terminal leaf is its own sole
  derivation; a completed sub-:class:`SppfNode` wraps each of its prefixes into a
  :class:`ParseTree` (via :class:`Derivations`).
- :class:`Derivations.eval` wraps a completed handle's prefixes into top-level
  :class:`ParseTree` derivations (all of them); :class:`BuildTree.eval` is the
  strict single-derivation façade — identical to the pre-SPPF behaviour for
  unambiguous input, and **raising** :exc:`~lexic.exceptions.UnsupportedConstructError`
  on ambiguous input (a lone :class:`ParseTree` cannot honestly represent it).

A :class:`ForestCtx` cursor carries the chart and a prefix memo so each
``(item, end)`` is expanded once (sharing) and cyclic recursion terminates.
"""

from __future__ import annotations

from itertools import product
from typing import ClassVar, Self, Sequence, cast

from lexic.exceptions import UnsupportedConstructError
from lexic.ir.action import IrAction
from lexic.ir.base import IrLeaf, IrNamedTuple, IrSelf, IrSeq, IrTuple
from lexic.ir.mapping import IrTypeMap
from lexic.ir.nodes import IrLiteral, IrRuleRef
from lexic.parsing_2.chart import Chart
from lexic.parsing_2.item import EarleyItem


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


class ForestCtx(IrLeaf[IrSelf, IrSelf]):
    """Per-read forest cursor — the chart plus the prefix memo.

    A **mutable** leaf (the mutable-chart exception, like
    :class:`~lexic.parsing_2.ops.ParseCtx`): ``chart`` is fixed for the read while
    ``memo`` caches each ``(item, end)`` handle's kid-sequence prefixes — so a
    shared sub-derivation is expanded once and cyclic recursion terminates. The
    cursor rides the argument channel ``nc`` exactly as :class:`ParseCtx` does; it
    is engine state, never walked.

    :ivar chart: The chart holding the family table.
    :ivar memo: ``(item, end)`` → its kid-sequence prefixes.

    .. note::
        ``memo`` is a plain ``dict``, not an :class:`~lexic.ir.mapping.IrMultiMap`.
        ``IrMultiMap`` is an append-only multi-valued map; ``memo`` is a
        single-valued *replacement* cache — it is seeded with a cycle-termination
        sentinel and then overwritten with the real result.  Append-only semantics
        would never expire the sentinel, breaking cycle termination.
    """

    __slots__ = ("chart", "memo")

    chart: Chart
    memo: dict[tuple[EarleyItem, int], IrSeq]

    def __init__(self, chart: Chart) -> None:
        """Seed the cursor for one forest read.

        :param chart: The chart holding the family table.
        """
        self.chart = chart
        self.memo = {}


class Prefixes(IrLeaf[IrSelf, IrSelf]):
    """Yield the kid-sequence prefixes a dotted :class:`SppfNode` handle packs.

    Invoked directly via :data:`PREFIXES`: ``n`` is the :class:`SppfNode` handle;
    ``nc`` is ``(chart,)`` on entry or ``(ForestCtx,)`` on recursion — the cursor
    carries the chart and the prefix memo, so the recursion threads no state by
    hand. Dot 0 is the single empty prefix; otherwise each family is the product of
    its predecessor handle's prefixes (recursing on this same body) and its consumed
    child's derivations (via :data:`CHILD_TREES`), appended in source order. The
    completed handle's symbol is applied only where the node is *consumed*
    (:data:`CHILD_TREES` / :class:`Derivations`), so this body returns one shape.
    """

    def eval(self, d: IrSelf, n: IrSelf, nc: Sequence[IrSelf], /) -> IrSeq:
        """Expand handle ``n`` to its kid-sequence prefixes.

        :param d: Dispatcher, forwarded to the child-kind dispatch.
        :param n: The :class:`SppfNode` handle to expand.
        :param nc: ``(chart | ForestCtx,)``.
        :returns: An :class:`IrSeq` of kid-sequence prefixes (each an :class:`IrSeq`).
        """
        node = cast(SppfNode, n)
        head = nc[0]
        ctx = head if isinstance(head, ForestCtx) else ForestCtx(cast(Chart, head))
        key = (node.item, node.end)
        cached = ctx.memo.get(key)
        if cached is not None:
            return cached
        ctx.memo[key] = IrSeq(IrSeq())  # seed: terminate cyclic recursion
        if node.item.dot == 0:
            return ctx.memo[key]
        ctx_nc = IrTuple(ctx)
        prefixes = [
            IrSeq(*prefix, child)
            for link in ctx.chart.links[key]
            for prefix, child in product(
                self.eval(d, SppfNode(link.predecessor, link.predecessor_end), ctx_nc),
                CHILD_TREES.eval(d, link.child, ctx_nc),
            )
        ]
        result = IrSeq(*prefixes)
        ctx.memo[key] = result
        return result


class Derivations(IrLeaf[IrSelf, IrSelf]):
    """Wrap a completed handle's prefixes into top-level :class:`ParseTree` trees.

    Invoked directly via :data:`DERIVATIONS`: ``n`` is a completed
    :class:`SppfNode`; ``nc`` is ``(chart,)`` or ``(ForestCtx,)``. Each prefix the
    handle packs becomes one :class:`ParseTree` under the rule's symbol — so an
    ambiguous handle yields every derivation, an unambiguous one exactly the single
    derivation. The public way to recover ALL derivations of a parse.
    """

    def eval(self, d: IrSelf, n: IrSelf, nc: Sequence[IrSelf], /) -> IrSeq:
        """Enumerate every :class:`ParseTree` the handle ``n`` packs.

        :param d: Dispatcher, forwarded to prefix expansion.
        :param n: The completed :class:`SppfNode` handle.
        :param nc: ``(chart | ForestCtx,)``.
        :returns: An :class:`IrSeq` of :class:`ParseTree` derivations.
        """
        symbol = cast(SppfNode, n).item.rule_name
        return IrSeq(*(ParseTree(symbol, kids) for kids in PREFIXES.eval(d, n, nc)))


class ChildTrees(IrLeaf[IrSelf, IrSelf]):
    """Child-kind seam for a completed sub-:class:`SppfNode` consumed in a family.

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


class Whole(IrLeaf[IrSelf, IrSelf]):
    """Child-kind seam for an already-whole consumed child — a terminal leaf.

    The non-recursing arm of :data:`CHILD_TREES`. A consumed terminal
    :class:`~lexic.ir.nodes.IrLiteral` is its own sole derivation, contributed as a
    one-element sequence so the family product treats it as a single alternative
    (iterating a leaf's own string would otherwise split it into characters).
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


CHILD_TREES: IrTypeMap[IrSeq] = IrTypeMap(
    IrAction(SppfNode, ChildTrees()),
    IrAction(IrLiteral, Whole()),
)
"""Child-kind dispatch over a family's consumed child: a completed sub-node — including
an empty-span nullable completion — wraps to its own :class:`ParseTree` derivations
(:class:`ChildTrees`); a consumed terminal :class:`~lexic.ir.nodes.IrLiteral` is its
sole derivation (:class:`Whole`)."""


class BuildTree(IrLeaf[IrSelf, IrSelf]):
    """Single-derivation façade — the ONE derivation the root handle packs (strict).

    Invoked directly via :data:`BUILD_TREE`: ``n`` is the (typically complete)
    :class:`EarleyItem`; the argument channel carries ``(chart, IrInt(end))``. The
    approved single-result policy: a single :class:`ParseTree` cannot honestly
    represent ambiguity, so a root handle packing more than one derivation
    **raises** rather than silently picking one. For unambiguous input the handle
    packs exactly one derivation, matching the pre-SPPF behaviour. To recover ALL
    derivations of an ambiguous input, build the :class:`SppfNode` and apply
    :data:`DERIVATIONS` (the :func:`~lexic.parsing_2.engine.derivations` entry).
    """

    def eval(self, d: IrSelf, n: IrSelf, nc: Sequence[IrSelf], /) -> IrSelf:
        """Return the sole :class:`ParseTree` the root ``(item, end)`` packs.

        :param d: Dispatcher, forwarded to enumeration.
        :param n: The :class:`EarleyItem` to reconstruct.
        :param nc: ``(chart, IrInt(end))``.
        :returns: The single :class:`ParseTree` derivation for the item.
        :raises UnsupportedConstructError: If the handle packs more than one
            derivation (ambiguous input).
        """
        node = SppfNode(cast(EarleyItem, n), int(cast(int, nc[1])))
        trees = DERIVATIONS.eval(d, node, IrTuple(nc[0]))
        if len(trees) > 1:
            raise UnsupportedConstructError(
                f"parsing_2: ambiguous input — {len(trees)} derivations of "
                f"{cast(SppfNode, node).item.rule_name!r}; use the forest "
                "enumeration entry (parse_forest / derivations) instead"
            )
        return trees[0]


PREFIXES = Prefixes()
"""Shared :class:`Prefixes` instance — prefix expansion is stateless."""

DERIVATIONS = Derivations()
"""Shared :class:`Derivations` instance — root-handle enumeration is stateless."""

BUILD_TREE = BuildTree()
"""Shared :class:`BuildTree` instance — single-derivation extraction is stateless."""
