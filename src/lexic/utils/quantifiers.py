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
