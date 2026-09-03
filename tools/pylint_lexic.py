"""Astroid brain plugins for the shapes this repository's types actually use.

Two transforms, both restoring behaviour the checker gets wrong about a
construct the interpreter handles correctly. Neither suppresses a message.

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
"""

from __future__ import annotations

from typing import cast

import astroid
from astroid import nodes
from astroid.brain.brain_dataclasses import _infer_instance_from_annotation
from astroid.brain.brain_namedtuple_enum import (
    _has_namedtuple_base,
    infer_typing_namedtuple_class,
)
from astroid.typing import TransformFn

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


def register(_linter: object) -> None:
    """pylint entry point — install every transform."""
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
