"""Adversarial recursion tests — left recursion must never hang the parse.

A predictive (top-down) machine cannot run left recursion: entering the rule
re-enters it at the same position before consuming anything. Most left
recursion islands by accident (the recursive arm's FIRST always contains the
escape arm's FIRST, an arm conflict) — but a nullable-only escape arm
contributes no FIRST, so ``root ::= root "a" | ""`` used to compile to a PDA
clone and descend forever. The analysis now detects left recursion
structurally and islands every cycle member; the Earley island sub-parse
handles left recursion natively. Each parse runs under a watchdog so a
regression fails the suite instead of hanging it.
"""

from __future__ import annotations

import pytest

from lexic.compile import compile_text
from lexic.exceptions import UnsupportedConstructError
from tests.adversarial.lexic.adversarial_helpers import watchdog

# The four recursion/nullability quadrants: only left-rec + nullable used to
# hang (its three neighbours island or run fine); all four must round-trip.
QUADRANT = [
    ("left-rec-non-nullable", 'root ::= root "a" | "a"\n', "aaa"),
    ("left-rec-nullable", 'root ::= root "a" | ""\n', "a"),
    ("right-rec-nullable", 'root ::= "a" root | ""\n', "aaa"),
    ("right-rec-non-nullable", 'root ::= "a" root | "a"\n', "aaa"),
]


@pytest.mark.parametrize(
    ("label", "grammar", "text"), QUADRANT, ids=[q[0] for q in QUADRANT]
)
def test_recursion_quadrant_round_trips(label: str, grammar: str, text: str) -> None:
    """Every recursion/nullability quadrant parses and round-trips, bounded."""
    compiled = compile_text(grammar, cache_key=f"adversarial-lr-{label}")
    with watchdog(20):
        model = compiled.parse(text)
    assert model.to_text() == text


def test_nullable_left_recursion_parses_longer_input() -> None:
    """The hang grammar handles multi-step left recursion, not just one 'a'."""
    compiled = compile_text('root ::= root "a" | ""\n', cache_key="adversarial-lr-5")
    with watchdog(20):
        model = compiled.parse("aaaaa")
    assert model.to_text() == "aaaaa"


def test_nullable_left_recursion_parses_empty_input() -> None:
    """The nullable escape arm alone derives the empty input."""
    compiled = compile_text('root ::= root "a" | ""\n', cache_key="adversarial-lr-e")
    with watchdog(20):
        model = compiled.parse("")
    assert model.to_text() == ""


def test_indirect_left_recursion_with_nullable_escape_round_trips() -> None:
    """Indirect left recursion through a nullable escape arm parses, bounded.

    ``a`` and ``b`` are mutually left-recursive; ``a``'s escape arm is empty,
    so no FIRST overlap islands the cycle by accident.
    """
    grammar = 'a ::= b | ""\nb ::= a "x" | "y"\n'
    compiled = compile_text(grammar, cache_key="adversarial-lr-ind")
    with watchdog(20):
        model = compiled.parse("yx")
    assert model.to_text() == "yx"


def test_sole_arm_left_recursion_rejects_cleanly() -> None:
    """``x ::= x "a"`` derives nothing — a bounded, clean rejection."""
    compiled = compile_text('x ::= x "a"\n', cache_key="adversarial-lr-sole")
    with watchdog(20), pytest.raises(UnsupportedConstructError):
        compiled.parse("aaa")
