"""Borg and Singleton metaclasses — shared-state and single-instance semantics."""

from __future__ import annotations

import gc
import threading
import weakref

import pytest

from lexic.ir.meta import Borg, Singleton

# ── Borg: identity and shared state ────────────────────────────────────


def test_borg_dict_instances_are_distinct_objects():
    """Test that Borg returns separate objects rather than one cached instance."""

    class C(metaclass=Borg):
        def __init__(self, value=None):
            self.value = value

    assert C("a") is not C("a")


def test_borg_slots_instances_are_distinct_objects():
    """Test that distinct objects also hold for slotted Borg classes."""

    class C(metaclass=Borg):
        __slots__ = ("value",)

        def __init__(self, value=None):
            self.value = value

    assert C("a") is not C("a")


def test_borg_dict_state_is_shared_live():
    """Test that mutating one dict-backed Borg instance is visible through another."""

    class C(metaclass=Borg):
        def __init__(self, value=None):
            self.value = value

    a, b = C("a"), C("a")
    b.value = "changed"
    assert a.value == "changed"


def test_borg_slots_state_is_shared_live():
    """Test that mutating one slotted Borg instance is visible through another."""

    class C(metaclass=Borg):
        __slots__ = ("value",)

        def __init__(self, value=None):
            self.value = value

    a, b = C("a"), C("a")
    b.value = "changed"
    assert a.value == "changed"


# ── Borg: newest construction wins ─────────────────────────────────────


def test_borg_dict_newest_construction_overwrites_state():
    """Test that a later dict-backed construction overwrites the shared state."""

    class C(metaclass=Borg):
        def __init__(self, value=None):
            self.value = value

    a, b = C("a"), C("b")
    assert a.value == b.value == "b"


def test_borg_slots_newest_construction_overwrites_state():
    """Test that a later slotted construction overwrites the shared state."""

    class C(metaclass=Borg):
        __slots__ = ("value",)

        def __init__(self, value=None):
            self.value = value

    a, b = C("a"), C("b")
    assert a.value == b.value == "b"


# ── Borg: slot mechanics ───────────────────────────────────────────────


def test_borg_slots_are_rewritten_into_properties():
    """Test that first construction converts every slot into a shared-state property."""

    class C(metaclass=Borg):
        __slots__ = ("value",)

        def __init__(self, value=None):
            self.value = value

    C("x")
    assert isinstance(C.__dict__["value"], property)


def test_borg_slots_proxies_unset_slots():
    """Test that slots unset on first construction are still proxied and shareable."""

    class C(metaclass=Borg):
        __slots__ = ("a", "b")

        def __init__(self, a="a"):
            self.a = a

    x = C()
    assert isinstance(C.__dict__["b"], property)
    with pytest.raises(AttributeError):
        _ = x.b
    y = C()
    y.b = "shared"
    assert x.b == "shared"


def test_borg_slots_reject_unknown_attribute():
    """Test that assigning a non-slot attribute on a slotted Borg instance raises."""

    class C(metaclass=Borg):
        __slots__ = ("value",)

        def __init__(self, value=None):
            self.value = value

    x = C("x")
    with pytest.raises(AttributeError):
        x.other = "nope"  # type: ignore  Forcing error for test.


def test_borg_dict_shares_dynamically_added_attribute():
    """Test that an attribute added after construction is shared in dict mode."""

    class C(metaclass=Borg):
        def __init__(self, value=None):
            self.value = value

    a, b = C("a"), C("a")
    a.extra = "x"  # type: ignore  Adding attribute after construction.
    assert b.extra == "x"  # type: ignore


# ── Borg: isolation, reentrancy, lifetime ──────────────────────────────


def test_borg_state_is_isolated_per_class():
    """Test that two Borg classes keep independent shared state."""

    class A(metaclass=Borg):
        def __init__(self, value=None):
            self.value = value

    class B(metaclass=Borg):
        def __init__(self, value=None):
            self.value = value

    a, b = A("a"), B("b")
    a.value = "changed"
    assert b.value == "b"


def test_borg_reentrant_construction_does_not_deadlock():
    """Test that building a Borg instance inside another's __init__ does not deadlock."""
    done: list[int] = []

    def build() -> None:
        class Inner(metaclass=Borg):
            __slots__ = ("v",)

            def __init__(self, v=1):
                self.v = v

        class Outer(metaclass=Borg):
            __slots__ = ("inner",)

            def __init__(self):
                self.inner = Inner()

        done.append(Outer().inner.v)

    thread = threading.Thread(target=build, daemon=True)
    thread.start()
    thread.join(timeout=5)
    assert not thread.is_alive(), "reentrant Borg construction deadlocked"
    assert done == [1]


def test_borg_class_is_collectable_when_unreferenced():
    """Test that the weak registry lets a dropped Borg class be garbage-collected."""

    def make() -> weakref.ReferenceType:
        class Tmp(metaclass=Borg):
            __slots__ = ("v",)

            def __init__(self, v=1):
                self.v = v

        Tmp(1)
        return weakref.ref(Tmp)

    ref = make()
    gc.collect()
    assert ref() is None


# ── Singleton ──────────────────────────────────────────────────────────


def test_singleton_dict_returns_same_instance():
    """Test that a dict-backed Singleton returns one cached object for every call."""

    class S(metaclass=Singleton):
        def __init__(self, value=None):
            self.value = value

    assert S("x") is S("y")


def test_singleton_slots_returns_same_instance():
    """Test that a slotted Singleton returns one cached object for every call."""

    class S(metaclass=Singleton):
        __slots__ = ("value",)

        def __init__(self, value=None):
            self.value = value

    assert S("x") is S("y")


def test_singleton_ignores_constructor_args_after_first():
    """Test that later Singleton calls reuse the first instance and ignore new args."""

    class S(metaclass=Singleton):
        def __init__(self, value=None):
            self.value = value

    first = S("first")
    assert S("second") is first
    assert first.value == "first"


def test_singleton_is_isolated_per_class():
    """Test that distinct Singleton classes cache independent instances."""

    class A(metaclass=Singleton):
        def __init__(self):
            self.tag = "a"

    class B(metaclass=Singleton):
        def __init__(self):
            self.tag = "b"

    assert A() is not B()
    assert A().tag == "a"
    assert B().tag == "b"


def test_singleton_reentrant_construction_does_not_deadlock():
    """Test that building a Singleton inside another's __init__ does not deadlock."""
    done: list[int] = []

    def build() -> None:
        class Inner(metaclass=Singleton):
            __slots__ = ("v",)

            def __init__(self, v=1):
                self.v = v

        class Outer(metaclass=Singleton):
            __slots__ = ("inner",)

            def __init__(self):
                self.inner = Inner()

        done.append(Outer().inner.v)

    thread = threading.Thread(target=build, daemon=True)
    thread.start()
    thread.join(timeout=5)
    assert not thread.is_alive(), "reentrant Singleton construction deadlocked"
    assert done == [1]
