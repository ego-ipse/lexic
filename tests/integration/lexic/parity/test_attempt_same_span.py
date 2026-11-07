"""An attempted arm that also derives the winner's span is a value question only
where it builds another value there.

``x``'s arm ``z*`` is two entries of its attempt: admitted where ``z`` can start
or where it may derive nothing, and again as the rule's nullable default. When
the first wins with nothing, auditing the default runs the same arm, which
overshoots and also derives the empty span with the winner's own value. Read as
two arms over one span, every text a reading reached that way declined, though
the decider keeps ``x`` taking ``z`` as Earley does.
"""

from __future__ import annotations

import pytest

from tests.parity_helpers import answers

GRAMMAR = (
    'root ::= x z* [ab]*\nx ::= "b"? "b"+ "b"+ | "ab"+ [ab]? | z*\n'
    'y ::= z | "b"* "ab"+\nz ::= [a;]+ [a;]\n'
)
"""A generated grammar (fuzz seed 3, index 6) — its 128 such texts, smallest."""


@pytest.mark.parametrize("text", ["aa", "a;", ";;", "aab", "a;a"])
def test_the_default_entry_tried_again_is_no_rival(text: str) -> None:
    """The predictive model is Earley's, ``x`` taking ``z``."""
    predictive, gated = answers(GRAMMAR, "attempt-same-span", text)
    assert "XArm3((Z(" in gated
    assert predictive == gated
