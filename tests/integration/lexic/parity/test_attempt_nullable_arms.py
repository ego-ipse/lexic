"""An attempted alternation tries every arm that can derive the empty string.

``x ::= ";"? "ab"? [ab] | z? | y?`` has two arms that derive the empty string,
with different values. The rule's one default holds the last of them, so where
no arm's FIRST admits the next character, as at the end of ``a`` under
``root ::= [a;]+ x? | …``, the attempt saw a single entry and built
``XArm3()``, while Earley refuses ``a`` as ambiguous. An empty-deriving arm is
admitted wherever its continuation can follow, so the attempt runs both and the
gated engine answers. ``;`` under the second grammar is the same choice between
``x``'s two empty-deriving arms.
"""

from __future__ import annotations

import pytest

from lexic.compile import compile_text
from lexic.exceptions import UnsupportedConstructError
from tests.parity_helpers import DECLINED, REFUSED, answers

CASES = {
    "x-at-the-end": (
        'root ::= [a;]+ x? | ";"? | "b"? "ab"?\n'
        'x ::= ";"? "ab"? [ab] | z? | y?\ny ::= [ab]+ z z\nz ::= "b"+ "a"\n',
        "a",
    ),
    "x-after-the-separator": (
        'root ::= y* | y? ";"+ x | "a"\nx ::= z z | [a;]* "ab"? "b"?\n'
        'y ::= z*\nz ::= "b"+ | [ab] | "a"* "a"*\n',
        ";",
    ),
}
VIEWS = {
    "plain": "",
    "lex": "# @lexical y\n",
    "lex-ns": "# @lexical y\n# @non-semantic z\n",
}


@pytest.mark.parametrize("view", VIEWS)
@pytest.mark.parametrize("case", CASES)
def test_every_empty_deriving_arm_is_attempted(case: str, view: str) -> None:
    """Earley refuses the text; the predictive engine agrees or declines, and
    the public parse refuses."""
    source, text = CASES[case]
    source = VIEWS[view] + source
    predictive, gated = answers(source, f"nullable-arms-{case}-{view}", text)
    assert gated == REFUSED
    assert predictive in (REFUSED, DECLINED)
    with pytest.raises(UnsupportedConstructError):
        compile_text(source, cache_key=f"nullable-arms-public-{case}-{view}").parse(
            text
        )
