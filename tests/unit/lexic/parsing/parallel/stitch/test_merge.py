"""Focused shell and boundary reconstruction tests."""

from __future__ import annotations

from tests.unit.lexic.parsing.parallel.stitch.support import (
    assert_exact_split,
    assert_outer_split,
    split_case,
)

OUTER = (
    "root ::= outer\n"
    "outer ::= lead group trail\n"
    'lead ::= "[" ws\n'
    "group ::= open items close\n"
    'open ::= "{" ws\n'
    'close ::= ws "}"\n'
    "items ::= item more*\n"
    "more ::= comma item\n"
    'comma ::= "," ws\n'
    "item ::= [a-z]+\n"
    'trail ::= ws "]"\n'
    'ws ::= " "*\n'
)


def test_configured_outer_arm_preserves_closing_boundary_spaces() -> None:
    """An indirect group keeps whitespace owned by its closing arm."""
    text = "[ { " + ", ".join("a" * 20 for _ in range(900))
    text += "   } ]"
    assert_outer_split(split_case(OUTER, text, "group", 4), text)


def test_mixed_separator_whitespace_survives_shallow_joint_reconstruction() -> None:
    """Boundary tails retain varying separator whitespace during a shallow join."""
    separators = [", ", ",    ", ",   ", ",  "]
    items = ["a" * 20]
    for index in range(899):
        items.append(separators[index % len(separators)] + "a" * 20)
    text = "[ { " + "".join(items) + " } ]"
    assert_exact_split(split_case(OUTER, text, "group", 8), text)
