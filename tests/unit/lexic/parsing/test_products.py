"""Tests for lexic.parsing.products — the two product entries + their
per-identity memoisation.

``parse_reduced``/``parse_model`` are the PDA-first product entries; the
tests here exercise them directly (rather than through ``compile.py``'s
thin wrappers, already covered in ``test_compile.py``) and pin the parts of
the module those wrappers never touch: the Earley-completion entries as a
route-forcing seam, ``_reduce_product``/``_model_product`` memoisation by
object identity (including the ``reset_product_cache`` test seam), and the
two boundary checks (``_as_ast``'s type narrowing, ``parse_reduced``'s
reducer-shape guard).
"""

from __future__ import annotations

from typing import cast

import pytest

from lexic.exceptions import UnsupportedConstructError
from lexic.grammars.gbnf import GBNF_FLAVOUR
from lexic.ir.nodes import IrAst
from lexic.model import GrammarModel
from lexic.parsing.earley.normalize import normalize
from lexic.parsing.earley.reduce import Reducer
from lexic.parsing.fold import lift_optional_nullables
from lexic.parsing.products import (
    _as_ast,
    _model_product,
    _reduce_product,
    earley_model,
    earley_reduce,
    parse_model,
    parse_reduced,
    reset_product_cache,
)
from tests.unit.lexic.parsing.parsing_helpers import compiled

# ── the Earley completions (route-forcing seam) ────────────────────────────


def test_earley_reduce_returns_ir_ast():
    """earley_reduce folds grammar text straight to IR over a normalised grammar."""
    text = 'root ::= "x" | "y"\n'
    ast = earley_reduce(normalize(GBNF_FLAVOUR.grammar), text, GBNF_FLAVOUR.reducer)
    assert isinstance(ast, IrAst)
    assert [r.name for r in ast.rules] == ["root"]


def test_earley_model_returns_model_and_round_trips():
    """earley_model parses instance text over the instance grammar + fold,
    with pre-built run-collapsed tables supplied."""
    cg = compiled()
    product = _model_product(cg.codegen_grammar, cg.fold)
    model = earley_model(product.instance_grammar, "ab", cg.fold, product.tables)
    assert isinstance(model, GrammarModel)
    assert model.to_text() == "ab"


def test_earley_model_compiles_its_own_tables_when_none_supplied():
    """earley_model's tables parameter is optional — omitting it compiles plain
    (non-collapsed) tables internally rather than requiring the caller to."""
    cg = compiled()
    product = _model_product(cg.codegen_grammar, cg.fold)
    model = earley_model(product.instance_grammar, "ab", cg.fold)
    assert isinstance(model, GrammarModel)
    assert model.to_text() == "ab"


# ── the product entries agree with their Earley completions ────────────────


def test_parse_reduced_matches_earley_reduce_completion():
    """parse_reduced (PDA-first) and earley_reduce (the forced completion, over
    the normalised grammar) agree on the same grammar-text input."""
    text = 'root ::= "x" "y" | "z"\n'
    got = parse_reduced(GBNF_FLAVOUR.grammar, text, GBNF_FLAVOUR.reducer)
    expected = earley_reduce(
        normalize(GBNF_FLAVOUR.grammar), text, GBNF_FLAVOUR.reducer
    )
    assert got == expected


def test_parse_model_matches_earley_model_completion():
    """parse_model (PDA-first) and earley_model (the forced completion) agree
    on the same instance-text input."""
    cg = compiled()
    got = parse_model(cg.codegen_grammar, "ab", cg.fold)
    product = _model_product(cg.codegen_grammar, cg.fold)
    expected = earley_model(product.instance_grammar, "ab", cg.fold, product.tables)
    assert isinstance(got, GrammarModel)
    assert isinstance(expected, GrammarModel)
    assert got.semantic_dump() == expected.semantic_dump()
    assert got.to_text() == "ab"


def test_reduce_product_earley_grammar_is_lifted_before_normalizing():
    """``_reduce_product.earley_grammar`` is ``normalize(lift_optional_nullables
    (grammar))`` — the SAME lifted, normalised grammar the reduce PDA compiles
    over, not the plain (un-lifted) ``normalize(grammar)`` a stale completion
    route would use. A PDA/completion item-position mismatch on a grammar with
    an ``R?`` over a nullable ``R`` is exactly what this pins against."""
    product = _reduce_product(GBNF_FLAVOUR.grammar, GBNF_FLAVOUR.reducer)
    assert product.earley_grammar == normalize(
        lift_optional_nullables(GBNF_FLAVOUR.grammar)
    )


# ── per-identity memoisation ────────────────────────────────────────────────


def test_reduce_product_is_the_same_object_for_the_same_identity():
    """Two calls with the identical (grammar, reducer) objects return the
    SAME compiled product — no recompilation."""
    first = _reduce_product(GBNF_FLAVOUR.grammar, GBNF_FLAVOUR.reducer)
    second = _reduce_product(GBNF_FLAVOUR.grammar, GBNF_FLAVOUR.reducer)
    assert first is second


def test_model_product_is_the_same_object_for_the_same_identity():
    """Two calls with the identical (grammar, fold) objects return the SAME
    compiled product — no recompilation."""
    cg = compiled()
    first = _model_product(cg.codegen_grammar, cg.fold)
    second = _model_product(cg.codegen_grammar, cg.fold)
    assert first is second


def test_reset_product_cache_forces_reduce_product_recompilation():
    """reset_product_cache drops the reduce cache — the next call for the same
    identity recompiles rather than reusing the stale product."""
    first = _reduce_product(GBNF_FLAVOUR.grammar, GBNF_FLAVOUR.reducer)
    reset_product_cache()
    second = _reduce_product(GBNF_FLAVOUR.grammar, GBNF_FLAVOUR.reducer)
    assert first is not second
    assert first.grammar is second.grammar
    assert first.reducer is second.reducer


def test_reset_product_cache_forces_model_product_recompilation():
    """reset_product_cache drops the model cache — the next call for the same
    identity recompiles rather than reusing the stale product."""
    cg = compiled()
    first = _model_product(cg.codegen_grammar, cg.fold)
    reset_product_cache()
    second = _model_product(cg.codegen_grammar, cg.fold)
    assert first is not second
    assert first.grammar is second.grammar
    assert first.fold is second.fold


# ── boundary checks ─────────────────────────────────────────────────────────


def test_as_ast_returns_an_ir_ast_value_unchanged():
    """_as_ast is a pure narrowing — an IrAst value passes through as-is."""
    ast = earley_reduce(
        normalize(GBNF_FLAVOUR.grammar), 'root ::= "x"\n', GBNF_FLAVOUR.reducer
    )
    assert _as_ast(ast) is ast


def test_as_ast_raises_on_a_non_ir_ast_value():
    """_as_ast raises UnsupportedConstructError on anything that isn't an IrAst —
    the reduction producing a non-IrAst value would otherwise pass silently."""
    with pytest.raises(UnsupportedConstructError):
        _as_ast("not an IrAst")


def test_parse_reduced_raises_on_a_non_reducer():
    """parse_reduced's reducer-shape guard: a reducer that isn't a Reducer
    instance is rejected before any parse is attempted."""
    with pytest.raises(UnsupportedConstructError):
        parse_reduced(
            GBNF_FLAVOUR.grammar, 'root ::= "x"\n', cast(Reducer, "not-a-reducer")
        )
