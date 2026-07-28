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
    :ivar leo_links: deferred Leo provenance — top handle → the bottom
        family of every chain that jumped to it (converging ambiguous
        chains each file theirs), rebuilt into :attr:`links` on demand.
    """

    __slots__ = (
        "seen",
        "waiting",
        "scannable",
        "predicted",
        "leo",
        "links",
        "leo_links",
    )

    seen: list[set[int]]
    waiting: list[dict[int, list[int]]]
    scannable: list[dict[int, list[int]]]
    predicted: list[set[int]]
    leo: list[dict[int, int]]
    links: dict[int, list[KLink]]
    leo_links: dict[int, list[KLink]]

    def __init__(self, columns: int) -> None:
        """Seed empty per-parse state for ``columns`` columns."""
        self.seen = [set() for _ in range(columns)]
        self.waiting = [{} for _ in range(columns)]
        self.scannable = [{} for _ in range(columns)]
        self.predicted = [set() for _ in range(columns)]
        self.leo = [{} for _ in range(columns)]
        self.links = {}
        self.leo_links = {}

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
