"""Tests for ``lexic.compile.artifact`` — the ``CompiledGrammar`` artefact.

The class moved here from ``compile/__init__`` (260718: ``export`` imports
it cycle-free); the behavioral surface — ``parse`` delegating to the engine
product and the model narrowing — stays pinned via the public
``lexic.compile`` import, plus the artefact's own identity fields.

Also carries the full-grammar round-trip tests exercising
``compile_from_path(...).parse(...)`` (ported from the removed
``test_artifact_parse.py``): parse → to_text → parse → dump() equality,
via the shared :func:`tests.unit.lexic.compile.compile_helpers.roundtrip` helper.

Grammar input notes:
- arithmetic: root is (expr "=" term "\\n")+.  RHS is *term*, not *expr*, so
  "a+b" is not a valid term — use "x=1\\n", "a=b\\n", or "x=(a+b)\\n".
- chess: root requires "1. " <move> " " <move> "\\n" followed by one or more
  numbered continuation lines, so a minimum of 2 lines is required.
- json_ws: root is object (not value), so "[]" is not a valid top-level input.
"""

from __future__ import annotations

import pytest

from lexic.compile import CompiledGrammar, compile_from_path, compile_text
from lexic.compile.artifact import CompiledGrammar as ArtifactCompiledGrammar
from lexic.exceptions import UnsupportedConstructError
from lexic.model import GrammarModel
from lexic.parsing import PdaTables
from tests.paths import GROUND_TRUTH
from tests.unit.lexic.compile.compile_helpers import roundtrip


def test_the_package_root_reexports_the_artifact_class():
    """`lexic.compile.CompiledGrammar` IS the artifact module's class."""
    assert CompiledGrammar is ArtifactCompiledGrammar


def test_parse_returns_a_grammar_model_instance():
    """The artefact's parse drives the engine product to a model."""
    cg = compile_text('root ::= "hi"\n')
    inst = cg.parse("hi")
    assert isinstance(inst, GrammarModel)
    assert inst.to_text() == "hi"


def test_parse_refuses_text_outside_the_grammar():
    """A non-deriving input surfaces the engine's UnsupportedConstructError."""
    cg = compile_text('root ::= "hi"\n')
    with pytest.raises(UnsupportedConstructError):
        cg.parse("nope")


def test_compile_from_path_threads_flavour_and_stem():
    """The artefact records its source flavour and stem (export identity)."""
    cg = compile_from_path(GROUND_TRUTH / "json.gbnf")
    assert cg.flavour == "gbnf"
    assert cg.stem == "json"


def test_compile_text_threads_the_content_stem():
    """compile_text stems by content hash — the anon_<sha> identity."""
    cg = compile_text('root ::= "hi"\n')
    assert cg.stem.startswith("anon_")


def test_pda_tables_returns_pda_tables():
    """CompiledGrammar.pda_tables() reaches the engine's compiled predictive
    tables for this artefact's (codegen_grammar, fold)."""
    cg = compile_text('root ::= "hi"\n')
    assert isinstance(cg.pda_tables(), PdaTables)


def test_pda_tables_is_hot_across_calls():
    """Repeated calls return the same tables object — no recompilation."""
    cg = compile_text('root ::= "hi"\n')
    assert cg.pda_tables() is cg.pda_tables()


def test_pda_tables_is_the_same_object_the_parse_path_used():
    """The tables a parse compiled are the exact object pda_tables() returns —
    the artefact and the parse share one memo entry."""
    cg = compile_text('root ::= "hi"\n')
    before = cg.pda_tables()
    cg.parse("hi")
    assert cg.pda_tables() is before


# ── arithmetic ────────────────────────────────────────────────────────────────


def test_arithmetic_simple():
    """Minimal: single-char ident assigned a single-digit number."""
    roundtrip("x=1\n", "arithmetic")


def test_arithmetic_ident_rhs():
    """Ident on both sides of the assignment."""
    roundtrip("a=b\n", "arithmetic")


def test_arithmetic_paren_expr():
    """Parenthesised expression as the term on the RHS."""
    roundtrip("x=(a+b)\n", "arithmetic")


# ── list ─────────────────────────────────────────────────────────────────────


def test_list_single_item():
    """Round-trip a single list item."""
    roundtrip("- foo\n", "list")


def test_list_multiple_items():
    """Round-trip multiple list items."""
    roundtrip("- foo\n- bar\n- baz\n", "list")


# ── json_ws ───────────────────────────────────────────────────────────────────


def test_json_ws_empty_object():
    """Simplest valid json_ws input: an empty object."""
    roundtrip("{}", "json_ws")


def test_json_ws_simple_object():
    """Object with one string key and a number value."""
    roundtrip('{"a":1}', "json_ws")


def test_json_ws_nested_object():
    """Nested object — exercises the value→object recursion."""
    roundtrip('{"x":{}}', "json_ws")


# ── chess ─────────────────────────────────────────────────────────────────────


def test_chess_two_move_pairs():
    """Two move pairs (minimum valid chess input: first line + one continuation)."""
    roundtrip("1. e4 e5\n2. d4 d5\n", "chess")


def test_chess_three_move_pairs():
    """Three move pairs — exercises the root_item list."""
    roundtrip("1. e4 e5\n2. d4 d5\n3. Nc3 Nf6\n", "chess")


# ── japanese ─────────────────────────────────────────────────────────────────


def test_japanese_hiragana():
    """Hiragana sequence round-trips exactly."""
    roundtrip("あいう", "japanese")


def test_japanese_single_char():
    """Single hiragana character."""
    roundtrip("あ", "japanese")


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
    roundtrip(text, grammar)


# ── Negative: bad input raises ────────────────────────────────────────────────


def test_parse_invalid_raises():
    """Completely invalid input for arithmetic must raise a parse error."""
    with pytest.raises(UnsupportedConstructError):
        compile_from_path(GROUND_TRUTH / "arithmetic.gbnf").parse(
            "THIS IS NOT VALID ARITHMETIC !!!\n"
        )
