"""Tests for ``lexic.parsing.parallel.regions`` — the runs worth dividing.

A document's parallelism lives in its bracketed runs, wherever they sit. The
scan derives the brackets, separators and opaque interiors from the grammar,
cuts each big run into pieces that carry their own brackets, parses the
remaining shell once, and puts each run's merged value back where its
stand-in stood.

The end-to-end cases pass ``cores`` explicitly. ``doc_workers(AUTO)`` is 1
under the GIL, so a test that let the policy decide would take the early
return and assert nothing at all.
"""

from __future__ import annotations

import pytest

from lexic.compile import compile_from_path
from lexic.exceptions import UnsupportedConstructError
from lexic.grammars.json import JSON_GRAMMAR, JSON_REDUCER
from lexic.ir import IrInt, IrMap, IrStr, IrTuple
from lexic.parsing.parallel import MIN_CHUNK
from lexic.parsing.parallel.regions import (
    Region,
    choose,
    find,
    merge,
    pair_rules,
    pieces,
    rooted,
    separators,
    shell,
    sole_route,
    split_regions,
    stub,
)
from tests.reduce_oracle import reduce_one as _reduce_one
from tests.paths import GROUND_TRUTH

JSON_FORMULATIONS = ("json.gbnf", "json.abnf", "json.ebnf")


def _split(text: str, cores: int = 4):
    return split_regions(_reduce_one, JSON_GRAMMAR, text, JSON_REDUCER, cores)


def _sequential(text: str):
    return _reduce_one(JSON_GRAMMAR, text, JSON_REDUCER)


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


def test_a_run_with_no_separator_is_not_a_region():
    """One item does not divide, so it is not a run."""
    assert not find(JSON_GRAMMAR, '{"a": [1]}')


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


def test_the_stub_is_the_runs_first_item():
    """The shell is the one part still parsed whole, so the stand-in is one
    item, not one piece."""
    doc = "[" + _run(50) + "]"
    region = _one_region(doc)
    assert stub(doc, region) == "0"


def test_each_run_stands_in_for_a_different_item():
    """What makes two runs distinguishable in the shell's reduced value: run
    k keeps its k-th item, so equal-looking runs still leave unequal
    stand-ins."""
    doc = "[" + _run(50) + "]"
    region = _one_region(doc)
    assert [stub(doc, region, k) for k in range(3)] == ["0", "1", "2"]


def test_the_nth_item_is_clamped_to_what_the_run_has():
    """More runs than a run has items is not an error — the last item stands,
    and ``sole_route`` refuses if that turns out to collide."""
    doc = "[1,2]"
    region = _one_region(doc)
    assert stub(doc, region, 9) == "2"


def test_the_shell_is_the_document_with_each_run_shrunk_to_its_stub():
    """What is left over is parsed once, and it is small."""
    doc = '{"a": [1,2,3], "b": {"c": 1, "d": 2}}'
    divided = [r for r in find(JSON_GRAMMAR, doc) if r.rule != "object" or r.opener]
    keep = [stub(doc, r) for r in divided]
    assert shell(doc, divided, keep) == '{"a": [1], "b": {"c": 1}}'


# ── merge ─────────────────────────────────────────────────────────────────


def test_merge_concatenates_the_children_of_every_piece():
    """Every piece is the same bracketing rule carrying its own items."""
    merged = merge([IrTuple(IrInt(1), IrInt(2)), IrTuple(IrInt(3))])
    assert merged == IrTuple(IrInt(1), IrInt(2), IrInt(3))


def test_merge_refuses_pieces_of_different_types():
    """Disagreeing pieces mean the split was wrong, so it declines."""
    assert merge([IrTuple(IrInt(1)), IrMap()]) is None


def test_merge_of_nothing_is_nothing():
    """No pieces, no value — the caller reduces sequentially."""
    assert merge([]) is None


# ── sole_route and splice ────────────────────────────────────────────────


def test_a_stand_in_that_sits_in_one_place_routes_there():
    """The ordinary case: one node equals it, so that is where it goes."""
    whole = IrTuple(IrStr("a"), IrTuple(IrInt(0)))
    assert sole_route(whole, IrTuple(IrInt(0))) == (1,)


def test_a_stand_in_that_sits_in_two_places_routes_nowhere():
    """The regression that matters. Two runs standing in for the same value
    give one node two claimants: taking the first writes one run's items over
    the other's and leaves the second holding its stub, with nothing raised.

    Position cannot break the tie — an ``IrMap`` yields its entries in KEY
    order, so the run that opens first in the text may reduce to a node the
    walk reaches last. Refusing is the only sound answer here; :func:`stub`
    is what stops the case arising."""
    needle = IrTuple(IrInt(0))
    whole = IrTuple(IrTuple(IrStr("a"), needle), IrTuple(IrStr("b"), needle))
    assert sole_route(whole, needle) is None


def test_a_map_yields_its_entries_in_key_order_not_document_order():
    """The fact the routing rests on, pinned: any scheme that assumed the walk
    followed the document would mis-place a run on the first real file."""
    keys = ["version", "model", "added_tokens"]
    built = IrMap(*(IrTuple(IrStr(k), IrInt(i)) for i, k in enumerate(keys)))
    assert [str(entry[0]) for entry in built.children()] == sorted(keys)


def test_a_stand_in_that_sits_nowhere_routes_nowhere():
    """No place for the stand-in means the split declines."""
    assert sole_route(IrTuple(IrInt(1)), IrStr("q")) is None


def test_the_whole_value_can_itself_be_the_stand_in():
    """An empty route is the root, which is a route like any other."""
    assert sole_route(IrTuple(IrInt(1)), IrTuple(IrInt(1))) == ()


# ── choose ────────────────────────────────────────────────────────────────


def test_a_run_below_the_floor_is_not_worth_dividing():
    """Overhead outweighs a small run, so nothing is picked."""
    doc = "[" + _run(20) + "]"
    assert not choose(doc, find(JSON_GRAMMAR, doc), 4)


def test_a_big_run_that_cannot_divide_steps_aside_for_the_runs_inside_it():
    """A tokenizer file's top level is a handful of members, two of them
    enormous: size alone would let it claim the territory and block the runs
    that CAN divide."""
    doc = '{"a": [' + _run(BIG) + '], "b": 1}'
    picked = choose(doc, find(JSON_GRAMMAR, doc), 4)
    assert [region.rule for region, _parts in picked] == ["array"]


def test_picked_runs_never_overlap_and_come_in_document_order():
    """Otherwise the same text would be divided twice — and the ordered route
    search downstream depends on this order being the document's."""
    doc = '{"a": [' + _run(BIG) + '], "b": 1, "c": [' + _run(BIG) + "]}"
    picked = [region for region, _parts in choose(doc, find(JSON_GRAMMAR, doc), 4)]
    assert picked
    assert all(a.closer < b.opener for a, b in zip(picked, picked[1:], strict=False))


# ── split_regions ─────────────────────────────────────────────────────────


def test_one_worker_never_splits():
    """``cores=1`` is the explicit way to say "do not thread"."""
    doc = "[" + _run(BIG) + "]"
    assert _split(doc, 1) is None


def test_a_document_below_the_floor_never_splits():
    """Too little text to divide — the overhead is the whole cost."""
    assert _split('{"a": [1,2,3]}') is None


def test_a_document_with_no_divisible_run_never_splits():
    """No region clears the floor, so the caller reduces sequentially."""
    assert _split('{"a": "' + "x" * (FLOOR + 16) + '"}') is None


def test_a_split_reduction_equals_the_sequential_one():
    """The whole contract: same value, or the sequential parse."""
    doc = '{"a": [' + _run(BIG) + '], "b": "tail"}'
    assert _split(doc) == _sequential(doc)


def test_two_runs_beginning_with_the_same_item_still_reduce_correctly():
    """The regression that matters, end to end. Both runs BEGIN with the same
    item, so a shell that kept each run's first one gave them the same
    stand-in: the second run's items went under the first and the second was
    left holding its stub — a wrong document, returned without a refusal.
    Eight workers is what makes the enclosing object decline, so the two
    arrays are the runs that get divided."""
    run = _run(BIG)
    doc = '{"a": [' + run + '], "b": [' + run + "]}"
    picked = choose(doc, find(JSON_GRAMMAR, doc), 8)
    assert [region.rule for region, _parts in picked] == ["array", "array"]
    assert _split(doc, 8) == _sequential(doc)


def test_a_run_that_is_the_whole_document_reduces_correctly():
    """The shell reduces to the stand-in ALONE, so the run's merged value is
    the answer itself rather than something to splice into a place."""
    doc = "[" + _run(BIG) + "]"
    assert _split(doc) == _sequential(doc)


def test_a_run_of_objects_reduces_to_the_same_map():
    """Regions are not only arrays — the rule a piece parses under is derived
    per pair, so an object run divides the same way."""
    body = ",".join(f'"k{i}": {i}' for i in range(BIG // 2))
    doc = '{"a": {' + body + '}, "b": 1}'
    assert _split(doc) == _sequential(doc)


def test_a_piece_parses_under_its_own_regions_rule():
    """Re-rooting is what lets a piece cost its own text; the start rule is
    left alone when it already names that rule."""
    assert rooted(JSON_GRAMMAR, "array").start == "array"
    assert rooted(JSON_GRAMMAR, str(JSON_GRAMMAR.start)) is JSON_GRAMMAR


def test_a_bad_document_is_refused_by_the_sequential_parse_not_the_split():
    """A refusal is a verdict on the input, and the split never issues one:
    it declines, and the caller's whole-text reduce is what raises."""
    doc = "[" + _run(BIG) + ",\x00not json]"
    assert _split(doc) is None
    with pytest.raises(UnsupportedConstructError):
        _sequential(doc)
