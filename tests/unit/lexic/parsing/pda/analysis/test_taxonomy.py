"""Unit tests for :mod:`lexic.parsing.pda.analysis.taxonomy` — the notes + gate store."""

import pytest

from lexic.exceptions import UnsupportedConstructError
from lexic.parsing.pda.analysis.taxonomy import AttemptSpec, Taxonomy
from lexic.parsing.pda.core.charsets import CharSet
from lexic.parsing.pda.core.scanner import SG_MATCH, SG_SCAN, Recognizer, ScanGate


def rec() -> Recognizer:
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
    tax.store_struct_loop(1, ScanGate(SG_MATCH, rec(), (0,)))
    tax.store_struct_loop(1, ScanGate(SG_MATCH, rec(), (0,)))
    assert tax.struct_loop_gates[1].kind == SG_MATCH


def test_store_struct_loop_raises_on_conflicting_spec():
    """A different spec under the same item identity is the opt-out tripwire."""
    tax = Taxonomy()
    tax.store_struct_loop(1, ScanGate(SG_MATCH, rec(), (0,)))
    with pytest.raises(UnsupportedConstructError):
        tax.store_struct_loop(
            1, ScanGate(SG_SCAN, rec(), (0,), (frozenset("x"), False))
        )


def test_store_group_attempt_accepts_equal_respecification():
    """Re-storing the identical (order, follow) pair under one node id is not
    a conflict — the same shape the struct-loop and windows/peek tripwires
    already grant an equal re-store."""
    tax = Taxonomy()
    attempt = (AttemptSpec((0, 1)), CharSet.from_chars("d"))
    tax.store_group_attempt(1, attempt)
    tax.store_group_attempt(1, attempt)
    assert tax.grp_arm_gates[1] == (None, None, attempt)


def test_store_group_attempt_raises_on_conflicting_continuation():
    """One node, two decision points, different continuations.

    ``@lexical`` splices one body into several call sites, so the SAME
    ``IrAlternation`` node can stand at two of them with different soft
    continuations. A confident-wrong gate there would be silent, so a
    differing re-store refuses instead of overwriting.
    """
    tax = Taxonomy()
    tax.store_group_attempt(1, (AttemptSpec((0, 1)), CharSet.from_chars("d")))
    with pytest.raises(UnsupportedConstructError):
        tax.store_group_attempt(1, (AttemptSpec((0, 1)), CharSet.from_chars("z")))


def test_store_group_attempt_raises_on_conflicting_order_too():
    """A differing ORDER under the same node id is exactly as much a conflict
    as a differing follow set — the whole tuple is the identity."""
    tax = Taxonomy()
    follow = CharSet.from_chars("d")
    tax.store_group_attempt(1, (AttemptSpec((0, 1)), follow))
    with pytest.raises(UnsupportedConstructError):
        tax.store_group_attempt(1, (AttemptSpec((1, 0)), follow))
