"""Parse derivations — the reducible output of the engine.

A :class:`ParseTree` is one derivation: a non-terminal symbol over a span,
with its children (sub-trees, or :class:`~lexic.ir.nodes.IrLiteral` leaves for
consumed characters). It IS-AN :class:`~lexic.ir.base.IrNamedTuple`, so it walks
and rebuilds like any IR node and :class:`~lexic.parsing_2.reduce.Reducer` can
fold it with the action algebra.

:func:`build_tree` reconstructs a derivation from the chart's provenance links:
it walks an item from its dot back to dot 0, collecting the child consumed at
each step, then assembles them in source order. Because the completer builds
sub-trees eagerly (a rule's children are all linked before it is processed), one
pass suffices.

Shape caveat: a real Earley parse yields a shared packed forest (SPPF) that
encodes *all* derivations of an ambiguous input. The grammars in scope (JSON,
ABNF) are unambiguous, so this models the single-derivation case directly; SPPF
binarisation and disambiguation are the generalisation, not shown here.
"""

from __future__ import annotations

from typing import ClassVar

from lexic.ir.base import IrNamedTuple, IrSelf, IrSeq
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


def build_tree(chart: Chart, item: EarleyItem, end: int) -> ParseTree:
    """Reconstruct the derivation of ``item`` ending at column ``end``.

    Walks the provenance links from ``item``'s dot back to dot 0, collecting the
    child consumed at each step, then reverses them into source order.

    :param chart: The completed chart carrying the provenance links.
    :param item: The (typically complete) item to reconstruct.
    :param end: The column ``item`` ends at — the link-table key with ``item``.
    :returns: The :class:`ParseTree` for ``item``.
    """
    kids: list[IrSelf] = []
    cur, cur_end = item, end
    while cur.dot > 0:
        prev, prev_end, child = chart.links[(cur, cur_end)]
        kids.append(child)
        cur, cur_end = prev, prev_end
    kids.reverse()
    return ParseTree(item.rule_name, IrSeq(*kids))
