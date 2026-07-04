"""Tests for lexic.ir.__init__: public surface re-exported from the package."""

from __future__ import annotations

import importlib

from lexic import ir
from lexic.ir.base import IrNone
from lexic.ir.base import IrNoneType as _IrNoneType


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
        obj = getattr(ir, name, IrNone)
        assert obj is not None or name == "IrNone", (
            f"lexic.ir.{name} resolved to None (should only happen for IrNone itself)"
        )


# ── Spot-checks for key symbols ───────────────────────────────────────


def test_ir_none_exported() -> None:
    """IrNone sentinel is re-exported from lexic.ir."""
    assert hasattr(ir, "IrNone")
    assert ir.IrNone is IrNone


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
    ):
        assert hasattr(ir, name), f"Core node type {name!r} missing from lexic.ir"
        assert name in ir.__all__, f"Core node type {name!r} missing from __all__"


def test_retired_spec_and_derive_symbols_not_exported() -> None:
    """The RuleSpec/derive/topo surface died in Task 6 — none re-exported.

    ``RuleSpec`` (``ir/spec.py``), ``derive_specs`` and its helpers
    (``ir/derive.py``), ``render_specs`` (``ir/emit.py``) and ``topo_sort``
    (``ir/topo.py``) are gone; their successors live in ``lexic.codegen``
    (binding view + passes) and ``lexic.ir.order``.
    """
    for name in (
        "RuleSpec",
        "derive_specs",
        "classify_kind",
        "compute_parents",
        "has_ruleref",
        "hoist_helpers",
        "render_specs",
        "topo_sort",
    ):
        assert not hasattr(ir, name), f"{name!r} should be gone from lexic.ir"
        assert name not in ir.__all__, f"{name!r} should be gone from __all__"


def test_action_algebra_exported() -> None:
    """Action-algebra nodes are re-exported."""
    for name in (
        "IrAction",
        "IrChild",
        "IrChildren",
        "IrConcat",
        "IrCond",
        "IrField",
        "IrIndex",
        "IrJoin",
        "IrReturn",
    ):
        assert hasattr(ir, name), f"{name!r} missing from lexic.ir"
        assert name in ir.__all__, f"{name!r} missing from __all__"


def test_rule_order_exported() -> None:
    """RuleOrder (topo_sort's successor) is re-exported from lexic.ir."""
    assert hasattr(ir, "RuleOrder")
    assert "RuleOrder" in ir.__all__


def test_directives_not_exported() -> None:
    """parse_directives moved to lexic.parsing.directives — no longer an ir export."""
    assert not hasattr(ir, "parse_directives")
    assert "parse_directives" not in ir.__all__


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


def test_new_algebra_ops_are_public() -> None:
    """Phase-0a algebra ops are re-exported (IrOp replaces the abandoned Cmp)."""
    for name in ("IrScalar", "IrInt", "IrOp", "IrCompare", "IrAnd"):
        assert hasattr(ir, name), name
        assert name in ir.__all__, name
