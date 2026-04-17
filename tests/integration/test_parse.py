"""Integration tests: parse() round-trips across all 7 grammars."""

from __future__ import annotations
from pathlib import Path
from lexic.parse import parse

GRAMMAR_DIR = Path(__file__).parent.parent.parent / "resources" / "ground_truth"


def _roundtrip(text: str, grammar: str) -> None:
    gpath = GRAMMAR_DIR / f"{grammar}.gbnf"
    inst = parse(text, gpath)
    assert inst.to_text() == text, (
        f"Round-trip failed for {grammar!r}: {text!r} → {inst.to_text()!r}"
    )


# ── arithmetic ────────────────────────────────────────────────────────────────
def test_arithmetic_simple():
    _roundtrip("x=1\n", "arithmetic")


def test_arithmetic_multi_assignment():
    _roundtrip("x=1\na=b\n", "arithmetic")


def test_arithmetic_nested_parens():
    _roundtrip("x=(a+b)\n", "arithmetic")


def test_arithmetic_deeply_nested_parens():
    _roundtrip("x=((a+b))\n", "arithmetic")


def test_arithmetic_single_char_ident():
    # The grammar stores [a-z0-9_]* as a single char field; use single-char idents
    _roundtrip("x=y\n", "arithmetic")


# ── json_ws ───────────────────────────────────────────────────────────────────
def test_json_ws_empty_object():
    _roundtrip("{}", "json_ws")


def test_json_ws_simple_key_value():
    _roundtrip('{"a":1}', "json_ws")


def test_json_ws_null_value():
    _roundtrip('{"k":null}', "json_ws")


def test_json_ws_true_value():
    _roundtrip('{"k":true}', "json_ws")


def test_json_ws_false_value():
    _roundtrip('{"k":false}', "json_ws")


def test_json_ws_number_value():
    _roundtrip('{"n":1}', "json_ws")


def test_json_ws_nested_object():
    _roundtrip('{"a":{"b":{}}}', "json_ws")


def test_json_ws_array_value():
    _roundtrip('{"k":[]}', "json_ws")


# ── json_arr ──────────────────────────────────────────────────────────────────
def test_json_arr_empty():
    _roundtrip("[\n]", "json_arr")


# ── chess ─────────────────────────────────────────────────────────────────────
def test_chess_two_moves():
    _roundtrip("1. e4 e5\n2. d4 d5\n", "chess")


def test_chess_three_moves():
    _roundtrip("1. e4 e5\n2. d4 d5\n3. Nc3 Nf6\n", "chess")


def test_chess_castling():
    _roundtrip("1. O-O e5\n2. d4 d5\n", "chess")


def test_chess_check():
    _roundtrip("1. Nf3+ e5\n2. d4 d5\n", "chess")


# ── japanese ──────────────────────────────────────────────────────────────────
def test_japanese_five_chars():
    _roundtrip("あいうえお", "japanese")


# ── list ──────────────────────────────────────────────────────────────────────
def test_list_single_item():
    _roundtrip("- foo\n", "list")


def test_list_ten_items():
    _roundtrip("".join(f"- item{i}\n" for i in range(10)), "list")
