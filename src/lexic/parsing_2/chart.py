"""Earley chart — the per-column item sets, as mutable IR leaves.

An Earley parse grows a chart of columns, one per input position. A column is an
ordered, de-duplicated set of :class:`~lexic.parsing_2.item.EarleyItem` plus a
scan buffer (terminal items deferred to the scanner). These are the one
deliberate concession to mutability in the package: the predictor/completer add
to a column *while it is being iterated* (the Earley fixpoint), so a frozen tuple
would be rebuilt on every insert.

The chart also carries the **provenance links** that derivation extraction walks:
``links[(item, end)]`` records how an advanced item was built — its predecessor
(one dot to the left) and the child consumed to reach it (a terminal leaf or a
completed sub-:class:`~lexic.parsing_2.forest.ParseTree`). For the unambiguous
grammars in scope each ``(item, end)`` is reached one way, so one link suffices.

They still IS-A :class:`~lexic.ir.base.IrSelf` (via :class:`~lexic.ir.base.IrLeaf`),
declaring their own ``__slots__`` — :class:`~lexic.ir.meta.IrMeta` injects empty
slots by default but leaves an explicit declaration intact. ``object.__setattr__``
seeds the slots at construction, matching :class:`~lexic.ir.base.IrCallable`.
"""

from __future__ import annotations

from typing import Iterator

from lexic.ir.base import IrLeaf, IrSelf
from lexic.parsing_2.item import EarleyItem

Link = tuple[EarleyItem, int, IrSelf]
"""Provenance of one advanced item: ``(predecessor, predecessor_end, child)``.

``child`` is the node consumed to advance the dot — an
:class:`~lexic.ir.nodes.IrLiteral` terminal leaf, or a
:class:`~lexic.parsing_2.forest.ParseTree` for a completed sub-derivation.
"""


class Column(IrLeaf[IrSelf, IrSelf]):
    """One Earley set: an append-only, de-duplicated list of items.

    Iteration order is insertion order; membership is by item identity (the
    native tuple equality of :class:`EarleyItem`). ``to_scan`` collects terminal
    items for the scanner step between columns.

    :ivar index: This column's input position.
    :ivar to_scan: Terminal items deferred to :meth:`EarleyParser._scan`.
    """

    __slots__ = ("index", "_items", "_seen", "to_scan")

    index: int
    _items: list[EarleyItem]
    _seen: set[EarleyItem]
    to_scan: list[EarleyItem]

    def __init__(self, index: int) -> None:
        """Seed an empty column at ``index``.

        :param index: The input position this column represents.
        """
        object.__setattr__(self, "index", index)
        object.__setattr__(self, "_items", [])
        object.__setattr__(self, "_seen", set())
        object.__setattr__(self, "to_scan", [])

    def add(self, item: EarleyItem) -> bool:
        """Add ``item`` if absent; report whether it was new.

        The fixpoint loop relies on the boolean: a freshly added item extends
        the column being iterated, a duplicate is dropped.

        :param item: The item to insert.
        :returns: ``True`` if newly added, ``False`` if already present.
        """
        if item in self._seen:
            return False
        self._seen.add(item)
        self._items.append(item)
        return True

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

    :ivar columns: Columns indexed by input position (``0 .. len(text)``).
    :ivar links: Provenance — ``(advanced_item, end_column)`` → its :data:`Link`.
    """

    __slots__ = ("columns", "links")

    columns: list[Column]
    links: dict[tuple[EarleyItem, int], Link]

    def __init__(self) -> None:
        """Seed an empty chart (no columns, no links yet)."""
        object.__setattr__(self, "columns", [])
        object.__setattr__(self, "links", {})

    def ensure(self, i: int) -> None:
        """Grow the chart so column ``i`` exists.

        :param i: The column index that must be addressable after the call.
        """
        while len(self.columns) <= i:
            self.columns.append(Column(len(self.columns)))

    def __getitem__(self, i: int) -> Column:
        """Column ``i`` (call :meth:`ensure` first if it may not exist)."""
        return self.columns[i]

    def __len__(self) -> int:
        """Number of columns built so far."""
        return len(self.columns)
