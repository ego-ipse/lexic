"""Unit tests for :mod:`lexic.parsing.pda.analysis.taxonomy` — the notes + gate store."""

import pytest

from lexic.exceptions import UnsupportedConstructError
from lexic.parsing.pda.analysis.taxonomy import Taxonomy
from lexic.parsing.pda.core.scanner import SG_MATCH, SG_SCAN, Recognizer, ScanGate


def _rec() -> Recognizer:
    """A trivial recognizer stand-in (identity-unstable across builds)."""
    return Recognizer((), {})


def test_taxonomy_seeds_empty():
    """A fresh taxonomy has empty note maps, fail set and gate families."""
    tax = Taxonomy()
    assert not tax.conflicts and not tax.demoted and not tax.fail
    assert not tax.arm_gates and not tax.loop_gates
    assert not tax.pn_arm_gates and not tax.pn_loop_gates
    assert not tax.struct_loop_gates


def test_gate_accessors_are_live_views_of_the_store():
    """Writes through the named accessors land in the one gate store."""
    tax = Taxonomy()
    tax.arm_gates["r"] = ((), ())
    tax.loop_gates[7] = ()
    assert tax.gates.arm == {"r": ((), ())}
    assert tax.gates.loop == {7: ()}


def test_store_struct_loop_accepts_equal_respecification():
    """Re-storing an identical spec (fresh recognizer object) is not a conflict."""
    tax = Taxonomy()
    tax.store_struct_loop(1, ScanGate(SG_MATCH, _rec(), (0,)))
    tax.store_struct_loop(1, ScanGate(SG_MATCH, _rec(), (0,)))
    assert tax.struct_loop_gates[1].kind == SG_MATCH


def test_store_struct_loop_raises_on_conflicting_spec():
    """A different spec under the same item identity is the opt-out tripwire."""
    tax = Taxonomy()
    tax.store_struct_loop(1, ScanGate(SG_MATCH, _rec(), (0,)))
    with pytest.raises(UnsupportedConstructError):
        tax.store_struct_loop(
            1, ScanGate(SG_SCAN, _rec(), (0,), (frozenset("x"), False))
        )
