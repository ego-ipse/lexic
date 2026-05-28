"""Utility functions for working with quantifiers."""

from __future__ import annotations


def bounds_to_quantifier(min_: int, max_: int | None) -> str:
    """Convert (min, max) bounds to a Lark quantifier string."""
    _table: dict[tuple[int, int | None], str] = {
        (1, 1): "",
        (0, 1): "?",
        (0, None): "*",
        (1, None): "+",
    }
    result = _table.get((min_, max_))
    if result is None:
        if max_ is None:
            result = f"{{{min_},}}"
        elif min_ == max_:
            result = f"{{{min_}}}"
        else:
            result = f"{{{min_},{max_}}}"
    return result
