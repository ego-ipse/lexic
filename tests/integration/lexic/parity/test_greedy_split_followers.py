"""A greedy split whose iteration can fail where a follower could start is attempted.

GREEDY_SPLIT commits each iteration of a loop on its first character. Under
``root ::= "ab"* [ab]* | y* "ab"+``, ``"ab"*`` takes the first ``a`` of ``aab``
and then meets ``a``: the arm failed, though ``[ab]*`` reads the whole text,
and an attempt over root's arms read that failure as the arm's miss. The
second arm was then built where Earley refuses ``aab`` as ambiguous. Such a
loop is attempted now: an iteration that fails closes the loop, and the arm
reads on.
"""

from __future__ import annotations

import pytest

from lexic.compile import compile_text
from lexic.parsing.lift import lift_optional_nullables
from lexic.parsing.pda.analysis.analysis import GrammarAnalysis
from tests.parity_helpers import DECLINED, REFUSED, answers

WITNESSES = {
    "fuzz3:38": (
        'root ::= [ab]* y | [a;]+\nx ::= z+ "b"? | z+ ";" z\n'
        'y ::= z? ";"* z | "a"+ z+ ";"? | z? "b"* [a;]*\n'
        'z ::= [a;]+ "ab" ";" | "a"+ "a"+ "ab"?\n',
        ";",
    ),
    "fuzz1:72": (
        'root ::= x* y* | y "a"? | "a"*\nx ::= z\ny ::= z+ | z "b" | "a" [ab]\n'
        "z ::= [ab]* [a;]\n",
        ";b",
    ),
    "fuzz1:161": (
        'root ::= "ab"* [ab]* | y* "ab"+\nx ::= z [a;]+ [ab]?\n'
        'y ::= z z* z | "b" z? z+ | "a"? ";"*\nz ::= ";" ";"*\n',
        "aab",
    ),
    "fuzz1:58": (
        'root ::= "a" z* [a;] | "a"? "ab"* | z* "ab"*\n'
        'x ::= [ab]? y? "ab" | ";"+ "b" [a;] | y? [a;] ";"\n'
        'y ::= "ab"* | "a"+ z | z*\nz ::= [ab]? ";" "a" | "b" "a" [a;]* | [ab]? [a;]?\n',
        "ab",
    ),
    "fuzz2:85": (
        'root ::= x x? z? | "b" "ab" | z* [ab]*\nx ::= [a;]?\n'
        'y ::= [ab]* ";" | "b" [ab]? "b" | "a"?\nz ::= [a;]* "ab" "b"\n',
        "a",
    ),
    "fuzz3:19": (
        'root ::= y\nx ::= [ab] "a"? | "b"\ny ::= "ab" ";"* z+ | "ab"+ z* z*\n'
        'z ::= [a;] "b"? "b"\n',
        "ababb",
    ),
}


@pytest.mark.parametrize("name", sorted(WITNESSES))
def test_a_failed_greedy_iteration_is_no_arm_miss(name: str) -> None:
    """Earley refuses; the predictive engine refuses or declines."""
    source, text = WITNESSES[name]
    predictive, gated = answers(source, f"greedy-follower-{name}", text)
    assert gated == REFUSED
    assert predictive in (REFUSED, DECLINED)


def _notes(source: str) -> list[str]:
    compiled = compile_text(source, cache_key=f"greedy-notes-{hash(source)}")
    analysis = GrammarAnalysis(lift_optional_nullables(compiled.codegen_grammar))
    return [note for notes in analysis.demoted.values() for note in notes]


def test_a_one_character_loop_keeps_the_greedy_split() -> None:
    """An iteration of one character cannot fail once admitted, so the split
    stands; a literal's can, so it is attempted."""
    assert any("loop greedy split" in n for n in _notes('root ::= [ab]* "a"*\n'))
    assert any(
        "loop iterations attempted" in n for n in _notes('root ::= "ab"* [ab]*\n')
    )
