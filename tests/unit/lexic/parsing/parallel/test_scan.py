"""Tests for ``lexic.parsing.parallel.scan`` — the self-locating window scan.

The load-bearing property: windows scanned independently, rebased by an
O(windows) prefix sum, produce EXACTLY the offsets a single sequential
window produces. One window IS the sequential scan — same code path.
"""

from __future__ import annotations

from lexic.compile import parse_grammar
from lexic.grammars import GBNF_FLAVOUR
from lexic.parsing.parallel import Roles, Scanner, roles
from tests.unit.lexic.parsing.parallel.test_anchors import JSONISH

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
    scanner = Scanner(Roles((), frozenset()))
    window = scanner.window(DOC, 0, len(DOC))
    assert window == (0, 0, 0, ())
    assert not scanner.offsets([window])
