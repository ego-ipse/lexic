# tests/test_base.py
from __future__ import annotations

from typing import ClassVar, List, Optional
from base import GrammarModel
from codegen.ir import CharClassAtom, LiteralAtom, RuleRefAtom, RuleSpec


# ── value_str ─────────────────────────────────────────────────────────────────


def test_to_text_value_str():
    spec = RuleSpec(
        "ws",
        "Ws",
        "GrammarModel",
        "value_str",
        items=[CharClassAtom("[ \\t\\n]", 0, None)],
        field_map={},
    )

    class Ws(GrammarModel):
        __grammar__: ClassVar[RuleSpec] = spec
        value: str

    assert Ws(value="  ").to_text() == "  "
    assert Ws(value="").to_text() == ""
    assert Ws(value="\n\t").to_text() == "\n\t"


# ── sequence with literal (literal baked in) ──────────────────────────────────


def test_to_text_sequence_emits_literal():
    spec = RuleSpec(
        "eq-expr",
        "EqExpr",
        "GrammarModel",
        "sequence",
        items=[
            CharClassAtom("[a-z]", 1, 1),
            LiteralAtom("="),
            CharClassAtom("[0-9]", 1, 1),
        ],
        field_map={"first": 0, "second": 2},
    )

    class EqExpr(GrammarModel):
        __grammar__: ClassVar[RuleSpec] = spec
        first: str
        second: str

    assert EqExpr(first="x", second="1").to_text() == "x=1"


# ── sequence with nested GrammarModel ─────────────────────────────────────────


def test_to_text_nested_grammar_model():
    ws_spec = RuleSpec("ws", "Ws", "GrammarModel", "value_str", items=[], field_map={})

    class Ws(GrammarModel):
        __grammar__: ClassVar[RuleSpec] = ws_spec
        value: str

    ident_spec = RuleSpec(
        "ident",
        "Ident",
        "GrammarModel",
        "sequence",
        items=[
            CharClassAtom("[a-z]", 1, 1),
            RuleRefAtom("ws", 1, 1),
        ],
        field_map={"first": 0, "ws": 1},
    )

    class Ident(GrammarModel):
        __grammar__: ClassVar[RuleSpec] = ident_spec
        first: str
        ws: Ws

    inst = Ident(first="x", ws=Ws(value=" "))
    assert inst.to_text() == "x "


# ── sequence with List field ──────────────────────────────────────────────────


def test_to_text_list_of_grammar_model():
    item_spec = RuleSpec(
        "it", "It", "GrammarModel", "value_str", items=[], field_map={}
    )

    class It(GrammarModel):
        __grammar__: ClassVar[RuleSpec] = item_spec
        value: str

    root_spec = RuleSpec(
        "root",
        "Root",
        "GrammarModel",
        "sequence",
        items=[RuleRefAtom("it", 1, None)],
        field_map={"it": 0},
    )

    class Root(GrammarModel):
        __grammar__: ClassVar[RuleSpec] = root_spec
        it: List[It]

    inst = Root(it=[It(value="a"), It(value="b"), It(value="c")])
    assert inst.to_text() == "abc"


# ── Optional field absent ─────────────────────────────────────────────────────


def test_to_text_optional_absent():
    ws_spec = RuleSpec("ws", "Ws", "GrammarModel", "value_str", items=[], field_map={})

    class Ws(GrammarModel):
        __grammar__: ClassVar[RuleSpec] = ws_spec
        value: str

    spec = RuleSpec(
        "r",
        "R",
        "GrammarModel",
        "sequence",
        items=[CharClassAtom("[a-z]", 1, 1), RuleRefAtom("ws", 0, 1)],
        field_map={"first": 0, "ws": 1},
    )

    class R(GrammarModel):
        __grammar__: ClassVar[RuleSpec] = spec
        first: str
        ws: Optional[Ws] = None

    assert R(first="x", ws=None).to_text() == "x"
    assert R(first="x", ws=Ws(value=" ")).to_text() == "x "


# ── alternation (abstract) raises ─────────────────────────────────────────────


def test_to_text_alternation_raises():
    from codegen.ir import AlternationAtom
    import pytest

    spec = RuleSpec(
        "base",
        "Base",
        "GrammarModel",
        "alternation",
        items=[AlternationAtom(["a", "b"])],
        field_map={},
    )

    class Base(GrammarModel):
        __grammar__: ClassVar[RuleSpec] = spec

    with pytest.raises(NotImplementedError):
        Base().to_text()


# ── semantic_dump excludes ws fields ─────────────────────────────────────────


def test_semantic_dump_excludes_ws():
    ws_spec = RuleSpec("ws", "Ws", "GrammarModel", "value_str", items=[], field_map={})

    class Ws(GrammarModel):
        __grammar__: ClassVar[RuleSpec] = ws_spec
        value: str

    spec = RuleSpec(
        "ident",
        "Ident",
        "GrammarModel",
        "sequence",
        items=[CharClassAtom("[a-z]", 1, 1), RuleRefAtom("ws", 1, 1)],
        field_map={"first": 0, "ws": 1},
    )

    class Ident(GrammarModel):
        __grammar__: ClassVar[RuleSpec] = spec
        first: str
        ws: Ws

    inst = Ident(first="x", ws=Ws(value=" "))
    d = inst.semantic_dump()
    assert "first" in d
    assert "ws" not in d
