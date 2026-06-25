"""Tests for lexic.parsing_2.__init__ — the package's public API surface.

API changes:

- ``build_tree`` (free function) removed → ``BUILD_TREE`` singleton (``BuildTree``
  instance) is the new export. The test is updated to import and check
  ``BUILD_TREE`` instead.

- ``Link`` and ``Links`` are new re-exports (added to ``__all__``).

Removed test: ``test_build_tree_re_exported_from_package`` (targeted the
removed ``build_tree`` free function). Replaced by
``test_build_tree_singleton_re_exported_from_package`` which covers the new
``BUILD_TREE`` singleton.
"""

from __future__ import annotations

from lexic.parsing_2 import (
    BUILD_TREE,
    EARLEY_OPS,
    Chart,
    Column,
    Complete,
    EarleyItem,
    EarleyParser,
    Link,
    Links,
    ParseTree,
    Predict,
    Reducer,
    Scan,
    SppfNode,
    derivations,
    is_ambiguous,
    parse,
    parse_forest,
    recognize,
)
from lexic.parsing_2.chart import Chart as ChartDirect
from lexic.parsing_2.chart import Column as ColumnDirect
from lexic.parsing_2.chart import Link as LinkDirect
from lexic.parsing_2.chart import Links as LinksDirect
from lexic.parsing_2.engine import EarleyParser as EarleyParserDirect
from lexic.parsing_2.forest import BUILD_TREE as BUILD_TREE_DIRECT
from lexic.parsing_2.forest import ParseTree as ParseTreeDirect
from lexic.parsing_2.forest import SppfNode as SppfNodeDirect
from lexic.parsing_2.item import EarleyItem as EarleyItemDirect
from lexic.parsing_2.ops import EARLEY_OPS as EARLEY_OPS_DIRECT
from lexic.parsing_2.ops import Complete as CompleteDirect
from lexic.parsing_2.ops import Predict as PredictDirect
from lexic.parsing_2.ops import Scan as ScanDirect
from lexic.parsing_2.reduce import Reducer as ReducerDirect


def test_chart_re_exported_from_package():
    """Chart is re-exported from the package top-level."""
    assert Chart is ChartDirect


def test_column_re_exported_from_package():
    """Column is re-exported from the package top-level."""
    assert Column is ColumnDirect


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


def test_earley_ops_re_exported_from_package():
    """EARLEY_OPS is re-exported from the package top-level."""
    assert EARLEY_OPS is EARLEY_OPS_DIRECT


def test_predict_re_exported_from_package():
    """Predict is re-exported from the package top-level."""
    assert Predict is PredictDirect


def test_scan_re_exported_from_package():
    """Scan is re-exported from the package top-level."""
    assert Scan is ScanDirect


def test_complete_re_exported_from_package():
    """Complete is re-exported from the package top-level."""
    assert Complete is CompleteDirect


# ── New SPPF exports ──────────────────────────────────────────────────


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
