"""Tests for ``lexic.parsing.parallel.discovery.scan`` — the self-locating window scan.

The load-bearing property: windows scanned independently, rebased by an
O(windows) prefix sum, produce EXACTLY the offsets a single sequential
window produces. One window IS the sequential scan — same code path.
"""

from __future__ import annotations

from lexic.compile import parse_grammar
from lexic.grammars import GBNF_FLAVOUR
from lexic.parsing.parallel import Roles, Scanner, roles
from lexic.parsing.parallel.discovery.scan import clustered
from lexic.parsing.parallel.roles import Terminator
from tests.unit.lexic.parsing.parallel.discovery.test_anchors import JSONISH

DOC = "{qaq: {qbq: {qcq: qdq}}, qeq: qfq, qgq: {qhq: qiq}}".replace("q", '"')


def _scanner() -> Scanner:
    return Scanner(roles(parse_grammar(JSONISH, GBNF_FLAVOUR)))


def test_windowed_offsets_equal_the_sequential_scan():
    """Any window count reproduces the one-window answer exactly."""
    scanner = _scanner()
    sequential = scanner.offsets([scanner.window(DOC, 0, len(DOC))], depth=1)
    assert sequential
    for n in (2, 3, 5):
        step = len(DOC) // n
        windows = [
            scanner.window(DOC, k * step, (k + 1) * step if k < n - 1 else len(DOC))
            for k in range(n)
        ]
        assert scanner.offsets(windows, depth=1) == sequential


def test_depth_selects_the_nesting_level():
    """Depth 1 sees the top-level commas; depth 2 the nested object's."""
    scanner = _scanner()
    window = scanner.window(DOC, 0, len(DOC))
    top = scanner.offsets([window], depth=1)
    nested = scanner.offsets([window], depth=2)
    assert [DOC[o] for o in top + nested] == [","] * (len(top) + len(nested))
    assert set(top).isdisjoint(nested)


def test_a_window_reports_its_own_floor():
    """A window that starts inside nesting pops below its relative zero."""
    scanner = _scanner()
    closing = DOC.rindex("}")
    window = scanner.window(DOC, closing, len(DOC))
    assert window.floor < 0
    assert window.delta < 0


def test_empty_roles_scan_nothing():
    """No role chars → no pattern, no marks, no offsets — an answer."""
    scanner = Scanner(Roles((), ()))
    window = scanner.window(DOC, 0, len(DOC))
    assert window == (0, 0, 0, 0, ())
    assert not scanner.offsets([window])


def test_marks_carry_segment_floors():
    """A mark's segment floor records the dip since the previous mark — the
    guard telling two same-depth marks in DIFFERENT containers apart."""
    scanner = _scanner()
    window = scanner.window(DOC, 0, len(DOC))
    top = [mark for mark in window.marks if mark[1] == 1]
    dipped = [mark for mark in top if mark[2] < 1]
    assert dipped, "a top-level mark after the nested object must record the dip"


# ── multi-character marks ─────────────────────────────────────────────────


def _mark_scanner(*marks: str) -> Scanner:
    """A scanner whose only roles are the given mark spellings."""
    return Scanner(Roles((), (), tuple(Terminator(m, "root", "u") for m in marks)))


def test_a_spelling_straddling_a_window_boundary_is_found_exactly_once():
    """A mark STARTS inside its window however far past the end it reaches, so
    an arithmetic boundary landing mid-spelling neither loses it nor doubles
    it — the windowed scan still equals the one-window answer."""
    scanner = _mark_scanner("\n\n")
    text = "aaa\n\nbbb\n\nccc\n\nddd"
    whole = scanner.offsets([scanner.window(text, 0, len(text))])
    assert whole == [3, 8, 13]
    for cut in range(1, len(text)):
        split = [scanner.window(text, 0, cut), scanner.window(text, cut, len(text))]
        assert scanner.offsets(split) == whole, cut


def test_overlapping_occurrences_thin_to_one_boundary_per_run():
    """``"\\n\\n\\n\\n"`` reads three occurrences and the grammar has ONE
    boundary in it. Which end it stands at is the plan's static answer; either
    way no two boundaries are adjacent and no piece can be empty."""
    marks = [0, 1, 2, 7, 9, 10]
    assert clustered(marks, 2, trailing=False) == [0, 7, 9]
    assert clustered(marks, 2, trailing=True) == [2, 7, 10]


def test_a_one_character_mark_thins_to_itself():
    """One character never overlaps, so every occurrence is its own run and
    the filter is the identity — the strict-extension guarantee at the scan."""
    marks = [0, 1, 2, 7, 9, 10]
    assert clustered(marks, 1, trailing=False) == marks
    assert clustered(marks, 1, trailing=True) == marks
