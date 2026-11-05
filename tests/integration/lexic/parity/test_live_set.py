"""A boundary whose readings run on past it is settled on the predictive route.

Two shapes once went to the gated engine whole, because the boundary's two
sides each met further boundaries before either settled, and a guess there
decided nothing: an envelope whose every line carries two marks, where one
reading dies a line later, and pairs that reopen, where both readings complete
and the decider keeps one. A live set carries every reading forward, so each
settles on the predictive route with the gated engine's model.
"""

from __future__ import annotations

import pytest

from lexic.parsing.pda.runtime.kernel.verdicts.liveset import LiveSet
from tests.parity_helpers import DECLINED, answers
from tests.unit.lexic.parsing.parallel.envelope_fixtures import TWO_MARK_SOURCE

REOPENING = (
    'root ::= arr\narr ::= "[" pair ("," pair)* "]"\n'
    'pair ::= "(" num ")" "," "(" num ")" | "(" num ")"\nnum ::= [0-9]+\n'
)
"""``(0),(1)`` is one long pair or two short ones: the decider keeps the long."""


def _envelope(entries: int) -> str:
    """``entries`` lines of the two-mark envelope."""
    return "\n".join(
        f"k{chr(97 + i % 26)}{chr(97 + (i // 26) % 26)} = v" for i in range(entries)
    )


def _pairs(count: int) -> str:
    """An array of ``count`` short pairs."""
    return "[" + ",".join(f"({k})" for k in range(count)) + "]"


@pytest.mark.parametrize(
    ("source", "key", "text"),
    [
        (TWO_MARK_SOURCE, "live-set-envelope", _envelope(40)),
        (REOPENING, "live-set-reopening", _pairs(12)),
    ],
    ids=["two-mark-envelope", "reopening-pairs"],
)
def test_a_boundary_with_readings_past_it_answers_predictively(
    monkeypatch, source: str, key: str, text: str
) -> None:
    """Each shape asks live sets, and the predictive route answers every one
    with the gated engine's model; where the lockstep guessed, it forked
    within a few lines."""
    sets = [0]
    decide = vars(LiveSet)["_decide"]

    def counted(self, roots, ahead_first):
        sets[0] += 1
        return decide(self, roots, ahead_first)

    monkeypatch.setattr(LiveSet, "_decide", counted)
    predictive, gated = answers(source, key, text)
    assert sets[0], "no boundary asked a set — the witness proves nothing"
    assert predictive != DECLINED
    assert predictive == gated


TWO_FLOORS = (
    'root ::= "ab"+ "ab"+ | x? x+ ";"? | [a;]*\nx ::= y? ";"\n'
    'y ::= z* [ab] z | [a;]* [a;] "ab"\n'
    'z ::= "a" "ab" [ab]+ | "ab"* ";"? | [ab] [ab]* "ab"\n'
)
"""``a;;aa`` meets with values that differ, so its set reruns keeping ledgers,
and a reading of it is forked inside two sub-runs rooted at one depth: an
attempted iteration of ``x+`` and the attempt entry its payload runs."""


def test_a_ranked_reading_settles_both_sub_runs_rooted_at_one_depth() -> None:
    """Both floors settle where the reading drains back to their depth, the
    inner first. Stepped one copied frame out after the first, the drive
    passed the second, and the next fork of the reading read its caller from
    a frame no longer on the stack."""
    predictive, gated = answers(TWO_FLOORS, "live-set-two-floors", "a;;aa")
    assert predictive == gated == "RootArm3('a;;aa')"


TWO_DEEP_IN_PAIRS = (
    'root ::= arr\narr ::= "[" pair ("," pair)* "]"\n'
    'pair ::= "(" e ")" "," "(" e ")" | "(" e ")"\n'
)
"""Pairs that may reopen, around an ``e`` whose run ends where a tail the
class overlaps does: decided two characters deep, inside each reading."""


@pytest.mark.parametrize("tail", ["[aeiou]", '"e"'])
def test_an_exit_decided_two_deep_inside_a_reading_answers_predictively(
    monkeypatch, tail: str
) -> None:
    """The two-deep grant settles ``e``'s run inside a live set's readings, as
    it does outside them: the sets are asked, and the predictive route builds
    the gated engine's model."""
    source = TWO_DEEP_IN_PAIRS + f"e ::= [a-z]* {tail}\n"
    sets = [0]
    decide = vars(LiveSet)["_decide"]

    def counted(self, roots, ahead_first):
        sets[0] += 1
        return decide(self, roots, ahead_first)

    monkeypatch.setattr(LiveSet, "_decide", counted)
    text = "[" + ",".join(f"(b{'ca' * k}e)" for k in range(12)) + "]"
    predictive, gated = answers(source, f"two-deep-pairs-{tail}", text)
    assert sets[0], "no boundary asked a set — the witness proves nothing"
    assert predictive == gated != DECLINED
