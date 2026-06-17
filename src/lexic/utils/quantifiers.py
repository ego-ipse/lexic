"""Utility functions for working with quantifiers."""

from __future__ import annotations

from lexic.ir.base import IrNoneType


def bounds_to_quantifier(lo: int, hi: int | IrNoneType) -> str:
    """Convert inclusive ``(lo, hi)`` bounds to a Lark quantifier string.

    :param lo: Lower bound.
    :param hi: Upper bound; :data:`~lexic.ir.base.IrNone` means unbounded.
    :returns: ``""``/``?``/``*``/``+`` or a ``{m,n}``-style suffix.
    """
    hi_int: int | None = None if isinstance(hi, IrNoneType) else hi
    _table: dict[tuple[int, int | None], str] = {
        (1, 1): "",
        (0, 1): "?",
        (0, None): "*",
        (1, None): "+",
    }
    result = _table.get((lo, hi_int))
    if result is None:
        if hi_int is None:
            result = f"{{{lo},}}"
        elif lo == hi_int:
            result = f"{{{lo}}}"
        else:
            result = f"{{{lo},{hi_int}}}"
    return result
