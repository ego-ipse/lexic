"""Tests for lexic.ir.__init__: public surface re-exported from the package."""

from __future__ import annotations

import importlib

from lexic import ir
from lexic.ir.nodes import IrNone as _IrNone
from lexic.ir.nodes import IrNoneType as _IrNoneType


def test_module_has_all() -> None:
    """lexic.ir defines __all__."""
    assert hasattr(ir, "__all__")


def test_all_names_importable() -> None:
    """Every name in __all__ is importable from lexic.ir."""
    for name in ir.__all__:
        assert hasattr(ir, name), f"lexic.ir is missing __all__ member {name!r}"


def test_all_names_present_in_namespace() -> None:
    """Every name in __all__ resolves to a non-None object."""
    for name in ir.__all__:
        obj = getattr(ir, name, None)
        assert obj is not None or name == "IrNone", (
            f"lexic.ir.{name} resolved to None (should only happen for IrNone itself)"
        )


# ── Spot-checks for key symbols ───────────────────────────────────────


def test_ir_none_exported() -> None:
    """IrNone sentinel is re-exported from lexic.ir."""
    assert hasattr(ir, "IrNone")
    assert ir.IrNone is _IrNone


def test_ir_none_type_exported() -> None:
    """IrNoneType is re-exported from lexic.ir."""
    assert "IrNoneType" in ir.__all__
    assert ir.IrNoneType is _IrNoneType


def test_ir_none_is_instance_of_ir_none_type() -> None:
    """IrNone is an instance of IrNoneType."""
    assert isinstance(ir.IrNone, ir.IrNoneType)


def test_core_node_types_exported() -> None:
    """Core grammar AST node types are all re-exported."""
    for name in (
        "IrLiteral",
        "IrCharClass",
        "IrRuleRef",
        "IrGroup",
        "IrNot",
        "IrItem",
        "IrSequence",
        "IrAlternation",
        "IrRule",
        "IrAst",
        "IrQuantifier",
        "IrSelf",
        "IrNode",
        "IrLeaf",
        "IrAtom",
        "IrComposite",
    ):
        assert hasattr(ir, name), f"Core node type {name!r} missing from lexic.ir"
        assert name in ir.__all__, f"Core node type {name!r} missing from __all__"


def test_rule_spec_exported() -> None:
    """RuleSpec is re-exported from lexic.ir."""
    assert hasattr(ir, "RuleSpec")
    assert "RuleSpec" in ir.__all__


def test_derive_helpers_exported() -> None:
    """derive_specs and helpers are re-exported."""
    for name in (
        "derive_specs",
        "classify_kind",
        "compute_parents",
        "has_ruleref",
        "hoist_helpers",
    ):
        assert hasattr(ir, name), f"{name!r} missing from lexic.ir"
        assert name in ir.__all__, f"{name!r} missing from __all__"


def test_action_algebra_exported() -> None:
    """Action-algebra nodes are re-exported."""
    for name in (
        "IrAction",
        "IrCallable",
        "IrChild",
        "IrChildren",
        "IrConcat",
        "IrCond",
        "IrField",
        "IrJoin",
        "IrReturn",
    ):
        assert hasattr(ir, name), f"{name!r} missing from lexic.ir"
        assert name in ir.__all__, f"{name!r} missing from __all__"


def test_topo_sort_exported() -> None:
    """topo_sort is re-exported from lexic.ir."""
    assert hasattr(ir, "topo_sort")
    assert "topo_sort" in ir.__all__


def test_directives_exported() -> None:
    """Directives and parse_directives are re-exported."""
    assert hasattr(ir, "Directives")
    assert hasattr(ir, "parse_directives")
    assert "Directives" in ir.__all__
    assert "parse_directives" in ir.__all__


def test_walk_exports_present() -> None:
    """IrVisitor and IrTransformer are re-exported."""
    assert hasattr(ir, "IrVisitor")
    assert hasattr(ir, "IrTransformer")
    assert "IrVisitor" in ir.__all__
    assert "IrTransformer" in ir.__all__


def test_no_removed_symbols_in_all() -> None:
    """Removed symbols (IrType, IrStrLeaf, IrCollection) are absent from __all__."""
    removed = {"IrType", "IrStrLeaf", "IrCollection"}
    for name in removed:
        assert name not in ir.__all__, (
            f"Removed symbol {name!r} should not be in __all__"
        )


def test_package_reimport_is_idempotent() -> None:
    """Re-importing lexic.ir returns the same module object."""
    mod = importlib.import_module("lexic.ir")
    assert mod is ir
