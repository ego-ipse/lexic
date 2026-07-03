"""Unit tests for lexic.compile (compile_text/_from_path, compile_grammar, parse_grammar)."""

import os
import time
from typing import cast

import pytest

import lexic
import lexic.compile as compile_module
from lexic.base import GrammarModel
from lexic.compile import (
    CompiledGrammar,
    compile_from_path,
    compile_grammar,
    compile_text,
    parse_grammar,
    reset_cache_for_tests,
)
from lexic.exceptions import UnsupportedConstructError
from lexic.grammars.gbnf import GBNF_FLAVOUR
from lexic.ir.escapes import CANONICAL_ESCAPES
from lexic.ir.flavour import IrFlavour
from lexic.ir.nodes import IrAst
from lexic.ir.walk import IrDispatch
from lexic.parsing.models import ModelFold
from tests.paths import GROUND_TRUTH


class _FlavourWithBadReducer(IrFlavour):
    """A concrete IrFlavour whose reducer is not a parsing Reducer instance."""

    name = "badreducer"
    extensions = (".bad",)
    escapes = CANONICAL_ESCAPES
    # Intentionally not a Reducer — this fixture exercises compile_grammar's
    # error path when a flavour carries a malformed reducer.
    reducer = cast(IrDispatch, "not-a-reducer")


@pytest.fixture(autouse=True)
def clear_cache():
    """Clear cache before and after each test."""
    reset_cache_for_tests()
    yield
    reset_cache_for_tests()


def test_compile_from_path_returns_compiled_grammar():
    """Same path should return cached result."""
    cg = compile_from_path(GROUND_TRUTH / "arithmetic.gbnf")
    assert isinstance(cg, CompiledGrammar)
    assert cg.classes
    assert isinstance(cg.specs, dict)
    assert cg.specs


def test_compile_from_path_memoises_by_path_mtime_size():
    """Same path but different mtime should invalidate."""
    src = GROUND_TRUTH / "arithmetic.gbnf"
    cg1 = compile_from_path(src)
    cg2 = compile_from_path(src)
    assert cg1 is cg2


def test_compile_from_path_invalidates_on_mtime_change(tmp_path):
    """Same mtime but different size should invalidate."""
    src = tmp_path / "test_invalidate_mtime.gbnf"
    src.write_text('root ::= "a"\n')
    cg1 = compile_from_path(src)
    time.sleep(0.01)
    src.write_text('root ::= "b"\n')
    cg2 = compile_from_path(src)
    assert cg1 is not cg2


def test_compile_from_path_invalidates_on_size_change_same_mtime(tmp_path):
    """Same mtime but different size should invalidate."""
    src = tmp_path / "test_invalidate_size.gbnf"
    src.write_text('root ::= "aa"\n')
    cg1 = compile_from_path(src)
    original_mtime = src.stat().st_mtime
    src.write_text('root ::= "bbb"\n')
    os.utime(src, (original_mtime, original_mtime))
    cg2 = compile_from_path(src)
    assert cg1 is not cg2


def test_compile_no_cache_by_default():
    """compile_text(text) should not cache."""
    text = (GROUND_TRUTH / "arithmetic.gbnf").read_text()
    cg1 = compile_text(text)
    cg2 = compile_text(text)
    assert cg1 is not cg2  # no cache_key → no memoization


def test_compile_with_cache_key():
    """compile_text(text, cache_key) should cache."""
    text = (GROUND_TRUTH / "arithmetic.gbnf").read_text()
    cg1 = compile_text(text, cache_key="fixture-a")
    cg2 = compile_text(text, cache_key="fixture-a")
    assert cg1 is cg2


def test_compile_and_compile_from_path_share_cache():
    """compile_from_path(path) should cache-hit after compile_text(text, cache_key=key)."""
    path = GROUND_TRUTH / "arithmetic.gbnf"
    resolved = str(path.resolve())
    stat = path.stat()
    key = (resolved, stat.st_mtime, stat.st_size, "gbnf")
    cg1 = compile_text(path.read_text(), cache_key=key)
    cg2 = compile_from_path(path)
    assert cg1 is cg2


def test_compiled_grammar_parse_roundtrips():
    """CompiledGrammar.parse() should round-trip."""
    cg = compile_from_path(GROUND_TRUTH / "arithmetic.gbnf")
    inst = cg.parse("x=1\n")
    assert inst.to_text() == "x=1\n"


def test_compiled_grammar_grammar_field_is_ir_ast():
    """CompiledGrammar.grammar is the normalized instance IrAst (engine-backed,
    Lark-free shape — no .parser/.transformer fields)."""
    cg = compile_from_path(GROUND_TRUTH / "arithmetic.gbnf")
    assert isinstance(cg.grammar, IrAst)


def test_compiled_grammar_fold_field_is_model_fold():
    """CompiledGrammar.fold is the ParseTree -> model-instance ModelFold."""
    cg = compile_from_path(GROUND_TRUTH / "arithmetic.gbnf")
    assert isinstance(cg.fold, ModelFold)


def test_compiled_grammar_parse_returns_a_grammar_model():
    """CompiledGrammar.parse() returns a GrammarModel instance."""
    cg = compile_from_path(GROUND_TRUTH / "arithmetic.gbnf")
    inst = cg.parse("x=1\n")
    assert isinstance(inst, GrammarModel)


def test_repeated_parse_is_fast():
    """Repeated parse() should be fast."""
    cg = compile_from_path(GROUND_TRUTH / "arithmetic.gbnf")
    cg.parse("x=1\n")  # warm
    start = time.perf_counter()
    for _ in range(100):
        cg.parse("x=1\n")
    elapsed = time.perf_counter() - start
    assert elapsed < 0.5, f"100 cached parses took {elapsed:.3f}s"


def test_compile_explicit_gbnf_flavour():
    """compile_text(text, flavour="gbnf") should compile GBNF"""
    text = (GROUND_TRUTH / "arithmetic.gbnf").read_text()
    cg = compile_text(text, flavour="gbnf")
    assert isinstance(cg, CompiledGrammar)
    assert cg.classes
    assert cg.specs


def test_compile_from_path_explicit_gbnf_flavour():
    """compile_from_path(path, flavour="gbnf") should compile GBNF"""
    cg = compile_from_path(GROUND_TRUTH / "arithmetic.gbnf", flavour="gbnf")
    assert isinstance(cg, CompiledGrammar)
    assert cg.classes
    assert cg.specs


def test_compile_unknown_flavour_raises():
    """compile_text(text, flavour="abnf") should raise"""
    text = (GROUND_TRUTH / "arithmetic.gbnf").read_text()
    with pytest.raises(UnsupportedConstructError):
        compile_text(text, flavour="abnf")


def test_compile_from_path_unknown_flavour_raises():
    """compile_from_path(path, flavour="abnf") should raise"""
    with pytest.raises(UnsupportedConstructError):
        compile_from_path(GROUND_TRUTH / "arithmetic.gbnf", flavour="abnf")


# ── compile_grammar unit tests ──


def test_compile_grammar_returns_start_and_specs():
    """compile_grammar returns (start_name, specs) tuple."""
    start, specs = compile_grammar('root ::= "x"\n', GBNF_FLAVOUR)
    assert start == "root"
    assert len(specs) == 1
    assert specs[0].rule_name == "root"


def test_compile_grammar_falls_back_to_first_rule():
    """start defaults to the first rule when no directive."""
    start, _ = compile_grammar("root ::= [0-9]+\n", GBNF_FLAVOUR)
    assert start == "root"


def test_compile_grammar_start_directive_wins_over_first_rule():
    """@start directive overrides positional first-rule fallback."""
    text = "# @start expr\nroot ::= expr\nexpr ::= [0-9]+\n"
    start, _ = compile_grammar(text, GBNF_FLAVOUR)
    assert start == "expr"


def test_compile_grammar_explicit_start_wins_over_directive():
    """Explicit start= argument wins over @start directive."""
    text = "# @start expr\nroot ::= expr\nexpr ::= [0-9]+\n"
    start, _ = compile_grammar(text, GBNF_FLAVOUR, start="root")
    assert start == "root"


def test_compile_grammar_invalid_start_raises():
    """Unresolvable start rule raises UnsupportedConstructError."""
    with pytest.raises(UnsupportedConstructError, match="start"):
        compile_grammar("root ::= [0-9]+\n", GBNF_FLAVOUR, start="nonexistent")


def test_compile_grammar_flavour_with_non_reducer_raises():
    """compile_grammar raises UnsupportedConstructError when flavour.reducer
    is not a parsing Reducer instance."""
    with pytest.raises(UnsupportedConstructError, match="no parse Reducer"):
        compile_grammar('root ::= "x"\n', _FlavourWithBadReducer())


def test_parse_grammar_returns_ir_ast():
    """parse_grammar is the public grammar-text → IrAst seam."""
    ast = parse_grammar('root ::= digit "+" digit\ndigit ::= [0-9]\n', GBNF_FLAVOUR)
    assert isinstance(ast, IrAst)
    assert [r.name for r in ast.rules] == ["root", "digit"]


def test_parse_grammar_is_importable_from_the_package_root():
    """The lexic package re-exports parse_grammar as primary API."""
    assert lexic.parse_grammar is parse_grammar


def test_parse_grammar_flavour_with_non_reducer_raises():
    """parse_grammar raises UnsupportedConstructError on a malformed reducer."""
    with pytest.raises(UnsupportedConstructError, match="no parse Reducer"):
        parse_grammar('root ::= "x"\n', _FlavourWithBadReducer())


def test_parse_grammar_malformed_source_raises():
    """Unparseable grammar text surfaces as UnsupportedConstructError."""
    with pytest.raises(UnsupportedConstructError):
        parse_grammar("root ::=\n::= broken", GBNF_FLAVOUR)


def test_normalized_grammar_memo_is_reused_across_compile_grammar_calls(monkeypatch):
    """The per-flavour self-grammar normalization memo means a second
    compile_grammar call for the same flavour never re-normalizes the
    self-grammar (identity is preserved across calls, keeping the engine's
    identity-memoised table compilation hot)."""
    calls: list[object] = []
    original_normalize = compile_module.normalize

    def spy(grammar):
        calls.append(grammar)
        return original_normalize(grammar)

    monkeypatch.setattr(compile_module, "normalize", spy)

    compile_grammar('root ::= "x"\n', GBNF_FLAVOUR)
    count_after_first = len(calls)
    compile_grammar('root ::= "y"\n', GBNF_FLAVOUR)

    assert len(calls) == count_after_first
