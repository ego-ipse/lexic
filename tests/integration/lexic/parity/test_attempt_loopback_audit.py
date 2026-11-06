"""An attempt loop audits the next occurrence of its rule unless a take covers it.

``x ::= [ab] | "ab"+`` under ``x*``: where ``"ab"+`` ends one ``x``, the stop side
may go on into the next ``x``, which can be ``a`` alone. A take of another
``ab`` does not cover that, so ``a`` is audited and the predictive engine never
force-takes it into ``a, a, b, a`` where Earley reads ``a, ab, a``. Under
``y ::= "a" "a"?`` in ``y+`` the next ``y`` is always ``a`` and complete ``y``'s,
so the take covers it and the split rule's answer comes back predictively.
"""

from __future__ import annotations

import pytest

from tests.parity_helpers import DECLINED, answers

LOOPBACK = (
    'root ::= "a"+ [a;]? y+ | z? x*\nx ::= [ab] | "ab"+\n'
    'y ::= ";"? ";" "b" | [ab] z+ z | z+ ";"?\n'
    'z ::= "b"? "ab" "ab" | ";" "ab"* | "ab" [a;]\n'
)
UNIT_RUN = 'root ::= "x" y+\ny ::= "a" "a"?\n'


@pytest.mark.parametrize("text", [";aaba", ";baba", "aaba", ";abab"])
def test_a_next_occurrence_the_take_cannot_cover_is_audited(text: str) -> None:
    """The predictive engine builds Earley's model or declines."""
    predictive, gated = answers(LOOPBACK, "loopback-audit", text)
    assert predictive in (gated, DECLINED)


@pytest.mark.parametrize("text", ["xaa", "xaaa", "xaaaa"])
def test_a_unit_runs_next_occurrence_is_covered_by_the_take(text: str) -> None:
    """The predictive engine answers, and its answer is Earley's."""
    predictive, gated = answers(UNIT_RUN, "loopback-unit-run", text)
    assert predictive == gated
