# tests/test_parser.py
"""Full round-trip tests: parse → to_text → parse → model_dump() equality.

_roundtrip(text, grammar) asserts two things:
  1. inst.to_text() == text  (exact text reconstruction)
  2. parse(inst.to_text()).model_dump() == inst.model_dump()  (structural equality)

Grammar input notes:
- arithmetic: root is (expr "=" term "\\n")+.  RHS is *term*, not *expr*, so
  "a+b" is not a valid term — use "x=1\\n", "a=b\\n", or "x=(a+b)\\n".
- chess: root requires "1. " <move> " " <move> "\\n" followed by one or more
  numbered continuation lines, so a minimum of 2 lines is required.
- json_ws: root is object (not value), so "[]" is not a valid top-level input.
"""

from __future__ import annotations
from pathlib import Path

import pytest
from lexic.parse import parse
from lexic.base import GrammarModel

GRAMMAR_DIR = Path(__file__).parent.parent / "resources" / "ground_truth"


def _roundtrip(text: str, grammar: str):
    gpath = GRAMMAR_DIR / f"{grammar}.gbnf"
    inst = parse(text, gpath)
    assert inst is not None
    assert isinstance(inst, GrammarModel)

    roundtrip_str = inst.to_text()
    assert text == roundtrip_str, (
        f"to_text() mismatch for {grammar!r}:\n"
        f"  original:  {text!r}\n"
        f"  roundtrip: {roundtrip_str!r}"
    )

    rt = parse(roundtrip_str, gpath)
    assert inst.model_dump() == rt.model_dump(), (
        f"model_dump() mismatch after round-trip for {grammar!r}:\n"
        f"  original:  {inst.model_dump()}\n"
        f"  roundtrip: {rt.model_dump()}"
    )
    return inst


# ── arithmetic ────────────────────────────────────────────────────────────────


def test_arithmetic_simple():
    """Minimal: single-char ident assigned a single-digit number."""
    _roundtrip("x=1\n", "arithmetic")


def test_arithmetic_ident_rhs():
    """Ident on both sides of the assignment."""
    _roundtrip("a=b\n", "arithmetic")


def test_arithmetic_paren_expr():
    """Parenthesised expression as the term on the RHS."""
    _roundtrip("x=(a+b)\n", "arithmetic")


def test_arithmetic_type_dispatch():
    """parse() returns a concrete GrammarModel with a non-None model_dump."""
    inst = parse("x=1\n", GRAMMAR_DIR / "arithmetic.gbnf")
    assert isinstance(inst, GrammarModel)
    assert inst.model_dump() is not None


# ── list ─────────────────────────────────────────────────────────────────────


def test_list_single_item():
    _roundtrip("- foo\n", "list")


def test_list_multiple_items():
    _roundtrip("- foo\n- bar\n- baz\n", "list")


# ── json_ws ───────────────────────────────────────────────────────────────────


def test_json_ws_empty_object():
    """Simplest valid json_ws input: an empty object."""
    _roundtrip("{}", "json_ws")


def test_json_ws_simple_object():
    """Object with one string key and a number value."""
    _roundtrip('{"a":1}', "json_ws")


def test_json_ws_nested_object():
    """Nested object — exercises the value→object recursion."""
    _roundtrip('{"x":{}}', "json_ws")


# ── chess ─────────────────────────────────────────────────────────────────────


def test_chess_two_move_pairs():
    """Two move pairs (minimum valid chess input: first line + one continuation)."""
    _roundtrip("1. e4 e5\n2. d4 d5\n", "chess")


def test_chess_three_move_pairs():
    """Three move pairs — exercises the root_item list."""
    _roundtrip("1. e4 e5\n2. d4 d5\n3. Nc3 Nf6\n", "chess")


# ── japanese ─────────────────────────────────────────────────────────────────


def test_japanese_hiragana():
    """Hiragana sequence round-trips exactly."""
    _roundtrip("あいう", "japanese")


def test_japanese_single_char():
    """Single hiragana character."""
    _roundtrip("あ", "japanese")


# ── Parametrized smoke round-trip ─────────────────────────────────────────────


@pytest.mark.parametrize(
    "grammar,text",
    [
        ("arithmetic", "x=1\n"),
        ("arithmetic", "a=b\n"),
        ("list", "- item\n"),
        ("json_ws", "{}"),
        ("json_ws", '{"a":1}'),
        ("chess", "1. e4 e5\n2. d4 d5\n"),
        ("japanese", "あ"),
    ],
)
def test_roundtrip_parametrized(grammar: str, text: str):
    _roundtrip(text, grammar)


# ── Negative: bad input raises ────────────────────────────────────────────────


def test_parse_invalid_raises():
    """Completely invalid input for arithmetic must raise a parse error."""
    import lark

    with pytest.raises((lark.exceptions.UnexpectedInput, Exception)):
        parse("THIS IS NOT VALID ARITHMETIC !!!\n", GRAMMAR_DIR / "arithmetic.gbnf")
