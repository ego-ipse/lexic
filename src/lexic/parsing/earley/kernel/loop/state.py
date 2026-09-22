"""Per-parse index state — the kernel's mutable-chart exception.

Candidate ``lexic/parsing/earley/kernel/state.py``. The five per-column indexes
and the two SPPF link tables one Earley parse fills, plus the one filing
operation that is theirs and not the driver's. A leaf: it imports nothing from
the kernel, so ``kernel``, ``leo`` and ``readout`` all sit above it.
"""

from __future__ import annotations

from lexic.ir import IrLeaf, IrSelf
from lexic.parsing.earley.kernel.forest.forest import PayloadLeaf

KLink = tuple[int, int, int | str | PayloadLeaf]
"""One packed SPPF family: ``(predecessor_item, predecessor_end, child)`` —
``child`` is a packed handle (completed sub-derivation), the scanned char, or a
delegated :class:`~lexic.parsing.earley.kernel.forest.forest.PayloadLeaf` (island-interior
delegation)."""


PROMOTED: KLink = (-1, -1, -1)
"""Leads a bucket whose later families are read from its completion group.

A distinguished VALUE rather than a second container: one ``links`` lookup
then tells a reader both that the key exists and how to read it, where a
parallel set cost a second hash on every query.

Shaped as a :data:`KLink` so a bucket stays ``list[KLink]`` and needs no wider
element type, and negative so it cannot collide: a predecessor item, an origin
column and a child handle are all packed non-negative ints, so no producer can
file this triple. Compared by IDENTITY against this one module-level object,
never by value."""


class KernelState(IrLeaf[IrSelf, IrSelf]):
    """Per-parse index state — the kernel's mutable-chart exception.

    The five per-column indexes are position-indexed lists (one small
    container per column, created once); the SPPF tables are parse-global,
    keyed by packed handles. Everything mutates in place.

    :ivar seen: Per column, the packed items already filed (the dedup set).
    :ivar waiting: Per column, ``rule_id`` → items whose dot faces that rule.
    :ivar scannable: Per column, ``term_id`` → items whose dot faces that atom.
    :ivar predicted: Per column, the ``rule_id``\\ s already predicted.
    :ivar leo: Per column, ``rule_id`` → memoised Leo top (``-1`` = none).
    :ivar links: handle → its packed SPPF families.
    :ivar groups: ``(rule_id, end)`` → the completed items of that rule
        ending there that the COMPLETER ACTUALLY PROCESSED, in event order,
        from the first promotion at that ``(rule, end)`` on. Created only then,
        so a chart that never promotes never builds one — and an empty
        ``groups`` is how a reader knows no key promoted at all.

        It exists because ``cols[end]`` is NOT a record of what the completer
        processed: ``_complete`` returns early when ``_try_leo`` takes a
        completion, leaving that completion in the column with no family
        filed. A reader that walked the column re-derived those families and
        served derivations the parse never built.
    :ivar leo_links: deferred Leo provenance — top handle → the bottom
        family of every chain that jumped to it (converging ambiguous
        chains each file theirs), rebuilt into :attr:`links` on demand.

    One store, classified by MULTIPLICITY, and the classification is a value
    IN :attr:`links` rather than a lane beside it: a bucket led by
    :data:`PROMOTED` means "more than one ordinary family: the first follows
    the marker, the rest are read from the group". A key with a single family
    keeps it exactly as it always did — same dict, same one-element list, same
    tuple — because at fanout one there is nothing to save and anything spent
    reconstructing it per read is pure loss. One lookup answers both what is
    stored and how to read it.
    """

    # pylint: disable=too-many-instance-attributes
    # An eighth lane: `groups` holds the completions the COMPLETER ACTUALLY
    # FILED, which `cols` is not a record of — `_complete` returns before
    # filing when `_try_leo` takes a completion. The alternative that would
    # satisfy the cap is folding `leo` and `leo_links` into one record, and
    # they are read SEPARATELY by the forest, the chart, `resume` and the
    # readout across three dozen sites — coupling two unrelated per-parse
    # indexes to please a counter would make four call sites worse to make
    # one number smaller.
    __slots__ = (
        "seen",
        "waiting",
        "scannable",
        "predicted",
        "leo",
        "links",
        "leo_links",
        "groups",
    )

    seen: list[set[int]]
    waiting: list[dict[int, list[int]]]
    scannable: list[dict[int, list[int]]]
    predicted: list[set[int]]
    leo: list[dict[int, int]]
    links: dict[int, list[KLink]]
    leo_links: dict[int, list[KLink]]
    groups: dict[tuple[int, int], list[int]]

    def __init__(self, columns: int) -> None:
        """Seed empty per-parse state for ``columns`` columns."""
        self.seen = [set() for _ in range(columns)]
        self.waiting = [{} for _ in range(columns)]
        self.scannable = [{} for _ in range(columns)]
        self.predicted = [set() for _ in range(columns)]
        self.leo = [{} for _ in range(columns)]
        self.links = {}
        self.leo_links = {}
        self.groups = {}

    def file_item(self, i: int, item: int, s: int) -> None:
        """File a just-inserted item under the symbol its dot faces.

        The out-of-line filing used by the rare insert sites (nullable
        advance, Leo top); the hot loops inline this logic.

        :param i: The column the item was inserted into.
        :param item: The packed item.
        :param s: Its non-zero ``next_sym`` discriminator.
        """
        if s > 0:
            index, k = self.waiting[i], s - 1
        else:
            index, k = self.scannable[i], -s - 1
        bucket = index.get(k)
        if bucket is None:
            index[k] = [item]
        else:
            bucket.append(item)
