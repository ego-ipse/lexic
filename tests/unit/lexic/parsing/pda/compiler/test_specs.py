"""Tests for lexic.parsing.pda.compiler.specs — the clone-compiler intermediate records.

Pins the field order and defaults of the NamedTuple vocabulary the clone
compiler builds and :mod:`lexic.parsing.pda.compiler.clones` re-exposes as its public
surface (behavioural assertions on their compiled contents live in
``test_clones``). Also pins that the re-export identity holds.
"""

from __future__ import annotations

from lexic.parsing.pda.compiler import clones
from lexic.parsing.pda.compiler.specs import (
    ArmSpec,
    CloneKey,
    CloneSpec,
    GroupSpec,
    IslandRef,
    ItemSpec,
    KTupleGate,
    PairGate,
    PeekGate,
    StopGate,
)
from lexic.parsing.pda.core.charsets import CharSet


def test_clone_key_is_name_then_tail():
    """A clone key is ``(name, tail)`` positionally and by field."""
    tail = CharSet.from_chars("ab")
    key = CloneKey("rule", tail)
    assert key.name == "rule"
    assert key.tail == tail
    assert tuple(key) == ("rule", tail)


def test_island_ref_defaults_to_non_fail():
    """An island ref is non-fail by default; ``fail=True`` marks a fail-island."""
    ref = IslandRef("x")
    assert ref.name == "x"
    assert ref.fail is False
    assert IslandRef("x", True).fail is True


def test_loop_gates_carry_their_payloads():
    """Each loop-gate NamedTuple exposes its payload by field name."""
    cs = CharSet.from_chars(",")
    assert StopGate(cs).charset == cs
    assert PairGate(frozenset({"fx"})).pairs == frozenset({"fx"})
    assert KTupleGate(((cs,),)).windows == ((cs,),)
    peek = PeekGate(cs, cs)
    assert (peek.w, peek.take) == (cs, cs)


def test_item_spec_field_order():
    """An item spec is ``(kind, payload, lo, hi, gate)`` in order."""
    cs = CharSet.from_chars("x")
    spec = ItemSpec("cc", cs, 1, None, StopGate(cs))
    assert (spec.kind, spec.payload, spec.lo, spec.hi) == ("cc", cs, 1, None)
    assert isinstance(spec.gate, StopGate)


def test_arm_spec_windows_and_peek_default_none():
    """An arm spec's ``windows``/``peek`` gate selectors default to ``None``."""
    first = CharSet.from_chars("a")
    arm = ArmSpec(first, ())
    assert arm.first == first
    assert arm.specs == ()
    assert arm.windows is None
    assert arm.peek is None


def test_group_spec_holds_arms_and_default():
    """A group spec is ``(arms, default)``."""
    arm = ArmSpec(CharSet.from_chars("a"), ())
    group = GroupSpec((arm,), None)
    assert group.arms == (arm,)
    assert group.default is None


def test_clone_spec_field_order():
    """A clone spec is ``(name, arms, default, fold, match_only)`` in order."""
    spec = CloneSpec("r", (), None, None, None, False)
    assert spec.name == "r"
    assert spec.arms == ()
    assert spec.default is None
    assert spec.fold is None
    assert spec.match_only is False


def test_clones_re_exports_the_spec_types():
    """The public compiler surface stays reachable through ``clones``."""
    for spec_type in (
        CloneKey,
        IslandRef,
        StopGate,
        PairGate,
        KTupleGate,
        PeekGate,
        ItemSpec,
        ArmSpec,
        GroupSpec,
        CloneSpec,
    ):
        assert getattr(clones, spec_type.__name__) is spec_type
