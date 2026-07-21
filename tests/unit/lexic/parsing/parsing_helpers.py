"""Shared parsing/PDA test helpers.

``prod`` is duplicated verbatim (pre-relocation) across the fold, compile,
delegate-compile and PDA-parity test files — the instance product for a
``CompiledGrammar`` (its ``instance_grammar``/``tables``/``pda``, the fields
the artefact itself no longer carries; memoised per ``(grammar, fold)``).
"""

from __future__ import annotations

from lexic.compile import CompiledGrammar, compile_text
from lexic.parsing.products import _model_product

PRODUCTS_GRAMMAR_TEXT = 'root ::= "a" "b"\n'


def prod(cg: CompiledGrammar):
    """The instance product for a CompiledGrammar — its instance_grammar / tables /
    pda (the fields the artefact no longer carries; memoised per (grammar, fold))."""
    return _model_product(cg.codegen_grammar, cg.fold)


def compiled() -> CompiledGrammar:
    """Compile the tiny ``"a" "b"`` products-test grammar (test_products.py)."""
    return compile_text(PRODUCTS_GRAMMAR_TEXT, cache_key="products-test-grammar")
