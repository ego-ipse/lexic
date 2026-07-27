"""Tests for lexic.ir.__init__: public surface re-exported from the package."""

from __future__ import annotations

import ast as pyast
import importlib
from importlib import import_module

import pytest

from lexic import ir
from lexic.compile import compile_from_path
from lexic.compile.notation.emit import ir_doc
from lexic.grammars.abnf import ABNF_GRAMMAR
from lexic.grammars.gbnf import GBNF_GRAMMAR
from lexic.ir.spine.spine import IrNone
from lexic.ir.spine.spine import IrNoneType as _IrNoneType
from lexic.ir.spine.records import IrTuple
from lexic.ir.spine.scalars import IrInt, IrStr
from tests.paths import GBNF_GRAMMARS, GROUND_TRUTH, PROJECT_ROOT


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
    (``ir/topo.py``) are gone; their successors live in ``lexic.compile``
    (binding view + passes) and ``lexic.ir.grammar.order``.
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


# ── the surface is closed under what emission spells ──────────────────────


def _spine_values() -> list[tuple[str, object]]:
    """Values lexic itself produces and can write into an importable module."""
    out: list[tuple[str, object]] = [
        ("gbnf-self", GBNF_GRAMMAR),
        ("abnf-self", ABNF_GRAMMAR),
        # A bare tuple is what a reduced document is BUILT of — the `ir` target
        # of any grammar whose reduction yields spine tuples.
        ("bare-tuple", IrTuple(IrStr("a"), IrStr("b"))),
        ("nested-tuple", IrTuple(IrTuple(IrStr("a")), IrInt(1))),
    ]
    out += [
        (stem, compile_from_path(GROUND_TRUTH / stem).grammar) for stem in GBNF_GRAMMARS
    ]
    return out


@pytest.mark.parametrize("label,value", _spine_values())
def test_public_surface_names_every_symbol_emission_spells(
    label: str, value: object
) -> None:
    """A module holding a spine value imports its symbols from ``lexic.ir``.

    So the surface has to be closed under what the notation SPELLS for the
    values lexic produces — otherwise a generated module names something it
    cannot import. ``load_ir``'s own ``SYMBOLS`` table is complete (it is built
    from the private modules); the public surface is the one a header reads.
    """
    spelled = set(ir_doc(value).symbols)
    assert spelled <= set(ir.__all__), (
        f"{label}: emission spells {sorted(spelled - set(ir.__all__))}, "
        "which no generated module could import from lexic.ir"
    )


def _assigned(node: pyast.stmt) -> list[str]:
    """The names a top-level assignment binds, annotated or not."""
    if isinstance(node, pyast.AnnAssign):
        return [node.target.id] if isinstance(node.target, pyast.Name) else []
    if isinstance(node, pyast.Assign):
        return [t.id for t in node.targets if isinstance(t, pyast.Name)]
    return []


def _public_names() -> dict[str, str]:
    """Every public top-level name each ir module defines, and where."""
    found: dict[str, str] = {}
    for path in sorted((PROJECT_ROOT / "src" / "lexic" / "ir").glob("*.py")):
        if path.name == "__init__.py":
            continue
        for node in pyast.parse(path.read_text(encoding="utf-8")).body:
            if isinstance(node, (pyast.ClassDef, pyast.FunctionDef)):
                if not node.name.startswith("_"):
                    found[node.name] = f"lexic.ir.{path.stem}"
            elif isinstance(node, pyast.Assign):
                for target in node.targets:
                    named = isinstance(target, pyast.Name)
                    if (
                        named
                        and not target.id.startswith("_")
                        and target.id[0].isupper()
                    ):
                        found[target.id] = f"lexic.ir.{path.stem}"
    return found


def test_the_facade_exports_every_public_name_in_the_package() -> None:
    """A surface that omits what consumers need is a surface they bypass.

    It once exported 70 of 120 public names — no ``layout``, no ``IrFlavour``,
    no ``IrLambda``, no ``IrDispatch`` — and 503 import sites reached past it
    into the submodules, which is what a partial façade earns.
    """
    missing = sorted(set(_public_names()) - set(ir.__all__))
    assert not missing, f"public but not on the façade: {missing}"


def _facade_source() -> tuple[dict[str, str], set[str]]:
    """The façade's ``_HOMES`` map and its eagerly-bound names, read structurally.

    From the SOURCE, as the package root's own pin does: the map is private, and
    a test that reads it as an attribute asserts against something the module
    does not offer.
    """
    tree = pyast.parse(
        (PROJECT_ROOT / "src" / "lexic" / "ir" / "__init__.py").read_text("utf-8")
    )
    homed: dict[str, str] = {}
    for node in pyast.walk(tree):
        if not isinstance(node, pyast.Assign) or not isinstance(node.value, pyast.Dict):
            continue
        if not any(
            isinstance(t, pyast.Name) and t.id == "_HOMES" for t in node.targets
        ):
            continue
        for key, home in zip(node.value.keys, node.value.values):
            if isinstance(key, pyast.Constant) and isinstance(home, pyast.Constant):
                homed[str(key.value)] = str(home.value)
    eager = {
        alias.name
        for node in tree.body
        if isinstance(node, pyast.ImportFrom)
        and node.module
        and node.module.startswith("lexic.ir")
        for alias in node.names
    } - {"IrSelf"}
    return homed, eager


def test_the_type_checking_block_names_the_same_modules_as_homes() -> None:
    """The static declarations and the runtime lookup must point at one module.

    They can disagree silently: a ``TYPE_CHECKING`` import of a module that no
    longer exists costs NOTHING at runtime — ``__getattr__`` still resolves the
    name — and only a type checker notices, by quietly widening every one of
    those names to the façade's return type. It happened to 15 names the moment
    ``base`` split into three, because ``_HOMES`` was repointed and the block
    was not.
    """
    tree = pyast.parse(
        (PROJECT_ROOT / "src" / "lexic" / "ir" / "__init__.py").read_text("utf-8")
    )
    declared = {
        alias.name: node.module
        for block in tree.body
        if isinstance(block, pyast.If)
        for node in pyast.walk(block)
        if isinstance(node, pyast.ImportFrom) and node.module
        for alias in node.names
    }
    homed, _ = _facade_source()
    disagree = {
        n: (declared[n], homed[n])
        for n in declared
        if homed.get(n, declared[n]) != declared[n]
    }
    assert not disagree, f"declared vs _HOMES: {disagree}"


def test_the_three_statements_of_the_surface_agree() -> None:
    """``__all__``, ``_HOMES`` and the eager bindings are one surface.

    It is stated three times because three consumers read it — the type
    checker, the export machinery, and the runtime lookup — so a name joins by
    joining all three or the façade lies to one of them.
    """
    homed, eager = _facade_source()
    assert set(ir.__all__) == set(homed) | eager
    assert not (set(homed) & eager), "a name is both lazy and eager"


def test_every_exported_name_resolves_to_its_recorded_module() -> None:
    """``_HOMES`` says where each name lives; that module has to define it.

    Asked of the MODULE, not of the value's ``__module__``: a type alias like
    ``IrDoc`` reports ``typing`` as its module and is still exactly what
    ``lexic.ir.text.layout`` defines under that name.
    """
    homed, _ = _facade_source()
    for name, home in homed.items():
        assert getattr(import_module(home), name) is getattr(ir, name), (name, home)
