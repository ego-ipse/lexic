"""Tests for tools.pylint_lexic — the two astroid transforms this repo installs.

Both PEP 695 transforms have a sharp edge. The scope one must unbind a ``type``
statement's parameters from module scope WITHOUT unbinding a real module-level
name that a function genuinely shadows. The named-tuple one must bind the
inherited members WITHOUT claiming them for a class that is not a named tuple.
Every direction is checked by running the real pylint over real source text,
because the defects being corrected live in the checker's own model and nothing
below it can observe the correction.
"""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[3]

_ALIAS_PARAM = '''"""A generic type alias beside a generic function — the false positive."""

type Alias[Carry] = list[Carry]


def free[Carry](value: Carry) -> Carry:
    """Return the value."""
    return value
'''

_REAL_SHADOW = '''"""A real module-level name a function parameter genuinely shadows."""

Carry = 1


def free(Carry: int) -> int:
    """Return the value."""
    return Carry
'''


def _lint(source: str, tmp_path: Path, name: str, enable: str) -> str:
    """Run one pylint check alone over ``source``, through the real plugin."""
    module = tmp_path / f"{name}.py"
    module.write_text(source, encoding="utf-8")
    done = subprocess.run(
        [
            sys.executable,
            "-m",
            "pylint",
            "--disable=all",
            f"--enable={enable}",
            str(module),
        ],
        cwd=_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    return done.stdout


def _w0621(source: str, tmp_path: Path, name: str) -> str:
    """Run pylint's redefined-outer-name check alone over ``source``."""
    module = tmp_path / f"{name}.py"
    module.write_text(source, encoding="utf-8")
    done = subprocess.run(
        [
            sys.executable,
            "-m",
            "pylint",
            "--disable=all",
            "--enable=W0621",
            str(module),
        ],
        cwd=_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    return done.stdout


def test_a_type_alias_parameter_is_not_a_module_level_name(tmp_path: Path):
    """A generic ``type`` alias does not make its parameter shadow anything.

    Without the transform this reports 'Redefining name Carry from outer scope',
    which the interpreter contradicts: the alias's parameter is not in the
    module namespace at all.
    """
    assert "W0621" not in _w0621(_ALIAS_PARAM, tmp_path, "alias_param")


def test_the_alias_parameter_really_is_absent_from_the_module_namespace(tmp_path: Path):
    """The runtime fact the transform is aligned to, asserted directly.

    Imported rather than executed: the interpreter's own module machinery is
    what binds a module's namespace, so importing the file is both the honest
    seam and the exact thing the transform models.
    """
    module = tmp_path / "runtime_scope.py"
    module.write_text(_ALIAS_PARAM, encoding="utf-8")
    spec = importlib.util.spec_from_file_location("runtime_scope", module)
    assert spec is not None and spec.loader is not None
    loaded = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(loaded)

    assert "Alias" in vars(loaded)
    assert "Carry" not in vars(loaded)


def test_a_real_module_level_name_is_still_reported_as_shadowed(tmp_path: Path):
    """The transform must not blind the checker to a genuine shadowing.

    This is the defect a too-broad transform would introduce: dropping every
    binding of a name that any alias also parameterises would silence a real
    finding elsewhere in the module.
    """
    assert "W0621" in _w0621(_REAL_SHADOW, tmp_path, "real_shadow")


@pytest.mark.parametrize(
    "source",
    [
        "type Plain = int\n",
        "type Alias[Carry] = list[Carry]\nCarry = 1\n",
    ],
)
def test_modules_the_transform_must_leave_alone_still_lint(source: str, tmp_path: Path):
    """A non-generic alias, and one whose parameter name is also a real global."""
    assert "E" not in _w0621(f'"""Doc."""\n\n{source}', tmp_path, "left_alone")


_GENERIC_NAMEDTUPLE = '''"""A generic named tuple reached through a generic factory."""

from typing import NamedTuple


class Two[T, U](NamedTuple):
    """Two parameters."""

    a: T
    b: U


def make[T, U](x: T, y: U) -> Two[T, U]:
    """Build one."""
    return Two(x, y)


def use() -> None:
    """Replace a field of one that arrived through the factory."""
    print(make(1, "a")._replace(a=2))
'''

_NOT_A_NAMEDTUPLE = '''"""A generic class that is not a named tuple at all."""


class Two[T, U]:
    """Two parameters, no named-tuple base."""

    def __init__(self, a: T) -> None:
        """Bind."""
        self.a = a


def use() -> None:
    """Reach for a member this class does not have."""
    print(Two(1)._replace(a=2))
'''


def test_a_generic_named_tuple_keeps_its_inherited_members(tmp_path: Path):
    """``_replace`` survives arriving through a generic factory's return.

    astroid supplies the named-tuple members through an inference tip that does
    not fire on that path, so without the transform this reports no-member for
    a method the interpreter resolves.
    """
    assert "E1101" not in _lint(_GENERIC_NAMEDTUPLE, tmp_path, "generic_nt", "E1101")


def test_the_members_are_not_granted_to_a_class_that_is_not_a_named_tuple(
    tmp_path: Path,
):
    """The transform must not hand ``_replace`` to every generic class.

    This is the defect a predicate keyed only on ``type_params`` would
    introduce: a real missing member would stop being reported.
    """
    assert "E1101" in _lint(_NOT_A_NAMEDTUPLE, tmp_path, "not_nt", "E1101")


_FIXTURE_CLASS = '''"""A metaclass exercised through a class built inside the test."""


class Meta(type):
    """The metaclass under test."""

    def __call__(cls, *args, **kwargs):
        """Build an instance."""
        return super().__call__(*args, **kwargs)


def test_the_metaclass():
    """Exercise it through a local fixture."""

    class C(metaclass=Meta):
        """One attribute, no public methods — whatever the assertion needs."""

        def __init__(self, value=None):
            self.value = value

    assert C("a").value == "a"
'''

_METHOD_GROUP = '''"""A mixin: one owner's methods, shed into a second file."""


class ExecutionMixin:
    """Method group over state the owner holds."""

    __slots__ = ()

    text: str
    pos: int

    def _run(self) -> int:
        """Do the private work."""
        return len(self.text) - self.pos
'''

_NAMED_LIKE_A_MIXIN = '''"""A class named like a mixin that holds its own state."""


class HolderMixin:
    """Holds a value of its own — a name is not a licence."""

    def __init__(self, value: int) -> None:
        """Bind the value."""
        self.value = value
'''

_GROUP_THAT_GAINED_STATE = '''"""A method group that grew a constructor."""


class ExecutionMixin:
    """No longer a method group: it owns what it reads."""

    __slots__ = ("text",)

    text: str

    def __init__(self, text: str) -> None:
        """Bind the text it used to expect from an owner."""
        self.text = text

    def _run(self) -> int:
        """Do the private work."""
        return len(self.text)
'''

_FINALIZER_MARKER = '''"""A sentinel whose whole interface is being finalizable."""


class Marker:
    """Nothing is read off it; it exists to be weakly referenceable."""

    __slots__ = ("__weakref__",)
'''

_MARKER_WITH_AN_INHERITED_INTERFACE = '''"""A marker whose BASE publishes the interface."""


class Published:
    """An ordinary class with a public method."""

    def read(self) -> int:
        """Publish something."""
        return 1


class Marker(Published):
    """Only slot is __weakref__, but the interface is inherited."""

    __slots__ = ("__weakref__",)
'''

_MARKER_WITH_A_STRING_SLOT = '''"""`__slots__` as a bare string is a legal single slot."""


class Marker:
    """Declares the weak-reference slot without a sequence."""

    __slots__ = "__weakref__"
'''

_FINALIZER_MARKER_WITH_METHOD = '''"""A finalizer marker that also publishes a public method."""


class Marker:
    """Weakly referenceable, but not silent: it has a public method."""

    __slots__ = ("__weakref__",)

    def ping(self) -> int:
        """Return a constant — a genuine public interface."""
        return 1
'''

_FINALIZER_MARKER_LIST_SLOTS = '''"""A finalizer marker declared with a list, not a tuple."""


class Marker:
    """Nothing is read off it; it exists to be weakly referenceable."""

    __slots__ = ["__weakref__"]
'''

_SLOTTED_HOLDER = '''"""A slotted class that does hold something."""


class Holder:
    """One ordinary slot — an abstraction with a thin interface."""

    __slots__ = ("value",)
'''

_MARKER_WITH_STATE = '''"""Weakly referenceable AND stateful — not a marker."""


class Both:
    """Declares the weak reference slot beside real state."""

    __slots__ = ("__weakref__", "value")
'''

_THIN_ABSTRACTION = '''"""A module-level class with a thin public interface."""


class Holder:
    """Holds a value and publishes nothing."""

    def __init__(self, value: int) -> None:
        """Bind the value."""
        self.value = value
'''


def test_a_fixture_class_is_not_an_abstraction_with_a_thin_interface(tmp_path: Path):
    """A class built inside a function is exercised, not depended on.

    Counting its public methods measures the assertion that owns it, which is
    why the checker's own exempt set — Enum, named tuple, TypedDict, dataclass
    — is the right place for it rather than a disable at every fixture.
    """
    assert "R0903" not in _lint(_FIXTURE_CLASS, tmp_path, "fixture_class", "R0903")


def test_a_method_group_publishes_nothing_by_design(tmp_path: Path):
    """A method group's interface is its owner's, and it is never built.

    Recognised by what it IS: no constructor, ``__slots__ = ()``, and instance
    attributes annotated but never assigned — state that belongs to whatever
    class inherits it.
    """
    assert "R0903" not in _lint(_METHOD_GROUP, tmp_path, "method_group", "R0903")


def test_a_finalizer_marker_publishes_nothing_by_design(tmp_path: Path):
    """A class whose only slot is ``__weakref__`` can hold nothing at all.

    Recognised by what it IS, never by a name: a slot list naming only the
    weak reference leaves no attribute to read, so the class exists solely to
    let an object's lifetime be observed. Declaring the slot is the whole
    mechanism — ``__slots__ = ()`` is not weakly referenceable.
    """
    assert "R0903" not in _lint(_FINALIZER_MARKER, tmp_path, "marker", "R0903")


def test_a_slotted_class_that_holds_something_still_counts(tmp_path: Path):
    """The exemption is about holding nothing, not about having slots."""
    assert "R0903" in _lint(_SLOTTED_HOLDER, tmp_path, "slotted_holder", "R0903")


def test_a_finalizer_marker_with_a_public_method_is_still_reported(tmp_path: Path):
    """A marker that publishes a method is not publishing nothing.

    The predicate's own licence is that the class "can hold nothing and
    publish nothing" — a slot list naming only the weak reference leaves no
    ATTRIBUTE to read. A method is not an attribute the slot list constrains,
    so a marker that grows one genuinely publishes an interface, and counting
    it is exactly what the message is for.
    """
    assert "R0903" in _lint(
        _FINALIZER_MARKER_WITH_METHOD, tmp_path, "marker_with_method", "R0903"
    )


def test_a_marker_that_inherits_an_interface_is_still_reported(tmp_path: Path):
    """`__slots__` constrains attributes and says nothing about a base.

    A class can declare the weak-reference slot and still publish a whole
    interface through what it derives from, so the slot list alone cannot
    license the exemption.
    """
    assert "R0903" in _lint(
        _MARKER_WITH_AN_INHERITED_INTERFACE, tmp_path, "marker_inherits", "R0903"
    )


def test_a_marker_declared_with_a_bare_string_is_exempt_too(tmp_path: Path):
    """``__slots__ = "__weakref__"`` declares the same one slot a tuple would.

    Reading only the sequence form would call a legal single-slot class
    slotless, and the predicate's licence is about what the class declares,
    not how the declaration is spelled.
    """
    assert "R0903" not in _lint(
        _MARKER_WITH_A_STRING_SLOT, tmp_path, "marker_string_slot", "R0903"
    )


def test_a_finalizer_marker_declared_with_a_list_is_exempt_too(tmp_path: Path):
    """`__slots__` spelled as a list reads the same names as a tuple would.

    The predicate reads the assigned value's `.elts`, which a `List` node
    carries exactly as a `Tuple` node does, so the exemption does not depend
    on which literal spells the one slot.
    """
    assert "R0903" not in _lint(
        _FINALIZER_MARKER_LIST_SLOTS, tmp_path, "marker_list_slots", "R0903"
    )


def test_a_weakly_referenceable_class_with_state_still_counts(tmp_path: Path):
    """Declaring ``__weakref__`` beside real state is not a marker.

    The narrow reading is the point: a class that can be finalized AND holds a
    value is an abstraction, and counting its interface means what it says.
    """
    assert "R0903" in _lint(_MARKER_WITH_STATE, tmp_path, "marker_state", "R0903")


def test_a_genuine_thin_abstraction_is_still_reported(tmp_path: Path):
    """The exemption must not blind the checker to the finding it exists for.

    This is the defect a blanket suppression would introduce: a module-level
    class with no public interface is exactly what the message is about, and it
    still arrives.
    """
    assert "R0903" in _lint(_THIN_ABSTRACTION, tmp_path, "thin_abstraction", "R0903")


def test_a_class_named_like_a_mixin_but_holding_its_own_state_still_counts(
    tmp_path: Path,
):
    """The exemption is a property, never a name.

    This class is called ``HolderMixin`` and is not a method group: it takes
    its value in a constructor and owns it, so counting its public interface
    means exactly what the message says it means.
    """
    assert "R0903" in _lint(_NAMED_LIKE_A_MIXIN, tmp_path, "named_mixin", "R0903")


def test_a_method_group_that_gains_a_constructor_rejoins_the_count(
    tmp_path: Path,
):
    """The moment it owns state, it stops being its owner's method group.

    The predicate reads three facts — no constructor, no slots of its own, and
    annotations it never assigns. This class breaks all three by binding what
    it used to expect from an owner, and the finding returns with it.
    """
    assert "R0903" in _lint(_GROUP_THAT_GAINED_STATE, tmp_path, "group_state", "R0903")
