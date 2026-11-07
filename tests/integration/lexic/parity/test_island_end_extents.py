"""A repeated reference whose run can end at more than one place keeps Earley's.

``root ::= y* y+ ";"``: in ``a;;`` the first ``y`` can take ``a`` or ``a;``, and
only the shorter one leaves ``y+`` its ``;`` before the closing one. Read as
one extent, the longer end was kept, ``y*`` was left empty, and the model
differed from Earley's.
"""

from __future__ import annotations

from lexic.compile import compile_text
from tests.parity_helpers import answers

SOURCE = (
    'root ::= y* y+ ";"\ny ::= z+ z? [ab] | z | "ab"\n'
    'z ::= [a;]+ | "b" "b"+ | ";"* "a"? ";"+\n'
)


def test_the_shorter_end_that_completes_is_kept() -> None:
    """Both engines build ``y*`` holding ``a`` and ``y+`` holding ``;``, and the
    public parse is that model."""
    predictive, gated = answers(SOURCE, "island-end-extents", "a;;")
    assert gated == "Root((Z('a'),), (Z(';'),))"
    assert predictive == gated
    public = compile_text(SOURCE, cache_key="island-end-extents-public").parse("a;;")
    assert repr(public) == gated
