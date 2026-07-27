"""Borg and Singleton metaclasses — shared-state and single-instance semantics."""

from __future__ import annotations

import gc
import threading
import weakref
from abc import ABC, ABCMeta, abstractmethod
from concurrent.futures import ThreadPoolExecutor
from typing import Any

import pytest

from lexic.ir.spine.meta import Borg, IrMeta, IrSingleton, Singleton
from lexic.ir.spine.spine import IrSelf

# Module-level alias; avoids pylint losing track of Singleton as a value after
# nested function-local class definitions (``class X(metaclass=Singleton)``)
# confuse pylint's scope analysis in the reentrant test.
SingletonRef = Singleton


def class_state(cls: type) -> dict[str, Any]:
    """Return the shared state dict Borg keeps for ``cls`` (tests inspect internals)."""
    return Borg._states[cls][0]  # pylint: disable=protected-access


def class_lock(cls: type) -> threading.RLock:
    """Return the per-class lock Borg stored alongside ``cls``'s shared state."""
    return Borg._states[cls][1]  # pylint: disable=protected-access


def blocks_while_locked(lock: threading.RLock, action) -> bool:
    """Run ``action`` in a worker and report whether ``lock`` actually gates it.

    The main thread holds ``lock``, starts the worker, and checks that the
    worker — which has provably started — cannot finish while the lock is held,
    then *does* finish once it is released. A True result is positive proof that
    the action acquires this lock.
    """
    started, completed = threading.Event(), threading.Event()

    def run() -> None:
        started.set()
        action()
        completed.set()

    worker = threading.Thread(target=run, daemon=True)
    with lock:
        worker.start()
        assert started.wait(2), "worker never started"
        blocked = not completed.wait(0.2)
    worker.join(timeout=2)
    return blocked and completed.is_set()


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


def test_borg_slots_are_routed_to_shared_state():
    """Test that first construction installs locked routing on a slotted class."""

    class C(metaclass=Borg):  # pylint: disable=too-few-public-methods
        """Slotted Borg fixture: slot-to-routing verification."""

        __slots__ = ("value",)

        def __init__(self, value=None):
            self.value = value

    C("x")
    assert "__setattr__" in C.__dict__  # routing installed, not a per-slot property
    assert not isinstance(C.__dict__.get("value"), property)


def test_borg_slots_unset_slot_is_routed_and_shareable():
    """Test that a slot left unset on first construction is still routed and shareable."""

    class C(metaclass=Borg):  # pylint: disable=too-few-public-methods
        """Slotted Borg fixture: unset-slot routing verification."""

        __slots__ = ("a", "b")

        def __init__(self, a="a"):
            self.a = a

    x = C()
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


def test_borg_bare_string_slots_are_honoured():
    """Test that a bare-string ``__slots__`` is treated as one name, not per-character."""

    class C(metaclass=Borg):  # pylint: disable=too-few-public-methods
        """Slotted Borg fixture: ``__slots__`` declared as a bare string."""

        # pylint: disable=single-string-used-for-slots  # bare string IS the test subject
        __slots__ = "value"  # a single slot name, not the chars v,a,l,u,e

        def __init__(self, value=None):
            self.value = value

    x = C("a")
    assert x.value == "a"  # constructable: "value" is in the allowed set
    with pytest.raises(AttributeError):
        x.other = "nope"  # type: ignore  still a closed set


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


def test_borg_reentrant_same_class_construction_preserves_state():
    """Test that constructing the same class inside its own __init__ keeps every write.

    Publishing the state before the first construction means the inner call takes
    the overwrite path against the *same* shared state; without that, the outer
    registration would re-publish a stale state and drop writes made after the
    re-entrant call (here, ``b``).
    """

    class C(metaclass=Borg):  # pylint: disable=too-few-public-methods
        """Slotted Borg fixture: re-entrant same-class construction."""

        __slots__ = ("a", "b")

        def __init__(self, reenter=False):
            self.a = "a"
            if reenter:
                C(reenter=False)  # second construction of the same class
            self.b = "b"

    x = C(reenter=True)
    assert x.a == "a"
    assert x.b == "b"  # the post-reentry write is not lost


def test_borg_first_construction_failure_does_not_wedge_class():
    """Test that a raising first __init__ leaves the class usable, not half-registered."""

    class C(metaclass=Borg):  # pylint: disable=too-few-public-methods
        """Slotted Borg fixture: first construction raises."""

        __slots__ = ("value",)

        def __init__(self, value=None, boom=False):
            if boom:
                raise RuntimeError("boom")
            self.value = value

    with pytest.raises(RuntimeError):
        C(boom=True)

    a, b = C("ok"), C("ok")  # class recovers; state is shared and live
    b.value = "shared"
    assert a.value == "shared"


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


# ── Borg: per-class lock and routed dict mutation ──────────────────────


def test_borg_classes_have_independent_locks():
    """Test that each Borg class gets its own lock, not a shared global one."""

    class A(metaclass=Borg):  # pylint: disable=too-few-public-methods
        """First slotted Borg fixture for per-class-lock isolation."""

        __slots__ = ("v",)

        def __init__(self, v=0):
            self.v = v

    class B(metaclass=Borg):  # pylint: disable=too-few-public-methods
        """Second slotted Borg fixture for per-class-lock isolation."""

        __slots__ = ("v",)

        def __init__(self, v=0):
            self.v = v

    A()
    B()
    assert class_lock(A) is not class_lock(B)


def test_borg_dict_routing_empties_instance_dict():
    """Test that a dict-backed instance holds no own state — it lives in the locked store."""

    class C(metaclass=Borg):  # pylint: disable=too-few-public-methods
        """Dict-backed Borg fixture: state routed out of the instance __dict__."""

        def __init__(self, value=None):
            self.value = value

    x = C("a")
    assert x.__dict__ == {}
    assert x.value == "a"  # still readable, via the routed __getattr__


def test_borg_dict_delattr_is_shared():
    """Test that deleting a routed attribute removes it from the shared state for all instances."""

    class C(metaclass=Borg):  # pylint: disable=too-few-public-methods
        """Dict-backed Borg fixture: shared __delattr__ routing."""

        def __init__(self, value=None):
            self.value = value

    a, b = C("a"), C("a")
    del a.value
    with pytest.raises(AttributeError):
        _ = b.value


# ── Borg: lock genuinely gates every access ────────────────────────────


def test_borg_slots_setattr_serialises_on_lock():
    """Test that a slotted proxy setter blocks while the per-class lock is held."""

    class C(metaclass=Borg):  # pylint: disable=too-few-public-methods
        """Slotted Borg fixture: setter-serialisation proof."""

        __slots__ = ("value",)

        def __init__(self, value=None):
            self.value = value

    x = C("a")

    def mutate() -> None:
        x.value = "threaded"

    assert blocks_while_locked(class_lock(C), mutate)
    assert x.value == "threaded"


def test_borg_slots_getattr_serialises_on_lock():
    """Test that a slotted proxy getter blocks while the per-class lock is held."""

    class C(metaclass=Borg):  # pylint: disable=too-few-public-methods
        """Slotted Borg fixture: getter-serialisation proof."""

        __slots__ = ("value",)

        def __init__(self, value=None):
            self.value = value

    x = C("a")
    seen: list[object] = []
    assert blocks_while_locked(class_lock(C), lambda: seen.append(x.value))
    assert seen == ["a"]


def test_borg_dict_setattr_serialises_on_lock():
    """Test that a dict-backed routed setter blocks while the per-class lock is held."""

    class C(metaclass=Borg):  # pylint: disable=too-few-public-methods
        """Dict-backed Borg fixture: routed-setter serialisation proof."""

        def __init__(self, value=None):
            self.value = value

    x = C("a")

    def mutate() -> None:
        x.value = "threaded"

    assert blocks_while_locked(class_lock(C), mutate)
    assert x.value == "threaded"


def test_borg_dict_getattr_serialises_on_lock():
    """Test that a dict-backed routed getter blocks while the per-class lock is held."""

    class C(metaclass=Borg):  # pylint: disable=too-few-public-methods
        """Dict-backed Borg fixture: routed-getter serialisation proof."""

        def __init__(self, value=None):
            self.value = value

    x = C("a")
    seen: list[object] = []
    assert blocks_while_locked(class_lock(C), lambda: seen.append(x.value))
    assert seen == ["a"]


def test_borg_overwrite_serialises_on_lock():
    """Test that a second construction (the overwrite path) blocks on the per-class lock."""

    class C(metaclass=Borg):  # pylint: disable=too-few-public-methods
        """Dict-backed Borg fixture: overwrite-serialisation proof."""

        def __init__(self, value=None):
            self.value = value

    C("a")  # first construction registers the class and its lock
    built: list[object] = []
    assert blocks_while_locked(class_lock(C), lambda: built.append(C("b").value))
    assert built == ["b"]


def test_borg_slots_overwrite_reenters_lock_without_deadlock():
    """Test that overwrite holding the lock while __init__'s setter reacquires it does not deadlock.

    ``_overwrite`` holds the per-class lock across construction, and the slot
    proxy setter invoked from ``__init__`` reacquires the same lock. A plain
    (non-reentrant) ``Lock`` would deadlock here; the ``RLock`` must not.
    """

    class C(metaclass=Borg):  # pylint: disable=too-few-public-methods
        """Slotted Borg fixture: reentrant-overwrite proof."""

        __slots__ = ("value",)

        def __init__(self, value=None):
            self.value = value

    C("a")  # register
    done: list[object] = []

    def build() -> None:
        done.append(C("b").value)  # exercises the overwrite path

    thread = threading.Thread(target=build, daemon=True)
    thread.start()
    thread.join(timeout=2)
    assert not thread.is_alive(), "reentrant overwrite deadlocked on the per-class lock"
    assert done == ["b"]


def test_borg_concurrent_construction_and_mutation_is_consistent():
    """Test that many threads constructing and mutating one Borg class never corrupt its state."""

    class C(metaclass=Borg):  # pylint: disable=too-few-public-methods
        """Slotted Borg fixture: concurrency stress."""

        __slots__ = ("value",)

        def __init__(self, value=0):
            self.value = value

    C(0)  # register before the threads race

    def worker(tag: int) -> None:
        for _ in range(500):
            inst = C(tag)
            inst.value = tag
            _ = inst.value

    with ThreadPoolExecutor(max_workers=8) as pool:
        futures = [pool.submit(worker, n) for n in range(8)]
    for future in futures:
        future.result()  # re-raises any exception raised in a worker

    final_value = class_state(C)["value"]
    assert final_value in range(8)  # whichever writer last won — never torn


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
    assert issubclass(IrSingleton, SingletonRef)


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


# ── IrMeta: the "init" class keyword (static-only dataclass_transform param) ──


def test_irmeta_class_creation_with_init_false_succeeds():
    """Test that declaring `init=False` on an IrMeta class does not raise."""

    class C(metaclass=IrMeta, init=False):  # pylint: disable=too-few-public-methods
        """IrMeta fixture: init=False class-keyword succeeds."""

    assert getattr(C, "__slots__") == ()


def test_irmeta_init_keyword_does_not_leak_to_init_subclass():
    """Test that `init` is popped in IrMeta.__new__ before __init_subclass__ runs."""
    seen: dict[str, object] = {}

    class Base(metaclass=IrMeta):  # pylint: disable=too-few-public-methods
        """IrMeta fixture: records kwargs forwarded to __init_subclass__."""

        def __init_subclass__(cls, **kwargs: object) -> None:
            seen.update(kwargs)
            super().__init_subclass__()

    class Sub(Base, init=False):  # pylint: disable=too-few-public-methods
        """IrMeta fixture: subclass declared with init=False."""

    assert issubclass(Sub, Base)
    assert "init" not in seen


def test_irmeta_normal_class_keyword_still_forwards():
    """Test that a genuine class keyword (not `init`) still reaches __init_subclass__."""
    seen: dict[str, object] = {}

    class Base(metaclass=IrMeta):  # pylint: disable=too-few-public-methods
        """IrMeta fixture: records kwargs forwarded to __init_subclass__."""

        def __init_subclass__(cls, **kwargs: object) -> None:
            seen.update(kwargs)
            super().__init_subclass__()

    class Sub(Base, tag="marked"):  # pylint: disable=too-few-public-methods
        """IrMeta fixture: subclass declared with a normal class keyword."""

    assert issubclass(Sub, Base)
    assert seen == {"tag": "marked"}


def test_bare_singleton_conflicts_on_irself_subclass():
    """Test that a bare Singleton metaclass raises TypeError on an IrSelf subclass.

    ``IrSelf`` already has ``IrMeta`` as its metaclass; ``Singleton`` does not
    subclass ``IrMeta``, so Python's metaclass-conflict rule fires.
    """
    with pytest.raises(TypeError):
        SingletonRef("Bad", (IrSelf,), {})
