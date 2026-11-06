"""A reading that splits on an attempted iteration's ends keeps the loop's stop.

``root ::= x? ";" "a"* | ";"? z+`` with ``x ::= [a;]+ z | z+``: Earley refuses
``b;a`` as ambiguous, because root's first arm reads ``x = Z('b')`` and its
second ``Z('b;a')``. Inside root's attempted first arm, the ``z+`` iteration at
``;`` is an island with several ends. The reading split one child per end, each
taking the iteration, so the stop that lets the arm read its own ``;`` was never
a child. The arm died, and the second arm was built where Earley refuses.
"""

from __future__ import annotations

import pytest

from tests.parity_helpers import DECLINED, REFUSED, answers

Z = 'x ::= [a;]+ z | z+\nz ::= "b"* ";" "a"? | [a;] | "ab"* "b" [a;]?\n'
ATTEMPTED = 'root ::= x? ";" "a"* | ";"? z+\n' + Z
SOLE = 'root ::= x? ";" "a"* | "q"\n' + Z


@pytest.mark.parametrize("text", ["b;a", "b;aa", "bb;a", "b;b;a", "bab;a"])
def test_an_attempted_arm_keeps_the_stop_its_iteration_splits_past(text: str) -> None:
    """Earley refuses; the predictive engine refuses or declines."""
    predictive, gated = answers(ATTEMPTED, "iteration-ends-stop", text)
    assert gated == REFUSED
    assert predictive in (REFUSED, DECLINED)


@pytest.mark.parametrize("text", ["b;a", "b;aa", "bb;a"])
def test_the_same_arm_alone_still_answers_as_earley(text: str) -> None:
    """With root unattempted, its first arm is read as Earley reads it."""
    predictive, gated = answers(SOLE, "iteration-ends-sole", text)
    assert predictive == gated
