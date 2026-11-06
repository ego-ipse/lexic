"""An island that refuses its text inside an attempted arm leaves the document
to the gated engine.

An island refuses a span that derives two ways meaning different things. That
is the text's answer, not the arm's miss: read as a miss, the next arm wins
and the predictive route returns a model the gated engine refuses.
"""

from __future__ import annotations

import pytest

from lexic.exceptions import UnsupportedConstructError
from lexic.parsing.pda.core.errors import ProbeFork
from lexic.parsing.pda.runtime.kernel.kernel import pda_model
from tests.parity_helpers import DECLINED, REFUSED, answers, built

ARMS = (
    'root ::= x x* "a" | y "a"\nx ::= y | z\n'
    'y ::= ";" [a;]?\nz ::= ";"* ";" | ";"? [a;]*\n'
)
"""``root`` attempts its two arms; the first runs ``x`` as an island, and
``x`` derives ``;;`` as a ``y`` and as a ``z``. The second arm alone builds
``RootArm2(Y(';;'))``."""


def test_an_island_refusing_inside_an_arm_declines_to_the_gated_refusal() -> None:
    """The predictive route declines, and the gated engine refuses the text."""
    assert answers(ARMS, "island-refusal-arms", ";;a") == (DECLINED, REFUSED)


def test_the_decline_is_the_islands_refusal() -> None:
    """The fork the attempt raises is caused by the island's own refusal, so
    the decline is that refusal's, not some other boundary's."""
    compiled, product = built(ARMS, "island-refusal-arms")
    with pytest.raises(ProbeFork) as fork:
        pda_model(product.pda, ";;a", compiled.product.executor)
    assert isinstance(fork.value.__cause__, UnsupportedConstructError)
    assert "two ways" in str(fork.value.__cause__)


def test_the_public_parse_refuses() -> None:
    """The public parse answers the gated engine's refusal."""
    compiled, _product = built(ARMS, "island-refusal-arms")
    with pytest.raises(UnsupportedConstructError):
        compiled.parse(";;a", cores=1)
