"""A loop whose body can be its leading noise alone is not skip-then-peeked.

The ``SG_SCAN`` gate skips the loop body's leading noise run and takes another
iteration only if a content lead follows it. Under ``y ::= z* z | z* "ab" z``
with ``z ::= "b"+``, the run of ``b`` it skips can be a whole ``y`` on its own
(the first arm), so after the skip there is nothing left to peek at and the
iteration was refused: ``root ::= [a;] y* z?`` gave ``ab``'s ``b`` to ``z?``,
where Earley's leftmost-longest carving takes it into ``y*``.
"""

from __future__ import annotations

import itertools

import pytest

from tests.parity_helpers import DECLINED, answers

ALL_NOISE_ARM = (
    'root ::= "a" z "a" | [a;] y* z? | y y\n'
    'x ::= z "ab" z+ | z "ab" y*\n'
    'y ::= z* z | z* "ab" z\n'
    'z ::= "b"+\n'
)
WORDS = ["".join(w) for n in range(1, 5) for w in itertools.product("ab;", repeat=n)]


@pytest.mark.parametrize("text", ["ab", ";b"])
def test_a_body_that_is_noise_alone_is_taken_as_earley_takes_it(text: str) -> None:
    """``y*`` takes the ``b``, as Earley does, rather than leaving it to ``z?``."""
    predictive, gated = answers(ALL_NOISE_ARM, "noise-alone-scan", text)
    assert "YArm1" in gated
    assert predictive == gated


def test_no_word_gets_a_model_earley_does_not_build() -> None:
    """Over every word up to four characters, an answer is Earley's or a decline."""
    for text in WORDS:
        predictive, gated = answers(ALL_NOISE_ARM, "noise-alone-scan", text)
        assert predictive in (gated, DECLINED), text
