"""A probe's nested boundary whose stop side the text refutes is a forced take.

Inside a probe a both-viable boundary is resolved by class, and its outcome
is a SAMPLED path: a verdict reached through it decides nothing, so the outer
boundary forks and the document goes to the gated engine. Where the stop
side's continuation cannot begin with the text at all, there was nothing to
sample — taking is the only resolution — and the probe stays exact.
"""

from __future__ import annotations

import pytest

from lexic.parsing.pda.runtime.kernel import verdicts
from tests.parity_helpers import DECLINED, answers

S = (
    'root ::= w ";"? "!"*\nw ::= x? tail?\nx ::= item+\n'
    'item ::= [a;] | "a"+ "a"\ntail ::= "a;" ";"\n'
)
"""Inside ``item+`` a boundary's stop side hands the next ``a`` to ``tail``,
which must spell ``a;`` and then ``;`` — a ``;`` the text does not have at
that point, though the stop side's first character admits."""


@pytest.mark.parametrize("text", ["aaaa;a", ";aaaaa"])
def test_a_refuted_stop_side_keeps_the_probe_exact(text: str, monkeypatch) -> None:
    """The predictive route answers what the gated engine answers, where it
    used to fork and hand the document over; and it does so because a stop
    side was proved dead against the text, not by some other route."""
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
