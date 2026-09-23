"""One family store, classified by MULTIPLICITY — and the reader for it.

A key with a single family keeps it in :attr:`KernelState.links` exactly as it
always did — same dict, same one-element list, same tuple. The SECOND distinct
family at a key PROMOTES it: its bucket becomes ``[PROMOTED, first]``, and every
family after the first is read back from the completion group of its
``(rule, end)`` — the completed items the completer processed there from the
first promotion on.

A chart on which no key promoted has an empty ``groups``, and its reader is the
dict itself — :meth:`Kernel.family_reader` hands that over directly, so a flat
chart reads its families the way it always did, with no wrapper and no marker
check. :class:`FamilyTable` exists only for charts that factored.

**What is never read back.** Scan families live at keys facing a terminal and
never reach the completer. Keys facing a nullable or a delegated rule are never
promoted, because their families interleave with those of `_nullable_advance`
and `_complete_delegated`. Leo families are appended by expansion after
recognition, behind the first family, and read after the ordinary ones — which
is where the old recorder had them too.
"""

from __future__ import annotations

from collections.abc import Iterator

from lexic.parsing.earley.kernel.loop.state import PROMOTED, KLink


class FamilyTable:
    """A factored chart's families: stored at fanout one, read back when promoted.

    :ivar explicit: The store — :attr:`KernelState.links`.
    :ivar kern: The finished kernel a promoted key's families are read from.
    """

    __slots__ = ("explicit", "kern")

    __iter__ = None
    """Not iterable. With ``__getitem__`` defined and int keys, a ``for`` would
    otherwise fall back to the legacy index protocol and walk ``table[0]``,
    ``table[1]``… — a wrong walk rather than an error."""

    def __init__(self, kern) -> None:
        """:param kern: the kernel whose ``cols`` and ``waiting`` hold the rest."""
        self.kern = kern
        self.explicit = kern.st.links

    def get(self, key: int, /) -> list[KLink] | None:
        """This key's families, or ``None`` when it names none.

        A key that never promoted returns the stored list ITSELF.
        """
        stored = self.explicit.get(key)
        if stored is None or stored[0] is not PROMOTED:
            return stored
        return self._promoted(key, stored)

    def __getitem__(self, key: int, /) -> list[KLink]:
        """This key's families; raises :class:`KeyError` when it names none."""
        out = self.get(key)
        if out is None:
            raise KeyError(key)
        return out

    def items(self) -> Iterator[tuple[int, list[KLink]]]:
        """Every key with its families, one key at a time."""
        for key, stored in self.explicit.items():
            if stored[0] is PROMOTED:
                yield key, self._promoted(key, stored)
            else:
                yield key, stored

    def _promoted(self, key: int, stored: list[KLink]) -> list[KLink]:
        """A promoted key's families: its first, its group's, then Leo's.

        ``stored`` is ``[PROMOTED, first, *leo]``. The first family leads
        because any completion the group holds that was processed before it
        would have filed at this key first. It may also be in the group — when
        it was filed after the group existed — so the group's copy is skipped.
        What follows it was appended by Leo expansion, after recognition, and
        so after every ordinary family.
        """
        first = stored[1]
        out = [first]
        out.extend(one for one in self._from_group(key) if one != first)
        if len(stored) > 2:
            seen = set(out)
            out.extend(one for one in stored[2:] if one not in seen)
        return out

    def _from_group(self, key: int) -> Iterator[KLink]:
        """The ordinary families at a promoted ``key`` its group records, in order.

        The group holds completions in the order the completer processed them.
        A completion yields a family for this key iff the key's waiter was
        waiting on the rule at the completion's origin; that bucket is keyed by
        ORIGIN and final once that column closed, which strictly precedes any
        completion ending later, so reading it now reads what the completer saw.
        """
        kern = self.kern
        pk = kern.tables.packing
        bits, mask = pk.bits, pk.mask
        end = key & mask
        waiter = (key >> bits) - pk.advance
        rid = kern.tables.codes.next_sym[waiter >> bits] - 1
        waiting = kern.st.waiting
        for it in kern.st.groups[(rid, end)]:
            origin = it & mask
            if waiter in waiting[origin].get(rid, ()):
                yield waiter, origin, (it << bits) | end
