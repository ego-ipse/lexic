"""Tests for ``lexic.parsing.parallel.discovery.partition`` — which spans to divide.

The partition packs a span's adjacent items into runs of about one worker's
share, descends into an item too big for one, and renders every piece and the
shell with the stand-ins of the spans divided inside them. The region scan
supplies the spans here; the partition itself never reads a bracket.
"""

from __future__ import annotations

import random

import pytest

from lexic.grammars.json import JSON_GRAMMAR
from lexic.parsing.parallel import MIN_CHUNK
from lexic.parsing.parallel.discovery.regions import Region, find
from lexic.parsing.parallel.discovery.partition import (
    Division,
    Weights,
    partition,
    render,
    runs,
    units,
)

FLOOR = 2 * MIN_CHUNK
BIG = FLOOR // 2  # items of 2-5 chars, so a run of this many clears the floor


def _one_region(doc: str) -> Region:
    """The document's single run — the shape these cases are written around."""
    found = find(JSON_GRAMMAR, doc)
    assert len(found) == 1
    return found[0]


def _run(items: int) -> str:
    """A comma-separated integer run."""
    return ",".join(str(i) for i in range(items))


# ── units, render ─────────────────────────────────────────────────────────


def test_each_piece_carries_its_own_brackets_and_the_shell_its_stand_in():
    """A piece is a document under its region's rule — that is what decides
    whether splitting pays — and the shell keeps the region's brackets."""
    doc = "[0,1,2,3,4,5]"
    region = _one_region(doc)
    cut = doc.index(",", doc.index("2"))
    out = units(doc, [Division(region, (cut,))], ["9"])
    assert [unit.text for unit in out] == ["[0,1,2]", "[3,4,5]", "[9]"]
    assert [unit.owner for unit in out] == [0, 0, -1]
    assert (out[-1].held, out[-1].items) == ([0], [-1])


def test_render_replaces_each_interior_and_keeps_the_brackets():
    """Over the whole text or a window of it, each interior becomes its
    stand-in and the brackets stay."""
    doc = '{"a": [0,1,2], "b": [0,1,2]}'
    arrays = [region for region in find(JSON_GRAMMAR, doc) if region.rule == "array"]
    assert render(doc, (0, len(doc)), arrays, ["0", "1"]) == '{"a": [0], "b": [1]}'
    assert render(doc, (6, 13), arrays[:1], ["x"]) == "[x]"


def test_a_nested_division_is_held_by_the_item_of_the_piece_around_it():
    """The array sits in the object's second member, which the object's first
    piece holds: that piece carries the array's stand-in and says which item
    holds it; the shell carries only the object's."""
    doc = '{"b": 7, "a": [0,1,2], "c": 8}'
    found = find(JSON_GRAMMAR, doc)
    obj = next(region for region in found if region.rule == "object")
    arr = next(region for region in found if region.rule == "array")
    cut = doc.index(",", arr.closer)
    split = [Division(obj, (cut,)), Division(arr, (doc.index(",", arr.opener),))]
    out = units(doc, split, ["X", "S"])
    assert [(u.owner, u.text, u.held, u.items) for u in out] == [
        (0, '{"b": 7, "a": [S]}', [1], [1]),
        (0, '{ "c": 8}', [], []),
        (1, "[0]", [], []),
        (1, "[1,2]", [], []),
        (-1, "{X}", [0], [-1]),
    ]


# ── partition ─────────────────────────────────────────────────────────────


def _bounds_sizes(division: Division) -> list[int]:
    """Each piece's source width, separators excluded."""
    bounds = division.bounds
    return [bounds[k + 1] - bounds[k] for k in range(len(bounds) - 1)]


def test_a_document_of_one_unit_of_work_is_not_divided():
    """Below the floor nothing runs beside anything, so nothing is divided."""
    doc = "[" + _run(20) + "]"
    assert partition(doc, find(JSON_GRAMMAR, doc), 4) == []


def test_one_long_run_packs_into_a_piece_per_worker():
    """Adjacent items pack up to a quarter of the text each: four pieces, cut
    at the region's own separators, each clearing the floor."""
    doc = "[" + _run(20000) + "]"
    (division,) = partition(doc, find(JSON_GRAMMAR, doc), 4)
    target = len(doc) / 4
    assert len(division.cuts) == 3
    assert all(doc[cut] == "," for cut in division.cuts)
    assert all(
        MIN_CHUNK <= size <= target + MIN_CHUNK for size in _bounds_sizes(division)
    )


def test_an_oversized_item_is_descended_and_its_path_divided():
    """The object's big member holds the array: the array is divided four
    ways, and the object — on the path, with a floor's worth of text of its
    own — is divided too, whole, so the piece holding the array's stand-in
    is found by item."""
    doc = '{"pad": "' + "p" * 3000 + '", "a": [' + _run(20000) + "]}"
    picked = partition(doc, find(JSON_GRAMMAR, doc), 4)
    assert [(d.region.rule, len(d.cuts)) for d in picked] == [
        ("object", 0),
        ("array", 3),
    ]


def test_a_path_region_with_little_text_of_its_own_is_left_to_its_holder():
    """Without the padding the object keeps a few bytes once the array is
    descended: a unit of its own would cost more than finding the stand-in
    in the shell, so only the array is divided."""
    doc = '{"a": [' + _run(20000) + '], "b": 1}'
    picked = partition(doc, find(JSON_GRAMMAR, doc), 4)
    assert [(d.region.rule, len(d.cuts)) for d in picked] == [("array", 3)]


def test_adjacent_regions_ship_together_rather_than_divided():
    """Twelve inner arrays of a fifth of a piece each: the outer array packs
    them three to a piece, and not one of them is divided."""
    inner = "[" + _run(1000) + "]"
    doc = "[" + ",".join([inner] * 12) + "]"
    (division,) = partition(doc, find(JSON_GRAMMAR, doc), 4)
    outer = max(find(JSON_GRAMMAR, doc), key=lambda region: region.span)
    assert division.region == outer
    assert division.cuts == tuple(outer.marks[k] for k in (2, 5, 8))


def test_no_piece_falls_below_the_floor():
    """A small item after an oversized one would make a sub-floor run: it
    rejoins the run before, and with one run left the region is not divided."""
    doc = '["' + "a" * 100 + '","' + "b" * 30000 + '","' + "c" * 100 + '"]'
    assert partition(doc, find(JSON_GRAMMAR, doc), 8) == []


def test_a_division_carries_the_cuts_its_pieces_were_cut_at():
    """The cuts ARE the pieces' boundaries: removing each piece's own brackets
    and rejoining with the separator at each cut gives the region back."""
    doc = "[" + _run(BIG) + "]"
    (division,) = partition(doc, find(JSON_GRAMMAR, doc), 4)
    region = division.region
    parts = [unit.text for unit in units(doc, [division], ["0"]) if unit.owner == 0]
    assert len(parts) == len(division.cuts) + 1 > 1
    rebuilt = ",".join(part[1:-1] for part in parts)
    assert rebuilt == doc[region.opener + 1 : region.closer]
    assert all(doc[cut] == "," for cut in division.cuts)
    inner = [len(part) - 2 for part in parts]
    starts = [region.opener + 1 + sum(inner[:k]) + k for k in range(1, len(inner))]
    assert [start - 1 for start in starts] == list(division.cuts)


# ── runs by bisection, against the item-by-item greedy ───────────────────


def _greedy(target: float, sizes: list[int], marks: tuple[int, ...]) -> tuple[int, ...]:
    """The reference: walk every item, close a run before the item that would
    carry a run of at least MIN_CHUNK past ``target``; a short last run rejoins."""
    cuts: list[int] = []
    run = 0
    for at, size in enumerate(sizes):
        if run >= MIN_CHUNK and run + size > target:
            cuts.append(marks[at - 1])
            run = 0
        run += size
    if cuts and run < MIN_CHUNK:
        cuts.pop()
    return tuple(cuts)


def _random_region(rng: random.Random) -> tuple[Weights, list[int]]:
    """A region of random items, some descended with a random weight left —
    as :class:`Weights` and as the per-item weights the reference walks."""
    opener = rng.randrange(0, 50)
    sizes = [
        rng.choice((1, 2, 40, 900, 3000, 9000)) for _ in range(rng.randrange(1, 60))
    ]
    ends = [opener + sum(sizes[: i + 1]) for i in range(len(sizes))]
    marks, closer = tuple(ends[:-1]), ends[-1]
    down = sorted(
        rng.sample(range(len(sizes)), rng.randrange(0, min(4, len(sizes)) + 1))
    )
    weights = list(sizes)
    shed = [0]
    for item in down:
        weights[item] = rng.randrange(1, sizes[item] + 1)
        shed.append(shed[-1] + sizes[item] - weights[item])
    return Weights(opener, closer, marks, down, shed), weights


@pytest.mark.parametrize("seed", range(400))
def test_runs_by_bisection_cut_where_the_item_walk_cuts(seed: int) -> None:
    """Cutting by bisection over the separators, with descended items' weights
    shed, picks exactly the separators the item-by-item walk picks."""
    rng = random.Random(seed)
    region, weights = _random_region(rng)
    target = rng.choice(
        (MIN_CHUNK / 2, MIN_CHUNK, 1.5 * MIN_CHUNK, 4000.5, 9000.0, 25000.0)
    )
    assert runs(target, region) == _greedy(target, weights, region.marks)
    assert region.before(len(region.marks) + 1) == sum(weights)
