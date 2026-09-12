"""Tests for ``lexic.parsing.parallel.discovery.regions`` — the runs worth dividing.

A document's parallelism lives in its bracketed runs, wherever they sit. The
scan derives the brackets, separators and opaque interiors from the grammar,
and cuts each big run into balanced pieces carrying their own brackets.
Model stitching is owned by the orchestrator, not this analysis leaf.
"""

from __future__ import annotations

from functools import partial
from types import SimpleNamespace

import pytest

from lexic.compile import compile_from_path, compile_text
from lexic.grammars.json import JSON_GRAMMAR
from lexic.parsing.parallel import MIN_CHUNK
from lexic.parsing.parallel.discovery.interiors import Skip
from lexic.parsing.parallel.discovery.regions import (
    R_CLOSE,
    R_DONE,
    R_MARK,
    R_OPEN,
    Region,
    Roles,
    Vocab,
    _bounds,
    _roles,
    _sweep,
    _vocabulary,
    _walk,
    choose,
    find,
    merge_windows,
    pair_rules,
    par_find,
    piece_marks,
    pieces,
    separators,
    shell,
    stub,
)
from tests.paths import GROUND_TRUTH

JSON_FORMULATIONS = ("json.gbnf", "json.abnf", "json.ebnf")


def _one_region(doc: str) -> Region:
    """The document's single run — the shape these cases are written around."""
    found = find(JSON_GRAMMAR, doc)
    assert len(found) == 1
    return found[0]


FLOOR = 2 * MIN_CHUNK
"""The region floor — a run must be able to feed two workers."""


def _run(items: int) -> str:
    """A comma-separated integer run comfortably past the region floor."""
    return ",".join(str(i) for i in range(items))


BIG = FLOOR // 2  # items of 2-5 chars, so a run of this many clears the floor


# ── pair_rules ────────────────────────────────────────────────────────────


def test_json_derives_both_bracket_pairs_with_the_rule_a_piece_parses_under():
    """A piece needs the RULE, not just the characters — that is what lets it
    parse at the cost of its own text."""
    assert pair_rules(JSON_GRAMMAR) == {"{": ("}", "object"), "[": ("]", "array")}


@pytest.mark.parametrize("name", JSON_FORMULATIONS)
def test_every_json_formulation_derives_the_same_pairs(name: str):
    """No privileged formulation: the shape is read, not the file."""
    path = GROUND_TRUTH / name
    if not path.exists():
        pytest.skip(f"fixture absent: {name}")
    grammar = compile_from_path(path).grammar
    assert pair_rules(grammar) == {"{": ("}", "object"), "[": ("]", "array")}
    assert separators(grammar) == frozenset(",")


def test_json_derives_the_comma_separator():
    """Derived, never named: the char every arm of a repeated body leads with."""
    assert separators(JSON_GRAMMAR) == frozenset(",")


# ── find ──────────────────────────────────────────────────────────────────


def test_find_reports_every_run_with_the_separators_directly_inside_it():
    """A mark belongs to the bracket that most recently opened, which is what
    makes the answer depth-agnostic."""
    doc = '{"a": [1,2,3], "b": {"c": 1, "d": 2}}'
    got = find(JSON_GRAMMAR, doc)
    assert [(r.rule, r.marks) for r in got] == [
        ("array", (8, 10)),
        ("object", (27,)),
        ("object", (13,)),
    ]


def test_a_separator_inside_a_string_is_text_not_a_mark():
    """The opaque interior is skipped whole — this is the case a naive
    splitter mis-cuts, and the reason interiors are derived at all."""
    doc = '{"a": "x,y,z", "b": 1}'
    region = _one_region(doc)
    assert region.marks == (doc.index('", "') + 1,)


def test_an_escaped_delimiter_does_not_end_the_interior():
    """``\\"`` is text; a scan that stopped there would read the rest of the
    string as structure, and the comma inside it as a separator."""
    doc = '{"a": "x\\",y", "b": 1}'
    region = _one_region(doc)
    assert region.marks == (doc.index('", "') + 1,)


def test_an_even_escape_run_does_not_hide_the_closing_delimiter():
    """Two escaped backslashes leave the following quote structural."""
    doc = r'{"a": "\\\\", "b": 1}'
    region = _one_region(doc)
    assert region.marks == (doc.index('", "') + 1,)


def test_a_run_with_no_separator_is_not_a_region():
    """One item does not divide, so it is not a run."""
    assert not find(JSON_GRAMMAR, '{"a": [1]}')


def test_find_can_drop_regions_below_the_callers_work_floor():
    """Discovery need not retain runs a scheduler can never delegate."""
    doc = '{"a": [1,2,3], "b": 4}'
    assert find(JSON_GRAMMAR, doc)
    assert not find(JSON_GRAMMAR, doc, len(doc) + 1)


def test_a_closer_with_no_matching_opener_is_ignored():
    """The stack walk never pops what it did not push."""
    assert find(JSON_GRAMMAR, ']}{"a": 1, "b": 2}') == [Region(2, 17, "object", (9,))]


# ── pieces, stub, shell ───────────────────────────────────────────────────


def test_each_piece_carries_its_own_brackets():
    """A piece is a document under its region's rule — that is the difference
    that decides whether splitting pays."""
    doc = "[" + _run(6) + "]"
    region = _one_region(doc)
    assert pieces(doc, region, 2) == ["[0,1,2]", "[3,4,5]"]


def test_piece_marks_are_the_source_offsets_removed_by_pieces():
    """The stitch's cut metadata is exactly the separators pieces remove."""
    doc = "[" + _run(6) + "]"
    region = _one_region(doc)
    cuts = piece_marks(region, 2)
    assert cuts == [doc.index(",", doc.index("2"))]
    assert list(pieces(doc, region, 2) or ()) == [
        "[0,1,2]",
        "[3,4,5]",
    ]


def test_stubs_can_keep_equal_leading_items_distinct_and_shell_keeps_brackets():
    """Each region gets a distinct stand-in while its shell punctuation stays."""
    doc = '{"a": [0,1,2], "b": [0,1,2]}'
    arrays = [region for region in find(JSON_GRAMMAR, doc) if region.rule == "array"]
    assert len(arrays) == 2
    kept = [stub(doc, region, index) for index, region in enumerate(arrays)]
    assert kept == ["0", "1"]
    assert shell(doc, arrays, kept) == '{"a": [0], "b": [1]}'


def test_cuts_aim_at_equal_positions_not_at_equal_counts():
    """Dividing the separator COUNT divides the work only when the items are
    evenly spread; the nearest separator to the position is taken instead."""
    doc = '["aaaaaaaaaaaaaaaaaaaa","b","c","d"]'
    region = _one_region(doc)
    assert pieces(doc, region, 2) == ['["aaaaaaaaaaaaaaaaaaaa"]', '["b","c","d"]']


def test_a_run_that_will_not_divide_evenly_returns_none():
    """One enormous item beside a small one cannot be cut four ways, so the
    region declines rather than handing one worker most of the document."""
    doc = '["' + "a" * 400 + '","b"]'
    region = _one_region(doc)
    assert pieces(doc, region, 4) is None
    assert pieces(doc, region, 2) is not None  # two ways it does divide


def test_a_run_below_the_floor_is_not_worth_dividing():
    """Overhead outweighs a small run, so nothing is picked."""
    doc = "[" + _run(20) + "]"
    assert not choose(doc, find(JSON_GRAMMAR, doc), 4)


def test_each_requested_worker_must_receive_one_full_chunk():
    """A useful region is clamped to its available pieces, not declined."""
    doc = "[" + _run(BIG) + "]"
    assert choose(doc, find(JSON_GRAMMAR, doc), 4)
    picked = choose(doc, find(JSON_GRAMMAR, doc), 8)
    assert len(picked) == 1
    assert len(picked[0][1]) == 4


def test_a_big_run_that_cannot_divide_steps_aside_for_the_runs_inside_it():
    """An outer run that cannot divide steps aside for its balanced child."""
    doc = '{"a": [' + _run(BIG) + '], "b": 1}'
    picked = choose(doc, find(JSON_GRAMMAR, doc), 4)
    assert [region.rule for region, _parts in picked] == ["array"]


def test_runner_count_prefers_an_eight_way_child_over_a_three_way_outer():
    """Ownership ranking chooses the nested plan that fills more workers."""
    items = ['"' + "x" * 2200 + '"' for _ in range(8)]
    doc = (
        '{"head":"'
        + "h" * 17000
        + '","items":['
        + ",".join(items)
        + '],"tail":"'
        + "t" * 17000
        + '"}'
    )
    found = find(JSON_GRAMMAR, doc)
    outer = max(found, key=lambda region: region.span)
    nested = next(region for region in found if region.rule == "array")

    assert outer.rule == "object"
    assert len(pieces(doc, outer, 3) or ()) == 3
    assert len(pieces(doc, nested, 8) or ()) == 8
    picked = choose(doc, found, 8)
    assert [(region.rule, len(parts)) for region, parts in picked] == [("array", 8)]


def test_picked_runs_never_overlap_and_come_in_document_order():
    """Otherwise the same text would be divided twice — and the ordered route
    search downstream depends on this order being the document's."""
    doc = '{"a": [' + _run(BIG) + '], "b": 1, "c": [' + _run(BIG) + "]}"
    picked = [region for region, _parts in choose(doc, find(JSON_GRAMMAR, doc), 4)]
    assert picked
    assert all(a.closer < b.opener for a, b in zip(picked, picked[1:], strict=False))


# ── _bounds ───────────────────────────────────────────────────────────────


def _covers_exactly_once(bounds: list[tuple[int, int]], size: int) -> bool:
    """Whether ``bounds`` is contiguous, gapless, and spans ``[0, size)``.

    Contiguity plus matching outer edges already forces every offset into
    exactly one window; there is no gap or overlap left for a second offset
    to slip through.
    """
    if not bounds:
        return size == 0
    if bounds[0][0] != 0 or bounds[-1][1] != size:
        return False
    return all(a[1] == b[0] for a, b in zip(bounds, bounds[1:]))


@pytest.mark.parametrize(
    "size, windows",
    [
        (0, 3),
        (1, 1),
        (1, 3),
        (4, 5),  # size == windows - 1
        (5, 5),  # size == windows
        (6, 5),  # size == windows + 1
        (17, 5),  # a prime size
    ],
)
def test_bounds_covers_every_offset_exactly_once(size: int, windows: int) -> None:
    """Every requested edge case, from an empty document to a prime size."""
    bounds = _bounds(size, windows)
    assert len(bounds) == windows
    assert _covers_exactly_once(bounds, size)


def test_bounds_last_window_takes_the_tail() -> None:
    """An uneven division piles the remainder on the LAST window."""
    bounds = _bounds(17, 5)
    assert bounds[:-1] == [(0, 3), (3, 6), (6, 9), (9, 12)]
    assert bounds[-1] == (12, 17)
    assert bounds[-1][1] - bounds[-1][0] > bounds[0][1] - bounds[0][0]


# ── _roles ────────────────────────────────────────────────────────────────


def _vocab(
    pairs: dict[str, tuple[str, str]] | None = None,
    closers: dict[str, str] | None = None,
    marks: frozenset[str] = frozenset(),
    skips: dict[str, Skip] | None = None,
) -> Vocab:
    """A hand-built :class:`Vocab`, every table empty unless given."""
    return Vocab(pairs or {}, closers or {}, marks, skips or {})


def test_roles_of_an_empty_vocabulary_is_all_empty() -> None:
    """No skips, no pairs, no marks — every table comes out empty."""
    assert _roles(_vocab()) == Roles("", "", (), (), 0, 0, "")


def test_watched_deduplicates_a_two_role_character() -> None:
    """A separator that is also a closer stands twice in the classification
    spelling and ONCE in the sweep alphabet.

    The spelling needs both, so `find` can resolve the character by precedence;
    a sweep that iterated it would report every one of that character's offsets
    twice.
    """
    vocab = _vocab(
        pairs={"[": ("]", "list")}, closers={"]": "[", "|": "("}, marks={"|"}
    )
    roles = _roles(vocab)
    assert roles.spelling.count("|") == 2
    assert roles.watched.count("|") == 1
    assert set(roles.watched) == set(roles.spelling)


def test_names_is_padded_across_the_skip_section() -> None:
    """The skip section reads ``""`` under ``names``, so the walk indexes by
    position and never subtracts an offset before reading it."""
    skip: Skip = (";", "", 0, "", 1)
    vocab = _vocab(pairs={"(": (")", "paren")}, closers={")": "("}, skips={"'": skip})
    roles = _roles(vocab)
    assert roles.n_skip == 1
    assert roles.spelling[: roles.n_skip] == "'"
    assert roles.names[: roles.n_skip] == ("",)
    assert roles.skips == (skip,)
    assert roles.names[roles.n_skip] == "paren"  # the opener right after it


TWO_ROLE_VOCAB = _vocab(
    pairs={"(": ("|", "paren"), "[": ("]", "brak")},
    closers={"|": "(", "]": "["},
    marks=frozenset({"|", ","}),
)
"""``|`` closes ``(`` AND is a separator — the two-role case the section
order has to resolve."""


def test_a_closer_that_is_also_a_mark_closes_when_it_matches_the_open_frame() -> None:
    """Closers are spelled before marks, so ``find`` always lands on the
    closer entry first; when it matches the frame on top, CLOSE wins — the
    old elif chain's first test for this character."""
    roles = _roles(TWO_ROLE_VOCAB)
    text = "(a,b|"
    offsets = _sweep(text, TWO_ROLE_VOCAB.watched)
    assert _walk(text, offsets, roles, 0) == [Region(0, 4, "paren", (2,))]


def test_an_unmatched_closer_that_is_also_a_mark_falls_through_to_mark() -> None:
    """The same ``|``, but the open frame wants ``]`` — the closer test
    fails, and the fallthrough treats it as a separator instead, exactly as
    the old ``elif char in vocab.marks and stack`` branch did."""
    roles = _roles(TWO_ROLE_VOCAB)
    text = "[a|]"
    offsets = _sweep(text, TWO_ROLE_VOCAB.watched)
    assert _walk(text, offsets, roles, 0) == [Region(0, 3, "brak", (2,))]


# ── merge_windows ─────────────────────────────────────────────────────────


def test_an_opener_spanning_three_windows_closes_with_its_middle_mark() -> None:
    """``R_OPEN`` in window 1, ``R_MARK`` in window 2, ``R_CLOSE`` in window
    3 — the replay threads all three through the one real stack."""
    frame = (5, "(", [], "paren")
    chunks = [[(R_OPEN, 5, frame)], [(R_MARK, 10)], [(R_CLOSE, 15, "(", False)]]
    assert merge_windows(chunks, 0) == [Region(5, 15, "paren", (10,))]


def test_a_mismatched_closer_that_is_also_a_mark_falls_through() -> None:
    """A closer that does not match the frame on top is not dropped outright
    — if it is ALSO a separator, the fallthrough keeps it as a mark."""
    chunks = [
        [
            (R_OPEN, 1, (1, "[", [], "brak")),
            (R_CLOSE, 5, "(", True),  # wrong opener, but a separator
            (R_CLOSE, 9, "[", False),
        ]
    ]
    assert merge_windows(chunks, 0) == [Region(1, 9, "brak", (5,))]


def test_a_mismatched_closer_with_no_mark_role_is_dropped() -> None:
    """Same mismatch, but not a separator — nothing is recorded for it."""
    chunks = [
        [
            (R_OPEN, 1, (1, "[", [], "brak")),
            (R_MARK, 3),
            (R_CLOSE, 5, "(", False),  # wrong opener, not a separator: dropped
            (R_CLOSE, 9, "[", False),
        ]
    ]
    assert merge_windows(chunks, 0) == [Region(1, 9, "brak", (3,))]


def test_r_done_regions_from_two_windows_keep_document_order() -> None:
    """Each window settles its own fully-enclosed regions; the merge must
    not reorder what document order already put in the right sequence."""
    earlier = Region(5, 10, "brak", (7,))
    later = Region(15, 20, "paren", (18,))
    chunks = [[(R_DONE, 10, earlier)], [(R_DONE, 20, later)]]
    assert merge_windows(chunks, 0) == [earlier, later]


def test_an_empty_chunk_list_merges_to_nothing() -> None:
    """No windows at all is not a special case — just nothing to replay."""
    assert not merge_windows([], 0)


def test_a_chunk_with_no_events_contributes_nothing() -> None:
    """A window that swept nothing structural sits between others harmlessly."""
    later = Region(15, 20, "paren", (18,))
    assert merge_windows([[], [(R_DONE, 20, later)], []], 0) == [later]


# ── par_find refusal ──────────────────────────────────────────────────────


def _raise_if_called(fn, spans):
    """A pool ``map`` a refused call must never reach."""
    raise AssertionError("par_find touched the pool on a refused call")


_RAISING_POOL = SimpleNamespace(map=_raise_if_called)
"""A pool stub whose ``map`` fails loudly if a refusal ever reaches it."""


BRACKET_SOURCE = 'root ::= arr\narr ::= "[" item ("," item)* "]"\nitem ::= [a-z0-9]+\n'
"""A flat, skip-free bracket grammar — no opaque interior, so eligibility for
the windows turns only on the worker count and the document length."""


def test_a_skip_bearing_vocabulary_never_touches_the_pool() -> None:
    """A grammar carrying an opaque interior takes the serial walk, and the
    refusal decides this BEFORE the pool is ever asked to do anything."""
    assert _vocabulary(JSON_GRAMMAR).skips, "the fixture must carry a skip"
    doc = '{"a": [1,2,3], "b": {"c": 1, "d": 2}}'
    result = par_find(JSON_GRAMMAR, doc, 0, 8, pool=_RAISING_POOL)
    assert result == find(JSON_GRAMMAR, doc, 0)
    assert result, "the fixture must find a region for the refusal to mean anything"


def test_fewer_than_two_workers_never_touches_the_pool() -> None:
    """One worker is not a division — the serial walk answers directly."""
    grammar = compile_text(BRACKET_SOURCE, cache_key="test-regions-workers-1").grammar
    doc = "[" + ",".join(f"i{i}" for i in range(200)) + "]"
    result = par_find(grammar, doc, 0, 1, pool=_RAISING_POOL)
    assert result == find(grammar, doc, 0)
    assert result


def test_a_document_shorter_than_the_worker_count_never_touches_the_pool() -> None:
    """``windows`` is clamped to ``len(text)``, so a one-character document
    with eight requested workers still resolves to a single unwindowed walk."""
    grammar = compile_text(BRACKET_SOURCE, cache_key="test-regions-short-doc").grammar
    doc = "["
    result = par_find(grammar, doc, 0, 8, pool=_RAISING_POOL)
    assert result == find(grammar, doc, 0) == []


# ── par_find with a real pool ─────────────────────────────────────────────


def _record_and_run(seen: list[tuple[int, int]], fn, spans):
    """Record ``spans`` into ``seen``, then run every window on this thread."""
    seen.extend(spans)
    return [fn(span) for span in spans]


def test_the_pool_receives_every_span_exactly_once_and_matches_serial() -> None:
    """The spans handed to the pool partition the document exactly once, and
    the merged answer equals the serial walk on a document whose one region
    is the whole array — straddling every window boundary by construction."""
    grammar = compile_text(BRACKET_SOURCE, cache_key="test-regions-pool-spans").grammar
    doc = "[" + ",".join(f"item-{i:04d}" for i in range(400)) + "]"
    spans_seen: list[tuple[int, int]] = []
    pool = SimpleNamespace(map=partial(_record_and_run, spans_seen))
    result = par_find(grammar, doc, 0, 5, pool=pool)

    assert len(spans_seen) == 5
    assert _covers_exactly_once(spans_seen, len(doc))

    serial = find(grammar, doc, 0)
    assert result == serial
    assert serial, (
        "the fixture must produce a region for the comparison to mean anything"
    )
