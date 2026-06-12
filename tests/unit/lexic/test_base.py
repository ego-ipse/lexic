"""Unit tests for src/lexic/ir/test_base.py"""

from __future__ import annotations

from typing import ClassVar, List, Optional

import pytest

from lexic.base import GrammarModel
from lexic.compile import compile_from_path
from lexic.exceptions import UnsupportedConstructError
from lexic.ir.base import IrNone
from lexic.ir.nodes import IrCharClass, IrItem, IrLiteral, IrQuantifier, IrRuleRef
from lexic.ir.spec import RuleSpec
from tests.paths import GROUND_TRUTH
from tests.unit.lexic.conftest import make_ident_spec

# ── value_str ─────────────────────────────────────────────────────────────────


def test_to_text_value_str():
    """to_text() emits the raw value for value_str specs."""
    spec = RuleSpec(
        "ws",
        "Ws",
        "GrammarModel",
        "value_str",
        items=[IrItem(IrCharClass(" \\t\\n"), IrQuantifier(0, IrNone))],
        field_map={},
    )

    class Ws(GrammarModel):
        """Whitespace rule."""

        __grammar__: ClassVar[RuleSpec] = spec
        value: str

    assert Ws(value="  ").to_text() == "  "
    assert Ws(value="").to_text() == ""
    assert Ws(value="\n\t").to_text() == "\n\t"


# ── sequence with literal (literal baked in) ──────────────────────────────────


def test_to_text_sequence_emits_literal():
    """to_text() concatenates literal tokens between field values."""
    spec = RuleSpec(
        "eq-expr",
        "EqExpr",
        "GrammarModel",
        "sequence",
        items=[
            IrItem(IrCharClass("a-z")),
            IrItem(IrLiteral("=")),
            IrItem(IrCharClass("0-9")),
        ],
        field_map={"first": 0, "second": 2},
    )

    class EqExpr(GrammarModel):
        """Equality expression."""

        __grammar__: ClassVar[RuleSpec] = spec
        first: str
        second: str

    assert EqExpr(first="x", second="1").to_text() == "x=1"


# ── sequence with nested GrammarModel ─────────────────────────────────────────


def test_to_text_nested_grammar_model():
    """Nested GrammarModel fields are emitted recursively."""
    ws_spec = RuleSpec("ws", "Ws", "GrammarModel", "value_str", items=[], field_map={})

    class Ws(GrammarModel):
        """Whitespace model."""

        __grammar__: ClassVar[RuleSpec] = ws_spec
        value: str

    ident_spec = RuleSpec(
        "ident",
        "Ident",
        "GrammarModel",
        "sequence",
        items=[
            IrItem(IrCharClass("a-z")),
            IrItem(IrRuleRef("ws")),
        ],
        field_map={"first": 0, "ws": 1},
    )

    class Ident(GrammarModel):
        """Identifier model."""

        __grammar__: ClassVar[RuleSpec] = ident_spec
        first: str
        ws: Ws

    inst = Ident(first="x", ws=Ws(value=" "))
    assert inst.to_text() == "x "


# ── sequence with List field ──────────────────────────────────────────────────


def test_to_text_list_of_grammar_model():
    """List-typed fields emit each element in order."""
    item_spec = RuleSpec(
        "it", "It", "GrammarModel", "value_str", items=[], field_map={}
    )

    class It(GrammarModel):
        """Item model."""

        __grammar__: ClassVar[RuleSpec] = item_spec
        value: str

    root_spec = RuleSpec(
        "root",
        "Root",
        "GrammarModel",
        "sequence",
        items=[IrItem(IrRuleRef("it"), IrQuantifier(1, IrNone))],
        field_map={"it": 0},
    )

    class Root(GrammarModel):
        """Root model."""

        __grammar__: ClassVar[RuleSpec] = root_spec
        it: List[It]

    inst = Root(it=[It(value="a"), It(value="b"), It(value="c")])
    assert inst.to_text() == "abc"


# ── Optional field absent ─────────────────────────────────────────────────────


def test_to_text_optional_absent():
    """Optional-typed fields that are None are omitted from output."""
    ws_spec = RuleSpec("ws", "Ws", "GrammarModel", "value_str", items=[], field_map={})

    class Ws(GrammarModel):
        """Whitespace model."""

        __grammar__: ClassVar[RuleSpec] = ws_spec
        value: str

    spec = RuleSpec(
        "r",
        "R",
        "GrammarModel",
        "sequence",
        items=[IrItem(IrCharClass("a-z")), IrItem(IrRuleRef("ws"), IrQuantifier(0, 1))],
        field_map={"first": 0, "ws": 1},
    )

    class R(GrammarModel):
        """R model with optional whitespace."""

        __grammar__: ClassVar[RuleSpec] = spec
        first: str
        ws: Optional[Ws] = None

    assert R(first="x", ws=None).to_text() == "x"
    assert R(first="x", ws=Ws(value=" ")).to_text() == "x "


# ── alternation (abstract) raises ─────────────────────────────────────────────


def test_to_text_alternation_raises():
    """Calling to_text() on an abstract alternation class raises NotImplementedError."""
    spec = RuleSpec(
        "base",
        "Base",
        "GrammarModel",
        "alternation",
        items=[],
        field_map={},
    )

    class Base(GrammarModel):
        """Abstract base model."""

        __grammar__: ClassVar[RuleSpec] = spec

    with pytest.raises(NotImplementedError):
        Base().to_text()


# ── semantic_dump excludes ws fields ─────────────────────────────────────────


def test_semantic_dump_excludes_ws():
    """semantic_dump() omits fields listed in non_semantic_fields."""
    ws_spec = RuleSpec("ws", "Ws", "GrammarModel", "value_str", items=[], field_map={})

    class Ws(GrammarModel):
        """Whitespace model."""

        __grammar__: ClassVar[RuleSpec] = ws_spec
        value: str

    spec = make_ident_spec(non_semantic_fields=frozenset({"ws"}))

    class Ident(GrammarModel):
        """Identifier model."""

        __grammar__: ClassVar[RuleSpec] = spec
        first: str
        ws: Ws

    inst = Ident(first="x", ws=Ws(value=" "))
    d = inst.semantic_dump()
    assert "first" in d
    assert "ws" not in d


# ── to_grammar ────────────────────────────────────────────────────────────────


def test_to_grammar_returns_string_no_trailing_newline():
    """to_grammar() returns a string with no trailing newline."""
    cg = compile_from_path(GROUND_TRUTH / "arithmetic.gbnf")
    inst = cg.parse("x=1\n")
    result = inst.to_grammar()
    assert isinstance(result, str)
    assert not result.endswith("\n")


def test_to_grammar_default_flavour_is_gbnf():
    """Default flavour for to_grammar() is gbnf."""
    cg = compile_from_path(GROUND_TRUTH / "arithmetic.gbnf")
    inst = cg.parse("x=1\n")
    assert inst.to_grammar() == inst.to_grammar("gbnf")


def test_to_grammar_contains_rule_name():
    """to_grammar() output contains the rule name."""
    cg = compile_from_path(GROUND_TRUTH / "arithmetic.gbnf")
    inst = cg.parse("x=1\n")
    result = inst.to_grammar()
    assert inst.__grammar__.rule_name in result


def test_to_grammar_unknown_flavour_raises():
    """Unknown flavour raises UnsupportedConstructError."""
    cg = compile_from_path(GROUND_TRUTH / "arithmetic.gbnf")
    inst = cg.parse("x=1\n")
    with pytest.raises(UnsupportedConstructError):
        inst.to_grammar("xyz_unknown_flavour")
