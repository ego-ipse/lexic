"""Tests for ``lexic.parsing.parallel.discovery.regions`` — the runs worth dividing.

A document's parallelism lives in its bracketed runs, wherever they sit. The
scan derives the brackets, separators and opaque interiors from the grammar,
and cuts each big run into balanced pieces carrying their own brackets.
Model stitching is owned by the orchestrator, not this analysis leaf.
"""

from __future__ import annotations

from math import ceil
from typing import NamedTuple, cast

import pytest

from lexic.compile import compile_from_path, compile_text, parse_grammar
from lexic.grammars import GBNF_FLAVOUR
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
    find,
    listed,
    merge_windows,
    nearest_first,
    pair_rules,
    par_find,
    scan_vocabulary,
    separators,
    walk_roles,
    window_bounds,
)
from lexic.parsing.parallel.pool import WorkPool
from tests.paths import GROUND_TRUTH
from tests.split_helpers import (
    CLOSER_SEPARATOR_UNREAD,
    SHARED_CLOSER,
    closer_separator_document,
    shared_closer_source,
    two_role_source,
)

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


_NUM_LIST = 'arr ::= open num ("," num)* close\nnum ::= [0-9]+\n'
_PUNCTUATION = 'open ::= ws "[" ws\nclose ::= ws "]"\nws ::= [ ]*\n'


def _pairs_of(source: str) -> dict[str, tuple[str, str]]:
    """The pairs the region scan counts for one gbnf source."""
    return pair_rules(parse_grammar(source, GBNF_FLAVOUR))


def test_a_closer_spelled_inside_its_own_span_derives_no_pair():
    """The scan counts depth on every ``)`` it reads, and ``(a),b)`` spells one
    inside the pair's span: only the list's bracket stands."""
    source = (
        'root ::= list\nlist ::= "[" pair ("," pair)* "]"\n'
        'pair ::= "(" [a-z),]* ")" | [a-z]+ ")"\n'
    )
    assert _pairs_of(source) == {"[": ("]", "list")}


def test_a_punctuation_rule_named_only_by_its_bracket_derives_the_pair():
    """``open ::= ws "[" ws`` spells the bracket wherever it is named."""
    assert _pairs_of("root ::= arr\n" + _NUM_LIST + _PUNCTUATION) == {"[": ("]", "arr")}


def test_a_punctuation_rule_also_named_off_a_bracket_derives_no_pair():
    """``tag`` names ``open`` with no closer after it: that ``[`` is stray."""
    source = "root ::= arr | tag\ntag ::= open num\n" + _NUM_LIST + _PUNCTUATION
    assert _pairs_of(source) == {}


def test_an_opener_spelled_only_inside_a_skipped_interior_derives_the_pair():
    """``[^"]`` emits ``[``, but only inside the string the scan skips whole."""
    source = (
        'root ::= arr\narr ::= "[" val ("," val)* "]"\n'
        'val ::= str | [0-9]+\nstr ::= "\\"" [^"]* "\\""\n'
    )
    assert _pairs_of(source) == {"[": ("]", "arr")}


@pytest.mark.parametrize("shape", CLOSER_SEPARATOR_UNREAD)
def test_a_closer_spelling_an_unread_separator_is_never_a_mark(shape: str):
    """The pair stands and its closer keeps one role: ``,`` is no mark."""
    vocab = scan_vocabulary(compile_text(CLOSER_SEPARATOR_UNREAD[shape]).grammar)
    assert vocab.pairs == {"<": (",", "root")}
    assert vocab.closers == {",": "<"}
    assert vocab.marks == frozenset(".")


@pytest.mark.parametrize("shape", CLOSER_SEPARATOR_UNREAD)
def test_a_closer_spelling_an_unread_separator_finds_the_run(shape: str):
    """The run opens at ``<``, takes every ``.`` as its mark and closes on the
    final ``,``; a ``,`` inside a string is skipped, never a mark."""
    doc = closer_separator_document(shape, 40)
    dots = tuple(at for at, char in enumerate(doc) if char == ".")
    grammar = compile_text(CLOSER_SEPARATOR_UNREAD[shape]).grammar
    assert find(grammar, doc) == [Region(0, len(doc) - 1, "root", dots)]


def test_a_closer_that_opens_another_pair_derives_neither():
    """``|`` closes ``angle`` and opens ``bar``; the walk could read it only
    as one of the two, opening a frame from an angle's closer inside a bar.
    Neither pair stands, so nothing is read from the wrong delimiter."""
    grammar = compile_text(two_role_source("nest")).grammar
    assert pair_rules(grammar) == {}
    assert not find(grammar, "|<x|;y;z>")


def test_an_opener_two_pairs_claim_derives_neither():
    """The scan opens one frame per ``(`` and closes it on ONE closer, so a
    ``(`` closed by ``]`` elsewhere would end every ``(`` … ``)`` early."""
    source = (
        'root ::= item ("," item)*\nitem ::= par | rng | [0-9]+\n'
        'par ::= "(" item ")"\nrng ::= "(" item "]"\n'
    )
    assert _pairs_of(source) == {}


@pytest.mark.parametrize("shape", SHARED_CLOSER)
def test_two_pairs_sharing_a_closer_both_stand(shape: str):
    """``(`` and ``[`` both close on ``)``: the closer keeps BOTH openers."""
    vocab = scan_vocabulary(compile_text(shared_closer_source(shape)).grammar)
    assert {o: vocab.pairs[o] for o in "(["} == {"(": (")", "a"), "[": (")", "b")}
    assert vocab.closers[")"] == "(["


_SHARED_CLOSER_REGIONS = [
    Region(0, 4, "a", (2,)),
    Region(6, 10, "b", (8,)),
    Region(12, 16, "a", (14,)),
]
"""``(x;y),[p;q),(r;s)``'s three runs, read off the text by hand."""


def test_a_shared_closer_closes_each_pairs_own_frame():
    """Each ``)`` closes the frame on top, whichever of its openers opened it,
    so neither ``a`` region is lost to the ``b`` pair."""
    grammar = compile_text(shared_closer_source("top")).grammar
    assert find(grammar, "(x;y),[p;q),(r;s)") == _SHARED_CLOSER_REGIONS


def test_a_shared_closer_leaves_the_enclosing_frame_to_its_own_closer():
    """An ``a`` frame left open would swallow the ``}``: the root run closes."""
    grammar = compile_text(shared_closer_source("wrapped")).grammar
    shifted = [
        Region(r.opener + 1, r.closer + 1, r.rule, (r.marks[0] + 1,))
        for r in _SHARED_CLOSER_REGIONS
    ]
    assert find(grammar, "{(x;y),[p;q),(r;s)}") == [
        *shifted,
        Region(0, 18, "root", (6, 12)),
    ]


def test_the_region_scan_counts_a_bracket_around_no_construct():
    """A bracket arm delimiting only a class still moves the depth the scan
    counts, so its pair stands here, where roles does not take it."""
    source = 'root ::= unit ("," unit)*\nunit ::= "<" [a-z] ">" | [0-9]+\n'
    assert pair_rules(compile_text(source).codegen_grammar) == {"<": (">", "unit")}


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


# ── window_bounds ───────────────────────────────────────────────────────────────


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
    bounds = window_bounds(size, windows)
    assert len(bounds) == windows
    assert _covers_exactly_once(bounds, size)


def test_bounds_last_window_takes_the_tail() -> None:
    """An uneven division piles the remainder on the LAST window."""
    bounds = window_bounds(17, 5)
    assert bounds[:-1] == [(0, 3), (3, 6), (6, 9), (9, 12)]
    assert bounds[-1] == (12, 17)
    assert bounds[-1][1] - bounds[-1][0] > bounds[0][1] - bounds[0][0]


# ── walk_roles ────────────────────────────────────────────────────────────────


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
    assert walk_roles(_vocab()) == Roles("", (), (), (), 0, 0)


def test_names_is_padded_across_the_skip_section() -> None:
    """The skip section reads ``""`` under ``names``, so the walk indexes by
    position and never subtracts an offset before reading it."""
    skip: Skip = (";", "", 0, "", 1)
    vocab = _vocab(pairs={"(": (")", "paren")}, closers={")": "("}, skips={"'": skip})
    roles = walk_roles(vocab)
    assert roles.n_skip == 1
    assert roles.spelling[: roles.n_skip] == "'"
    assert roles.names[: roles.n_skip] == ("",)
    assert roles.skips == (skip,)
    assert roles.names[roles.n_skip] == "paren"  # the opener right after it
    assert roles.closes[: roles.n_skip] == ("",)
    assert roles.closes[roles.n_skip] == ")"


def test_every_frame_of_a_shared_closer_waits_for_it() -> None:
    """``(`` and ``[`` both close on ``)``: each opener's frame waits for
    ``)``, and nothing past the openers waits for anything."""
    vocab = scan_vocabulary(compile_text(shared_closer_source("top")).grammar)
    roles = walk_roles(vocab)
    waiting = {roles.spelling[at]: closer for at, closer in enumerate(roles.closes)}
    assert {char: closer for char, closer in waiting.items() if closer} == {
        "(": ")",
        "[": ")",
    }


# ── merge_windows ─────────────────────────────────────────────────────────


def test_an_opener_spanning_three_windows_closes_with_its_middle_mark() -> None:
    """``R_OPEN`` in window 1, ``R_MARK`` in window 2, ``R_CLOSE`` in window
    3 — the replay threads all three through the one real stack."""
    frame = (5, ")", [], "paren")
    chunks = [[(R_OPEN, 5, frame)], [(R_MARK, 10)], [(R_CLOSE, 15, ")")]]
    assert merge_windows(chunks, 0) == [Region(5, 15, "paren", (10,))]


def test_a_mismatched_closer_is_dropped() -> None:
    """A closer the frame on top does not wait for records nothing: no closer
    is also a separator (:func:`scan_vocabulary`), so it has no other role."""
    chunks = [
        [
            (R_OPEN, 1, (1, "]", [], "brak")),
            (R_MARK, 3),
            (R_CLOSE, 5, ")"),  # not the frame's closer: dropped
            (R_CLOSE, 9, "]"),
        ]
    ]
    assert merge_windows(chunks, 0) == [Region(1, 9, "brak", (3,))]


def test_an_underflowed_shared_closer_closes_either_pairs_frame() -> None:
    """Frames of two pairs sharing ``)`` both wait for it, so the one
    underflowed closer closes whichever opened the frame on top."""
    chunks = [
        [(R_OPEN, 0, (0, ")", [], "a")), (R_MARK, 2)],
        [(R_CLOSE, 4, ")"), (R_OPEN, 6, (6, ")", [], "b")), (R_MARK, 8)],
        [(R_CLOSE, 10, ")")],
    ]
    assert merge_windows(chunks, 0) == [
        Region(0, 4, "a", (2,)),
        Region(6, 10, "b", (8,)),
    ]


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


class RaisingPool(NamedTuple):
    """A mapper a refused call must never reach; it fails loudly if one does.

    A real type rather than a namespace: `par_find` asks for something that
    maps, and a stub should satisfy that requirement honestly rather than be
    an object the checker cannot look inside. It carries no state, so it is
    spelled as the empty record it is.
    """

    def map(self, work, items):
        """Never legitimately called."""
        raise AssertionError("par_find touched the pool on a refused call")


class RecordingPool:
    """Runs every window on this thread, keeping the spans it was handed.

    What the pool DOES with the windows is the pool's business; what `par_find`
    hands it is this module's, so the stub records and then runs serially. The
    question asked of the recording lives here too, beside what recorded it.
    """

    def __init__(self) -> None:
        self.spans: list[tuple[int, int]] = []

    def map(self, work, items):
        """Record the spans, then apply ``work`` to each in order."""
        self.spans.extend(items)
        return [work(item) for item in items]

    def covers_exactly_once(self, size: int) -> bool:
        """Whether the recorded spans partition ``[0, size)``."""
        return _covers_exactly_once(self.spans, size)


_RAISING_POOL = cast(WorkPool, RaisingPool())
"""One shared instance — it holds no state and exists to refuse."""


BRACKET_SOURCE = 'root ::= arr\narr ::= "[" item ("," item)* "]"\nitem ::= [a-z0-9]+\n'
"""A flat, skip-free bracket grammar — no opaque interior, so eligibility for
the windows turns only on the worker count and the document length."""


def test_a_skip_bearing_vocabulary_never_touches_the_pool() -> None:
    """A grammar carrying an opaque interior takes the serial walk, and the
    refusal decides this BEFORE the pool is ever asked to do anything."""
    assert scan_vocabulary(JSON_GRAMMAR).skips, "the fixture must carry a skip"
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


def test_the_pool_receives_every_span_exactly_once_and_matches_serial() -> None:
    """The spans handed to the pool partition the document exactly once, and
    the merged answer equals the serial walk on a document whose one region
    is the whole array — straddling every window boundary by construction."""
    grammar = compile_text(BRACKET_SOURCE, cache_key="test-regions-pool-spans").grammar
    doc = "[" + ",".join(f"item-{i:04d}" for i in range(400)) + "]"
    pool = RecordingPool()
    result = par_find(grammar, doc, 0, 5, pool=cast(WorkPool, pool))

    assert len(pool.spans) == 5
    assert pool.covers_exactly_once(len(doc))

    serial = find(grammar, doc, 0)
    assert result == serial
    assert serial, (
        "the fixture must produce a region for the comparison to mean anything"
    )


NESTED_SOURCE = (
    'root ::= arr\narr ::= "[" item ("," item)* "]"\nitem ::= arr | [a-z0-9]+\n'
)
"""Arrays of arrays: small inner runs the floor drops, inside one big one."""


def test_the_floor_holds_on_both_window_paths_at_its_boundary() -> None:
    """A run one short of the floor is dropped and one AT the floor is kept,
    whichever path closes it: inside one window, or replayed by the merge
    because its brackets straddle a window boundary. Every inner run here
    spans exactly 4 and the window count forces both paths."""
    grammar = compile_text(NESTED_SOURCE, cache_key="test-regions-floor").grammar
    doc = "[" + ",".join("[a,b]" for _ in range(60)) + "]"
    windows = 7
    bounds = window_bounds(len(doc), windows)

    def window(at: int) -> int:
        return next(k for k, (lo, hi) in enumerate(bounds) if lo <= at < hi)

    inner = find(grammar, doc, 0)[:-1]
    assert {r.closer - r.opener for r in inner} == {4}
    straddles = [window(r.opener) != window(r.closer) for r in inner]
    assert any(straddles) and not all(straddles), "the fixture must take both paths"

    outer = Region(0, len(doc) - 1, "arr", tuple(range(6, len(doc) - 1, 6)))
    assert par_find(grammar, doc, 5, windows) == find(grammar, doc, 5) == [outer]
    kept = par_find(grammar, doc, 4, windows)
    assert kept == find(grammar, doc, 4) and len(kept) == len(inner) + 1


@pytest.mark.parametrize("want", (0, 3, 4.5, 7, 12.5, 30))
def test_nearest_first_orders_found_marks_as_listed_orders_a_list(want: float) -> None:
    """Two walks out from ``want`` merge into the order :func:`listed` reads
    off a list: nearest first, the earlier on a tie, every mark once."""
    marks = [1, 2, 4, 5, 9, 12, 13, 20]
    lo, hi, middle = 0, 25, min(max(ceil(want), 0), 25)
    down = iter([at for at in reversed(marks) if lo <= at < middle])
    up = iter([at for at in marks if middle <= at < hi])
    assert list(nearest_first(down, up, want)) == list(listed(marks, want, lo, hi))
