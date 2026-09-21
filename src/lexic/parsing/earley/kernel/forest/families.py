"""One family store, classified by MULTIPLICITY.

A key with a single family keeps it in :attr:`KernelState.links` exactly as it
always did — same dict, same one-element list, same tuple — and reads return
THAT OBJECT. At fanout one the baseline already stores one family in one hash
slot, so there is nothing to save there, and anything spent rebuilding a tuple
and a list per read is pure loss. The flat charts therefore take the old path
by construction, not by tuning.

The SECOND distinct family at a key PROMOTES it. From then on nothing more is
stored for that key, and its families are read back from the chart: for a
promoted key the waiter is the key's own, and the completions of the rule it
faces that end there sit in ``cols[end]``, in the order ``_close`` completed
them — which is the order the families were recorded in. That is the
population that grows faster than the document on a split-ambiguous chart, and
it is the only one this stops storing.

**What is never read back.** Scan, nullable, delegated and Leo families are
filed by other producers and stay stored whatever their multiplicity:

* a scan family's child is consumed TEXT, and which origins scanned to an end
  is indexed by ``scannable``, not by rule completion;
* a zero-width family is filed by ``_nullable_advance`` at the waiter's own
  visit — ``_close`` skips ``_complete`` entirely when ``it & mask == i``;
* a delegated family's child is a built model payload, and only ``_complete``
  writes the promotion set, so a delegated completion cannot enter it;
* a Leo chain's INTERMEDIATE completions are never filed in ``cols`` —
  ``_try_leo`` appends only the chain top — so no walk of a column reaches
  them.
"""

from __future__ import annotations

from collections.abc import Iterator

from lexic.parsing.earley.kernel.loop.state import PROMOTED, KLink


class FamilyTable:
    """One parse's families: stored at fanout one, read back when promoted.

    :ivar explicit: The store — :attr:`KernelState.links`, unchanged in shape.
    :ivar kern: The finished kernel a promoted key's families are read from.
    """

    __slots__ = ("explicit", "kern")

    def __init__(self, kern) -> None:
        """:param kern: the kernel whose ``cols`` and ``waiting`` hold the rest."""
        self.kern = kern
        self.explicit = kern.st.links

    def get(self, key: int, /) -> list[KLink] | None:
        """This key's families, or ``None`` when it names none.

        The common case is one dict lookup and one set membership: a key that
        never promoted returns the stored list ITSELF, the same object the
        recorder built, with nothing reconstructed.
        """
        stored = self.explicit.get(key)
        if stored is None or stored[0] is not PROMOTED:
            return stored
        return self._promoted(key, stored)

    def _promoted(self, key: int, stored: list) -> list[KLink]:
        """A promoted key's families: the column's, then anything else filed.

        ``stored[0]`` is the marker; whatever follows it was filed by another
        producer at the same key and is not recoverable from the column.
        """
        out = list(self._from_chart(key))
        seen = set(out)
        out.extend(one for one in stored[1:] if one not in seen)
        return out

    def _from_chart(self, key: int) -> Iterator[KLink]:
        """A promoted key's families, from what the COMPLETER processed.

        Read from the ``(rule, end)`` group, never from ``cols[end]``. The
        column also holds completions ``_try_leo`` swallowed — ``_complete``
        returns before filing for those — so a column walk would serve
        families the parse never built.

        Eligibility is the waiter's presence in ``waiting[origin][rule]``,
        which is sound here because a waiter bucket is keyed by ORIGIN and is
        final once that column closes, which strictly precedes any completion
        ending later. This path only ever sees positive-width completions.
        """
        kern = self.kern
        pk = kern.tables.packing
        bits, mask = pk.bits, pk.mask
        end = key & mask
        waiter = (key >> bits) - pk.advance
        rid = kern.tables.codes.next_sym[waiter >> bits] - 1
        if rid < 0:
            return
        waiting = kern.st.waiting
        for it in kern.st.groups.get((rid, end), ()):
            origin = it & mask
            if waiter in waiting[origin].get(rid, ()):
                yield waiter, origin, (it << bits) | end

    def first(self, key: int) -> KLink | None:
        """This key's FIRST family — one dict lookup on the direct path."""
        stored = self.explicit.get(key)
        if not stored:
            return None
        if stored[0] is not PROMOTED:
            return stored[0]
        return next(iter(self._from_chart(key)), None)

    def at_least_two(self, key: int) -> bool:
        """Whether this key names more than one family — one lookup."""
        stored = self.explicit.get(key)
        if not stored:
            return False
        return stored[0] is PROMOTED or len(stored) > 1

    def __getitem__(self, key: int) -> list[KLink]:
        """This key's families; raises like the mapping it replaces."""
        out = self.get(key)
        if out is None:
            raise KeyError(key)
        return out

    def __contains__(self, key: int) -> bool:
        """Whether this key names any family at all."""
        return key in self.explicit

    def keys(self) -> Iterator[int]:
        """Every key naming a family — the store holds one entry for each."""
        return iter(self.explicit)

    __iter__ = keys
    """Iterating yields KEYS, as the mapping this replaces did.

    Defined explicitly because it would otherwise be WRONG rather than
    missing: with ``__getitem__`` present and keys being plain ints, ``for k
    in table`` falls back to the legacy index protocol and yields
    ``table[0]``, ``table[1]`` … before raising ``KeyError``.
    """

    def __len__(self) -> int:
        """How many keys name a family."""
        return len(self.explicit)

    def items(self) -> Iterator[tuple[int, list[KLink]]]:
        """Every key with its families, ONE key at a time.

        Streams: the decode path consumes a key's families and moves on, so
        nothing here holds the whole population at once. A shape that grouped
        every family into one dict before returning would put the cross
        product back in memory on exactly the path this exists to relieve.
        """
        for key, stored in self.explicit.items():
            if stored and stored[0] is PROMOTED:
                yield key, self._promoted(key, stored)
            else:
                yield key, stored
