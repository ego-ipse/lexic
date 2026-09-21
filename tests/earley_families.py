"""What the Earley completer actually filed — the shared family oracle.

Lives here rather than in either test that uses it, because both the unit
tests for the family store and the forced-seat integration test need the same
expectation and a copy in each is a second thing to keep true.

**It is independent of the reader's own record, which is the point.** It walks
the COLUMN and subtracts the completions ``_try_leo`` swallowed — recoverable
from ``leo_links``, since each deferred entry's child IS the handle of the
completion whose family was never filed. ``cols`` alone is NOT a record of
what the completer processed: ``_complete`` returns before filing when Leo
takes a completion, and a reader that walked the column served derivations the
parse never built.
"""

from __future__ import annotations


def filed_families(kern) -> dict[int, list]:
    """Every family ``_complete`` filed, per key, in completion order.

    :param kern: a finished :class:`~lexic.parsing.earley.kernel.loop.kernel.Kernel`.
    :returns: packed key → its families as ``(waiter, origin, child)`` triples.
    """
    pk, codes = kern.tables.packing, kern.tables.codes
    swallowed = {one[2] for chain in kern.st.leo_links.values() for one in chain}
    out: dict[int, list] = {}
    for end, col in enumerate(kern.cols):
        for it in col:
            if codes.next_sym[it >> pk.bits] != 0 or (it & pk.mask) == end:
                continue
            if (it << pk.bits) | end in swallowed:
                continue
            rid = codes.arm_rule[codes.code_arm[it >> pk.bits]]
            for waiter in kern.st.waiting[it & pk.mask].get(rid, ()):
                bucket = out.setdefault(((waiter + pk.advance) << pk.bits) | end, [])
                entry = (waiter, it & pk.mask, (it << pk.bits) | end)
                if entry not in bucket:
                    bucket.append(entry)
    return out
