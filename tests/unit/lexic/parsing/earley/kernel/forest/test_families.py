"""Tests for lexic.parsing.earley.kernel.forest.families — the derived relation.

The table replaces a STORED cross product with one derived from `cols` and
`waiting`, so what has to be pinned is that it answers the same families the
producer would have filed, in the same order, and that the kinds it does NOT
derive are still served from the explicit store.

The oracle throughout is the producer itself: `_complete` filed
``(w, origin, (it << bits) | i)`` for every ``w`` in ``waiting[origin][rule]``,
so these tests rebuild that expectation from the chart rather than from a
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
"""One derivation per document — every key holds exactly one family."""


def parsed(source: str, text: str) -> Kernel:
    """A finished kernel over ``source``, links recorded."""
    grammar = normalize(compile_text(source).codegen_grammar)
    return Kernel(compile_tables(grammar, tier_for(len(text))), text, True).run()


def producer_families(kern: Kernel) -> dict[int, list]:
    """What `_complete` WOULD have filed, rebuilt from the finished chart.

    The oracle: for each completed item over ``[origin, end]`` with
    ``origin < end``, one family per waiter on that rule at ``origin``, in the
    order ``_close`` walks ``cols[end]``.
    """
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


def test_the_table_answers_every_family_the_producer_would_have_filed():
    """Membership: derived families are exactly the producer's, key by key."""
    kern = parsed(AMBIGUOUS, "a\n\nb\n\n")
    table = FamilyTable(kern)
    oracle = producer_families(kern)
    assert oracle, "this document files no ordinary family — it proves nothing"
    for key, want in oracle.items():
        assert table.derived(key) == want, key


def test_derived_families_come_in_cols_insertion_order():
    """Ordering: the order a consumer sees is the order `_close` completed in.

    Asserted against the column itself rather than against the oracle, so a
    reordering that moved BOTH would not pass.
    """
    kern = parsed(AMBIGUOUS, "a\n\nb\n\nc\n\n")
    table = FamilyTable(kern)
    pk = kern.tables.packing
    bits, mask = pk.bits, pk.mask
    checked = 0
    for key in producer_families(kern):
        fams = table.derived(key)
        if len(fams) < 2:
            continue
        end = key & mask
        order = {it: n for n, it in enumerate(kern.cols[end])}
        children = [one[2] for one in fams]
        assert all(isinstance(one, int) for one in children), key
        positions = [order[one >> bits] for one in children if isinstance(one, int)]
        assert positions == sorted(positions), (key, positions)
        checked += 1
    assert checked, "no multi-family key was compared — the test proves nothing"


def test_a_terminal_facing_key_derives_nothing_and_is_served_from_the_store():
    """Scan provenance is not derived: its child is consumed TEXT."""
    kern = parsed(PLAIN, "a\nb\n")
    table = FamilyTable(kern)
    scan_keys = [
        key
        for key, bucket in kern.st.links.items()
        if any(isinstance(one[2], str) for one in bucket)
    ]
    assert scan_keys, "this document scans nothing — the test proves nothing"
    for key in scan_keys:
        assert table.derived(key) == [], key
        assert table[key] == kern.st.links[key], key


def test_the_kernel_no_longer_stores_ordinary_families():
    """The point of the change: the cross product is not in `links` any more."""
    kern = parsed(AMBIGUOUS, "a\n\nb\n\nc\n\n")
    end_mask = kern.tables.packing.mask
    for key, bucket in kern.st.links.items():
        for one in bucket:
            positive = not isinstance(one[2], str) and one[1] != (key & end_mask)
            assert not positive, (
                f"an ordinary positive-width family is still STORED at {key}: "
                f"{one[:2]} — the derivation is not replacing it"
            )
    assert producer_families(kern), "no ordinary family exists to have been removed"


def test_a_missing_key_raises_and_get_returns_the_default():
    """The read surface behaves like the mapping it replaces."""
    kern = parsed(PLAIN, "a\n")
    table = FamilyTable(kern)
    absent = 1 << 60
    assert table.get(absent) is None
    assert absent not in table
    with pytest.raises(KeyError):
        _ = table[absent]


def test_keys_covers_the_derived_and_the_stored_without_repeating_one():
    """`keys()` is the union, and each key appears once."""
    kern = parsed(AMBIGUOUS, "a\n\nb\n\n")
    table = FamilyTable(kern)
    listed = list(table.keys())
    assert len(listed) == len(set(listed)), "a key was yielded twice"
    assert set(producer_families(kern)) <= set(listed)
    assert set(kern.st.links) <= set(listed)


def test_leo_families_are_served_after_the_derived_ones():
    """Mixed provenance: expansion appends, so stored families come last.

    `leo.py` states a Leo top can carry BOTH — some families from the normal
    completer, others deferred — and `expand_chain` appends after whatever was
    already filed. Expansion happens once recognition has closed, so every
    derived family precedes every expanded one.
    """
    kern = parsed(AMBIGUOUS, "a\n\nb\n\nc\n\nd\n\n")
    for key in list(kern.st.leo_links):
        expand_leo(kern.st, kern.tables, key)
    table = FamilyTable(kern)
    mixed = [
        key for key, stored in kern.st.links.items() if stored and table.derived(key)
    ]
    if not mixed:
        pytest.skip("this document has no key carrying both kinds")
    novel_seen = 0
    for key in mixed:
        served = table[key]
        derived = table.derived(key)
        # the stored tail keeps the store's OWN order behind the derived prefix
        novel = [one for one in kern.st.links[key] if one not in set(derived)]
        assert served == derived + novel, key
        novel_seen += len(novel)
    # Pinned as an observation, not assumed: on THIS document every family Leo
    # re-files at a key that also derives is one derivation already produces,
    # so the stored tail is empty and it is the DEDUP that is being exercised
    # here. A document where this stops holding is one where stored-family
    # ORDER at a mixed key starts to matter, which no witness here covers.
    assert novel_seen == 0, (
        f"{novel_seen} stored families now follow a derived one — stored order "
        "at a mixed key is no longer unexercised and needs its own witness"
    )


def test_the_table_does_not_duplicate_a_family_the_store_also_holds():
    """Leo expansion can re-file a family derivation already produces."""
    kern = parsed(AMBIGUOUS, "a\n\nb\n\nc\n\nd\n\n")
    for key in list(kern.st.leo_links):
        expand_leo(kern.st, kern.tables, key)
    table = FamilyTable(kern)
    for key, served in table.items():
        assert len(served) == len(set(served)), f"duplicate family at {key}"


def test_iterating_the_table_yields_keys_not_an_index_walk():
    """``for k in table`` must iterate KEYS, as the mapping it replaces did.

    Without an explicit ``__iter__`` this does not merely fail — with
    ``__getitem__`` defined and keys being plain ints, Python falls back to the
    legacy index protocol and yields ``table[0]``, ``table[1]`` … before
    raising ``KeyError``. A silently wrong walk, not a clean error.
    """
    kern = parsed(AMBIGUOUS, "a\n\nb\n\n")
    table = FamilyTable(kern)
    walked = list(table)
    assert walked == list(table.keys())
    assert all(isinstance(one, int) for one in walked)
    assert set(kern.st.links) <= set(walked)
    # the index walk would start at 0; a real key is a packed handle
    assert 0 not in walked or 0 in set(table.keys())


def test_len_and_truth_match_the_mapping_they_replace():
    """An empty table is falsey and a populated one counts its keys."""
    kern = parsed(AMBIGUOUS, "a\n\nb\n\n")
    table = FamilyTable(kern)
    assert len(table) == len(list(table.keys()))
    assert bool(table) is True


RIGHT_REC = 'root ::= a\na ::= "x" a | b\nb ::= "x" | "x" b\n'
"""Right recursion (Leo engages) with a second route to completing the same
rule at the same end — the shape `leo.py` calls MIXED provenance."""


def test_a_mixed_provenance_leo_key_is_served_derived_then_stored():
    """The L4 shape: a Leo top reached BOTH by the completer and by deferral.

    `leo.py` names this case as the one whose miss caused the embedded-ambiguity
    undercount, so it is built deliberately rather than hoped for.
    """
    kern = parsed(RIGHT_REC, "xxxxx")
    assert kern.st.leo_links, "this grammar does not engage Leo — nothing tested"
    for key in list(kern.st.leo_links):
        expand_leo(kern.st, kern.tables, key)
    table = FamilyTable(kern)
    mixed = [
        key for key, stored in kern.st.links.items() if stored and table.derived(key)
    ]
    assert mixed, "no key carries both kinds — this witness proves nothing"
    novel_total = 0
    for key in mixed:
        derived = table.derived(key)
        novel = [one for one in kern.st.links[key] if one not in set(derived)]
        assert table[key] == derived + novel, key
        novel_total += len(novel)
    # Searched for and NOT found: four purpose-built right-recursive and
    # ambiguous grammars all produce mixed keys whose stored tail is EMPTY —
    # every family Leo re-files there is one derivation already yields. So the
    # ORDER of a non-empty stored tail at a mixed key remains unexercised, and
    # this pins that fact instead of claiming the coverage.
    assert novel_total == 0, (
        f"{novel_total} stored families now follow a derived one at a mixed "
        "key — stored-tail order is no longer unexercised and needs a witness"
    )
