"""Astroid brain plugin: PEP 681 ``dataclass_transform`` field inference.

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
"""

from __future__ import annotations

from typing import cast

import astroid
from astroid import nodes
from astroid.brain.brain_dataclasses import _infer_instance_from_annotation
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


def register(_linter: object) -> None:
    """pylint entry point — install the field-record inference transform."""
    astroid.MANAGER.register_transform(
        nodes.ClassDef,
        cast(TransformFn[nodes.ClassDef], _bind_annotated_fields),
        _is_field_record,
    )
