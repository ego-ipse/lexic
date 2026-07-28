"""IrBind — the field-binding marker generated model fields carry.

An :class:`IrBind` ties one generated model field to its grammar item slot:
``item`` is the positional index into the rule's single sequence arm, ``mode``
says how the parse-tree kid at that slot folds into the field value, and
``semantic`` is ``False`` for structural-noise fields (whitespace refs).

Pure data: readable by ``base.py`` and the ``lexic.compile`` package. The
binding view (:mod:`lexic.compile.pipeline.binding`) produces these; the fold consumes
them.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import ClassVar, Self, cast

from lexic.exceptions import UnsupportedConstructError
from lexic.ir.spine.records import IrNamedTuple
from lexic.ir.spine.spine import IrLeaf

BIND_MODES: tuple[str, ...] = ("text", "gtext", "model", "models")
"""The fold-mode vocabulary — how a bound kid slot becomes a field value.

- ``text``: terminal atom (literal/char class); the slot's consumed characters.
- ``gtext``: literal-only group; its text, or absent when an optional group
  matched nothing.
- ``model``: single sub-model (rule ref, or ref-bearing group, ``hi == 1``).
- ``models``: list of sub-models (same atoms with ``hi > 1`` or unbounded).
"""


class IrBind(IrLeaf, IrNamedTuple[int, str, bool]):
    """Binding of one generated field to its grammar item slot.

    All three fields are scalar payload (``_child_attrs`` is empty); the node
    is a frozen record with repr-is-codegen (``IrBind(2, 'model')`` — the
    default ``semantic=True`` elides).
    """

    _child_attrs: ClassVar[tuple[str, ...]] = ()
    item: int
    mode: str
    semantic: bool = True

    def __new__(cls, item: int, mode: str, semantic: bool = True) -> Self:
        """Construct, refusing a mode outside :data:`BIND_MODES`.

        :param item: Index of the bound item in the rule's sequence arm.
        :param mode: One of :data:`BIND_MODES`.
        :param semantic: ``False`` for a structural-noise field.
        :raises UnsupportedConstructError: On an unknown ``mode``.
        """
        if mode not in BIND_MODES:
            raise UnsupportedConstructError(
                f"IrBind: unknown mode {mode!r} (expected one of {BIND_MODES})"
            )
        return cast(Callable[..., Self], super().__new__)(cls, item, mode, semantic)
