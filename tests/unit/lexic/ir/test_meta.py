"""Borg and Singleton metaclasses — shared-state and single-instance semantics."""

from __future__ import annotations

import gc
import threading
import weakref
from abc import ABC, ABCMeta, abstractmethod

import pytest

from lexic.ir.base import IrSelf
from lexic.ir.meta import Borg, IrMeta, IrSingleton, Singleton

# Module-level alias; avoids pylint losing track of Singleton as a value after
# nested function-local class definitions (``class X(metaclass=Singleton)``)
# confuse pylint's scope analysis in the reentrant test.
_Singleton = Singleton

# ── Borg: identity and shared state ────────────────────────────────────


def test_borg_dict_instances_are_distinct_objects():
    """Test that Borg returns separate objects rather than one cached instance."""

    class C(metaclass=Borg):  # pylint: disable=too-few-public-methods
        """Dict-backed Borg fixture: distinct objects, shared state."""

        def __init__(self, value=None):
            self.value = value

    assert C("a") is not C("a")


def test_borg_slots_instances_are_distinct_objects():
    """Test that distinct objects also hold for slotted Borg classes."""

    class C(metaclass=Borg):  # pylint: disable=too-few-public-methods
        """Slotted Borg fixture: distinct objects, shared state."""

        __slots__ = ("value",)

        def __init__(self, value=None):
            self.value = value

    assert C("a") is not C("a")


def test_borg_dict_state_is_shared_live():
    """Test that mutating one dict-backed Borg instance is visible through another."""

    class C(metaclass=Borg):  # pylint: disable=too-few-public-methods
        """Dict-backed Borg fixture for shared-state mutation test."""

        def __init__(self, value=None):
            self.value = value

    a, b = C("a"), C("a")
    b.value = "changed"
    assert a.value == "changed"


def test_borg_slots_state_is_shared_live():
    """Test that mutating one slotted Borg instance is visible through another."""

    class C(metaclass=Borg):  # pylint: disable=too-few-public-methods
        """Slotted Borg fixture for shared-state mutation test."""

        __slots__ = ("value",)

        def __init__(self, value=None):
            self.value = value

    a, b = C("a"), C("a")
    b.value = "changed"
    assert a.value == "changed"


# ── Borg: newest construction wins ─────────────────────────────────────


def test_borg_dict_newest_construction_overwrites_state():
    """Test that a later dict-backed construction overwrites the shared state."""

    class C(metaclass=Borg):  # pylint: disable=too-few-public-methods
        """Dict-backed Borg fixture: newest-wins state overwrite."""

        def __init__(self, value=None):
            self.value = value

    a, b = C("a"), C("b")
    assert a.value == b.value == "b"


def test_borg_slots_newest_construction_overwrites_state():
    """Test that a later slotted construction overwrites the shared state."""

    class C(metaclass=Borg):  # pylint: disable=too-few-public-methods
        """Slotted Borg fixture: newest-wins state overwrite."""

        __slots__ = ("value",)

        def __init__(self, value=None):
            self.value = value

    a, b = C("a"), C("b")
    assert a.value == b.value == "b"


# ── Borg: slot mechanics ───────────────────────────────────────────────


def test_borg_slots_are_rewritten_into_properties():
    """Test that first construction converts every slot into a shared-state property."""

    class C(metaclass=Borg):  # pylint: disable=too-few-public-methods
        """Slotted Borg fixture: slot-to-property rewrite verification."""

        __slots__ = ("value",)

        def __init__(self, value=None):
            self.value = value

    C("x")
    assert isinstance(C.__dict__["value"], property)


def test_borg_slots_proxies_unset_slots():
    """Test that slots unset on first construction are still proxied and shareable."""

    class C(metaclass=Borg):  # pylint: disable=too-few-public-methods
        """Slotted Borg fixture: unset-slot proxy verification."""

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

    class C(metaclass=Borg):  # pylint: disable=too-few-public-methods
        """Slotted Borg fixture: unknown-attribute rejection."""

        __slots__ = ("value",)

        def __init__(self, value=None):
            self.value = value

    x = C("x")
    with pytest.raises(AttributeError):
        x.other = "nope"  # type: ignore  Forcing error for test.


def test_borg_dict_shares_dynamically_added_attribute():
    """Test that an attribute added after construction is shared in dict mode."""

    class C(metaclass=Borg):  # pylint: disable=too-few-public-methods
        """Dict-backed Borg fixture: dynamic-attribute sharing."""

        def __init__(self, value=None):
            self.value = value

    a, b = C("a"), C("a")
    a.extra = "x"  # type: ignore  Adding attribute after construction.
    assert b.extra == "x"  # type: ignore


# ── Borg: isolation, reentrancy, lifetime ──────────────────────────────


def test_borg_state_is_isolated_per_class():
    """Test that two Borg classes keep independent shared state."""

    class A(metaclass=Borg):  # pylint: disable=too-few-public-methods
        """First dict-backed Borg fixture for isolation test."""

        def __init__(self, value=None):
            self.value = value

    class B(metaclass=Borg):  # pylint: disable=too-few-public-methods
        """Second dict-backed Borg fixture for isolation test."""

        def __init__(self, value=None):
            self.value = value

    a, b = A("a"), B("b")
    a.value = "changed"
    assert b.value == "b"


def test_borg_reentrant_construction_does_not_deadlock():
    """Test that building a Borg instance inside another's __init__ does not deadlock."""
    done: list[int] = []

    def build() -> None:
        class Inner(metaclass=Borg):  # pylint: disable=too-few-public-methods
            """Slotted inner Borg fixture for reentrancy test."""

            __slots__ = ("v",)

            def __init__(self, v=1):
                self.v = v

        class Outer(metaclass=Borg):  # pylint: disable=too-few-public-methods
            """Slotted outer Borg fixture for reentrancy test."""

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
        class Tmp(metaclass=Borg):  # pylint: disable=too-few-public-methods
            """Slotted Borg fixture for garbage-collection test."""

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

    class S(metaclass=Singleton):  # pylint: disable=too-few-public-methods
        """Dict-backed Singleton fixture: same-instance verification."""

        def __init__(self, value=None):
            self.value = value

    assert S("x") is S("y")


def test_singleton_slots_returns_same_instance():
    """Test that a slotted Singleton returns one cached object for every call."""

    class S(metaclass=Singleton):  # pylint: disable=too-few-public-methods
        """Slotted Singleton fixture: same-instance verification."""

        __slots__ = ("value",)

        def __init__(self, value=None):
            self.value = value

    assert S("x") is S("y")


def test_singleton_ignores_constructor_args_after_first():
    """Test that later Singleton calls reuse the first instance and ignore new args."""

    class S(metaclass=Singleton):  # pylint: disable=too-few-public-methods
        """Dict-backed Singleton fixture: constructor-args-ignored test."""

        def __init__(self, value=None):
            self.value = value

    first = S("first")
    assert S("second") is first
    assert first.value == "first"


def test_singleton_is_isolated_per_class():
    """Test that distinct Singleton classes cache independent instances."""

    class A(metaclass=Singleton):  # pylint: disable=too-few-public-methods
        """First Singleton fixture for class-isolation test."""

        def __init__(self):
            self.tag = "a"

    class B(metaclass=Singleton):  # pylint: disable=too-few-public-methods
        """Second Singleton fixture for class-isolation test."""

        def __init__(self):
            self.tag = "b"

    assert A() is not B()
    assert A().tag == "a"
    assert B().tag == "b"


def test_singleton_reentrant_construction_does_not_deadlock():
    """Test that building a Singleton inside another's __init__ does not deadlock."""
    done: list[int] = []

    def build() -> None:
        class Inner(metaclass=Singleton):  # pylint: disable=too-few-public-methods
            """Slotted inner Singleton fixture for reentrancy test."""

            __slots__ = ("v",)

            def __init__(self, v=1):
                self.v = v

        class Outer(metaclass=Singleton):  # pylint: disable=too-few-public-methods
            """Slotted outer Singleton fixture for reentrancy test."""

            __slots__ = ("inner",)

            def __init__(self):
                self.inner = Inner()

        done.append(Outer().inner.v)

    thread = threading.Thread(target=build, daemon=True)
    thread.start()
    thread.join(timeout=5)
    assert not thread.is_alive(), "reentrant Singleton construction deadlocked"
    assert done == [1]


# ── IrMeta ─────────────────────────────────────────────────────────────


def test_irmeta_is_abcmeta_subclass():
    """Test that IrMeta derives from ABCMeta (composes with ABC bases)."""
    assert issubclass(IrMeta, ABCMeta)


def test_irmeta_injects_empty_slots_when_none_declared():
    """Test that a class with no __slots__ declaration gets __slots__ == ()."""

    class C(metaclass=IrMeta):  # pylint: disable=too-few-public-methods
        """IrMeta fixture: empty-slots injection when none declared."""

    assert getattr(C, "__slots__") == ()


def test_irmeta_no_dict_on_plain_class():
    """Test that an IrMeta class with no __slots__ has no __dict__ on instances."""

    class C(metaclass=IrMeta):  # pylint: disable=too-few-public-methods
        """IrMeta fixture: no-__dict__ verification."""

    c = C()
    with pytest.raises(AttributeError):
        setattr(c, "x", "nope")


def test_irmeta_preserves_declared_slots():
    """Test that setdefault does not clobber an explicit __slots__ declaration."""

    class C(metaclass=IrMeta):  # pylint: disable=too-few-public-methods
        """IrMeta fixture: explicit __slots__ preserved."""

        __slots__ = ("x",)

        def __init__(self) -> None:
            """Initialise ``x`` via the declared slot."""
            self.x = 42

    c = C()
    assert c.x == 42


def test_irmeta_non_slot_attribute_raises_on_slotted_class():
    """Test that setting a non-slot attribute on a slotted IrMeta class raises."""

    class C(metaclass=IrMeta):  # pylint: disable=too-few-public-methods
        """IrMeta fixture: non-slot attribute rejected."""

        __slots__ = ("x",)

    c = C()
    with pytest.raises(AttributeError):
        setattr(c, "y", "nope")


def test_irmeta_composes_with_abc_abstractmethod():
    """Test that IrMeta composes with ABC: abstract class cannot be instantiated."""

    class Base(ABC, metaclass=IrMeta):  # pylint: disable=too-few-public-methods
        """Abstract IrMeta fixture: must not be directly instantiated."""

        @abstractmethod
        def run(self) -> int:
            """Return an integer result."""

    class Concrete(Base):  # pylint: disable=too-few-public-methods
        """Concrete subclass implementing the abstract method."""

        def run(self) -> int:
            return 1

    with pytest.raises(TypeError):
        Base()  # type: ignore[abstract]

    assert Concrete().run() == 1


# ── IrSingleton ────────────────────────────────────────────────────────


def test_irsingleton_is_irmeta_subclass():
    """Test that IrSingleton inherits from IrMeta."""
    assert issubclass(IrSingleton, IrMeta)


def test_irsingleton_is_singleton_subclass():
    """Test that IrSingleton inherits from Singleton."""
    assert issubclass(IrSingleton, _Singleton)


def test_irsingleton_returns_same_instance():
    """Test that an IrSingleton class returns one cached instance for every call."""

    class C(metaclass=IrSingleton):  # pylint: disable=too-few-public-methods
        """IrSingleton fixture: one-instance-per-class verification."""

    assert C() is C()


def test_irsingleton_later_calls_ignore_args():
    """Test that later IrSingleton calls reuse the first instance, ignoring new args."""

    class S(metaclass=IrSingleton):  # pylint: disable=too-few-public-methods
        """IrSingleton fixture: later constructor arguments are discarded."""

    first = S()
    assert S() is first


def test_irsingleton_instances_are_isolated_per_class():
    """Test that two distinct IrSingleton classes cache independent instances."""

    class A(metaclass=IrSingleton):  # pylint: disable=too-few-public-methods
        """First IrSingleton fixture for class-isolation test."""

    class B(metaclass=IrSingleton):  # pylint: disable=too-few-public-methods
        """Second IrSingleton fixture for class-isolation test."""

    assert A() is not B()


def test_irsingleton_injects_empty_slots():
    """Test that IrMeta's slots injection applies to IrSingleton classes too."""

    class C(metaclass=IrSingleton):  # pylint: disable=too-few-public-methods
        """IrSingleton fixture: empty-slots injection verification."""

    assert getattr(C, "__slots__") == ()
    c = C()
    with pytest.raises(AttributeError):
        setattr(c, "x", "nope")


def test_irsingleton_composes_on_irself_subclass():
    """Test that IrSingleton can be the metaclass of an IrSelf subclass without conflict."""

    class S(IrSelf, metaclass=IrSingleton):  # pylint: disable=too-few-public-methods
        """IrSelf subclass using IrSingleton — the actual production use-case."""

        def __repr__(self) -> str:
            return "S()"

    assert S() is S()


def test_bare_singleton_conflicts_on_irself_subclass():
    """Test that a bare Singleton metaclass raises TypeError on an IrSelf subclass.

    ``IrSelf`` already has ``IrMeta`` as its metaclass; ``Singleton`` does not
    subclass ``IrMeta``, so Python's metaclass-conflict rule fires.
    """
    with pytest.raises(TypeError):
        _Singleton("Bad", (IrSelf,), {})
