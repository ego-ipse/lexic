"""Tests for lexic.parsing.earley.kernel.forest.families — one store, by multiplicity.

The oracle is the recorder as it stood before factoring
(:func:`tests.earley_families.paired`): the same recognition, recorded one family
per waiter per completion. Every comparison below is of COMPLETE ORDERED
buckets against it — not prefixes, not sets, and never against the group the
factored store keeps, which would check the store against itself.

Each witness is named for the provenance it reaches, and asserts that it
reaches it: a witness that silently stopped exercising its path would pass.
"""

from __future__ import annotations

import pytest

from lexic.compile import compile_text
from lexic.parsing.earley.kernel.forest.families import FamilyTable
from lexic.parsing.earley.kernel.loop import kernel as kernel_module
from lexic.parsing.earley.kernel.loop.kernel import LAZY_PROMOTION, Kernel
from lexic.parsing.earley.kernel.loop.state import PROMOTED, lazy_parts
from lexic.parsing.earley.kernel.tables.atoms import tier_for
from lexic.parsing.earley.kernel.tables.builder import compile_tables
from lexic.parsing.earley.normalize import normalize
from tests.earley_families import before_group, bucket_differences, facing, paired
from tests.paths import GROUND_TRUTH

LATE = ('root ::= e\ne ::= e "+" e | e "*" e | "n"\n', "n+n*n+n*n+n*n*n+n")
"""Keys at one ``(rule, end)`` promote at different times, so a key's first
family is often filed BEFORE its group exists, and the group never holds it."""

SPLIT = (
    "root ::= para+\npara ::= line+ blank\n"
    'line ::= [a-z ]* nl\nblank ::= nl\nnl ::= "\\n"\n',
    "a\n\nb\n\nc\n\nd\n\n",
)
"""The split-ambiguous shape; one promoted key also receives a Leo family."""

NULLABLE = ('root ::= s\ns ::= p q r\np ::= "a"*\nq ::= "a"*\nr ::= "a"*\n', "aaaa")
"""One waiter sits at several origins facing a nullable rule, so its key gets a
zero-width family from `_nullable_advance` AND ordinary ones, interleaved."""

FLAT = ('root ::= item+\nitem ::= [a-z] nl\nnl ::= "\\n"\n', "a\nb\nc\n")
"""One derivation per document: no key ever reaches a second family."""

DELEGATED = ('root ::= p item\np ::= "0"*\nitem ::= [a-z0]+ ";"\n', "000ab;")
"""`p` lets one waiter face `item` from several origins, all ending at the `;`."""


def spanning(lines: int) -> tuple[str, str]:
    """A vyx inline body of ``lines`` lines whose prose words admit the
    two-character separator, so one can span any run of them: keys facing a
    nullable rule reach many families, a waiter faces it both at earlier
    origins and at the key's own end, and groups open before later keys at
    their ``(rule, end)`` promote."""
    body = "\\n".join(["a\\n-: x"] * lines)
    return (GROUND_TRUTH / "vyx.gbnf").read_text(encoding="utf-8"), f"!R {body} >"


KEPT_BESIDE_GROUPS = (
    'root ::= "[" pair ("," pair)* "]"\n'
    'pair ::= "(" e ")" "," "(" e ")" | "(" e ")"\n'
    'e ::= e "+" e | "n"\n',
    "[(n+n+n),(n+n),(n+n+n),(n)]",
)
"""`e` factors into groups while the nullable repetition helper's keys get
several families each: every adjacent two pairs could also read as one."""


def tables(source: str, text: str):
    """Compiled Earley tables for ``source``, sized for ``text``."""
    grammar = normalize(compile_text(source).codegen_grammar)
    return compile_tables(grammar, tier_for(len(text)))


def delegating(tabs) -> dict:
    """A delegate for `item` that answers at even origins and declines at odd.

    Declining falls through to ordinary prediction, so one key receives both
    delegated and ordinary families.
    """

    def delegate(window: str, pos: int):
        """Answer the next `;`-terminated span, or decline."""
        if pos % 2:
            return None
        end = window.find(";", pos)
        return None if end < 0 else (end + 1, ("payload", pos))

    return {tabs.decode.rule_ids["item"]: delegate}


def promoted(kern: Kernel) -> list[int]:
    """The keys whose bucket is led by the promotion marker."""
    return [key for key, bucket in kern.st.links.items() if bucket[0] is PROMOTED]


def test_a_chart_that_never_promotes_is_read_through_the_dict_itself():
    """No promotion, no wrapper: the reader IS the link table."""
    kern = Kernel(tables(*FLAT), FLAT[1], True).run()
    assert kern.st.links, "nothing was filed — the test proves nothing"
    assert not kern.st.groups
    assert kern.family_reader() is kern.st.links


def test_a_factored_chart_serves_an_unpromoted_key_the_stored_object():
    """Fanout one keeps the recorder's own list — identity, not equality."""
    base, kern = paired(tables(*SPLIT), SPLIT[1])
    reader = kern.family_reader()
    assert isinstance(reader, FamilyTable), "nothing promoted — pick another witness"
    direct = [key for key, bucket in kern.st.links.items() if bucket[0] is not PROMOTED]
    assert direct
    for key in direct:
        assert reader.get(key) is kern.st.links[key], key
    assert not bucket_differences(base, kern)


def test_a_promoted_key_stores_its_marker_and_first_family_only():
    """The cross product leaves the store: a promoted bucket is
    ``[PROMOTED, first]``, plus only what Leo expansion appends after
    recognition."""
    tabs = tables(*LATE)
    base, kern = paired(tabs, LATE[1])
    unexpanded = Kernel(tabs, LATE[1], True).run()
    keys = promoted(unexpanded)
    assert keys, "nothing promoted — the test proves nothing"
    for key in keys:
        assert unexpanded.st.links[key] == [PROMOTED, base.st.links[key][0]], key
    widest = max(len(base.st.links[key]) for key in promoted(kern))
    assert widest > 2, "no promoted key had a fanout the marker could save on"


@pytest.mark.parametrize(
    ("label", "witness"),
    [("late", LATE), ("split", SPLIT), ("nullable", NULLABLE), ("flat", FLAT)],
)
def test_every_bucket_matches_the_pre_factoring_recorder(label, witness):
    """Complete ordered buckets, every key, after every Leo chain is expanded."""
    base, kern = paired(tables(*witness), witness[1])
    assert base.st.links, f"{label}: nothing filed — the test proves nothing"
    differences = bucket_differences(base, kern)
    assert not differences, f"{label}: {differences[:2]}"


def test_a_late_promotion_reads_its_first_family_first():
    """The case that mis-ordered: a key's first family filed before its group.

    That family was filed before every entry the group gained, so a key
    promoting LATE must still read it first — and it must be read at all,
    since the group never saw it.
    """
    base, kern = paired(tables(*LATE), LATE[1])
    assert before_group(kern), "no first family predates its group — nothing tested"
    assert not bucket_differences(base, kern)


def test_a_promoted_key_that_also_gets_a_leo_family_reads_ordinary_first():
    """Mixed provenance: expansion appends after recognition, behind the marker."""
    base, kern = paired(tables(*SPLIT), SPLIT[1])
    mixed = [key for key in promoted(kern) if len(kern.st.links[key]) > 2]
    assert mixed, "no promoted key received a Leo family — nothing tested"
    reader = kern.family_reader()
    for key in mixed:
        served = reader.get(key)
        assert served is not None
        assert served[-(len(kern.st.links[key]) - 2) :] == kern.st.links[key][2:]
    assert not bucket_differences(base, kern)


def _interleaved(base: Kernel) -> list[int]:
    """Keys whose baseline bucket mixes zero-width and ordinary families."""
    end_mask = base.tables.packing.mask
    return [
        key
        for key, bucket in base.st.links.items()
        if {one[1] == (key & end_mask) for one in bucket} == {True, False}
    ]


def test_a_key_facing_a_nullable_rule_holds_few_families_explicitly(monkeypatch):
    """Zero-width and ordinary families interleave in filing order at such a key.
    Holding fewer than its threshold of them, it keeps them all."""
    monkeypatch.setattr(kernel_module, "LAZY_PROMOTION", 8)
    base, kern = paired(tables(*NULLABLE), NULLABLE[1])
    mixed = _interleaved(base)
    assert mixed, "no key mixes zero-width and ordinary families — nothing tested"
    for key in mixed:
        assert kern.st.links[key][0] is not PROMOTED, key
        assert len(kern.st.links[key]) < 8, key
    assert not bucket_differences(base, kern)


def test_empty_families_take_a_bucket_past_its_threshold_unpromoted() -> None:
    """The completer files a family while its bucket holds fewer than the
    threshold and promotes at the next; the empty families the waiter's own
    visit files go in beside them. A bucket can so hold more than the
    threshold, explicitly, and read as filed."""
    base, kern = paired(tables(*NULLABLE), NULLABLE[1])
    over = [
        key
        for key, bucket in kern.st.links.items()
        if bucket[0] is not PROMOTED and len(bucket) > LAZY_PROMOTION
    ]
    assert over, "no bucket past its threshold — nothing tested"
    assert not bucket_differences(base, kern)


def _lazy_heads(kern: Kernel) -> list[tuple[int, int, int]]:
    """The heads of lazily promoted buckets: ``(cursor, held, place)``."""
    return [
        lazy_parts(bucket[1])
        for bucket in kern.st.links.values()
        if bucket[0] is PROMOTED and bucket[1][0] < 0
    ]


@pytest.mark.parametrize(
    ("label", "witness", "threshold"),
    [
        ("nullable", NULLABLE, 1),
        ("beside-groups", KEPT_BESIDE_GROUPS, 1),
        ("separators", spanning(4), 2),
        ("separators-default", spanning(16), LAZY_PROMOTION),
    ],
)
def test_a_nullable_key_past_the_threshold_reads_its_families_in_order(
    monkeypatch, label, witness, threshold
):
    """Past the threshold a key facing a nullable rule promotes: it keeps the
    families it held and reads the rest from its group, from where it promoted.
    Each one is served in the order the pre-factoring recorder filed it."""
    monkeypatch.setattr(kernel_module, "LAZY_PROMOTION", threshold)
    base, kern = paired(tables(*witness), witness[1])
    heads = _lazy_heads(kern)
    assert heads, f"{label}: no key promoted lazily — nothing tested"
    assert all(held >= threshold for _cursor, held, _place in heads), heads
    if label.startswith("separators"):
        assert any(cursor > 0 for cursor, *_rest in heads), "every group opened here"
    assert not bucket_differences(base, kern)


def test_a_late_empty_family_stands_between_the_groups_entries(monkeypatch) -> None:
    """The ambiguous split, read back: one waiter faces the nullable rule at
    earlier origins and at the key's own end, so its empty families are filed
    after the key promoted. They are served where they were filed, between
    the group's entries before that place and those after it."""
    monkeypatch.setattr(kernel_module, "LAZY_PROMOTION", 2)
    base, kern = paired(tables(*spanning(4)), spanning(4)[1])
    end_mask = kern.tables.packing.mask
    reader = kern.family_reader()
    between = []
    for key, bucket in kern.st.links.items():
        if bucket[0] is not PROMOTED or bucket[1][0] >= 0:
            continue
        if lazy_parts(bucket[1])[2] < 0:
            continue
        served = reader[key]
        last = max(n for n, one in enumerate(served) if one[1] == key & end_mask)
        if any(one not in bucket for one in served[last + 1 :]):
            between.append(key)
        assert served == base.st.links[key], key
    assert between, "no group entry follows a late empty family — nothing tested"


def kept_rules(kern: Kernel) -> set[int]:
    """The rules whose keys this kernel does not factor at a second family:
    nullable (lazy) or delegated (kept)."""
    codes = kern.tables.codes
    return {
        rid
        for rid, done in enumerate(codes.nullable_completes)
        if done or rid in kern.delegates
    }


def test_a_kept_rule_never_gets_a_group():
    """A chart that factors still files a kept rule's families in their buckets.

    The tier is the completed rule's, decided once per completion: a nullable
    rule's keys holding fewer than :data:`LAZY_PROMOTION` families never promote
    and open no group for it, even on a chart where other rules' groups exist.
    """
    base, kern = paired(tables(*KEPT_BESIDE_GROUPS), KEPT_BESIDE_GROUPS[1])
    kept = kept_rules(kern)
    assert kern.st.groups, "nothing factored — the test proves nothing"
    several = [
        key
        for key, bucket in base.st.links.items()
        if len(bucket) > 1 and facing(kern, key) in kept
    ]
    assert several, "no kept key got a second family — nothing tested"
    assert not [rid for rid, _end in kern.st.groups if rid in kept]
    for key in several:
        assert kern.st.links[key][0] is not PROMOTED, key
    assert not bucket_differences(base, kern)


def test_a_delegated_rule_never_gets_a_group_in_the_kernel_that_delegates_it():
    """The keep is per kernel: `item` is not nullable, and only delegation keeps it."""
    tabs = tables(*DELEGATED)
    item = tabs.decode.rule_ids["item"]
    assert not tabs.codes.nullable_completes[item], "item is nullable — pick another"
    base, kern = paired(tabs, DELEGATED[1], delegating(tabs))
    several = [
        key
        for key, bucket in base.st.links.items()
        if len(bucket) > 1 and facing(kern, key) == item
    ]
    assert several, "no key facing item got a second family — nothing tested"
    assert not [rid for rid, _end in kern.st.groups if rid == item]
    assert not bucket_differences(base, kern)


def test_the_table_is_not_iterable_and_misses_like_a_mapping():
    """No legacy index walk, and a missing key is ``None`` / ``KeyError``."""
    _base, kern = paired(tables(*SPLIT), SPLIT[1])
    reader = kern.family_reader()
    assert isinstance(reader, FamilyTable)
    with pytest.raises(TypeError):
        iter(reader)
    absent = 1 << 60
    assert reader.get(absent) is None
    with pytest.raises(KeyError):
        _ = reader[absent]
