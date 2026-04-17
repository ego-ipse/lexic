# tests/test_ir_builder.py
from __future__ import annotations
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

import pytest
from codegen.parser import parse_gbnf
from codegen.ir_builder import IRBuilder
from codegen.ir import (
    AlternationAtom,
    CharClassAtom,
    LiteralAtom,
    RuleRefAtom,
    RuleSpec,
)

GRAMMAR_DIR = Path(__file__).parent.parent / "resources" / "ground_truth"


def _build(grammar_name: str) -> list[RuleSpec]:
    text = (GRAMMAR_DIR / f"{grammar_name}.gbnf").read_text()
    rules = parse_gbnf(text)
    return IRBuilder(rules).build()


def _by_rule(specs: list[RuleSpec]) -> dict[str, RuleSpec]:
    return {s.rule_name: s for s in specs}


# ── Smoke: all 7 grammars ─────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "grammar", ["arithmetic", "c", "chess", "japanese", "json_arr", "json_ws", "list"]
)
def test_all_grammars_produce_specs(grammar: str):
    specs = _build(grammar)
    assert len(specs) > 0
    for spec in specs:
        assert spec.rule_name, f"empty rule_name in {grammar}"
        assert spec.class_name, f"empty class_name in {grammar}"
        assert spec.kind in ("sequence", "alternation", "value_str")


@pytest.mark.parametrize(
    "grammar", ["arithmetic", "c", "chess", "japanese", "json_arr", "json_ws", "list"]
)
def test_root_spec_is_first(grammar: str):
    specs = _build(grammar)
    assert specs[0].rule_name == "root"


# ── arithmetic: rule kinds ───────────────────────────────────────────────────


def test_arithmetic_ws_is_value_str():
    d = _by_rule(_build("arithmetic"))
    assert d["ws"].kind == "value_str"
    assert d["ws"].class_name == "Ws"


def test_arithmetic_ident_is_sequence():
    d = _by_rule(_build("arithmetic"))
    ident = d["ident"]
    assert ident.kind == "sequence"
    assert ident.class_name == "Ident"


def test_arithmetic_term_is_alternation():
    d = _by_rule(_build("arithmetic"))
    term = d["term"]
    assert term.kind == "alternation"
    assert term.class_name == "Term"
    assert len(term.items) == 1
    alt = term.items[0]
    assert isinstance(alt, AlternationAtom)
    assert "ident" in alt.arm_rule_names
    assert "num" in alt.arm_rule_names


# ── arithmetic: ident items and field_map ────────────────────────────────────


def test_arithmetic_ident_items():
    d = _by_rule(_build("arithmetic"))
    ident = d["ident"]
    # ident ::= [a-z] [a-z0-9_]* ws
    assert isinstance(ident.items[0], CharClassAtom)
    assert ident.items[0].min == 1
    assert ident.items[0].max == 1

    assert isinstance(ident.items[1], CharClassAtom)
    assert ident.items[1].min == 0
    assert ident.items[1].max is None

    assert isinstance(ident.items[2], RuleRefAtom)
    assert ident.items[2].rule_name == "ws"
    assert ident.items[2].min == 1
    assert ident.items[2].max == 1


def test_arithmetic_ident_field_map():
    d = _by_rule(_build("arithmetic"))
    ident = d["ident"]
    fm = ident.field_map
    assert "first" in fm  # [a-z]
    assert "second" in fm  # [a-z0-9_]*
    assert "ws" in fm  # ws
    assert fm["first"] == 0
    assert fm["second"] == 1
    assert fm["ws"] == 2


def test_arithmetic_literals_not_in_field_map():
    # root ::= (expr "=" ws term "\n")+
    # The helper RootItem has "=" and "\n" as LiteralAtoms — must not be fields
    specs = _build("arithmetic")
    # Find the helper class for the root group body
    helper = next(
        (s for s in specs if "root" in s.rule_name and s.rule_name != "root"), None
    )
    if helper:
        for fname in helper.field_map:
            assert fname not in ("=", "\\n", "\n"), (
                f"literal '{fname}' must not be in field_map"
            )
        # Verify at least one LiteralAtom exists in items
        assert any(isinstance(a, LiteralAtom) for a in helper.items)


# ── arithmetic: num ──────────────────────────────────────────────────────────


def test_arithmetic_num_is_value_str_or_sequence():
    # num ::= [0-9]+ ws — single char class + ws ref; may be value_str or sequence
    d = _by_rule(_build("arithmetic"))
    num = d["num"]
    assert num.kind in ("value_str", "sequence")
    assert num.class_name == "Num"


# ── arithmetic: expr has list field ──────────────────────────────────────────


def test_arithmetic_expr_has_list_ruleref():
    # expr ::= term ([-+*/] term)* — the * group → list field
    d = _by_rule(_build("arithmetic"))
    expr = d["expr"]
    assert expr.kind == "sequence"
    # Should have a RuleRefAtom with max=None for the repeated group
    list_refs = [a for a in expr.items if isinstance(a, RuleRefAtom) and a.max is None]
    assert len(list_refs) >= 1, "expr must have a List[...] item for the * group"


# ── field naming: no positional names ────────────────────────────────────────


def test_no_fieldN_names_in_any_grammar():
    import re

    for grammar in [
        "arithmetic",
        "c",
        "chess",
        "japanese",
        "json_arr",
        "json_ws",
        "list",
    ]:
        specs = _build(grammar)
        for spec in specs:
            for fname in spec.field_map:
                assert not re.fullmatch(r"field\d+", fname), (
                    f"Grammar '{grammar}', rule '{spec.rule_name}': "
                    f"field name '{fname}' must be semantic, not positional"
                )


# ── parent class names ────────────────────────────────────────────────────────


def test_arithmetic_ident_parent_is_term():
    d = _by_rule(_build("arithmetic"))
    assert d["ident"].parent_class_name == "Term"


def test_arithmetic_num_parent_is_term():
    d = _by_rule(_build("arithmetic"))
    assert d["num"].parent_class_name == "Term"


def test_arithmetic_term_parent_is_grammar_model():
    d = _by_rule(_build("arithmetic"))
    assert d["term"].parent_class_name == "GrammarModel"


# ── japanese: hyphened rule names ─────────────────────────────────────────────


def test_japanese_hyphen_rules_have_valid_class_names():
    d = _by_rule(_build("japanese"))
    assert "jp-char" in d
    jp = d["jp-char"]
    assert jp.class_name == "JpChar"  # PascalCase from hyphenated name
    assert jp.kind == "alternation"
