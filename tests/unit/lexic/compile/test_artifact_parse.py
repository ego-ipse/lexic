"""Tests for the compile package's parse entries (``parse``/``parse_from_path``).

Full round-trip tests: parse → to_text → parse → dump() equality.

_roundtrip(text, grammar) asserts two things:
  1. inst.to_text() == text  (exact text reconstruction)
  2. parse_from_path(inst.to_text()).dump() == inst.dump()  (structural equality)

Grammar input notes:
- arithmetic: root is (expr "=" term "\\n")+.  RHS is *term*, not *expr*, so
  "a+b" is not a valid term — use "x=1\\n", "a=b\\n", or "x=(a+b)\\n".
- chess: root requires "1. " <move> " " <move> "\\n" followed by one or more
  numbered continuation lines, so a minimum of 2 lines is required.
- json_ws: root is object (not value), so "[]" is not a valid top-level input.
"""

from __future__ import annotations

import pytest

from lexic.compile import (
    compile_from_path,
    parse_instance,
    parse_instance_from_path,
)
from lexic.exceptions import UnsupportedConstructError
from lexic.model import GrammarModel
from tests.paths import GROUND_TRUTH as GRAMMAR_DIR


def _roundtrip(text: str, grammar: str):
    gpath = GRAMMAR_DIR / f"{grammar}.gbnf"
    inst = compile_from_path(gpath).parse(text)
    assert inst is not None
    assert isinstance(inst, GrammarModel)

    roundtrip_str = inst.to_text()
    assert text == roundtrip_str, (
        f"to_text() mismatch for {grammar!r}:\n"
        f"  original:  {text!r}\n"
        f"  roundtrip: {roundtrip_str!r}"
    )

    rt = compile_from_path(gpath).parse(roundtrip_str)
    assert inst.dump() == rt.dump(), (
        f"dump() mismatch after round-trip for {grammar!r}:\n"
        f"  original:  {inst.dump()}\n"
        f"  roundtrip: {rt.dump()}"
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
    """The path entry returns a concrete GrammarModel with a non-None dump."""
    inst = parse_instance_from_path("x=1\n", GRAMMAR_DIR / "arithmetic.gbnf")
    assert isinstance(inst, GrammarModel)
    assert inst.dump() is not None


# ── list ─────────────────────────────────────────────────────────────────────


def test_list_single_item():
    """Round-trip a single list item."""
    _roundtrip("- foo\n", "list")


def test_list_multiple_items():
    """Round-trip multiple list items."""
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
    """Parametrized round-trip test for all grammars."""
    _roundtrip(text, grammar)


# ── Negative: bad input raises ────────────────────────────────────────────────


def test_parse_invalid_raises():
    """Completely invalid input for arithmetic must raise a parse error."""
    with pytest.raises(UnsupportedConstructError):
        compile_from_path(GRAMMAR_DIR / "arithmetic.gbnf").parse(
            "THIS IS NOT VALID ARITHMETIC !!!\n"
        )


# ── the string-primary entry (parse takes grammar SOURCE) ─────────────────


def test_parse_takes_grammar_source_text():
    """The unqualified entry takes grammar text, per the string-primary rule."""
    inst = parse_instance("hi", 'root ::= "hi"\n')
    assert isinstance(inst, GrammarModel)
    assert inst.to_text() == "hi"


def test_parse_accepts_an_explicit_flavour():
    """The flavour parameter routes the text through the named front-end."""
    inst = parse_instance("hi", 'root = "hi"\n', flavour="abnf")
    assert inst.to_text() == "hi"


def test_parse_from_path_accepts_an_explicit_flavour_override():
    """parse_from_path forwards flavour instead of extension inference."""
    inst = parse_instance_from_path(
        "x=1\n", GRAMMAR_DIR / "arithmetic.gbnf", flavour="gbnf"
    )
    assert inst.to_text() == "x=1\n"
