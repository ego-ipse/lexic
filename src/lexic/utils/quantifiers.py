from __future__ import annotations


def bounds_to_quantifier(min_: int, max_: int | None) -> str:
    """Convert (min, max) bounds to a GBNF/Lark quantifier string."""
    if min_ == 1 and max_ == 1:
        return ""
    if min_ == 0 and max_ == 1:
        return "?"
    if min_ == 0 and max_ is None:
        return "*"
    if min_ == 1 and max_ is None:
        return "+"
    if max_ is None:
        return f"{{{min_},}}"
    if min_ == max_:
        return f"{{{min_}}}"
    return f"{{{min_},{max_}}}"


def quantifier_to_bounds(q: str | None) -> tuple[int, int | None]:
    """Parse a GBNF/Lark quantifier string into (min, max). max=None means unbounded."""
    if q is None:
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
