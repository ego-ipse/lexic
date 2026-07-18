"""Tests for compile/binding.py — the per-rule binding view.

The actual test bodies live in :mod:`tests.unit.lexic.compile.binding_cases`, bound here to
:mod:`lexic.compile.binding`.
"""

from __future__ import annotations

from typing import NamedTuple

import pytest

from lexic.compile import (
    _fold_config,
    binding,
    build_codegen_grammar,
    canonical_grammar,
    compute_binding,
    synthesize,
)
from lexic.compile.binding import (
    RuleBinding,
    RuleKind,
    check_supplied_class,
    field_kwargs,
)
from lexic.exceptions import UnsupportedConstructError
from lexic.grammars import get_flavour
from lexic.ir.base import IrLambda
from lexic.ir.bind import IrBind
from lexic.ir.mapping import IrMap
from lexic.parsing.fold import ModelBody
from tests.unit.lexic.compile.binding_cases import make_binding_tests

globals().update(make_binding_tests(binding))


# ── open binding table (settled 7 — compile-only) ─────────────────────
#
# Fixture constructors subclass ``NamedTuple`` / ``dict`` — both carry the
# public-method surface that keeps them ordinary classes to introspect, while
# giving the ``check_supplied_class`` signature the exact ``value`` / ``nope`` /
# ``**kwargs`` shapes under test.


class AcceptsValue(NamedTuple):
    """A constructor accepting the ``value`` fold kwarg."""

    value: object


class RejectsValue(NamedTuple):
    """A constructor accepting ``nope`` — never the ``value`` fold kwarg."""

    nope: object


class AcceptsAnyKw(dict):
    """A constructor with a ``**kwargs`` catch-all — accepts any fold kwarg."""

    def __init__(self, **kwargs: object) -> None:
        super().__init__(**kwargs)


def make_binding(kind: RuleKind, fields: dict) -> RuleBinding:
    """A minimal RuleBinding fixture for the given kind/fields."""
    return RuleBinding("r", "R", (), kind, fields)


def test_field_kwargs_per_kind() -> None:
    """The fold kwargs are ``{value}`` / the field names / ``∅`` per kind."""
    seq = make_binding(
        "sequence", {"head": IrBind(0, "text", True), "tail": IrBind(1, "text", True)}
    )
    assert field_kwargs(make_binding("value_str", {})) == frozenset({"value"})
    assert field_kwargs(make_binding("alternation", {})) == frozenset()
    assert field_kwargs(seq) == frozenset({"head", "tail"})


def test_check_supplied_class_accepts_matching_and_varkw() -> None:
    """A class accepting the field kwargs (or ``**kwargs``) passes the contract."""
    check_supplied_class(AcceptsValue, frozenset({"value"}))
    check_supplied_class(AcceptsAnyKw, frozenset({"a", "b"}))
    check_supplied_class(str, frozenset({"value"}))  # un-introspectable — trusted


def test_check_supplied_class_rejects_missing_kwarg() -> None:
    """A class whose signature omits a fold kwarg raises loudly."""
    with pytest.raises(UnsupportedConstructError):
        check_supplied_class(RejectsValue, frozenset({"value"}))


def compiled_parts(text: str, stem: str) -> tuple:
    """(ast, codegen grammar, binding view, fold config) for GBNF ``text``."""
    ast = canonical_grammar(text, get_flavour("gbnf"))
    codegen = build_codegen_grammar(ast)
    view = compute_binding(codegen)
    classes = synthesize(codegen, view, stem)
    return codegen, view, classes


def body_for(fold_map: IrMap, rule: str) -> ModelBody:
    """The ModelBody bound to ``rule`` in a fold-config IrMap."""
    for ref, body in fold_map.items():
        if str(ref) == rule:
            return body
    raise AssertionError(f"no fold body for {rule!r}")


def test_open_table_uses_authored_modelbody_verbatim() -> None:
    """A per-rule authored ``ModelBody`` override is used unchanged (primitive)."""
    codegen, view, classes = compiled_parts('root ::= "a" "b"', "open_primitive")
    marker = ModelBody("value_str", IrLambda(lambda value: ("OVR", value)), 0, ())
    fold_map = _fold_config(codegen, view, classes, overrides={"root": marker})
    assert body_for(fold_map, "root") is marker


def test_open_table_supplied_class_becomes_the_ctor() -> None:
    """A per-rule supplied class becomes the rule's fold constructor (sugar)."""
    codegen, view, classes = compiled_parts('root ::= "a" "b"', "open_sugar")
    fold_map = _fold_config(codegen, view, classes, overrides={"root": AcceptsValue})
    assert body_for(fold_map, "root").ctor.eval is AcceptsValue


def test_open_table_supplied_class_contract_enforced() -> None:
    """A supplied class rejecting the fold kwargs fails at bind time."""
    codegen, view, classes = compiled_parts('root ::= "a" "b"', "open_bad")
    with pytest.raises(UnsupportedConstructError):
        _fold_config(codegen, view, classes, overrides={"root": RejectsValue})
