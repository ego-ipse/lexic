"""Utility functions for working with quantifiers."""

from __future__ import annotations


def bounds_to_quantifier(min_: int, max_: int | None) -> str:
    """Convert (min, max) bounds to a GBNF/Lark quantifier string."""
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


def quantifier_to_bounds(q: str | None) -> tuple[int, int | None]:
    """Parse a GBNF/Lark quantifier string into (min, max). max=None means unbounded."""
    if not q:
        return 1, 1
    if q == "?":
        return 0, 1
    if q == "*":
        return 0, None
    if q == "+":
        return 1, None
    inner = q[1:-1]
    if "," in inner:
        lo_str, hi_str = inner.split(",", 1)
        lo = int(lo_str)
        hi = int(hi_str) if hi_str else None
        return lo, hi
    n = int(inner)
    return n, n
