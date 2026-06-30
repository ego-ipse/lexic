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
leaf or a completed sub-derivation, referenced as another ``(item, end)`` key).
Following Scott (2008, *SPPF-Style Parsing From Earley Recognisers*), an
``(item, end)`` reached **more than one way** records an ADDITIONAL link rather
than dropping it — the set of links for a key is its set of *packed families*,
and a key with two or more families is an **ambiguity point**. Identical
families dedup. This makes the link table a shared, packed parse forest (SPPF):
:mod:`~lexic.parsing_2.forest` walks it as a DAG.

:class:`Column` and :class:`Chart` ARE-A :class:`~lexic.ir.base.IrLeaf`,
declaring their own ``__slots__``; ``object.__setattr__`` seeds the slots at
construction and the backing ``list``/``set`` mutates in place.
:class:`Links` IS-A :class:`~lexic.ir.mapping.IrMultiMap` (which stores its
backing dict as the sole tuple element via ``tuple.__new__``), and overrides
only ``__iadd__`` to add SPPF-dedup on top of the inherited append.
"""

from __future__ import annotations

from typing import Iterator

from lexic.ir.base import IrLeaf, IrSelf
from lexic.ir.mapping import IrMultiMap
from lexic.ir.nodes import IrRuleRef
from lexic.parsing_2.item import EarleyItem

Link = tuple[EarleyItem, int, IrSelf]
"""Provenance of one advanced item — a plain ``tuple`` ``(predecessor,
predecessor_end, child)``: ``[0]`` the item one dot to the left, ``[1]`` the
column it ends at, ``[2]`` the node consumed to advance the dot (an
:class:`~lexic.ir.nodes.IrLiteral` terminal leaf, or a
:class:`~lexic.parsing_2.forest.SppfNode` referencing a completed sub-derivation
``(item, end)`` — shared, never flattened, so the forest stays polynomial under
ambiguity). Engine state, never walked, so construction is a single allocation
and the SPPF dedup in :class:`Links` uses native tuple equality."""


class Links(IrMultiMap[tuple[EarleyItem, int], Link]):
    """The provenance table — ``(advanced_item, end_column)`` → its packed families.

    Subclasses :class:`~lexic.ir.mapping.IrMultiMap`, which already provides the
    backing-dict singleton tuple, O(1) ``__contains__``, snapshot ``__getitem__``,
    identity ``__eq__``/``__hash__``, and the in-place ``__iadd__`` — so the only
    custom work is the SPPF dedup: ``links += (key, link)`` records a family only
    when it is not already present (idempotent dedup of identical families). A key
    with more than one distinct family is an **ambiguity point** (Scott 2008).

    The surface is dunders only (inherited from :class:`IrMultiMap`):

    - ``key in links`` — whether the key has at least one recorded family.
    - ``links[key]`` — the key's families as a fresh :class:`~lexic.ir.base.IrSeq`
      snapshot (empty on a miss), safe to iterate while the live list still grows.
    - ``links += (key, link)`` — record ``link`` as a family of ``key`` if it is
      not already present (idempotent dedup prevents spurious ambiguity from
      nullable Aycock-Horspool advances; see :class:`~lexic.parsing_2.ops.Predict`).
    """

    def __iadd__(self, entry: tuple[tuple[EarleyItem, int], Link]) -> Links:
        """Record a family for a key, deduping identical families; return self.

        Overrides :meth:`IrMultiMap.__iadd__` to add the SPPF dedup check —
        ``Link`` equality is tuple equality, so the check is O(bucket-size) but
        buckets remain small on unambiguous input (one family per key).

        :param entry: ``(key, link)`` — the ``(item, end)`` key and the new family.
        :returns: ``self`` (the in-place-mutated table).
        """
        key, link = entry
        bucket = self._table.setdefault(key, [])
        if link not in bucket:
            bucket.append(link)
        return self


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

    Symmetrically, an item whose dot faces a *terminal* atom is filed under that
    atom in the :attr:`scannable_by_atom` index — so the char-indexed scanner
    advances only the items facing an atom that accepts the current character
    (``column.scannable_by_atom[atom]``), never touching the two-thirds that face
    a ruleref nor the terminals that reject the char. Same incremental-maintenance
    reason as :attr:`waiting`.

    :ivar index: This column's input position.
    :ivar waiting: ``IrRuleRef`` after the dot → the items awaiting it.
    :ivar scannable_by_atom: Terminal atom after the dot → the items facing it.

    .. note::
        ``_items`` and ``_seen`` are a plain ``list`` + ``set``, not an
        :class:`~lexic.ir.mapping.IrMultiMap`.  The column is an **ordered-dedup
        sequence** (insertion order + O(1) membership via ``_seen``), which
        ``IrMultiMap`` (key → bucket) does not model — there is no key here, only
        items.  Forcing a map shape would require a dummy self-key that adds
        indirection with no gain.  ``waiting`` (key → items) is the correct
        :class:`IrMultiMap` use here.
    """

    __slots__ = (
        "index",
        "_items",
        "_seen",
        "waiting",
        "scannable_by_atom",
        "predicted",
        "leo",
    )

    index: int
    _items: list[EarleyItem]
    _seen: set[EarleyItem]
    waiting: IrMultiMap[IrRuleRef, EarleyItem]
    scannable_by_atom: IrMultiMap[IrSelf, EarleyItem]
    predicted: set[str]
    leo: IrMultiMap[IrRuleRef, IrSelf]

    def __init__(self, index: int) -> None:
        """Seed an empty column at ``index``.

        :param index: The input position this column represents.
        """
        self.index = index
        self._items = []
        self._seen = set()
        self.waiting = IrMultiMap()
        self.scannable_by_atom = IrMultiMap()
        self.predicted = set()
        # Leo transitive-item memo (recognition only): completing ``ref`` → the
        # topmost item to jump to (or :data:`IrNone` when not Leo-eligible),
        # filed single-valued once this column is closed. See
        # :class:`~lexic.parsing_2.ops.LeoItem`.
        self.leo = IrMultiMap()

    def __iadd__(self, item: EarleyItem) -> Column:
        """Insert ``item`` if absent (idempotent); return the column.

        Pair with ``item in column`` to act once on first insertion (e.g. to
        record a provenance link exactly once). An item whose dot faces a
        non-terminal is also filed under that :class:`~lexic.ir.nodes.IrRuleRef`
        in :attr:`waiting`; one facing a terminal is filed under that atom in
        :attr:`scannable_by_atom`.

        The :class:`~lexic.ir.mapping.IrMultiMap` ``__iadd__`` calls are inlined
        here — direct ``_table`` access avoids the method-call + tuple-unpack
        overhead on the per-item hot path.

        :param item: The item to insert.
        :returns: ``self`` (the in-place-mutated column).
        """
        if item not in self._seen:
            self._seen.add(item)
            self._items.append(item)
            _, arm, dot, _ = item  # tuple unpack: skips per-field descriptor reads
            if dot < len(arm):
                symbol = arm[dot].atom
                if isinstance(symbol, IrRuleRef):
                    t = self.waiting._table
                    bucket = t.get(symbol)
                    if bucket is None:
                        t[symbol] = [item]
                    else:
                        bucket.append(item)
                else:
                    t = self.scannable_by_atom._table
                    bucket = t.get(symbol)
                    if bucket is None:
                        t[symbol] = [item]
                    else:
                        bucket.append(item)
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
    :class:`Links` table — the packed parse forest in link form.

    ``chart.leo_links`` is the **deferred** half of that forest. A Leo completion
    jumps straight to a right-recursion chain's topmost item, skipping the
    intermediate completions that would otherwise record O(chain) links *per
    column* (Θ(n²) total). It files under ``(top_item, end)`` the single bottom
    triple ``(bottom_waiter, bottom_end, bottom_child)`` that lets the forest
    reader rebuild the skipped chain into :attr:`links` on demand — so only the
    chains a derivation actually walks are materialised (Θ(n) for one parse), not
    one per column. Shape matches :data:`Link`: same ``(item, end, child)`` triple,
    here naming the chain's bottom instead of one dot's predecessor.

    :ivar links: Provenance — ``(advanced_item, end_column)`` → its packed families.
    :ivar leo_links: Deferred Leo provenance — ``(top_item, end)`` → the bottom
        triple needed to rebuild its skipped right-recursion chain.
    """

    __slots__ = ("_columns", "links", "leo_links")

    _columns: list[Column]
    links: Links
    leo_links: IrMultiMap[tuple[EarleyItem, int], Link]

    def __init__(self) -> None:
        """Seed an empty chart (no columns, no links, no deferred Leo chains yet)."""
        self._columns = []
        self.links = Links()
        self.leo_links = IrMultiMap()

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
