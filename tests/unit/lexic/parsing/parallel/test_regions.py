"""Tests for ``lexic.parsing.parallel.discovery.regions`` — the runs worth dividing.

A document's parallelism lives in its bracketed runs, wherever they sit. The
scan derives the brackets, separators and opaque interiors from the grammar,
and cuts each big run into balanced pieces carrying their own brackets.
Model stitching is owned by the orchestrator, not this analysis leaf.
"""

from __future__ import annotations

import pytest

from lexic.compile import compile_from_path
from lexic.grammars.json import JSON_GRAMMAR
from lexic.parsing.parallel import MIN_CHUNK
from lexic.parsing.parallel.discovery.regions import (
    Region,
    choose,
    find,
    pair_rules,
    pieces,
    separators,
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
