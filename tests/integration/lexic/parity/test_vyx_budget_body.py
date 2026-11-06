"""vyx's optional budget before an inline body whose lines a ``\\n`` separates.

``!X:A L1< x\\nD:{} >`` reads ``L1<`` as the envelope's budget: the body is
``x``, the ``\\n`` separator, and ``D:{}``. It also reads as a body that begins
at ``L``, and the decider keeps the budget. The predictive engine forks the
budget into a take and a stop. On the take, ``nl-head``'s character loop runs
on through the separator's ``\\``, so the line after it cannot end where it
must, the take dies, and the stop is all that is left: the public parse builds
the body without the budget. On plain the loop is attempt licensed, and ``\\``
lies outside its audit set, which reads the structural tail and so leaves out
the repetition that follows a body line; on the @lexical views it is a
stop-set that runs longest. Auditing ``\\`` fixes plain but loses predictive
answers elsewhere, so each view is pinned as the open defect it is.
"""

from __future__ import annotations

import pytest

from lexic.compile import compile_text
from tests.parity_helpers import answers
from tests.paths import GROUND_TRUTH
from tools.benchmark.cases.directives import DIRECTIVES

LEX, NS = DIRECTIVES["vyx"]
VIEWS = {
    "plain": "",
    "lex": f"# @lexical {' '.join(LEX)}\n",
    "lex-ns": f"# @lexical {' '.join(LEX)}\n# @non-semantic {' '.join(NS)}\n",
}
TEXT = "!X:A L1< x\\nD:{} >\n"


@pytest.mark.parametrize(
    "view",
    [
        pytest.param(
            view,
            marks=pytest.mark.xfail(
                raises=AssertionError,
                strict=True,
                reason="nl-head's loop takes the separator's backslash",
            ),
        )
        for view in VIEWS
    ],
)
def test_a_body_after_the_budget_keeps_its_separator(view: str) -> None:
    """The predictive model and the public parse are Earley's: the budget is
    read, and the body splits at its ``\\n``."""
    source = VIEWS[view] + (GROUND_TRUTH / "vyx.gbnf").read_text()
    predictive, gated = answers(source, f"vyx-budget-{view}", TEXT)
    assert "Budget(" in gated
    assert predictive == gated
    public = compile_text(source, cache_key=f"vyx-budget-public-{view}").parse(TEXT)
    assert repr(public) == gated
