"""Tests for ``lexic.parsing.parallel.discovery.scan`` — the structural scan.

The property these tests defend: the depth at any offset is a count, so a
stretch scanned on its own, from the depth counted at its start, reports
EXACTLY the depth-0 marks the whole-document scan reports inside it.
"""

from __future__ import annotations

from lexic.compile import compile_text, parse_grammar
from lexic.grammars import GBNF_FLAVOUR
from lexic.parsing.parallel import Roles, Scanner, roles
from lexic.parsing.parallel.discovery.scan import occurrences, spelling_offsets
from lexic.parsing.parallel.roles.derive import Terminator
from tests.split_helpers import TWO_ROLE_PAIRS
from tests.unit.lexic.parsing.parallel.discovery.test_anchors import JSONISH

DOC = "{qaq: {qbq: {qcq: qdq}}, qeq: qfq, qgq: {qhq: qiq}}".replace("q", '"')


def _scanner() -> Scanner:
    return Scanner(roles(parse_grammar(JSONISH, GBNF_FLAVOUR)))


def _stretched(scanner: Scanner, text: str, bounds: list[int], base: int) -> list[int]:
    """The level read stretch by stretch, each from the depth counted at its start."""
    return [
        at
        for lo, hi in zip(bounds, bounds[1:])
        for at in scanner.level(text, lo, hi, base + scanner.drift(text, 0, lo))
    ]


def test_stretches_from_counted_depths_equal_the_sequential_scan():
    """Any division into stretches reproduces the whole-document answer."""
    scanner = _scanner()
    sequential = scanner.level(DOC, 0, len(DOC), -1)
    assert sequential
    for n in (2, 3, 5):
        step = len(DOC) // n
        bounds = [k * step for k in range(n)] + [len(DOC)]
        assert _stretched(scanner, DOC, bounds, -1) == sequential


def test_the_base_selects_the_nesting_level():
    """Starting a level at depth -1 reads the top-level commas; at -2 the
    nested objects' — the same pass, asked from a different depth."""
    scanner = _scanner()
    top = scanner.level(DOC, 0, len(DOC), -1)
    nested = scanner.level(DOC, 0, len(DOC), -2)
    assert [DOC[o] for o in top + nested] == [","] * (len(top) + len(nested))
    assert set(top).isdisjoint(nested)
    assert top == [
        DOC.index(", ", DOC.index("}}")),
        DOC.index(", ", DOC.index("qfq".replace("q", '"'))),
    ]


def test_a_stretch_starting_inside_nesting_drifts_below_zero():
    """A stretch that opens inside nesting closes more than it opens."""
    scanner = _scanner()
    closing = DOC.rindex("}")
    assert scanner.drift(DOC, closing, len(DOC)) == -1
    assert scanner.drift(DOC, 0, len(DOC)) == 0
    assert scanner.drift(DOC, 0, closing) == 1


def test_empty_roles_scan_nothing():
    """No role chars → no marks and no depth — an answer, not a failure."""
    scanner = Scanner(Roles((), ()))
    assert scanner.level(DOC, 0, len(DOC), 0) == []
    assert scanner.drift(DOC, 0, len(DOC)) == 0


def test_a_count_over_a_longer_spelling_counts_its_overlaps():
    """``str.count`` would read ``"aaa"`` as one ``"aa"``; the depth must count
    every START, as the walk does, or a stretch's base drifts off its marks."""
    assert occurrences("aaa", "aa", 0, 3) == 2
    assert occurrences("aaa", "a", 0, 3) == 3
    assert occurrences("aaa", "aa", 1, 3) == 1


def test_a_character_closing_one_pair_and_opening_another_is_never_counted():
    """``|`` closes ``angle`` and opens ``bar``; a count would move it by zero
    where the depth moves by one, reading the bar's own commas at depth 0. No
    such pair stands, so the scan counts no depth there at all — and the
    separator plan's own safety proof has to decide, before any cut."""
    scanner = Scanner(roles(compile_text(TWO_ROLE_PAIRS).codegen_grammar))
    assert not scanner.openers
    assert not scanner.closers


# ── multi-character marks ─────────────────────────────────────────────────


def _mark_scanner(*marks: str) -> Scanner:
    """A scanner whose only roles are the given mark spellings."""
    return Scanner(
        Roles((), (), tuple(Terminator(frozenset({m}), "root", "u") for m in marks))
    )


def test_a_spelling_straddling_a_stretch_boundary_is_found_exactly_once():
    """A mark STARTS inside its stretch however far past the end it reaches, so
    a boundary landing mid-spelling neither loses it nor doubles it — the
    stretched scan still equals the whole-document answer."""
    scanner = _mark_scanner("\n\n")
    text = "aaa\n\nbbb\n\nccc\n\nddd"
    whole = scanner.level(text, 0, len(text), 0)
    assert whole == [3, 8, 13]
    for cut in range(1, len(text)):
        assert _stretched(scanner, text, [0, cut, len(text)], 0) == whole, cut


def test_occurrences_finds_a_mark_starting_at_the_windows_last_offset():
    """A spelling whose FIRST character stands at the window's very last
    valid starting offset is still found whole, however far past ``hi`` its
    remaining characters reach — the property that makes it safe to search
    past the window end by the spelling's own width."""
    text = "a\n\nb"
    assert spelling_offsets(text, "\n\n", 0, 2) == [1]


def test_occurrences_belongs_to_the_window_it_starts_in_not_the_next():
    """The same occurrence is NOT found again by the window it merely spills
    into: ownership is decided once, by where the spelling STARTS, so a
    window scanning ``[2, 4)`` never rediscovers the mark that started at 1."""
    text = "a\n\nb"
    assert not spelling_offsets(text, "\n\n", 2, 4)
