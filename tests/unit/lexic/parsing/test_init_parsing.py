"""Tests for lexic.parsing.__init__ — the package's public API surface.

API changes from the int-kernel rework:

- ``EARLEY_OPS``, ``Column``, ``Complete``, ``Predict``, ``Scan`` are GONE
  (``lexic.parsing.ops`` no longer exists — the per-item type dispatch it
  held is compiled away into ``tables.py``'s int-coded ``next_sym``
  discriminator and ``kernel.py``'s flat loop). Their re-export tests are
  dropped.
- New re-exports added and tested here: ``FastTree``, ``Kernel``, ``Link``,
  ``Links``, ``ParserTables``, ``compile_tables`` (``Link``/``Links`` existed
  before this rework too, but were untested at this layer).
"""

from __future__ import annotations

from lexic.grammars.gbnf import GBNF_FLAVOUR
from lexic.ir import IrAst
from lexic.parsing import (
    BUILD_TREE,
    Chart,
    EarleyItem,
    EarleyParser,
    FastCtor,
    FastTree,
    FieldFold,
    Kernel,
    Link,
    Links,
    ModelBody,
    ModelFold,
    ParserTables,
    ParseTree,
    Reducer,
    RuleFold,
    SppfNode,
    compile_tables,
    derivations,
    is_ambiguous,
    lift_optional_nullables,
    normalize,
    parse,
    parse_forest,
    parse_model,
    parse_reduced,
    recognize,
)
from lexic.parsing.earley.chart import Chart as ChartDirect
from lexic.parsing.earley.chart import EarleyItem as EarleyItemDirect
from lexic.parsing.earley.chart import Link as LinkDirect
from lexic.parsing.earley.chart import Links as LinksDirect
from lexic.parsing.earley.engine import EarleyParser as EarleyParserDirect
from lexic.parsing.earley.forest import BUILD_TREE as BUILD_TREE_DIRECT
from lexic.parsing.earley.forest import ParseTree as ParseTreeDirect
from lexic.parsing.earley.forest import SppfNode as SppfNodeDirect
from lexic.parsing.earley.kernel import FastTree as FastTreeDirect
from lexic.parsing.earley.kernel import Kernel as KernelDirect
from lexic.parsing.earley.reduce import Reducer as ReducerDirect
from lexic.parsing.earley.tables import ParserTables as ParserTablesDirect
from lexic.parsing.earley.tables import compile_tables as compile_tables_direct
from lexic.parsing.products import earley_model, earley_reduce


def test_chart_re_exported_from_package():
    """Chart is re-exported from the package top-level."""
    assert Chart is ChartDirect


def test_link_re_exported_from_package():
    """Link is re-exported from the package top-level."""
    assert Link is LinkDirect


def test_links_re_exported_from_package():
    """Links is re-exported from the package top-level."""
    assert Links is LinksDirect


def test_earley_parser_re_exported_from_package():
    """EarleyParser is re-exported from the package top-level."""
    assert EarleyParser is EarleyParserDirect


def test_earley_item_re_exported_from_package():
    """EarleyItem is re-exported from the package top-level."""
    assert EarleyItem is EarleyItemDirect


def test_parse_tree_re_exported_from_package():
    """ParseTree is re-exported from the package top-level."""
    assert ParseTree is ParseTreeDirect


def test_build_tree_singleton_re_exported_from_package():
    """BUILD_TREE singleton is re-exported from the package top-level."""
    assert BUILD_TREE is BUILD_TREE_DIRECT


def test_reducer_re_exported_from_package():
    """Reducer is re-exported from the package top-level."""
    assert Reducer is ReducerDirect


def test_recognize_callable_from_package():
    """recognize is importable and callable from the package top-level."""
    assert callable(recognize)


def test_parse_callable_from_package():
    """parse is importable and callable from the package top-level."""
    assert callable(parse)


# ── SPPF exports ──────────────────────────────────────────────────────


def test_sppf_node_re_exported_from_package():
    """SppfNode is re-exported from the package top-level."""
    assert SppfNode is SppfNodeDirect


def test_parse_forest_callable_from_package():
    """parse_forest is importable and callable from the package top-level."""
    assert callable(parse_forest)


def test_derivations_callable_from_package():
    """derivations is importable and callable from the package top-level."""
    assert callable(derivations)


def test_is_ambiguous_callable_from_package():
    """is_ambiguous is importable and callable from the package top-level."""
    assert callable(is_ambiguous)


# ── New exports from the int-kernel rework ─────────────────────────────


def test_fast_tree_re_exported_from_package():
    """FastTree is re-exported from the package top-level."""
    assert FastTree is FastTreeDirect


def test_kernel_re_exported_from_package():
    """Kernel is re-exported from the package top-level."""
    assert Kernel is KernelDirect


def test_parser_tables_re_exported_from_package():
    """ParserTables is re-exported from the package top-level."""
    assert ParserTables is ParserTablesDirect


def test_compile_tables_re_exported_from_package():
    """compile_tables is re-exported from the package top-level."""
    assert compile_tables is compile_tables_direct


# ── Phase B: the product entries + the new root exports ────────────────


def test_parse_reduced_callable_from_package():
    """parse_reduced is importable and callable from the package top-level."""
    assert callable(parse_reduced)


def test_parse_model_callable_from_package():
    """parse_model is importable and callable from the package top-level."""
    assert callable(parse_model)


def test_new_root_exports_are_reachable():
    """The engine exports its normalisation, fold, and fold-authoring types at
    the package root (what compile.py imports, root-API-only)."""
    for obj in (
        normalize,
        lift_optional_nullables,
        ModelFold,
        ModelBody,
        RuleFold,
        FieldFold,
        FastCtor,
    ):
        assert obj is not None


def test_product_entries_take_the_authored_grammar_pda_first():
    """parse_reduced (the grammar-text product) takes the AUTHORED self-grammar
    and returns the reduced IrAst — PDA-first with the Earley completion inside,
    equal to the forced Earley completion."""
    text = 'root ::= "abc"\n'
    got = parse_reduced(GBNF_FLAVOUR.grammar, text, GBNF_FLAVOUR.reducer)
    assert isinstance(got, IrAst)
    assert got == earley_reduce(
        normalize(GBNF_FLAVOUR.grammar), text, GBNF_FLAVOUR.reducer
    )


def test_earley_completions_are_submodule_importable():
    """The Earley-completion / route-forcing seam lives on the products
    submodule (tests-only), not the package root."""
    assert callable(earley_reduce)
    assert callable(earley_model)
