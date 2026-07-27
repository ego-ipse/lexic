"""The IR-native SPPF link table — the decoded form of a kernel parse.

The per-column Earley sets live in the compiled kernel now
(:mod:`lexic.parsing.earley.kernel`), packed as ints. What remains here is the
IR-facing **provenance** shape the forest readers walk:
``chart.links[(item, end)]`` records how an advanced item was built — its
predecessor (one dot to the left) and the child consumed to reach it (a
terminal leaf or a completed sub-derivation, referenced as another
``(item, end)`` key). Following Scott (2008, *SPPF-Style Parsing From Earley
Recognisers*), an ``(item, end)`` reached **more than one way** records an
ADDITIONAL link rather than dropping it — the set of links for a key is its
set of *packed families*, and a key with two or more families is an
**ambiguity point**. Identical families dedup. This makes the link table a
shared, packed parse forest (SPPF): :mod:`~lexic.parsing.earley.forest` walks it
as a DAG.

A :class:`Chart` is produced by :meth:`~lexic.parsing.earley.kernel.Kernel
.to_chart`, which expands any deferred Leo chains first — so ``leo_links`` is
empty on a decoded chart and exists for shape compatibility only.

:class:`Chart` IS-A :class:`~lexic.ir.base.IrLeaf` (a mutable leaf, the
chart exception); :class:`Links` IS-A :class:`~lexic.ir.action.mapping.IrMultiMap`
overriding only ``__iadd__`` to add SPPF-dedup on top of the inherited append.
"""

from __future__ import annotations

from lexic.ir import IrLeaf, IrMultiMap, IrRuleRef, IrSelf, IrSequence

EarleyItem = tuple[IrRuleRef, IrSequence, int, int]
"""Earley items — a dotted arm ``(rule_name, arm, dot, origin)`` as a plain tuple."""

Link = tuple[EarleyItem, int, IrSelf]
"""Provenance of one advanced item — a plain ``tuple`` ``(predecessor,
predecessor_end, child)``: ``[0]`` the item one dot to the left, ``[1]`` the
column it ends at, ``[2]`` the node consumed to advance the dot (an
:class:`~lexic.ir.grammar.nodes.IrLiteral` terminal leaf, or a
:class:`~lexic.parsing.earley.forest.SppfNode` referencing a completed sub-derivation
``(item, end)`` — shared, never flattened, so the forest stays polynomial under
ambiguity)."""


class Links(IrMultiMap[tuple[EarleyItem, int], Link]):
    """The provenance table — ``(advanced_item, end_column)`` → its packed families.

    Subclasses :class:`~lexic.ir.action.mapping.IrMultiMap`, which already provides the
    backing-dict singleton tuple, O(1) ``__contains__``, live-bucket
    ``__getitem__``, identity ``__eq__``/``__hash__``, and the in-place
    ``__iadd__`` — so the only custom work is the SPPF dedup: ``links += (key,
    link)`` records a family only when it is not already present. A key with
    more than one distinct family is an **ambiguity point** (Scott 2008).
    """

    def __iadd__(self, entry: tuple[tuple[EarleyItem, int], Link]) -> Links:
        """Record a family for a key, deduping identical families; return self.

        :param entry: ``(key, link)`` — the ``(item, end)`` key and the new family.
        :returns: ``self`` (the in-place-mutated table).
        """
        key, link = entry
        bucket = self._table.setdefault(key, [])
        if link not in bucket:
            bucket.append(link)
        return self


class Chart(IrLeaf[IrSelf, IrSelf]):
    """The decoded forest — the provenance link table the IR readers walk.

    ``chart.links`` is the :class:`Links` table (the packed parse forest in
    link form); ``chart.leo_links`` exists for shape compatibility and is
    empty on a decoded chart (the kernel expands deferred Leo chains before
    decoding).

    :ivar links: Provenance — ``(advanced_item, end_column)`` → its packed families.
    :ivar leo_links: Deferred Leo provenance (empty once decoded).
    """

    __slots__ = ("links", "leo_links")

    links: Links
    leo_links: IrMultiMap[tuple[EarleyItem, int], Link]

    def __init__(self) -> None:
        """Seed an empty chart (no links, no deferred Leo chains)."""
        self.links = Links()
        self.leo_links = IrMultiMap()
