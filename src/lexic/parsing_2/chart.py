"""Earley chart — the per-column item sets, as mutable IR leaves.

An Earley parse grows a chart of columns, one per input position. A column is an
ordered, de-duplicated set of :class:`~lexic.parsing_2.item.EarleyItem`. These are
the one deliberate concession to mutability in the package (the **mutable-chart
exception**): the predictor/completer add to a column *while it is being iterated*
(the Earley fixpoint), so a frozen tuple would be rebuilt on every insert. The
mutation surface is dunders only — ``item in column`` (membership) and
``column += item`` (insert) — so the leaves stay ``eval`` + dunders, no named
methods.

The chart also carries the **provenance links** that derivation extraction walks:
``chart.links[(item, end)]`` records how an advanced item was built — its
predecessor (one dot to the left) and the child consumed to reach it (a terminal
leaf or a completed sub-:class:`~lexic.parsing_2.forest.ParseTree`). For the
unambiguous grammars in scope each ``(item, end)`` is reached one way, so one link
suffices.

All three leaves IS-A :class:`~lexic.ir.base.IrSelf` (via
:class:`~lexic.ir.base.IrLeaf`), declaring their own ``__slots__`` —
:class:`~lexic.ir.meta.IrMeta` injects empty slots by default but leaves an
explicit declaration intact. ``object.__setattr__`` seeds the slots at
construction; the backing ``list``/``set``/``dict`` then mutate in place.
"""

from __future__ import annotations

from typing import ClassVar, Iterator

from lexic.ir.base import IrLeaf, IrNamedTuple, IrSelf
from lexic.ir.mapping import IrMultiMap
from lexic.ir.nodes import IrRuleRef
from lexic.parsing_2.item import EarleyItem


class Link(IrNamedTuple[EarleyItem, int, IrSelf]):
    """Provenance of one advanced item: how its dot reached its current position.

    Scalar payload only (``_child_attrs = ()``): a link is engine state, not a
    grammar node to walk.

    :ivar predecessor: The item one dot to the left.
    :ivar predecessor_end: The column ``predecessor`` ends at.
    :ivar child: The node consumed to advance the dot — an
        :class:`~lexic.ir.nodes.IrLiteral` terminal leaf, or a
        :class:`~lexic.parsing_2.forest.ParseTree` for a completed sub-derivation.
    """

    _child_attrs: ClassVar[tuple[str, ...]] = ()
    predecessor: EarleyItem
    predecessor_end: int
    child: IrSelf


class Links(IrLeaf[IrSelf, IrSelf]):
    """The provenance table — ``(advanced_item, end_column)`` → its :class:`Link`.

    A mutable mapping leaf (the mutable-chart exception). Read with
    ``key in links`` / ``links[key]`` and written with ``links[key] = link`` —
    dunders only.
    """

    __slots__ = ("_table",)

    _table: dict[tuple[EarleyItem, int], Link]

    def __init__(self) -> None:
        """Seed an empty link table."""
        self._table = {}

    def __contains__(self, key: tuple[EarleyItem, int]) -> bool:
        """Whether ``key`` already has a recorded link."""
        return key in self._table

    def __getitem__(self, key: tuple[EarleyItem, int]) -> Link:
        """The link recorded for ``key``."""
        return self._table[key]

    def __setitem__(self, key: tuple[EarleyItem, int], link: Link) -> None:
        """Record ``link`` as the provenance of ``key``."""
        self._table[key] = link


class Column(IrLeaf[IrSelf, IrSelf]):
    """One Earley set: an append-only, de-duplicated list of items.

    Iteration order is insertion order; membership is by item identity (the
    native tuple equality of :class:`EarleyItem`). The mutation surface is
    dunders: ``item in column`` tests membership, ``column += item`` inserts (a
    duplicate is dropped), and ``column[i]`` / ``len(column)`` / iteration give
    the cursor view the driver walks.

    Insert also files an item under the :class:`~lexic.ir.nodes.IrRuleRef` its
    dot faces, in the :attr:`waiting` index — so the completer reads only the
    predecessors awaiting a finished rule (``column.waiting[rule_name]``) instead
    of rescanning the whole column. The index is maintained incrementally because
    the completer runs *while* the column is still being closed (items added
    mid-iteration are filed at once).

    :ivar index: This column's input position.
    :ivar waiting: ``IrRuleRef`` after the dot → the items awaiting it.
    """

    __slots__ = ("index", "_items", "_seen", "waiting")

    index: int
    _items: list[EarleyItem]
    _seen: set[EarleyItem]
    waiting: IrMultiMap[IrRuleRef, EarleyItem]

    def __init__(self, index: int) -> None:
        """Seed an empty column at ``index``.

        :param index: The input position this column represents.
        """
        self.index = index
        self._items = []
        self._seen = set()
        self.waiting = IrMultiMap()

    def __iadd__(self, item: EarleyItem) -> Column:
        """Insert ``item`` if absent (idempotent); return the column.

        Pair with ``item in column`` to act once on first insertion (e.g. to
        record a provenance link exactly once). An item whose dot faces a
        non-terminal is also filed under that :class:`~lexic.ir.nodes.IrRuleRef`
        in :attr:`waiting`.

        :param item: The item to insert.
        :returns: ``self`` (the in-place-mutated column).
        """
        if item not in self._seen:
            self._seen.add(item)
            self._items.append(item)
            if item.dot < len(item.arm):
                symbol = item.arm[item.dot].atom
                if isinstance(symbol, IrRuleRef):
                    self.waiting += (symbol, item)
        return self

    def __contains__(self, item: EarleyItem) -> bool:
        """Whether ``item`` is already in the column."""
        return item in self._seen

    def __iter__(self) -> Iterator[EarleyItem]:
        """Iterate items in insertion order."""
        return iter(self._items)

    def __len__(self) -> int:
        """Number of items currently in the column."""
        return len(self._items)

    def __getitem__(self, i: int) -> EarleyItem:
        """The item at position ``i`` (the cursor view used by the driver)."""
        return self._items[i]


class Chart(IrLeaf[IrSelf, IrSelf]):
    """The full chart — growable columns plus the provenance link table.

    ``chart[i]`` returns column ``i``, growing the chart so it exists (the old
    explicit ``ensure`` folds into indexed access). ``chart.links`` is the
    :class:`Links` table.

    :ivar links: Provenance — ``(advanced_item, end_column)`` → its :class:`Link`.
    """

    __slots__ = ("_columns", "links")

    _columns: list[Column]
    links: Links

    def __init__(self) -> None:
        """Seed an empty chart (no columns, no links yet)."""
        self._columns = []
        self.links = Links()

    def __getitem__(self, i: int) -> Column:
        """Column ``i``, growing the chart so it exists.

        :param i: The column index to read (and grow to).
        :returns: Column ``i``.
        """
        while len(self._columns) <= i:
            self._columns.append(Column(len(self._columns)))
        return self._columns[i]

    def __len__(self) -> int:
        """Number of columns built so far."""
        return len(self._columns)
