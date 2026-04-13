"""
Pytest test suite for src.parser — Grammar-Aware Parser (S02).

Covers:
- json_ws SOLID type hierarchy on parse result
- Field value correctness (key/value extraction)
- Correct concrete subclass selection for alternatives
- Parametrized "parse known-good sample" for all 6 ground-truth grammars
"""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import BaseModel

from src.codegen import build
from src.parser import parse


GROUND_TRUTH = Path(__file__).parent.parent / "resources" / "ground_truth"


# ---------------------------------------------------------------------------
# Known-good sample for each grammar
# ---------------------------------------------------------------------------

GRAMMAR_SAMPLES: list[tuple[str, str]] = [
    ("json_ws.gbnf", '{"city": "Porto"}'),
    ("arithmetic.gbnf", "x = 1\n"),
    ("list.gbnf", "- hello\n- world\n"),
    ("chess.gbnf", '{"move": "e4"}'),
    ("japanese.gbnf", '{"name": "Tokyo"}'),
    ("c.gbnf", "int f(){return 1;}"),
]


# ---------------------------------------------------------------------------
# Parametrized smoke test: all grammars parse without error
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("grammar_file,sample", GRAMMAR_SAMPLES)
def test_parse_returns_basemodel(grammar_file: str, sample: str) -> None:
    """parse() returns a Pydantic BaseModel instance for every ground-truth grammar."""
    grammar_path = GROUND_TRUTH / grammar_file
    if not grammar_path.exists():
        pytest.skip(f"{grammar_file} not found")
    result = parse(sample, grammar_path)
    assert isinstance(result, BaseModel), (
        f"parse() for {grammar_file} returned {type(result)}, expected BaseModel subclass"
    )


@pytest.mark.parametrize("grammar_file,sample", GRAMMAR_SAMPLES)
def test_parse_result_class_is_root(grammar_file: str, sample: str) -> None:
    """parse() result class name is 'Root' (the top-level generated class)."""
    grammar_path = GROUND_TRUTH / grammar_file
    if not grammar_path.exists():
        pytest.skip(f"{grammar_file} not found")
    result = parse(sample, grammar_path)
    assert type(result).__name__ == "Root", (
        f"{grammar_file}: expected Root, got {type(result).__name__}"
    )


# ---------------------------------------------------------------------------
# json_ws: SOLID type hierarchy correctness
# ---------------------------------------------------------------------------


def _json_ws_mods() -> dict[str, type]:
    return build(GROUND_TRUTH / "json_ws.gbnf")


def test_json_ws_root_is_subclass_of_object() -> None:
    """Root inherits from Object for json_ws grammar."""
    mods = _json_ws_mods()
    assert issubclass(mods["Root"], mods["Object"])


def test_json_ws_parse_simple_object() -> None:
    """parse('{"city": "Porto"}') returns Root with correct key and StringValue."""
    grammar = GROUND_TRUTH / "json_ws.gbnf"
    mods = build(grammar)

    # Use parse() and build() with same cached classes via fresh build call
    from src.parser import _gbnf_to_earley_lark, _fix_lark_grammar, _build_gbnf_rules, _transform
    from lark import Lark

    gbnf_text = grammar.read_text()
    lark_g = _fix_lark_grammar(_gbnf_to_earley_lark(gbnf_text), gbnf_text)
    lark_parser = Lark(
        lark_g, start="start", parser="earley", ambiguity="resolve",
        propagate_positions=True,
    )
    gbnf_rules = _build_gbnf_rules(gbnf_text)
    text = '{"city": "Porto"}'
    tree = lark_parser.parse(text)
    result = _transform(tree, mods, gbnf_rules, text)

    assert isinstance(result, mods["Root"])
    assert isinstance(result, mods["Object"])

    # Strings field: tuple (key, value, rest_list)
    assert result.strings is not None
    key, val, rest = result.strings
    assert key == "city"
    assert isinstance(val, mods["StringValue"])
    assert isinstance(val, mods["Value"])
    assert val.value == "Porto"
    assert rest == []


def test_json_ws_parse_empty_object() -> None:
    """parse('{}') returns Root with strings=None."""
    grammar = GROUND_TRUTH / "json_ws.gbnf"
    mods = build(grammar)

    from src.parser import _gbnf_to_earley_lark, _fix_lark_grammar, _build_gbnf_rules, _transform
    from lark import Lark

    gbnf_text = grammar.read_text()
    lark_g = _fix_lark_grammar(_gbnf_to_earley_lark(gbnf_text), gbnf_text)
    lark_parser = Lark(
        lark_g, start="start", parser="earley", ambiguity="resolve",
        propagate_positions=True,
    )
    gbnf_rules = _build_gbnf_rules(gbnf_text)
    text = "{}"
    tree = lark_parser.parse(text)
    result = _transform(tree, mods, gbnf_rules, text)

    assert isinstance(result, mods["Root"])
    assert result.strings is None


def test_json_ws_parse_multiple_keys() -> None:
    """parse('{"a": 1, "b": "hello"}') returns Root with correct rest_list."""
    grammar = GROUND_TRUTH / "json_ws.gbnf"
    mods = build(grammar)

    from src.parser import _gbnf_to_earley_lark, _fix_lark_grammar, _build_gbnf_rules, _transform
    from lark import Lark

    gbnf_text = grammar.read_text()
    lark_g = _fix_lark_grammar(_gbnf_to_earley_lark(gbnf_text), gbnf_text)
    lark_parser = Lark(
        lark_g, start="start", parser="earley", ambiguity="resolve",
        propagate_positions=True,
    )
    gbnf_rules = _build_gbnf_rules(gbnf_text)
    text = '{"a": 1, "b": "hello"}'
    tree = lark_parser.parse(text)
    result = _transform(tree, mods, gbnf_rules, text)

    assert isinstance(result, mods["Root"])
    key, val, rest = result.strings
    assert key == "a"
    assert isinstance(val, mods["NumberValue"])
    assert val.value == "1"
    assert len(rest) == 1
    key2, val2 = rest[0]
    assert key2 == "b"
    assert isinstance(val2, mods["StringValue"])
    assert val2.value == "hello"


def test_json_ws_parse_true_false_null() -> None:
    """Literal values true/false/null produce ValueAlt4 instances."""
    grammar = GROUND_TRUTH / "json_ws.gbnf"
    mods = build(grammar)

    from src.parser import _gbnf_to_earley_lark, _fix_lark_grammar, _build_gbnf_rules, _transform
    from lark import Lark

    gbnf_text = grammar.read_text()
    lark_g = _fix_lark_grammar(_gbnf_to_earley_lark(gbnf_text), gbnf_text)
    lark_parser = Lark(
        lark_g, start="start", parser="earley", ambiguity="resolve",
        propagate_positions=True,
    )
    gbnf_rules = _build_gbnf_rules(gbnf_text)

    for literal in ("true", "false", "null"):
        text = f'{{"x": {literal}}}'
        tree = lark_parser.parse(text)
        result = _transform(tree, mods, gbnf_rules, text)
        _, val, _ = result.strings
        assert isinstance(val, mods["ValueAlt4"]), (
            f"Expected ValueAlt4 for {literal}, got {type(val).__name__}"
        )
        assert val.value == literal


def test_json_ws_value_isinstance_hierarchy() -> None:
    """StringValue, NumberValue, ValueAlt4 are all instances of Value."""
    grammar = GROUND_TRUTH / "json_ws.gbnf"
    mods = build(grammar)

    from src.parser import _gbnf_to_earley_lark, _fix_lark_grammar, _build_gbnf_rules, _transform
    from lark import Lark

    gbnf_text = grammar.read_text()
    lark_g = _fix_lark_grammar(_gbnf_to_earley_lark(gbnf_text), gbnf_text)
    lark_parser = Lark(
        lark_g, start="start", parser="earley", ambiguity="resolve",
        propagate_positions=True,
    )
    gbnf_rules = _build_gbnf_rules(gbnf_text)

    cases = [
        ('{"x": "hello"}', "StringValue"),
        ('{"x": 42}', "NumberValue"),
        ('{"x": true}', "ValueAlt4"),
    ]
    for text, expected_subtype in cases:
        tree = lark_parser.parse(text)
        result = _transform(tree, mods, gbnf_rules, text)
        _, val, _ = result.strings
        assert isinstance(val, mods["Value"]), (
            f"{text}: {type(val).__name__} not a subclass of Value"
        )
        assert type(val).__name__ == expected_subtype


# ---------------------------------------------------------------------------
# Arithmetic: correct field structure
# ---------------------------------------------------------------------------


def test_arithmetic_parse_result_has_items() -> None:
    """arithmetic parse produces Root with items list of (Expr, Term) tuples."""
    result = parse("x = 1\n", GROUND_TRUTH / "arithmetic.gbnf")
    assert type(result).__name__ == "Root"
    assert hasattr(result, "items")
    assert isinstance(result.items, list)
    assert len(result.items) == 1
    expr, term = result.items[0]
    assert type(expr).__name__ == "Expr"
    assert type(term).__name__ in ("NumTerm", "IdentTerm", "TermAlt2")


# ---------------------------------------------------------------------------
# List: items as list of strings
# ---------------------------------------------------------------------------


def test_list_parse_result_has_str_items() -> None:
    """list grammar produces Root with items: list[str]."""
    result = parse("- hello\n- world\n", GROUND_TRUTH / "list.gbnf")
    assert type(result).__name__ == "Root"
    assert hasattr(result, "items")
    assert all(isinstance(i, str) for i in result.items)
    assert len(result.items) == 2


# ---------------------------------------------------------------------------
# C grammar: declaration structure
# ---------------------------------------------------------------------------


def test_c_parse_declaration_fields() -> None:
    """C grammar produces Declaration with correct datatype and identifier."""
    result = parse("int f(){return 1;}", GROUND_TRUTH / "c.gbnf")
    assert type(result).__name__ == "Root"
    assert len(result.items) == 1
    decl = result.items[0]
    assert type(decl).__name__ == "Declaration"
    assert decl.datatype == "int"
    assert decl.identifier == "f"
    assert len(decl.statements) >= 1
