"""The family oracle — the recorder as it stood before factoring.

Shared by the family-store unit tests and the forced-seat parity test, so the
expectation is kept true in one place.

**It is independent of the store it checks.** Swapped in for
``Kernel._index_completion`` during recognition, it files one family per waiter
per completion straight into ``links``, exactly as the pre-factoring kernel
did: no groups, no promotion, no column walk. Recognition itself is untouched —
the recorder only writes ``links`` — so a baseline kernel and a factored one
built from the same text have the same chart, and the baseline's buckets are
the complete, ordered answer the factored reader must reproduce.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from lexic.parsing.earley.kernel.forest.forest import PayloadLeaf
from lexic.parsing.earley.kernel.loop.kernel import Kernel
from lexic.parsing.earley.kernel.loop.leo import expand_leo
from lexic.parsing.earley.kernel.loop.state import PROMOTED


def baseline_index_completion(
    self, i: int, it: int, wl: list[int], origin: int
) -> None:
    """One family per waiter per completion — the pre-factoring recorder."""
    pk = self.tables.packing
    for w in wl:
        family = (w, origin, (it << pk.bits) | i)
        bucket = self.st.links.setdefault(((w + pk.advance) << pk.bits) | i, [])
        if family not in bucket:
            bucket.append(family)


@contextmanager
def baseline_recorder() -> Iterator[None]:
    """Every kernel built inside records families the pre-factoring way."""
    factored = vars(Kernel)["_index_completion"]
    setattr(Kernel, "_index_completion", baseline_index_completion)
    try:
        yield
    finally:
        setattr(Kernel, "_index_completion", factored)


def expanded(kern: Kernel) -> Kernel:
    """Expand every deferred Leo chain, so both sides compare complete buckets."""
    for key in list(kern.st.leo_links):
        expand_leo(kern.st, kern.tables, key)
    return kern


def paired(tables, text: str, delegates: dict | None = None) -> tuple[Kernel, Kernel]:
    """The same parse recorded both ways: ``(baseline, factored)``, Leo expanded."""
    with baseline_recorder():
        base = Kernel(tables, text, True, delegates).run()
    return expanded(base), expanded(Kernel(tables, text, True, delegates).run())


def comparable(bucket: list | None) -> list | None:
    """A bucket with each delegated child reduced to its value.

    Two parses of one text build DISTINCT :class:`PayloadLeaf` objects, and a
    leaf compares by identity — so the delegated child is compared by the
    payload and span it carries, which is what makes two of them the same
    family.
    """
    if bucket is None:
        return None
    return [
        (w, o, (c.payload, c.text) if isinstance(c, PayloadLeaf) else c)
        for w, o, c in bucket
    ]


def bucket_differences(base: Kernel, kern: Kernel) -> list[tuple[int, object, object]]:
    """Every key whose served families differ from the baseline's, in ORDER.

    Complete ordered buckets, not prefixes and not sets: the first family is
    what the fast path and the ambiguity walk take, so order is observable.
    """
    want = {key: comparable(bucket) for key, bucket in base.st.links.items()}
    served = {key: comparable(bucket) for key, bucket in kern.family_reader().items()}
    out: list[tuple[int, object, object]] = [
        (key, bucket, served.get(key))
        for key, bucket in want.items()
        if served.get(key) != bucket
    ]
    out.extend((key, None, bucket) for key, bucket in served.items() if key not in want)
    return out


def before_group(kern: Kernel) -> list[int]:
    """Promoted keys whose first family predates their group, which holds no copy.

    The late-promotion witness: such a key's first family is served only
    because the bucket kept it.
    """
    pk, codes = kern.tables.packing, kern.tables.codes
    out = []
    for key, bucket in kern.st.links.items():
        if bucket[0] is not PROMOTED:
            continue
        child = bucket[1][2]
        assert isinstance(child, int), key
        rid = codes.next_sym[((key >> pk.bits) - pk.advance) >> pk.bits] - 1
        if child >> pk.bits not in kern.st.groups[(rid, key & pk.mask)]:
            out.append(key)
    return out
