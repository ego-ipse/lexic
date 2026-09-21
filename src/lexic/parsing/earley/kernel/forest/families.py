"""The completion-family relation — ordinary families DERIVED, the rest stored.

An ordinary completion family carries no information the chart does not
already hold. ``_complete`` files one per waiter per completion:

    origin = it & mask
    wl     = waiting[origin][ arm_rule[code_arm[it >> bits]] ]
    for w in wl:  links[((w + advance) << bits) | i] += (w, origin, (it << bits) | i)

so the family is fixed by ``(origin, completed code)``: ``w`` is the key's own
waiter and ``child`` packs the code with the origin and the end column. The
stored table was therefore the CROSS PRODUCT of two facts the recogniser
retains anyway — where a waiter waits, and which completions end where — and
on a split-ambiguous chart that product is what grows.

**What is derived, and what is not.** Only ORDINARY, positive-width completion
families are derived. Scan, nullable, delegated and Leo provenance stay stored
in :attr:`KernelState.links`, because each is filed by a different producer
that this relation does not describe:

* a scan family's child is consumed TEXT, and which origins scanned to an end
  is indexed by ``scannable``, not by rule completion;
* a zero-width family is filed by ``_nullable_advance`` at the waiter's own
  visit — ``_close`` skips ``_complete`` entirely when ``it & mask == i``;
* a delegated family's child is a built model payload;
* a Leo chain's INTERMEDIATE completions are never filed in ``cols`` —
  ``_try_leo`` appends only the chain top — so no index over ``cols`` can
  reach them.

**Order.** Derivation walks ``cols[end]`` in insertion order, which is the
order ``_close`` completed those items in, which is the order their families
were appended. Stored families follow, because every producer that survives
here either owns its key alone or (Leo) runs after recognition closes.
"""

from __future__ import annotations

from collections.abc import Iterator

from lexic.parsing.earley.kernel.loop.state import KLink


class FamilyTable:
    """One parse's families: derived where possible, stored where not.

    Reads like the mapping it replaces — ``get``, ``[]``, ``in``, ``items`` —
    but holds only the families it cannot derive.

    :ivar explicit: The stored families (scan / nullable / delegated / Leo).
    :ivar kern: The finished kernel the ordinary families are derived from.
    """

    __slots__ = ("explicit", "kern")

    def __init__(self, kern) -> None:
        """:param kern: the kernel whose ``cols`` and ``waiting`` are the factors."""
        self.kern = kern
        self.explicit = kern.st.links

    def _completions(self, end: int) -> Iterator[tuple[int, int, int]]:
        """Every positive-width completion ending at ``end``, in `cols` order.

        Yields ``(rule_id, origin, item)``. Zero-width completions are skipped:
        ``_close`` never routes them through ``_complete``, so no ordinary
        family was ever filed for one.
        """
        codes = self.kern.tables.codes
        bits, mask = self.kern.tables.packing.bits, self.kern.tables.packing.mask
        for it in self.kern.cols[end]:
            code = it >> bits
            if codes.next_sym[code] == 0 and (it & mask) != end:
                yield codes.arm_rule[codes.code_arm[code]], it & mask, it

    def derived(self, key: int) -> list[KLink]:
        """The ordinary families at ``key``, in ``cols[end]`` order.

        Empty for a key whose waiter faces a terminal: those families are
        scanned, not completed, and are stored.
        """
        codes = self.kern.tables.codes
        bits = self.kern.tables.packing.bits
        end = key & self.kern.tables.packing.mask
        waiter = (key >> bits) - self.kern.tables.packing.advance
        code = waiter >> bits
        # A key the chart never produced decodes to nonsense. The mapping this
        # replaces answered such a key with a miss, so this does too rather
        # than letting an out-of-range index escape as an IndexError.
        if end >= len(self.kern.cols) or not 0 <= code < len(codes.next_sym):
            return []
        rid = codes.next_sym[code] - 1
        if rid < 0:
            return []
        waiting = self.kern.st.waiting
        return [
            (waiter, origin, (it << bits) | end)
            for rule, origin, it in self._completions(end)
            if rule == rid and waiter in waiting[origin].get(rid, ())
        ]

    def get(
        self, key: int, default: list[KLink] | None = None, /
    ) -> list[KLink] | None:
        """This key's families, derived then stored, or ``default`` if none."""
        out = self.derived(key)
        stored = self.explicit.get(key)
        if stored:
            if out:
                seen = set(out)
                out = out + [one for one in stored if one not in seen]
            else:
                out = list(stored)
        return out if out else default

    def __getitem__(self, key: int) -> list[KLink]:
        """This key's families; raises like the mapping it replaces."""
        out = self.get(key)
        if out is None:
            raise KeyError(key)
        return out

    def __contains__(self, key: int) -> bool:
        """Whether this key names any family at all."""
        return self.get(key) is not None

    def keys(self) -> Iterator[int]:
        """Every key naming a family — derived keys included.

        Enumerating the derived keys re-walks the completer's cross product,
        so a caller that materialises this pays the population the stored
        table used to hold. Only the decode path does.
        """
        bits = self.kern.tables.packing.bits
        advance = self.kern.tables.packing.advance
        waiting = self.kern.st.waiting
        seen: set[int] = set()
        for end in range(len(self.kern.cols)):
            for rid, origin, _it in self._completions(end):
                for waiter in waiting[origin].get(rid, ()):
                    key = ((waiter + advance) << bits) | end
                    if key not in seen:
                        seen.add(key)
                        yield key
        for key in self.explicit:
            if key not in seen:
                yield key

    __iter__ = keys
    """Iterating the table yields KEYS, as iterating the mapping it replaces did.

    Defined explicitly because it would otherwise not be missing so much as
    WRONG: with ``__getitem__`` present and keys being plain ints, ``for k in
    table`` falls back to the legacy index protocol and yields ``table[0]``,
    ``table[1]`` … before raising ``KeyError`` instead of stopping.
    """

    def __len__(self) -> int:
        """How many keys name a family — pays the full derivation walk.

        Defined rather than left to raise, but it is not cheap: unlike the
        dict this replaces, the count is not known until the cross product has
        been walked. ``bool(table)`` goes through it too, so an empty table is
        falsey as the mapping's was.
        """
        return sum(1 for _ in self.keys())

    def items(self) -> Iterator[tuple[int, list[KLink]]]:
        """Every key with its families — ONE pass, each family built once.

        Not ``keys()`` then ``get()`` per key: that walks every
        ``(end, completion, waiter)`` triple to find the keys and then walks
        each key's column AGAIN to rebuild its list, which is O(keys x column)
        where iterating the dict this replaces was O(families). A product
        where it should be a sum, and on a split-ambiguous chart the product
        is the thing that made the table worth removing.

        So: walk each column once, emit each family into its key's group as it
        is produced, then merge the stored families in behind the derived ones
        — the same derived-then-stored order :meth:`get` establishes.
        """
        pk = self.kern.tables.packing
        waiting = self.kern.st.waiting
        grouped: dict[int, list[KLink]] = {}
        for end in range(len(self.kern.cols)):
            for rid, origin, it in self._completions(end):
                child = (it << pk.bits) | end
                for waiter in waiting[origin].get(rid, ()):
                    key = ((waiter + pk.advance) << pk.bits) | end
                    grouped.setdefault(key, []).append((waiter, origin, child))
        for key, stored in self.explicit.items():
            bucket = grouped.setdefault(key, [])
            seen = set(bucket)
            bucket.extend(one for one in stored if one not in seen)
        return iter(grouped.items())
