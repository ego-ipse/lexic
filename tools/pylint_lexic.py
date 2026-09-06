"""Astroid brain plugins for the shapes this repository's types actually use.

Three transforms restore behaviour the checker gets wrong about a construct the
interpreter handles correctly, and one exemption extends a rule the checker
already states. None of them suppresses a finding on request: each names a
property of the construct under which the message cannot be true of it, and
each is pinned by a probe that also proves the message still reaches a genuine
instance (``tests/unit/tools/test_pylint_lexic.py``).

astroid models stdlib ``@dataclass`` classes (its ``brain_dataclasses``), but
it does **not** honour :pep:`681` ``dataclass_transform`` on a *base class*. Our
IR records (:class:`lexic.ir.base.IrNamedTuple` / :class:`IrCachingTuple`) declare
fields as annotated class attributes whose default is a :class:`lexic.ir.base.Field`
specifier. ``Field.__new__`` is typed (via overloads) to return the *field's* type,
so pyright sees ``aliases: dict = Field(...)`` as a ``dict`` — but astroid ignores
the ``__new__`` return and infers the attribute as a ``Field`` instance, producing
false ``no-member`` / ``unsupported-membership-test`` reports at every read site.

This transform restores the intended behaviour: for any class whose MRO reaches
``IrNamedTuple``, each annotated field attribute is re-bound to an *instance of its
annotation type* — exactly what astroid does for a stdlib dataclass field — so
``self.aliases`` infers as ``dict`` again. No linter suppressions required.

The second transform corrects the scope of :pep:`695` ``type`` statements.
``type Alias[Carry] = list[Carry]`` gives ``Carry`` the alias's OWN lazy scope —
``"Carry" in vars(module)`` is ``False`` at run time — but astroid binds it in
the module's ``locals``. Every generic function in the same module then reads as
redefining a module-level name it does not shadow. The transform gives the
module a ``globals`` mapping without those parameters, which is what
``redefined-outer-name`` reads, while ``locals`` keeps them so the alias's own
body still resolves the parameter it declared.

The exemption is `too-few-public-methods`. The design checker already skips the
shapes that are not abstractions with a public interface — an Enum, a named
tuple, a TypedDict, a dataclass — through one predicate. Two of this
repository's shapes belong in that set for the same reason, so they are added
to that predicate rather than answered one site at a time: see
:func:`_counts_no_interface`.
"""

from __future__ import annotations

from collections.abc import Callable
from functools import partial
from typing import cast

import astroid
from astroid import nodes
from astroid.brain.brain_dataclasses import _infer_instance_from_annotation
from astroid.brain.brain_namedtuple_enum import (
    _has_namedtuple_base,
    infer_typing_namedtuple_class,
)
from astroid.typing import TransformFn
from pylint.checkers import design_analysis
from pylint.lint import PyLinter

_FIELD_BASES = frozenset({"lexic.ir.base.IrNamedTuple", "lexic.ir.base.IrCachingTuple"})


def _is_field_record(node: nodes.ClassDef) -> bool:
    """True if ``node`` derives from one of the IR field-record bases."""
    try:
        return any(anc.qname() in _FIELD_BASES for anc in node.ancestors())
    except astroid.MroError:
        return False


def _bind_annotated_fields(node: nodes.ClassDef) -> None:
    """Re-bind each annotated field to an instance of its annotation type."""
    # instance_attrs stores inference results (Instance/Uninferable); the astroid
    # stubs type it imprecisely, so narrow both the mapping and the values here.
    attrs = cast("dict[str, list[nodes.NodeNG]]", node.instance_attrs)
    for child in node.body:
        if not isinstance(child, nodes.AnnAssign):
            continue
        if not isinstance(child.target, nodes.AssignName):
            continue
        instances = cast(
            list[nodes.NodeNG],
            list(_infer_instance_from_annotation(child.annotation)),
        )
        if instances:
            attrs[child.target.name] = instances


def _alias_param_names(node: nodes.Module) -> set[str]:
    """Every name bound only as a :pep:`695` ``type``-statement parameter."""
    found: set[str] = set()
    for statement in node.body:
        if not isinstance(statement, nodes.TypeAlias):
            continue
        for parameter in statement.type_params:
            if isinstance(parameter.name, nodes.AssignName):
                found.add(parameter.name.name)
    return found


def _has_alias_scope(node: nodes.Module) -> bool:
    """True if this module declares a generic ``type`` alias at all."""
    return any(
        isinstance(statement, nodes.TypeAlias) and statement.type_params
        for statement in node.body
    )


def _unbind_alias_params(node: nodes.Module) -> None:
    """Give the module a ``globals`` view without its type-alias parameters.

    ``globals`` is what the redefinition check reads and ``locals`` is what
    name resolution reads; astroid aliases the two, which is why one correction
    cannot be made by editing the other. A name that ALSO has a real
    module-level binding keeps it — only the entries a ``type`` statement's
    parameter list owns are dropped, so a genuine shadowing is still reported.
    """
    seen = _alias_param_names(node)
    if not seen:
        return
    scrubbed = dict(node.locals)
    for name in seen:
        kept = [
            binding
            for binding in scrubbed.get(name, ())
            if not isinstance(binding.parent, (nodes.TypeVar, nodes.ParamSpec))
        ]
        if kept:
            scrubbed[name] = kept
        else:
            scrubbed.pop(name, None)
    node.globals = scrubbed


_NAMEDTUPLE_MEMBERS = frozenset(
    {"_replace", "_make", "_asdict", "_fields", "_field_defaults"}
)
"""What ``NamedTuple`` gives every subclass, and astroid gives some of them."""


def _is_generic_namedtuple(node: nodes.ClassDef) -> bool:
    """True for a :pep:`695` generic subclass of ``typing.NamedTuple``."""
    return bool(node.type_params) and bool(_has_namedtuple_base(node))


def _bind_namedtuple_members(node: nodes.ClassDef) -> None:
    """Give a generic named tuple the members its base defines.

    astroid supplies them through an inference TIP, which fires when the class
    is named directly and not when an instance arrives through a generic
    function's return — so a ``Two[T, U]`` built by a generic factory reads as
    having no ``_replace``. Binding them on the class instead makes them
    present however the instance is reached, which is what the interpreter
    does.
    """
    try:
        generated = next(infer_typing_namedtuple_class(node))
    except astroid.InferenceError, StopIteration:
        return
    for name in _NAMEDTUPLE_MEMBERS:
        if name not in node.locals and name in generated.locals:
            node.locals[name] = generated.locals[name]


def _is_fixture_class(node: nodes.ClassDef) -> bool:
    """True for a class defined inside a function body.

    A property of the definition, not of a name: a class whose enclosing scope
    is a call lives and dies inside that call, nothing can import it, and its
    members are whatever the call needs to make its point. A node with no
    parent is not one — it has no enclosing call to belong to.
    """
    parent = node.parent
    return parent is not None and isinstance(
        parent.frame(), (nodes.FunctionDef, nodes.AsyncFunctionDef)
    )


def _declares_unowned_state(node: nodes.ClassDef) -> bool:
    """Whether the class annotates instance attributes it never assigns.

    A bare ``text: str`` in a class body binds nothing. A class full of them,
    with no ``__init__`` to fill them, is declaring what its OWNER holds.
    """
    return any(
        isinstance(child, nodes.AnnAssign) and child.value is None
        for child in node.body
    )


def _holds_no_state(node: nodes.ClassDef) -> bool:
    """Whether the class declares ``__slots__ = ()`` — no instance dict, no slot."""
    for child in node.body:
        if not isinstance(child, nodes.Assign):
            continue
        named = any(
            isinstance(target, nodes.AssignName) and target.name == "__slots__"
            for target in child.targets
        )
        if named:
            return isinstance(child.value, nodes.Tuple) and not child.value.elts
    return False


def _is_method_group(node: nodes.ClassDef) -> bool:
    """True for a mixin — a group of one owner's methods, shed into a file.

    Three structural facts, no name: it has no ``__init__``, it declares
    ``__slots__ = ()`` so it holds nothing, and it annotates instance
    attributes it never assigns — state that belongs to whatever class
    inherits it. Such a class is never instantiated and publishes nothing on
    its own; its interface is its owner's.
    """
    return (
        "__init__" not in node.locals
        and _holds_no_state(node)
        and _declares_unowned_state(node)
    )


type Exempt = Callable[[nodes.ClassDef], bool]
"""The checker's own question: is this class one the count means nothing for?"""


def _counts_no_interface(exempt: Exempt, node: nodes.ClassDef) -> bool:
    """Whether counting this class's public methods measures anything.

    ``too-few-public-methods`` is a design finding about an ABSTRACTION with a
    thin public interface, which is why the checker already exempts the shapes
    that are not one — an Enum, a named tuple, a TypedDict, a dataclass. Two of
    this repository's shapes belong in that set for the same reason:

    - a class defined inside a function is a fixture, built to be exercised by
      the call that owns it and unreachable from anywhere else;
    - a class with no ``__init__``, ``__slots__ = ()`` and annotations it never
      assigns is a method group: it holds nothing, it is never instantiated,
      and both its state and its interface belong to the class that inherits
      it (``parsing/README.md`` calls this an implementation seam).

    Everything else the checker decides for itself, which is what keeps a
    genuine thin abstraction reported.
    """
    return exempt(node) or _is_fixture_class(node) or _is_method_group(node)


def register(_linter: PyLinter) -> None:
    """pylint entry point — install every transform and the exemption."""
    # WHICH predicate: `design_analysis._is_exempt_from_public_methods`, the
    # one `MisdesignChecker.leave_classdef` consults to decide whether counting
    # a class's public methods measures anything at all. It already answers NO
    # for an Enum, a named tuple, a TypedDict and a dataclass.
    #
    # WHY it is wrong here: two of this repository's shapes are not
    # abstractions with a thin public interface either, and the predicate has
    # no way to know. A class defined inside a function is a fixture the call
    # owns; a class with no `__init__`, empty `__slots__` and annotations it
    # never assigns is a method group whose state and interface both belong to
    # the class that inherits it. Neither is a design decision the message can
    # comment on, and neither can be answered at its own site: the fixtures
    # number in the dozens and the mixin's finding is about a shape, not a line.
    #
    # WHAT the probes prove (tests/unit/tools/test_pylint_lexic.py): the
    # fixture and the method group are silent; a module-level class with one
    # constructor and no public method is still reported; a class NAMED like a
    # mixin but holding its own state is still reported; and a method group
    # that gains an `__init__` rejoins the count. The exemption is a property,
    # never a name.
    #
    # The access itself is private, and correcting checker internals is what
    # this file IS — the two astroid privates it imports above are the same
    # access through another door. pylint offers no public seam for extending
    # that set except the pyproject option, which is the repository's harness
    # and not a plugin's to edit.
    exempt = design_analysis._is_exempt_from_public_methods  # pylint: disable=protected-access
    design_analysis._is_exempt_from_public_methods = partial(  # pylint: disable=protected-access
        _counts_no_interface, exempt
    )
    astroid.MANAGER.register_transform(
        nodes.ClassDef,
        cast(TransformFn[nodes.ClassDef], _bind_annotated_fields),
        _is_field_record,
    )
    astroid.MANAGER.register_transform(
        nodes.Module,
        cast(TransformFn[nodes.Module], _unbind_alias_params),
        _has_alias_scope,
    )
    astroid.MANAGER.register_transform(
        nodes.ClassDef,
        cast(TransformFn[nodes.ClassDef], _bind_namedtuple_members),
        _is_generic_namedtuple,
    )
