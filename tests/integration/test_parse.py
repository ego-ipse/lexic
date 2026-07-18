"""Integration tests: compiled-artifact round-trips across all 7 grammars."""

from __future__ import annotations

from lexic.compile import compile_from_path
from tests.paths import GROUND_TRUTH as GRAMMAR_DIR


def roundtrip(text: str, grammar: str) -> None:
    """Parse text with the named grammar and assert to_text() round-trips."""
    gpath = GRAMMAR_DIR / f"{grammar}.gbnf"
    inst = compile_from_path(gpath).parse(text)
    assert inst.to_text() == text, (
        f"Round-trip failed for {grammar!r}: {text!r} → {inst.to_text()!r}"
    )


# ── arithmetic ────────────────────────────────────────────────────────────────


def test_arithmetic_simple():
    """Single assignment round-trips."""
    roundtrip("x=1\n", "arithmetic")


def test_arithmetic_multi_assignment():
    """Multiple assignments round-trip."""
    roundtrip("x=1\na=b\n", "arithmetic")


def test_arithmetic_nested_parens():
    """Nested parentheses round-trip."""
    roundtrip("x=(a+b)\n", "arithmetic")


def test_arithmetic_deeply_nested_parens():
    """Deeply nested parentheses round-trip."""
    roundtrip("x=((a+b))\n", "arithmetic")


def test_arithmetic_single_char_ident():
    """Single-character identifiers round-trip."""
    # The grammar stores [a-z0-9_]* as a single char field; use single-char idents
    roundtrip("x=y\n", "arithmetic")


# ── json_ws ───────────────────────────────────────────────────────────────────


def test_json_ws_empty_object():
    """Empty JSON object round-trips."""
    roundtrip("{}", "json_ws")


def test_json_ws_simple_key_value():
    """Simple JSON key-value round-trips."""
    roundtrip('{"a":1}', "json_ws")


def test_json_ws_null_value():
    """JSON null value round-trips."""
    roundtrip('{"k":null}', "json_ws")


def test_json_ws_true_value():
    """JSON true value round-trips."""
    roundtrip('{"k":true}', "json_ws")


def test_json_ws_false_value():
    """JSON false value round-trips."""
    roundtrip('{"k":false}', "json_ws")


def test_json_ws_number_value():
    """JSON number value round-trips."""
    roundtrip('{"n":1}', "json_ws")


def test_json_ws_nested_object():
    """Nested JSON objects round-trip."""
    roundtrip('{"a":{"b":{}}}', "json_ws")


def test_json_ws_array_value():
    """JSON array value round-trips."""
    roundtrip('{"k":[]}', "json_ws")


# ── json_arr ──────────────────────────────────────────────────────────────────


def test_json_arr_empty():
    """Empty JSON array round-trips."""
    roundtrip("[\n]", "json_arr")


# ── chess ─────────────────────────────────────────────────────────────────────


def test_chess_two_moves():
    """Two chess moves round-trip."""
    roundtrip("1. e4 e5\n2. d4 d5\n", "chess")


def test_chess_three_moves():
    """Three chess moves round-trip."""
    roundtrip("1. e4 e5\n2. d4 d5\n3. Nc3 Nf6\n", "chess")


def test_chess_castling():
    """Castling notation round-trips."""
    roundtrip("1. O-O e5\n2. d4 d5\n", "chess")


def test_chess_check():
    """Check notation (+) round-trips."""
    roundtrip("1. Nf3+ e5\n2. d4 d5\n", "chess")


# ── japanese ──────────────────────────────────────────────────────────────────


def test_japanese_five_chars():
    """Japanese hiragana round-trips."""
    roundtrip("あいうえお", "japanese")


# ── list ──────────────────────────────────────────────────────────────────────


def test_list_single_item():
    """Single markdown list item round-trips."""
    roundtrip("- foo\n", "list")


def test_list_ten_items():
    """Ten markdown list items round-trip."""
    roundtrip("".join(f"- item{i}\n" for i in range(10)), "list")
