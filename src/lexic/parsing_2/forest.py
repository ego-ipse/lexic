"""Parse derivations — the reducible output of the engine.

A :class:`ParseTree` is one derivation: a non-terminal symbol over a span,
with its children (sub-trees, or :class:`~lexic.ir.nodes.IrLiteral` leaves for
consumed characters). It IS-AN :class:`~lexic.ir.base.IrNamedTuple`, so it walks
and rebuilds like any IR node and :class:`~lexic.parsing_2.reduce.Reducer` can
fold it with the action algebra.

:class:`BuildTree` reconstructs a derivation from the chart's provenance links:
its ``eval`` walks an item from its dot back to dot 0, collecting the child
consumed at each step, then assembles them in source order. Because the completer
builds sub-trees eagerly (a rule's children are all linked before it is
processed), one pass suffices. It is invoked directly (not through a dispatch
table) via the shared :data:`BUILD_TREE` instance, with the chart and the
end-column handed in on the argument channel.

Shape caveat: a real Earley parse yields a shared packed forest (SPPF) that
encodes *all* derivations of an ambiguous input. The grammars in scope (JSON,
ABNF) are unambiguous, so this models the single-derivation case directly; SPPF
binarisation and disambiguation are the generalisation, not shown here.
"""

from __future__ import annotations

from typing import ClassVar, Self, Sequence, cast

from lexic.ir.base import IrLeaf, IrNamedTuple, IrSelf, IrSeq
from lexic.ir.nodes import IrRuleRef
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

        A derivation node's two fields are always supplied positionally, so
        building the tuple directly saves two Python-level ``__new__`` frames per
        node (one per completed rule).

        :param symbol: The rule this node derives.
        :param kids: The matched sub-derivations / terminals, in source order.
        :returns: A new :class:`ParseTree`.
        """
        return tuple.__new__(cls, (symbol, kids))


class BuildTree(IrLeaf[IrSelf, IrSelf]):
    """Reconstruct the derivation of an item from the chart's provenance links.

    Invoked directly via :data:`BUILD_TREE`: ``n`` is the (typically complete)
    :class:`EarleyItem` to reconstruct; the argument channel carries
    ``(chart, IrInt(end))`` — the chart holding the links and the column the item
    ends at (the link-table key alongside the item).
    """

    def eval(self, _d: IrSelf, n: IrSelf, nc: Sequence[IrSelf], /) -> IrSelf:
        """Walk provenance links from the dot back to dot 0; assemble in order.

        :param _d: Dispatcher (unused).
        :param n: The :class:`EarleyItem` to reconstruct.
        :param nc: ``(chart, IrInt(end))``.
        :returns: The :class:`ParseTree` for the item.
        """
        item = cast(EarleyItem, n)
        chart = cast(Chart, nc[0])
        end = int(cast(int, nc[1]))
        kids: list[IrSelf] = []
        cur, cur_end = item, end
        while cur.dot > 0:
            link = chart.links[(cur, cur_end)]
            kids.append(link.child)
            cur, cur_end = link.predecessor, link.predecessor_end
        kids.reverse()
        return ParseTree(item.rule_name, IrSeq(*kids))


BUILD_TREE = BuildTree()
"""Shared :class:`BuildTree` instance — derivation extraction is stateless."""
