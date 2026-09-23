"""Tests for ``lexic.parsing.parallel.partition`` — which spans to divide.

The partition packs a span's adjacent items into runs of about one worker's
share, descends into an item too big for one, and renders every piece and the
shell with the stand-ins of the spans divided inside them. The region scan
supplies the spans here; the partition itself never reads a bracket.
"""

from __future__ import annotations

from lexic.grammars.json import JSON_GRAMMAR
from lexic.parsing.parallel import MIN_CHUNK
from lexic.parsing.parallel.discovery.regions import Region, find
from lexic.parsing.parallel.partition import Division, partition, render, units

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
    """The object's one big member holds the array: the array is divided four
    ways, and the object — on the path — is divided too, whole, so the piece
    holding the array's stand-in is found by item."""
    doc = '{"a": [' + _run(20000) + '], "b": 1}'
    picked = partition(doc, find(JSON_GRAMMAR, doc), 4)
    assert [(d.region.rule, len(d.cuts)) for d in picked] == [
        ("object", 0),
        ("array", 3),
    ]


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
