"""Tests for lexic.parsing.earley.kernel.forest.families — one store, by multiplicity.

What has to hold: a key that never promotes costs what it always cost and is
served the SAME OBJECT the recorder built; a promoted key stores one family
and serves them all, in the order they were recorded; and the producer kinds
that are not ordinary completions stay stored whatever their multiplicity.

The oracle is the producer itself — `_complete` filed
``(w, origin, (it << bits) | i)`` for every ``w`` in ``waiting[origin][rule]``
— so these rebuild the expectation from the chart rather than from a
remembered list of triples.
"""

from __future__ import annotations

import pytest

from lexic.compile import compile_text
from lexic.parsing.earley.kernel.forest.families import FamilyTable
from lexic.parsing.earley.kernel.loop.kernel import Kernel
from lexic.parsing.earley.kernel.loop.leo import expand_leo
from lexic.parsing.earley.kernel.tables.atoms import tier_for
from lexic.parsing.earley.kernel.tables.builder import compile_tables
from lexic.parsing.earley.normalize import normalize

AMBIGUOUS = (
    "root ::= para+\npara ::= line+ blank\n"
    'line ::= [a-z ]* nl\nblank ::= nl\nnl ::= "\\n"\n'
)
"""The split-ambiguous shape: `line`'s CONTENT is nullable, so a bare newline
is both a possible line and a possible paragraph terminator."""

PLAIN = 'root ::= item+\nitem ::= [a-z] nl\nnl ::= "\\n"\n'
"""One derivation per document — no key ever promotes."""

RIGHT_REC = 'root ::= a\na ::= "x" a | b\nb ::= "x" | "x" b\n'
"""Right recursion, so Leo engages, with a second route to the same rule."""


def parsed(source: str, text: str) -> Kernel:
    """A finished kernel over ``source``, links recorded."""
    grammar = normalize(compile_text(source).codegen_grammar)
    return Kernel(compile_tables(grammar, tier_for(len(text))), text, True).run()


def producer_families(kern: Kernel) -> dict[int, list]:
    """What `_complete` WOULD have filed, rebuilt from the finished chart."""
    pk, codes = kern.tables.packing, kern.tables.codes
    out: dict[int, list] = {}
    for end, col in enumerate(kern.cols):
        for it in col:
            if codes.next_sym[it >> pk.bits] != 0 or (it & pk.mask) == end:
                continue
            rid = codes.arm_rule[codes.code_arm[it >> pk.bits]]
            for w in kern.st.waiting[it & pk.mask].get(rid, ()):
                bucket = out.setdefault(((w + pk.advance) << pk.bits) | end, [])
                entry = (w, it & pk.mask, (it << pk.bits) | end)
                if entry not in bucket:
                    bucket.append(entry)
    return out


def test_a_key_that_never_promotes_is_served_the_stored_object_itself():
    """The by-construction claim: fanout one costs what it always cost.

    Not "an equal list" — the SAME OBJECT the recorder built. Anything else
    means a tuple and a list are rebuilt per read on exactly the charts that
    had nothing to save in the first place.
    """
    kern = parsed(PLAIN, "a\nb\nc\n")
    table = FamilyTable(kern)
    assert not kern.st.promoted, "this document promotes — pick a flatter one"
    assert kern.st.links, "nothing was stored — the test proves nothing"
    for key, stored in kern.st.links.items():
        assert table.get(key) is stored, key
        assert table[key] is stored, key


def test_a_promoted_key_stores_one_family_and_serves_them_all():
    """Promotion stops storing; the rest come back from the chart."""
    kern = parsed(AMBIGUOUS, "a\n\nb\n\nc\n\n")
    assert kern.st.promoted, "nothing promoted — the test proves nothing"
    table = FamilyTable(kern)
    oracle = producer_families(kern)
    for key in kern.st.promoted:
        assert len(kern.st.links[key]) == 1, (
            f"{key} promoted but still stores {len(kern.st.links[key])} families"
        )
        served = table[key]
        assert len(served) > 1, key
        assert served == oracle[key], key


def test_the_cross_product_is_not_stored():
    """The point of the change, counted rather than asserted about."""
    kern = parsed(AMBIGUOUS, "a\n\nb\n\nc\n\nd\n\n")
    oracle = producer_families(kern)
    promoted = kern.st.promoted
    assert promoted, "nothing promoted — the test proves nothing"
    # Scoped to the keys the change touches: `links` also holds scan, nullable
    # and Leo families, and comparing the whole store against the ordinary
    # relation counts those on one side only.
    families = sum(len(oracle[key]) for key in promoted)
    stored = sum(len(kern.st.links[key]) for key in promoted)
    assert stored == len(promoted), "a promoted key stores more than its first"
    assert families > stored, f"stored {stored} of {families} — nothing was saved"


def test_families_come_back_in_completion_order():
    """A promoted key's order is the order `_close` completed the items in."""
    kern = parsed(AMBIGUOUS, "a\n\nb\n\nc\n\n")
    table = FamilyTable(kern)
    pk = kern.tables.packing
    checked = 0
    for key in kern.st.promoted:
        served = table[key]
        if len(served) < 2:
            continue
        order = {it: n for n, it in enumerate(kern.cols[key & pk.mask])}
        children = [one[2] for one in served]
        assert all(isinstance(one, int) for one in children), key
        positions = [order[one >> pk.bits] for one in children if isinstance(one, int)]
        assert positions == sorted(positions), (key, positions)
        checked += 1
    assert checked, "no multi-family key was compared — the test proves nothing"


def test_a_terminal_facing_key_is_served_from_the_store_unchanged():
    """Scan provenance is never read back: its child is consumed TEXT."""
    kern = parsed(PLAIN, "a\nb\n")
    table = FamilyTable(kern)
    scan_keys = [
        key
        for key, bucket in kern.st.links.items()
        if any(isinstance(one[2], str) for one in bucket)
    ]
    assert scan_keys, "this document scans nothing — the test proves nothing"
    for key in scan_keys:
        assert key not in kern.st.promoted, key
        assert table.get(key) is kern.st.links[key], key


def test_first_and_at_least_two_do_not_enumerate():
    """The hot reads answer from the store and the promotion set alone."""
    kern = parsed(AMBIGUOUS, "a\n\nb\n\nc\n\n")
    table = FamilyTable(kern)
    assert kern.st.promoted, "nothing promoted — the test proves nothing"
    for key, stored in kern.st.links.items():
        assert table.first(key) is stored[0], key
        assert table.at_least_two(key) == (len(table[key]) > 1), key


def test_a_missing_key_raises_and_get_returns_none():
    """The read surface behaves like the mapping it replaces."""
    kern = parsed(PLAIN, "a\n")
    table = FamilyTable(kern)
    absent = 1 << 60
    assert table.get(absent) is None
    assert absent not in table
    with pytest.raises(KeyError):
        _ = table[absent]


def test_iterating_the_table_yields_keys_not_an_index_walk():
    """``for k in table`` must iterate KEYS, as the mapping it replaces did.

    Without an explicit ``__iter__`` this does not merely fail — with
    ``__getitem__`` defined and keys being plain ints, Python falls back to
    the legacy index protocol and yields ``table[0]``, ``table[1]`` … before
    raising ``KeyError``. A silently wrong walk, not a clean error.
    """
    kern = parsed(AMBIGUOUS, "a\n\nb\n\n")
    table = FamilyTable(kern)
    walked = list(table)
    assert walked == list(kern.st.links)
    assert len(table) == len(kern.st.links)
    assert all(isinstance(one, int) for one in walked)


def test_items_serves_every_key_and_matches_the_point_reads():
    """The decode path sees the same families a point read would."""
    kern = parsed(AMBIGUOUS, "a\n\nb\n\nc\n\n")
    table = FamilyTable(kern)
    seen = 0
    for key, bucket in table.items():
        assert bucket == table[key], key
        seen += 1
    assert seen == len(kern.st.links)


def test_a_delegated_completion_never_promotes_a_key():
    """`_inject` puts the delegated completion in `cols[end]` too.

    Its family is filed by `_complete_delegated` with the `PayloadLeaf` as the
    child — NOT a child handle. Only `_complete` writes the promotion set, so
    a delegated completion cannot promote a key and cannot be read back as an
    ordinary child-handle family.

    Driven at the seam because NOTHING in the roster populates `delegates`:
    instrumenting every kernel the bench corpora build gives seven kernels and
    zero with a delegate table, so a test waiting for a natural witness would
    be testing nothing.
    """
    from lexic.parsing.earley.kernel.forest.forest import PayloadLeaf

    kern = parsed(PLAIN, "a\nb\n")
    pk, codes = kern.tables.packing, kern.tables.codes
    found = None
    for end, col in enumerate(kern.cols):
        for it in col:
            if codes.next_sym[it >> pk.bits] == 0 and (it & pk.mask) != end:
                found = (it, end)
                break
        if found:
            break
    assert found, "no positive-width completion to delegate — nothing tested"
    it, end = found
    before = set(kern.st.promoted)
    leaf = PayloadLeaf(object(), kern.text[it & pk.mask : end])
    kern._complete_delegated(end, it, leaf)  # pylint: disable=protected-access

    assert set(kern.st.promoted) == before, (
        "a delegated completion promoted a key — its families would then be "
        "read back from the column with a child handle the producer never filed"
    )


def test_a_mixed_provenance_leo_key_serves_stored_first():
    """The L4 shape: a Leo top reached BOTH by the completer and by deferral.

    `leo.py` names it and calls its miss the embedded-ambiguity undercount.
    Expansion appends to the store after recognition closes, so the stored
    families lead and anything read back from the chart follows.
    """
    kern = parsed(AMBIGUOUS, "a\n\nb\n\nc\n\nd\n\n")
    assert kern.st.leo_links, "Leo never engaged — the test proves nothing"
    for key in list(kern.st.leo_links):
        expand_leo(kern.st, kern.tables, key)
    table = FamilyTable(kern)
    mixed = [key for key in kern.st.promoted if len(kern.st.links.get(key, ())) > 1]
    if not mixed:
        pytest.skip("no promoted key also gained a Leo family on this witness")
    for key in mixed:
        assert table[key][: len(kern.st.links[key])] == kern.st.links[key], key


def test_leo_expansion_is_still_served_in_full():
    """Every family expansion files is served, promoted key or not."""
    kern = parsed(RIGHT_REC, "xxxxx")
    assert kern.st.leo_links, "Leo never engaged — the test proves nothing"
    for key in list(kern.st.leo_links):
        expand_leo(kern.st, kern.tables, key)
    table = FamilyTable(kern)
    for key, stored in kern.st.links.items():
        assert set(stored) <= set(table[key]), key
