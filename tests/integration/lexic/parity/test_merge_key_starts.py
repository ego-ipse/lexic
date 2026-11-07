"""Two readings meet only where every start their settles rewind to stands alike.

``root ::= x* "ab"*`` with ``x``'s arms sharing ``z``: in ``;a;a`` the readings
that split the ``z`` runs differently reach the same place with different
unsettled starts, and Earley refuses the texts as ambiguous. Merged on a key
blind to those starts, one reading stood for the other and the predictive
engine built a model.
"""

from __future__ import annotations

import pytest

from lexic.compile import compile_text
from lexic.exceptions import UnsupportedConstructError
from tests.parity_helpers import DECLINED, REFUSED, answers

SOURCE = (
    'root ::= x* "ab"*\nx ::= z? [ab]+ | z+ [ab] z | z+\n'
    'z ::= "a"+ "ab" "ab" | ";" [a;] | ";"? ";"+\n'
)


@pytest.mark.parametrize("text", [";a;a", "a;a;a", "b;a;a"])
def test_readings_with_different_starts_do_not_merge(text: str) -> None:
    """Earley refuses; the predictive engine refuses or declines, and so does
    the public parse."""
    predictive, gated = answers(SOURCE, "merge-key-starts", text)
    assert gated == REFUSED
    assert predictive in (REFUSED, DECLINED)
    with pytest.raises(UnsupportedConstructError):
        compile_text(SOURCE, cache_key="merge-key-starts-public").parse(text)
