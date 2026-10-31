"""A boundary inside a live set's reading whose stop side the text refutes is
a forced take.

Inside a reading a both-viable boundary splits the reading into its two ways.
Where the stop side's continuation cannot begin with the text at all, there is
nothing to split — taking is the only resolution — and the reading goes on as
one. Either way the set's answer is exact, and the predictive route answers
what the gated engine answers.
"""

from __future__ import annotations

import pytest

from lexic.parsing.pda.runtime.kernel.verdicts import verdicts
from tests.parity_helpers import DECLINED, answers

S = (
    'root ::= w ";"? "!"*\nw ::= x? tail?\nx ::= item+\n'
    'item ::= [a;] | "a"+ "a"\ntail ::= "a;" ";"\n'
)
"""Inside ``item+`` a boundary's stop side hands the next ``a`` to ``tail``,
which must spell ``a;`` and then ``;`` — a ``;`` the text does not have at
that point, though the stop side's first character admits."""


@pytest.mark.parametrize("text", ["aaaa;a", ";aaaaa"])
def test_a_boundary_inside_a_reading_answers_on_the_predictive_route(
    text: str,
) -> None:
    """The predictive route answers what the gated engine answers, where a
    sampled guess once forked and handed the document over."""
    predictive, gated = answers(S, "refuted-stop-s", text)
    assert predictive != DECLINED
    assert predictive == gated


def test_a_refuted_stop_side_takes_without_splitting(monkeypatch) -> None:
    """Under ``;aaaaa`` a stop side inside a reading is proved dead against the
    text: the reading takes rather than splitting there, and the answer is
    still the gated engine's."""
    text = ";aaaaa"
    proved = []
    real = verdicts.stop_side_dead

    def recorded(*args):
        """``stop_side_dead``, its proofs counted."""
        dead = real(*args)
        proved.append(dead)
        return dead

    monkeypatch.setattr(verdicts, "stop_side_dead", recorded)
    predictive, gated = answers(S, "refuted-stop-s", text)
    assert predictive != DECLINED
    assert predictive == gated
    assert any(proved)
