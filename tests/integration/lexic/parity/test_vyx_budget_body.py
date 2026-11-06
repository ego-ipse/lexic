"""vyx's optional budget before an inline body whose lines a ``\\n`` separates.

``!X:A L1< x\\nD:{} >`` reads ``L1<`` as the envelope's budget: the body is
``x``, the ``\\n`` separator, and ``D:{}``. It also reads as a body that begins
at ``L``, and the decider keeps the budget. The predictive engine forks the
budget into a take and a stop. On the take, ``nl-head``'s character loop runs
on through the separator's ``\\``, so the line after it cannot end where it
must, the take dies, and the stop is all that is left. On plain the loop is
attempt licensed, and its audit set reads the soft tail, so ``\\`` is
audited. On the @lexical views the same loop is a stop-set that runs longest,
routed there by an escape check that reads the structural tail; reading that on
the soft tail too makes more rules fail-islands and adds wrong models, so those
views stay pinned as the open defect.
"""

from __future__ import annotations

import pytest

from lexic.compile import compile_text
from tests.parity_helpers import DECLINED, answers
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
        "plain",
        *(
            pytest.param(
                view,
                marks=pytest.mark.xfail(
                    raises=AssertionError,
                    strict=True,
                    reason="nl-head runs longest through the separator",
                ),
            )
            for view in ("lex", "lex-ns")
        ),
    ],
)
def test_a_body_after_the_budget_keeps_its_separator(view: str) -> None:
    """The public parse is Earley's: the budget is read, and the body splits at
    its ``\\n``. The predictive engine builds that model or declines."""
    source = VIEWS[view] + (GROUND_TRUTH / "vyx.gbnf").read_text()
    predictive, gated = answers(source, f"vyx-budget-{view}", TEXT)
    assert "Budget(" in gated
    assert predictive in (gated, DECLINED)
    public = compile_text(source, cache_key=f"vyx-budget-public-{view}").parse(TEXT)
    assert repr(public) == gated
