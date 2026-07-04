"""Unit tests for src/lexic/base.py — GrammarModel over IrRule + IrBind."""

from __future__ import annotations

from typing import Annotated, ClassVar, List, Optional

import pytest

from lexic.base import GrammarModel
from lexic.compile import compile_from_path
from lexic.exceptions import UnsupportedConstructError
from lexic.ir.base import IrNone
from lexic.ir.bind import IrBind
from lexic.ir.nodes import (
    IrAlternation,
    IrCharClass,
    IrChr,
    IrItem,
    IrLiteral,
    IrQuantifier,
    IrRange,
    IrRule,
    IrRuleRef,
    IrSequence,
)
from tests.paths import GROUND_TRUTH

_LOWER = IrCharClass(IrRange(IrChr("a"), IrChr("z")))


def _ws_rule() -> IrRule:
    """ws ::= [ \\t\\n]* — a value_str rule (implicit value field, no binds)."""
    return IrRule(
        "ws",
        IrAlternation(
            IrSequence(
                IrItem(
                    IrCharClass(IrChr(" "), IrChr("\t"), IrChr("\n")),
                    IrQuantifier(0, IrNone),
                )
            )
        ),
    )


class Ws(GrammarModel):
    """Whitespace model — value_str shape."""

    __grammar__: ClassVar[IrRule] = _ws_rule()
    value: str


# ── value_str ─────────────────────────────────────────────────────────────────


def test_to_text_value_str():
    """to_text() emits the raw value for value_str classes."""
    assert Ws(value="  ").to_text() == "  "
    assert Ws(value="").to_text() == ""
    assert Ws(value="\n\t").to_text() == "\n\t"


# ── sequence with literal (literal baked in) ──────────────────────────────────


def test_to_text_sequence_emits_literal():
    """to_text() concatenates unbound literal items between field values."""

    class EqExpr(GrammarModel):
        """Equality expression."""

        __grammar__: ClassVar[IrRule] = IrRule(
            "eq-expr",
            IrAlternation(
                IrSequence(
                    IrItem(_LOWER),
                    IrItem(IrLiteral("=")),
                    IrItem(IrCharClass(IrRange(IrChr("0"), IrChr("9")))),
                )
            ),
        )
        first: Annotated[str, IrBind(0, "text")]
        second: Annotated[str, IrBind(2, "text")]

    assert EqExpr(first="x", second="1").to_text() == "x=1"


# ── sequence with nested GrammarModel ─────────────────────────────────────────


def _ident_rule() -> IrRule:
    """ident ::= [a-z] ws — one text field, one model field."""
    return IrRule(
        "ident",
        IrAlternation(IrSequence(IrItem(_LOWER), IrItem(IrRuleRef("ws")))),
    )


def test_to_text_nested_grammar_model():
    """Nested GrammarModel fields are emitted recursively."""

    class Ident(GrammarModel):
        """Identifier model."""

        __grammar__: ClassVar[IrRule] = _ident_rule()
        first: Annotated[str, IrBind(0, "text")]
        ws: Annotated[Ws, IrBind(1, "model")]

    inst = Ident(first="x", ws=Ws(value=" "))
    assert inst.to_text() == "x "


# ── sequence with List field ──────────────────────────────────────────────────


def test_to_text_list_of_grammar_model():
    """List-typed fields emit each element in order."""

    class It(GrammarModel):
        """Item model."""

        __grammar__: ClassVar[IrRule] = IrRule(
            "it", IrAlternation(IrSequence(IrItem(_LOWER, IrQuantifier(1, IrNone))))
        )
        value: str

    class Root(GrammarModel):
        """Root model."""

        __grammar__: ClassVar[IrRule] = IrRule(
            "root",
            IrAlternation(IrSequence(IrItem(IrRuleRef("it"), IrQuantifier(1, IrNone)))),
        )
        it: Annotated[List[It], IrBind(0, "models")]

    inst = Root(it=[It(value="a"), It(value="b"), It(value="c")])
    assert inst.to_text() == "abc"


# ── Optional field absent ─────────────────────────────────────────────────────


def test_to_text_optional_absent():
    """Optional-typed fields that are None are omitted from output."""

    class R(GrammarModel):
        """R model with optional whitespace."""

        __grammar__: ClassVar[IrRule] = IrRule(
            "r",
            IrAlternation(
                IrSequence(IrItem(_LOWER), IrItem(IrRuleRef("ws"), IrQuantifier(0, 1)))
            ),
        )
        first: Annotated[str, IrBind(0, "text")]
        ws: Annotated[Optional[Ws], IrBind(1, "model")] = None

    assert R(first="x", ws=None).to_text() == "x"
    assert R(first="x", ws=Ws(value=" ")).to_text() == "x "


# ── alternation (abstract) raises ─────────────────────────────────────────────


def test_to_text_alternation_raises():
    """Calling to_text() on an abstract alternation class raises NotImplementedError."""

    class Base(GrammarModel):
        """Abstract base model."""

        __grammar__: ClassVar[IrRule] = IrRule(
            "base",
            IrAlternation(
                IrSequence(IrItem(IrRuleRef("a"))),
                IrSequence(IrItem(IrRuleRef("b"))),
            ),
        )

    with pytest.raises(NotImplementedError):
        Base().to_text()


# ── empty alternate arm ───────────────────────────────────────────────────────


def test_to_text_empty_arm_all_fields_absent_is_empty():
    """A rule with an empty alternate arm emits '' when every field is None."""

    class Pair(GrammarModel):
        """pair ::= "<" x ">" | — all fields Optional."""

        __grammar__: ClassVar[IrRule] = IrRule(
            "pair",
            IrAlternation(
                IrSequence(
                    IrItem(IrLiteral("<")),
                    IrItem(IrRuleRef("ws")),
                    IrItem(IrLiteral(">")),
                ),
                IrSequence(),
            ),
        )
        ws: Annotated[Optional[Ws], IrBind(1, "model")] = None

    assert Pair().to_text() == ""
    assert Pair(ws=Ws(value=" ")).to_text() == "< >"


# ── semantic_dump excludes ws fields ─────────────────────────────────────────


def test_semantic_dump_excludes_ws():
    """semantic_dump() omits fields whose bind carries semantic=False."""

    class Ident(GrammarModel):
        """Identifier model with structural-noise ws."""

        __grammar__: ClassVar[IrRule] = _ident_rule()
        first: Annotated[str, IrBind(0, "text")]
        ws: Annotated[Ws, IrBind(1, "model", False)]

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
    assert str(inst.__grammar__.name) in result


def test_to_grammar_unknown_flavour_raises():
    """Unknown flavour raises UnsupportedConstructError."""
    cg = compile_from_path(GROUND_TRUTH / "arithmetic.gbnf")
    inst = cg.parse("x=1\n")
    with pytest.raises(UnsupportedConstructError):
        inst.to_grammar("xyz_unknown_flavour")
