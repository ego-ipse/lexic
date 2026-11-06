"""An attempt that reaches a fail-island forks; it never reads the fail as its arm's miss.

``root ::= "a"+ y? z? | z y?`` with ``y ::= z`` and ``z ::= [ab]+ [ab]?``: both
arms derive ``a`` with different values, so Earley refuses it as ambiguous.
``z`` is a fail-island (its loop's stop-set escapes into its soft FOLLOW, and it
is semantic), so a reference to it does not run the island. Root attempts its
arms, and arm 2's entry reaches ``z``. That only means the predictive engine
cannot read the text there, so the attempt forks instead of losing arm 2 and
letting arm 1 commit ``RootArm1('a')``.
"""

from __future__ import annotations

import pytest

from lexic.compile import compile_text
from lexic.exceptions import UnsupportedConstructError
from tests.parity_helpers import DECLINED, REFUSED, answers

SOURCE = 'root ::= "a"+ y? z? | z y?\ny ::= z\nz ::= [ab]+ [ab]?\n'
VIEWS = {
    "plain": "",
    "lex": "# @lexical z\n",
    "lex-ns": "# @lexical z\n# @non-semantic y\n",
}


@pytest.mark.parametrize("view", VIEWS)
def test_an_arm_reaching_a_fail_island_is_no_miss(view: str) -> None:
    """Earley refuses ``a``; the predictive engine agrees or declines, and the
    public parse refuses."""
    source = VIEWS[view] + SOURCE
    predictive, gated = answers(source, f"fail-island-miss-{view}", "a")
    assert gated == REFUSED
    assert predictive in (REFUSED, DECLINED)
    with pytest.raises(UnsupportedConstructError):
        compile_text(source, cache_key=f"fail-island-miss-public-{view}").parse("a")
