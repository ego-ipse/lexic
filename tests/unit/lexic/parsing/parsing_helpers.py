"""Shared parsing/PDA test helpers.

``prod`` is duplicated verbatim (pre-relocation) across the fold, compile,
delegate-compile and PDA-parity test files — the instance product for a
``CompiledGrammar`` (its ``instance_grammar``/``tables``/``pda``, the fields
the artefact itself no longer carries; memoised per ``(grammar, binding)``).
"""

from __future__ import annotations

from lexic.exceptions import UnsupportedConstructError
from lexic.compile import CompiledGrammar, compile_text
from lexic.parsing.pda.core.errors import PdaFail
from lexic.parsing.products import (
    _model_product,
    earley_model,
    parse_model,
    pda_model,
)

PRODUCTS_GRAMMAR_TEXT = 'root ::= "a" "b"\n'


def prod(cg: CompiledGrammar):
    """The instance product for a CompiledGrammar — its instance_grammar / tables /
    pda (the fields the artefact no longer carries; memoised per (grammar, binding))."""
    return _model_product(cg.codegen_grammar, cg.product)


def compiled() -> CompiledGrammar:
    """Compile the tiny ``"a" "b"`` products-test grammar (test_products.py)."""
    return compile_text(PRODUCTS_GRAMMAR_TEXT, cache_key="products-test-grammar")


def engines_agree_or_both_refuse(cg: CompiledGrammar, text: str, resolve=None) -> str:
    """Assert the two engines answer ``text`` the same way; say which way.

    Three outcomes, all of them the contract rather than an excuse:

    - ``"agreed"`` — both built a model and the models are equal.
    - ``"refused"`` — both refused. A span that means two things means two
      things to either engine.
    - ``"declined"`` — the predictive path escaped (``PdaFail``) rather than
      answering, which is what it does on a shape whose gates it cannot settle.
      There is no model to compare, so the assertion moves to the route a
      caller actually uses: the COMPOSED entry, PDA first with Earley
      completion, must equal Earley's own answer.

    A caller that needs a real comparison asserts on the verdict — a row that
    only ever returns ``"declined"`` has compared no models and should say so
    rather than pass quietly.

    :param cg: The compiled grammar.
    :param text: The input both engines parse.
    :param resolve: A resolver for the model route, or ``None`` to refuse.
    :returns: ``"agreed"``, ``"refused"`` or ``"declined"``.
    """
    product = prod(cg)
    gated = _answer(
        lambda: earley_model(
            product.instance_grammar, text, cg.product, product.tables, resolve
        )
    )
    try:
        predictive = repr(pda_model(product.pda, text, cg.product.executor))
    except PdaFail:
        composed = _answer(
            lambda: parse_model(cg.codegen_grammar, text, cg.product, resolve)
        )
        assert composed == gated, (
            f"{text!r}: the composed entry says {composed} where the gated "
            f"engine says {gated}"
        )
        return "declined"
    assert predictive == gated, (
        f"{text!r}: the predictive engine says {predictive} where the gated "
        f"engine says {gated}"
    )
    return "refused" if gated == _REFUSED else "agreed"


_REFUSED = "refused"
"""What :func:`_answer` reports for an engine that would not answer."""


def _answer(run) -> str:
    """One engine's answer as a string, or :data:`_REFUSED`."""
    try:
        return repr(run())
    except UnsupportedConstructError:
        return _REFUSED
