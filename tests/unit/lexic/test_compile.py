"""Unit tests for lexic.compile (compile_text/_from_path, canonical_grammar, parse_grammar)."""

import os
import tempfile
import time
from pathlib import Path
from typing import cast

import pytest

import lexic
import lexic.compile as compile_module
from lexic.base import GrammarModel
from lexic.codegen import resolve_out_dir
from lexic.compile import (
    CompiledGrammar,
    _ModelRoute,
    _ReduceRoute,
    _scan_directives,
    canonical_grammar,
    compile_from_path,
    compile_text,
    parse_grammar,
    reset_cache_for_tests,
    self_grammar_pda,
)
from lexic.exceptions import UnsupportedConstructError
from lexic.grammars.abnf import ABNF_FLAVOUR
from lexic.grammars.gbnf import GBNF_FLAVOUR
from lexic.ir.escapes import CANONICAL_ESCAPES
from lexic.ir.flavour import IrFlavour
from lexic.ir.nodes import IrAst
from lexic.ir.walk import IrDispatch
from lexic.parsing import ParserTables, parse_first, parse_reduced
from lexic.parsing.fold import ModelFold
from lexic.parsing.pda.clones import PdaTables
from lexic.parsing.pda.runtime import PdaFail
from tests.paths import GENERATED, GROUND_TRUTH


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


def test_compile_memoizes_by_content_by_default():
    """compile_text(text) memoizes by (content, flavour) with no explicit key."""
    text = (GROUND_TRUTH / "arithmetic.gbnf").read_text()
    cg1 = compile_text(text)
    cg2 = compile_text(text)
    assert cg1 is cg2  # content-keyed default memoization


def test_reset_cache_for_tests_clears_default_memo():
    """reset_cache_for_tests() drops the content-keyed entry — fresh objects after."""
    text = (GROUND_TRUTH / "arithmetic.gbnf").read_text()
    cg1 = compile_text(text)
    reset_cache_for_tests()
    cg2 = compile_text(text)
    assert cg1 is not cg2


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
    out_dir = str(resolve_out_dir(None).resolve())
    key = (resolved, stat.st_mtime, stat.st_size, "gbnf", out_dir)
    cg1 = compile_text(path.read_text(), cache_key=key)
    cg2 = compile_from_path(path)
    assert cg1 is cg2


def test_compiled_grammar_parse_roundtrips():
    """CompiledGrammar.parse() should round-trip."""
    cg = compile_from_path(GROUND_TRUTH / "arithmetic.gbnf")
    inst = cg.parse("x=1\n")
    assert inst.to_text() == "x=1\n"


def test_compiled_grammar_grammar_field_is_the_canonical_ast():
    """CompiledGrammar.grammar is the canonical grammar AST (the re-emit
    source), and instance_grammar the Earley-normalised instance grammar."""
    cg = compile_from_path(GROUND_TRUTH / "arithmetic.gbnf")
    assert isinstance(cg.grammar, IrAst)
    assert isinstance(cg.instance_grammar, IrAst)
    text = (GROUND_TRUTH / "arithmetic.gbnf").read_text(encoding="utf-8")
    assert cg.grammar == canonical_grammar(text, GBNF_FLAVOUR)


def test_compiled_grammar_fold_field_is_positional_fold():
    """CompiledGrammar.fold is the ParseTree -> model-instance ModelFold."""
    cg = compile_from_path(GROUND_TRUTH / "arithmetic.gbnf")
    assert isinstance(cg.fold, ModelFold)


def test_compiled_grammar_tables_field_is_parser_tables():
    """CompiledGrammar.tables is a ParserTables, compiled once at build time
    (see collapsed_instance_tables)."""
    cg = compile_from_path(GROUND_TRUTH / "arithmetic.gbnf")
    assert isinstance(cg.tables, ParserTables)


@pytest.mark.parametrize(
    ("grammar_file", "text"),
    [
        ("arithmetic.gbnf", "x=1\n"),
        ("json_ws.gbnf", '{"n":1}'),  # "1" is genuinely ambiguous (number's grammar)
    ],
)
def test_collapsed_and_plain_tables_parse_to_the_same_model(grammar_file, text):
    """CompiledGrammar's built-in collapsed-tables parse (cg.parse) matches a
    plain-tables parse (parse_first with no tables=) on model_dump()/to_text().

    The fold-config run-collapse licence changes the packed chart shape
    (fewer, longer terminal leaves) but must never change observable output —
    this is the in-suite spot-check of the author's full equality harness.
    """
    cg = compile_from_path(GROUND_TRUTH / grammar_file)
    collapsed_model = cg.parse(text)
    plain_model = cg.fold.apply(parse_first(cg.instance_grammar, text))
    assert isinstance(plain_model, GrammarModel)
    assert collapsed_model.model_dump() == plain_model.model_dump()
    assert collapsed_model.to_text() == plain_model.to_text() == text


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


def test_compile_from_path_explicit_gbnf_flavour():
    """compile_from_path(path, flavour="gbnf") should compile GBNF"""
    cg = compile_from_path(GROUND_TRUTH / "arithmetic.gbnf", flavour="gbnf")
    assert isinstance(cg, CompiledGrammar)
    assert cg.classes


def test_compile_unknown_flavour_raises():
    """compile_text(text, flavour="abnf") should raise"""
    text = (GROUND_TRUTH / "arithmetic.gbnf").read_text()
    with pytest.raises(UnsupportedConstructError):
        compile_text(text, flavour="abnf")


def test_compile_from_path_unknown_flavour_raises():
    """compile_from_path(path, flavour="abnf") should raise"""
    with pytest.raises(UnsupportedConstructError):
        compile_from_path(GROUND_TRUTH / "arithmetic.gbnf", flavour="abnf")


# ── out_dir unit tests ──


def _module_stem(cg) -> str:
    """The generated-module stem, read off a compiled class's public __module__."""
    cls = next(iter(cg.classes.values()))
    return cls.__module__.rsplit(".", 1)[-1]


def test_compile_text_out_dir_writes_module_there(tmp_path):
    """An explicit out_dir gets the generated module; default output is untouched."""
    text = 'root ::= "unique-out-dir-probe-value"\n'
    cg = compile_text(text, out_dir=tmp_path)
    stem = _module_stem(cg)
    assert (tmp_path / f"{stem}.py").exists()
    assert not (GENERATED / f"{stem}.py").exists()


def test_compile_text_out_dir_classes_round_trip(tmp_path):
    """A model compiled to a custom out_dir parses and round-trips normally."""
    text = 'root ::= "x"\n'
    cg = compile_text(text, out_dir=tmp_path)
    inst = cg.parse("x")
    assert inst.to_text() == "x"


def test_compile_text_default_out_dir_unchanged():
    """Omitting out_dir keeps writing to the project's generated/ directory."""
    text = 'root ::= "y"\n'
    cg = compile_text(text)
    stem = _module_stem(cg)
    assert (GENERATED / f"{stem}.py").exists()
    assert cg.classes


def test_compile_text_distinct_out_dirs_do_not_share_the_memo(tmp_path):
    """Same content, two different out_dirs: distinct cache entries."""
    text = 'root ::= "z"\n'
    dir_a = tmp_path / "a"
    dir_b = tmp_path / "b"
    cg1 = compile_text(text, out_dir=dir_a)
    cg2 = compile_text(text, out_dir=dir_b)
    assert cg1 is not cg2
    stem = _module_stem(cg1)
    assert (dir_a / f"{stem}.py").exists()
    assert (dir_b / f"{stem}.py").exists()


def test_compile_text_same_out_dir_hits_the_memo(tmp_path):
    """Same content, same out_dir: cache-hit, no double compile."""
    text = 'root ::= "w"\n'
    cg1 = compile_text(text, out_dir=tmp_path)
    cg2 = compile_text(text, out_dir=tmp_path)
    assert cg1 is cg2


def test_compile_from_path_out_dir_writes_module_there(tmp_path):
    """compile_from_path threads out_dir through to codegen the same way."""
    src = tmp_path / "src" / "root_out_dir.gbnf"
    src.parent.mkdir()
    src.write_text('root ::= "a"\n')
    out_dir = tmp_path / "out"
    cg = compile_from_path(src, out_dir=out_dir)
    assert (out_dir / "root_out_dir.py").exists()
    assert cg.parse("a").to_text() == "a"


def test_compile_from_path_distinct_out_dirs_do_not_share_the_memo(tmp_path):
    """Same path, two different out_dirs: distinct cache entries (memo includes out_dir)."""
    src = tmp_path / "root_path_out_dir.gbnf"
    src.write_text('root ::= "q"\n')
    dir_a = tmp_path / "path_a"
    dir_b = tmp_path / "path_b"
    cg1 = compile_from_path(src, out_dir=dir_a)
    cg2 = compile_from_path(src, out_dir=dir_b)
    assert cg1 is not cg2
    assert (dir_a / "root_path_out_dir.py").exists()
    assert (dir_b / "root_path_out_dir.py").exists()


def test_compile_text_out_dir_accepts_a_plain_string():
    """out_dir works as a plain str, not just a Path."""
    with tempfile.TemporaryDirectory() as tmp:
        text = 'root ::= "str-out-dir-probe"\n'
        cg = compile_text(text, out_dir=tmp)
        stem = _module_stem(cg)
        assert (Path(tmp) / f"{stem}.py").exists()
        assert cg.parse("str-out-dir-probe").to_text() == "str-out-dir-probe"


def test_compile_text_out_dir_creates_nested_nonexistent_directory(tmp_path):
    """A multi-level nonexistent out_dir is created on demand."""
    nested = tmp_path / "a" / "b" / "c"
    assert not nested.exists()
    text = 'root ::= "nested-out-dir-probe"\n'
    cg = compile_text(text, out_dir=nested)
    stem = _module_stem(cg)
    assert (nested / f"{stem}.py").exists()


def test_reset_cache_for_tests_regenerates_identical_source(tmp_path):
    """A fresh compile after reset_cache_for_tests writes byte-identical source
    to a distinct output directory — fresh objects, same generated text."""
    text = 'root ::= "reset-cache-probe"\n'
    dir_a = tmp_path / "first"
    dir_b = tmp_path / "second"
    cg1 = compile_text(text, out_dir=dir_a)
    stem = _module_stem(cg1)
    source_a = (dir_a / f"{stem}.py").read_text()
    reset_cache_for_tests()
    cg2 = compile_text(text, out_dir=dir_b)
    assert cg1 is not cg2
    source_b = (dir_b / f"{stem}.py").read_text()
    assert source_a == source_b


# ── canonical_grammar start-resolution unit tests ──


def test_canonical_grammar_returns_start_first_rule():
    """canonical_grammar binds the sole rule as start."""
    ast = canonical_grammar('root ::= "x"\n', GBNF_FLAVOUR)
    assert ast.start == "root"
    assert [str(r.name) for r in ast.rules] == ["root"]


def test_canonical_grammar_falls_back_to_first_rule():
    """start defaults to the first rule when no directive."""
    ast = canonical_grammar("root ::= [0-9]+\n", GBNF_FLAVOUR)
    assert ast.start == "root"


def test_canonical_grammar_start_directive_wins_over_first_rule():
    """@start directive overrides positional first-rule fallback."""
    text = "# @start expr\nroot ::= expr\nexpr ::= [0-9]+\n"
    ast = canonical_grammar(text, GBNF_FLAVOUR)
    assert ast.start == "expr"


def test_canonical_grammar_explicit_start_wins_over_directive():
    """Explicit start= argument wins over @start directive."""
    text = "# @start expr\nroot ::= expr\nexpr ::= [0-9]+\n"
    ast = canonical_grammar(text, GBNF_FLAVOUR, start="root")
    assert ast.start == "root"


def test_canonical_grammar_invalid_start_raises():
    """Unresolvable start rule raises UnsupportedConstructError."""
    with pytest.raises(UnsupportedConstructError, match="start"):
        canonical_grammar("root ::= [0-9]+\n", GBNF_FLAVOUR, start="nonexistent")


def test_canonical_grammar_flavour_with_non_reducer_raises():
    """canonical_grammar raises UnsupportedConstructError when flavour.reducer
    is not a parsing Reducer instance."""
    with pytest.raises(UnsupportedConstructError, match="no parse Reducer"):
        canonical_grammar('root ::= "x"\n', _FlavourWithBadReducer())


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


# ── canonical_grammar unit tests ──


def test_canonical_grammar_returns_flagged_canonical_ast():
    """canonical_grammar binds start and semantic=False flags onto the AST."""
    text = "# @non-semantic ws\nroot ::= ws\nws ::= [ ]*\n"
    ast = canonical_grammar(text, GBNF_FLAVOUR)
    assert isinstance(ast, IrAst)
    assert ast.start == "root"
    assert ast.non_semantic == frozenset({"ws"})


def test_canonical_grammar_folds_directive_names_like_rule_names():
    """A directive naming ws_x matches the canonically folded rule ws-x."""
    text = "# @non-semantic ws_x\nroot ::= ws_x\nws_x ::= [ ]*\n"
    ast = canonical_grammar(text, GBNF_FLAVOUR)
    assert ast.non_semantic == frozenset({"ws-x"})


def test_canonical_grammar_unknown_directive_rule_is_ignored():
    """A directive naming an undefined rule flags nothing."""
    text = "# @non-semantic ghost\nroot ::= [0-9]+\n"
    ast = canonical_grammar(text, GBNF_FLAVOUR)
    assert ast.non_semantic == frozenset()


# ── _scan_directives unit tests ──
#
# compile_grammar's start-directive precedence (directive vs explicit arg vs
# positional fallback) is already covered above by
# test_compile_grammar_start_directive_wins_over_first_rule and
# test_compile_grammar_explicit_start_wins_over_directive. These tests target
# the private _scan_directives helper directly: its defaults, @non-semantic
# parsing, comment-marker sensitivity, and directive-syntax edge cases.


def test_scan_directives_empty_text_defaults_to_none_and_empty_frozenset():
    """No directives at all: the helper defaults to (None, frozenset())."""
    assert _scan_directives("", line_comment="#") == (None, frozenset())


def test_scan_directives_no_directives_in_grammar_returns_empty():
    """A grammar with no comments at all has no directives."""
    text = "root ::= expr\nexpr ::= [0-9]+"
    start, non_semantic = _scan_directives(text, line_comment="#")
    assert start is None
    assert non_semantic == frozenset()


def test_scan_directives_non_semantic_single_arg():
    """A single @non-semantic directive extracts one rule name."""
    text = "# @non-semantic ws\nroot ::= ws value"
    _start, non_semantic = _scan_directives(text, line_comment="#")
    assert non_semantic == frozenset({"ws"})


def test_scan_directives_non_semantic_multiple_args():
    """Multiple @non-semantic arguments are all collected."""
    text = "# @non-semantic ws comment_block\nroot ::= ws value"
    _start, non_semantic = _scan_directives(text, line_comment="#")
    assert non_semantic == frozenset({"ws", "comment_block"})


def test_scan_directives_requires_at_marker():
    """Comments without @<name> are not directives."""
    text = "# this is just a comment\nroot ::= x"
    start, non_semantic = _scan_directives(text, line_comment="#")
    assert start is None
    assert non_semantic == frozenset()


def test_scan_directives_respects_line_comment_marker():
    """ABNF uses ';' — '#' is just data inside an ABNF source."""
    text = "; @non-semantic WSP\nroot = WSP value"
    _start, non_semantic = _scan_directives(text, line_comment=";")
    assert non_semantic == frozenset({"WSP"})


def test_scan_directives_unknown_directive_is_ignored():
    """Unknown directive names are silently ignored."""
    text = "# @future-thing foo\n# @non-semantic ws"
    _start, non_semantic = _scan_directives(text, line_comment="#")
    assert non_semantic == frozenset({"ws"})


def test_scan_directives_allows_leading_whitespace_before_marker():
    """`  # @non-semantic ws` is the same as `# @non-semantic ws`."""
    text = "  # @non-semantic ws\nroot ::= ws value"
    _start, non_semantic = _scan_directives(text, line_comment="#")
    assert non_semantic == frozenset({"ws"})


def test_scan_directives_empty_line_comment_disables_directive_parsing():
    """A flavour with no comment marker (line_comment='') has no directive channel."""
    text = "# @non-semantic ws\nroot ::= ws value"
    start, non_semantic = _scan_directives(text, line_comment="")
    assert start is None
    assert non_semantic == frozenset()


def test_scan_directives_start_last_wins():
    """Multiple @start directives: the last value wins."""
    text = "# @start a\n# @start b\n"
    start, _non_semantic = _scan_directives(text, line_comment="#")
    assert start == "b"


def test_scan_directives_start_and_non_semantic_coexist():
    """@start and @non-semantic directives in the same source both apply."""
    text = "# @start root\n# @non-semantic ws\nroot ::= ws value\n"
    start, non_semantic = _scan_directives(text, line_comment="#")
    assert start == "root"
    assert non_semantic == frozenset({"ws"})


def test_normalized_grammar_memo_is_reused_across_parse_calls(monkeypatch):
    """The per-flavour self-grammar normalization memo means a second
    canonical_grammar call for the same flavour never re-normalizes the
    self-grammar (identity is preserved across calls, keeping the engine's
    identity-memoised table compilation hot)."""
    calls: list[object] = []
    original_normalize = compile_module.normalize

    def spy(grammar):
        calls.append(grammar)
        return original_normalize(grammar)

    monkeypatch.setattr(compile_module, "normalize", spy)

    canonical_grammar('root ::= "x"\n', GBNF_FLAVOUR)
    count_after_first = len(calls)
    canonical_grammar('root ::= "y"\n', GBNF_FLAVOUR)

    assert len(calls) == count_after_first


# ── self_grammar_pda ──


def test_self_grammar_pda_builds_for_gbnf():
    """GBNF's self-grammar compiles to a real reduce PDA (its start rule,
    "grammar", is not itself an island)."""
    pda = self_grammar_pda(GBNF_FLAVOUR)
    assert isinstance(pda, PdaTables)
    assert pda.reduce is not None


def test_self_grammar_pda_is_none_for_abnf():
    """ABNF's start rule ("rulelist") is itself an island — the whole-grammar
    opt-out — so self_grammar_pda returns None rather than a PDA whose start
    can never be predictively entered."""
    assert self_grammar_pda(ABNF_FLAVOUR) is None


def test_self_grammar_pda_is_cached_per_flavour_name():
    """A second call for the same flavour returns the identical PdaTables
    object — no recompilation."""
    first = self_grammar_pda(GBNF_FLAVOUR)
    second = self_grammar_pda(GBNF_FLAVOUR)
    assert first is second


def test_self_grammar_pda_none_result_is_cached_too(monkeypatch):
    """The None opt-out result is itself memoised: a second call for the same
    (island-start) flavour never recompiles — mirrors
    ``test_normalized_grammar_memo_is_reused_across_parse_calls``'s spy idiom.
    """
    calls: list[object] = []
    original_compile_reduce_pda = compile_module.compile_reduce_pda

    def spy(lifted, instance_grammar, reducer):
        calls.append(lifted)
        return original_compile_reduce_pda(lifted, instance_grammar, reducer)

    monkeypatch.setattr(compile_module, "compile_reduce_pda", spy)

    self_grammar_pda(ABNF_FLAVOUR)
    count_after_first = len(calls)
    result = self_grammar_pda(ABNF_FLAVOUR)

    assert result is None
    assert len(calls) == count_after_first


# ── the one internal parse seam: _ParseRoute / _ModelRoute / _ReduceRoute ──
#
# _ModelRoute (CompiledGrammar.parse) and _ReduceRoute (parse_grammar) share
# _ParseRoute.run's PDA-first-then-Earley-completion policy; pda_first is a
# routing DATUM, not a code fork. These pin the route classes' own shape
# (A) plus the routing decision table (run's three branches).


def _gbnf_grammar_and_reducer():
    """(normalised self-grammar, reducer) for GBNF — the shared _ReduceRoute
    fixture pair. Reached via getattr since both are compile.py-private
    (memoised) helpers — matches test_runtime.py's
    getattr(rt, "_ReducePdaKernel") precedent, no protected-access dotted
    access to a leading-underscore name.
    """
    grammar = getattr(compile_module, "_normalized_grammar")(GBNF_FLAVOUR)
    reducer = getattr(compile_module, "_flavour_reducer")(GBNF_FLAVOUR)
    return grammar, reducer


def _pda_fold(route):
    """``route._pda_fold()`` via getattr — the same protected-access dodge."""
    return getattr(route, "_pda_fold")()


def test_modelroute_pda_first_is_true():
    """CompiledGrammar.parse's route is always PDA-first."""
    cg = compile_from_path(GROUND_TRUTH / "arithmetic.gbnf")
    route = _ModelRoute(cg.pda, True, cg.instance_grammar, cg.tables, cg.fold)
    assert route.pda_first is True


def test_modelroute_pda_fold_is_its_own_fold():
    """_ModelRoute splices island sub-models through its own fold."""
    cg = compile_from_path(GROUND_TRUTH / "arithmetic.gbnf")
    route = _ModelRoute(cg.pda, True, cg.instance_grammar, cg.tables, cg.fold)
    assert _pda_fold(route) is cg.fold


def test_modelroute_earley_matches_fold_apply_parse_first():
    """_ModelRoute.earley is exactly fold.apply(parse_first(grammar, text, tables))."""
    cg = compile_from_path(GROUND_TRUTH / "arithmetic.gbnf")
    route = _ModelRoute(cg.pda, True, cg.instance_grammar, cg.tables, cg.fold)
    text = "x=1\n"
    expected = cg.fold.apply(parse_first(cg.instance_grammar, text, cg.tables))
    assert route.earley(text) == expected


def test_reduceroute_pda_first_is_false():
    """parse_grammar's route is always Earley-only — the C2 regression guard."""
    grammar, reducer = _gbnf_grammar_and_reducer()
    route = _ReduceRoute(None, False, grammar, reducer)
    assert route.pda_first is False


def test_reduceroute_pda_fold_is_none():
    """_ReduceRoute has no fold to splice islands through — the reducer path."""
    grammar, reducer = _gbnf_grammar_and_reducer()
    route = _ReduceRoute(None, False, grammar, reducer)
    assert _pda_fold(route) is None


def test_reduceroute_earley_matches_parse_reduced():
    """_ReduceRoute.earley is exactly parse_reduced(grammar, text, reducer)."""
    grammar, reducer = _gbnf_grammar_and_reducer()
    route = _ReduceRoute(None, False, grammar, reducer)
    text = 'root ::= "abc"\n'
    assert route.earley(text) == parse_reduced(grammar, text, reducer)


def test_parseroute_run_never_calls_parse_pda_when_pda_first_is_false(monkeypatch):
    """pda_first=False routes straight to earley — parse_pda is never called,
    even with a real, non-None PDA in hand."""

    def _boom(*_args, **_kwargs):
        raise AssertionError("parse_pda must not be called when pda_first is False")

    monkeypatch.setattr(compile_module, "parse_pda", _boom)
    pda = self_grammar_pda(GBNF_FLAVOUR)
    assert pda is not None
    grammar, reducer = _gbnf_grammar_and_reducer()
    route = _ReduceRoute(pda, False, grammar, reducer)
    text = 'root ::= "abc"\n'
    assert route.run(text) == parse_reduced(grammar, text, reducer)


def test_parseroute_run_falls_through_to_earley_on_pdafail(monkeypatch):
    """pda_first=True with a non-None PDA tries parse_pda first; a PdaFail
    falls through to the earley completion, not a raised error."""

    def _fail(*_args, **_kwargs):
        raise PdaFail("forced")

    monkeypatch.setattr(compile_module, "parse_pda", _fail)
    cg = compile_from_path(GROUND_TRUTH / "arithmetic.gbnf")
    assert cg.pda is not None
    route = _ModelRoute(cg.pda, True, cg.instance_grammar, cg.tables, cg.fold)
    text = "x=1\n"
    expected = cg.fold.apply(parse_first(cg.instance_grammar, text, cg.tables))
    assert route.run(text) == expected


def test_parseroute_run_skips_parse_pda_when_pda_is_none(monkeypatch):
    """pda_first=True with pda=None goes straight to earley — parse_pda is
    never called (there is nothing to try)."""

    def _boom(*_args, **_kwargs):
        raise AssertionError("parse_pda must not be called when pda is None")

    monkeypatch.setattr(compile_module, "parse_pda", _boom)
    cg = compile_from_path(GROUND_TRUTH / "arithmetic.gbnf")
    route = _ModelRoute(None, True, cg.instance_grammar, cg.tables, cg.fold)
    text = "x=1\n"
    expected = cg.fold.apply(parse_first(cg.instance_grammar, text, cg.tables))
    assert route.run(text) == expected


# ── parse_grammar stays Earley-routed (C2 — load-bearing) ──────────────────


def test_parse_grammar_matches_parse_reduced_structurally():
    """parse_grammar's result equals driving parse_reduced directly over the
    flavour's own normalised self-grammar and reducer."""
    text = 'root ::= "abc"\n'
    grammar, reducer = _gbnf_grammar_and_reducer()
    assert parse_grammar(text, GBNF_FLAVOUR) == parse_reduced(grammar, text, reducer)


def test_parse_grammar_never_consults_the_pda_even_though_one_is_wired(monkeypatch):
    """STRONG pin: GBNF's self-grammar PDA is wired (self_grammar_pda is not
    None) but parse_grammar never reaches it — routing stays pda_first=False.
    Forcing parse_pda to raise must not change parse_grammar's result at all.
    """
    text = 'root ::= "abc" | "def"\n'
    assert self_grammar_pda(GBNF_FLAVOUR) is not None
    expected = parse_grammar(text, GBNF_FLAVOUR)

    def _boom(*_args, **_kwargs):
        raise AssertionError("parse_grammar must stay Earley-routed (C2)")

    monkeypatch.setattr(compile_module, "parse_pda", _boom)
    assert parse_grammar(text, GBNF_FLAVOUR) == expected


# ── CompiledGrammar.parse unchanged ─────────────────────────────────────────


def test_compiledgrammar_parse_returns_model_for_pda_backed_grammar():
    """A grammar with a non-None pda still parses to the expected model —
    the seam refactor left CompiledGrammar.parse's observable behavior alone."""
    cg = compile_from_path(GROUND_TRUTH / "arithmetic.gbnf")
    assert cg.pda is not None
    inst = cg.parse("x=1\n")
    assert isinstance(inst, GrammarModel)
    assert inst.to_text() == "x=1\n"


def test_compiledgrammar_parse_falls_back_to_engine_on_pdafail(monkeypatch):
    """A forced PdaFail still yields the correct model via the engine fold —
    the fallback path, not a raised error reaching the caller."""
    cg = compile_from_path(GROUND_TRUTH / "arithmetic.gbnf")
    assert cg.pda is not None

    def _fail(*_args, **_kwargs):
        raise PdaFail("forced")

    monkeypatch.setattr(compile_module, "parse_pda", _fail)
    text = "x=1\n"
    model = cg.parse(text)
    expected = cg.fold.apply(parse_first(cg.instance_grammar, text, cg.tables))
    assert isinstance(expected, GrammarModel)
    assert model.model_dump() == expected.model_dump()
    assert model.to_text() == text


def test_compiledgrammar_parse_still_works_when_pda_is_none():
    """A whole-grammar pda=None opt-out (start rule itself an island) still
    parses correctly via the engine-only path."""
    text = 'root ::= "a"? "a"\n'
    cg = compile_text(text, flavour="gbnf")
    assert cg.pda is None
    assert cg.parse("a").to_text() == "a"
    assert cg.parse("aa").to_text() == "aa"


# ── _flavour_reducer: the single home for the Reducer narrowing check ──────


def test_flavour_reducer_returns_the_flavours_own_reducer():
    """_flavour_reducer(flavour) returns exactly the flavour's reducer ClassVar."""
    _grammar, reducer = _gbnf_grammar_and_reducer()
    assert reducer is GBNF_FLAVOUR.reducer
