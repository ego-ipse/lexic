"""The FOLLOW-window loop gate end to end: same answers, and a decision it makes.

The gate replaces an attempt sub-run — which decides by RUNNING the iteration —
with a two-character window read off the grammar. A wrong window is silent: it
would take one iteration too many or too few and build a different model, or
refuse at a different position. So the tests here ask the two questions a gate
has to answer: does it change any answer, and does it withhold itself where it
was not proved.

Documents are chosen to sit ON the boundary the window reads, and the
late-failing near-misses are the point of the file — a document that is legal
for many characters and then is not exercises the failure path that successful
parses hide.
"""

from __future__ import annotations

import pytest

from lexic.compile import compile_text
from lexic.exceptions import UnsupportedConstructError
from lexic.parsing.pda.analysis.analysis import GrammarAnalysis
from lexic.parsing.pda.core.errors import PdaFail
from lexic.parsing.products import _model_product, earley_model, parse_model, pda_model
from tests.gate_grammars import REPEATED_ARM_FINAL_LOOP, REPEATED_NULL_ARM

CLASS = REPEATED_ARM_FINAL_LOOP
NULL_ARM = REPEATED_NULL_ARM


def _built(source: str, key: str):
    """Compile ``source``; return the compiled grammar and its model product."""
    compiled = compile_text(source, cache_key=key)
    return compiled, _model_product(compiled.codegen_grammar, compiled.product)


def _answers(source: str, key: str, text: str) -> tuple[str, str]:
    """``(predictive, gated)`` for one document — a decline or refusal named."""
    compiled, product = _built(source, key)
    try:
        predictive = repr(pda_model(product.pda, text, compiled.product.executor))
    except PdaFail:
        predictive = "declined"
    except UnsupportedConstructError:
        predictive = "refused"
    try:
        gated = repr(
            earley_model(
                product.instance_grammar, text, compiled.product, product.tables
            )
        )
    except UnsupportedConstructError:
        gated = "refused"
    return predictive, gated


VALID = [
    "a e.\n",
    "e e.\n",  # the word IS the terminator's lead character
    "ee e.\n",
    "a b c e.\n",
    "ex ey e.\n",  # every word starts with the lead
    "e e e.\n",
    "abc e.\na e.\n",
]
"""Documents the grammar accepts, each sitting on the window's boundary."""

NEAR_MISSES = [
    "abc e\n",  # terminator truncated to its first character
    "abc \n",  # terminator missing
    "abc e.",  # newline missing
    "eee eee e\n",  # a long legal run, then a truncated terminator
    "e.\n",  # the terminator without the space a word needs
    "e. e.\n",  # `.` is not a word character, so the first `e.` is no word
    "",
]
"""Legal for many characters and then not — the failure path successes hide."""


@pytest.mark.parametrize("text", VALID)
def test_both_engines_answer_the_same_way(text: str) -> None:
    """The one thing the gate may not do is change an answer."""
    predictive, gated = _answers(CLASS, "fwl-class", text)

    assert predictive == gated
    assert predictive != "declined", "the gate should have taken this shape"


@pytest.mark.parametrize("text", NEAR_MISSES)
def test_a_late_failing_document_is_refused_by_both(text: str) -> None:
    """A wrong window shows up here as one engine accepting what the other refuses."""
    predictive, gated = _answers(CLASS, "fwl-class", text)

    assert gated == "refused"
    assert predictive in {"refused", "declined"}


@pytest.mark.parametrize("text", VALID)
def test_every_accepted_document_round_trips(text: str) -> None:
    """The gate decides how many iterations the loop took, so the text it
    recovers is the direct witness that it decided correctly."""
    compiled, _product = _built(CLASS, "fwl-class")
    model = parse_model(compiled.codegen_grammar, text, compiled.product)

    assert model.to_text() == text


def test_the_class_is_decided_by_the_gate_and_not_by_an_attempt() -> None:
    """Without this the parity above could hold because nothing changed."""
    compiled, _product = _built(CLASS, "fwl-class")
    analysis = GrammarAnalysis(compiled.codegen_grammar)
    analysis.eval(analysis, compiled.codegen_grammar, ())

    assert not analysis.conflicts
    assert analysis.taxonomy.loop_gates
    assert not analysis.taxonomy.attempt_loops


def test_the_null_arm_never_reaches_the_gate() -> None:
    """`%` cannot start a word, so the cheapest tier settles it.

    The gate sits at the bottom of the separability tiers precisely so a
    decision a one-character stop set already makes never pays for a fixpoint.
    """
    compiled, _product = _built(NULL_ARM, "fwl-null")
    analysis = GrammarAnalysis(compiled.codegen_grammar)
    analysis.eval(analysis, compiled.codegen_grammar, ())

    assert not analysis.conflicts
    assert not analysis.taxonomy.loop_gates
    assert not analysis.taxonomy.attempt_loops


@pytest.mark.parametrize("words", [1, 2, 5, 30])
def test_a_long_run_takes_every_iteration_it_should(words: int) -> None:
    """The gate is consulted once per iteration, so a long run is where an
    off-by-one in the window would compound rather than cancel."""
    text = " ".join("abc" for _ in range(words)) + " e.\n"
    compiled, _product = _built(CLASS, "fwl-class")
    model = parse_model(compiled.codegen_grammar, text, compiled.product)

    assert model.to_text() == text
