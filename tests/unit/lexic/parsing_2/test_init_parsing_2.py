"""Tests for lexic.parsing_2.__init__ — the package's public API surface."""

from __future__ import annotations

from lexic.parsing_2 import (
    EARLEY_OPS,
    Chart,
    Column,
    Complete,
    EarleyItem,
    EarleyParser,
    ParseTree,
    Predict,
    Reducer,
    Scan,
    build_tree,
    parse,
    recognize,
)
from lexic.parsing_2.chart import Chart as ChartDirect
from lexic.parsing_2.chart import Column as ColumnDirect
from lexic.parsing_2.engine import EarleyParser as EarleyParserDirect
from lexic.parsing_2.engine import parse as parse_direct
from lexic.parsing_2.engine import recognize as recognize_direct
from lexic.parsing_2.forest import ParseTree as ParseTreeDirect
from lexic.parsing_2.forest import build_tree as build_tree_direct
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


def test_earley_parser_re_exported_from_package():
    """EarleyParser is re-exported from the package top-level."""
    assert EarleyParser is EarleyParserDirect


def test_earley_item_re_exported_from_package():
    """EarleyItem is re-exported from the package top-level."""
    assert EarleyItem is EarleyItemDirect


def test_parse_tree_re_exported_from_package():
    """ParseTree is re-exported from the package top-level."""
    assert ParseTree is ParseTreeDirect


def test_build_tree_re_exported_from_package():
    """build_tree is re-exported from the package top-level."""
    assert build_tree is build_tree_direct


def test_reducer_re_exported_from_package():
    """Reducer is re-exported from the package top-level."""
    assert Reducer is ReducerDirect


def test_recognize_re_exported_from_package():
    """recognize is re-exported from the package top-level."""
    assert recognize is recognize_direct


def test_parse_re_exported_from_package():
    """parse is re-exported from the package top-level."""
    assert parse is parse_direct


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
