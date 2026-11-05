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

**Keys facing a nullable rule promote lazily.** `_nullable_advance` files
their empty families at the waiter's own visit, so they interleave with the
completions'. Such a key promotes only once it holds
:data:`~lexic.parsing.earley.kernel.loop.kernel.LAZY_PROMOTION` families: it
keeps those, reads the rest from its group from its head's cursor on, and
files any later empty families explicitly, at the group's length then.
Families are read back in the order the old recorder kept them.

**What is never read back.** Scan families live at keys facing a terminal and
never reach the completer. Keys facing a delegated rule are never promoted,
because `_complete_delegated` files payload families no group can hold. Leo
families are appended by expansion after recognition, behind the stored ones,
and read after the ordinary ones — which is where the old recorder had them
too.
"""

from __future__ import annotations

from collections.abc import Iterator
from itertools import islice

from lexic.parsing.earley.kernel.loop.state import PROMOTED, KLink, lazy_parts


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
        so after every ordinary family. A lazily promoted key is read by
        :meth:`_lazy`.
        """
        first = stored[1]
        if first[0] < 0:
            return self._lazy(key, stored)
        out = [first]
        out.extend(one for one in self._from_group(key) if one != first)
        return _with_leo(out, stored, 2)

    def _lazy(self, key: int, stored: list[KLink]) -> list[KLink]:
        """A lazily promoted key's families, in the order they were filed.

        ``stored`` is ``[PROMOTED, head, *held, *late, *leo]``
        (:func:`~lexic.parsing.earley.kernel.loop.state.lazy_head`). The held
        families came first. The group's entries from the head's cursor on
        follow, with the late empty families at the group's length when they
        were filed: entries before it were processed before them.
        """
        cursor, held, place = lazy_parts(stored[1])
        held += 2
        out = stored[2:held]
        if place < 0:
            out.extend(self._from_group(key, cursor))
            return _with_leo(out, stored, held)
        late = held + len(self._completes(key))
        out.extend(self._from_group(key, cursor, place))
        out.extend(stored[held:late])
        out.extend(self._from_group(key, place))
        return _with_leo(out, stored, late)

    def _completes(self, key: int) -> tuple[int, ...]:
        """The empty-deriving arms of the rule ``key``'s waiter faces."""
        pk = self.kern.tables.packing
        codes = self.kern.tables.codes
        waiter = (key >> pk.bits) - pk.advance
        return codes.nullable_completes[codes.next_sym[waiter >> pk.bits] - 1]

    def _from_group(
        self, key: int, start: int = 0, stop: int | None = None
    ) -> Iterator[KLink]:
        """The ordinary families at a promoted ``key`` its group records, in order.

        The group holds completions in the order the completer processed them;
        ``start`` and ``stop`` bound the slice of it read.
        A completion yields a family for this key iff the key's waiter was
        waiting on the rule at the completion's origin; that column closed
        before any completion ending later, so reading it now reads what the
        completer saw. The waiter faces the rule by construction, so it waited
        there iff it stands in that column: an advanced item iff the column's
        ``seen`` holds it, a dot-0 item iff the column is its own origin, where
        alone it is ever seeded. Both are one test, where the column's waiting
        list is one scan per completion.
        """
        kern = self.kern
        bits, mask = kern.tables.packing.bits, kern.tables.packing.mask
        codes = kern.tables.codes
        end = key & mask
        waiter = (key >> bits) - kern.tables.packing.advance
        rid = codes.next_sym[waiter >> bits] - 1
        group = islice(kern.st.groups[(rid, end)], start, stop)
        if codes.arm_base[codes.code_arm[waiter >> bits]] == waiter >> bits:
            home = waiter & mask  # a dot-0 waiter stands in its origin alone
            for it in group:
                if it & mask == home:
                    yield waiter, home, (it << bits) | end
            return
        seen = kern.st.seen
        for it in group:
            if waiter in seen[it & mask]:
                yield waiter, it & mask, (it << bits) | end


def _with_leo(out: list[KLink], stored: list[KLink], tail: int) -> list[KLink]:
    """``out`` and the Leo families stored from ``tail`` on that it lacks."""
    if len(stored) > tail:
        seen = set(out)
        out.extend(one for one in stored[tail:] if one not in seen)
    return out
