"""Unit tests for lexic.compile (compile_text/_from_path, canonical_grammar, parse_grammar)."""

from __future__ import annotations

import os
import time
from typing import cast

import pytest

import lexic
import lexic.compile as compile_module
from lexic.compile import (
    CompiledGrammar,
    Directives,
    Vocabulary,
    _scan_directives,
    bind_module,
    canonical_grammar,
    compile_from_path,
    compile_text,
    parse_grammar,
    parse_instance,
    parse_instance_from_path,
    reset_cache_for_tests,
)
from lexic.exceptions import LexicError, UnsupportedConstructError
from lexic.grammars.abnf import ABNF_FLAVOUR
from lexic.grammars.ebnf import EBNF_FLAVOUR
from lexic.grammars.gbnf import GBNF_FLAVOUR
from lexic.ir import EscapeCodec, IrAst, IrDispatch, IrFlavour, IrLiteral
from lexic.model import GrammarModel
from lexic.parsing import normalize
from lexic.parsing.fold import ModelFold
from lexic.parsing.pda.compiler.specs import IslandRef
from lexic.parsing.pda.compiler.tables import PdaTables
from lexic.parsing.products import (
    _reduce_product,
    earley_model,
    earley_reduce,
)
from tests.paths import GROUND_TRUTH
from tests.unit.lexic.parsing.parsing_helpers import prod


class FlavourWithBadReducer(IrFlavour):
    """A concrete IrFlavour whose reducer is not a parsing Reducer instance."""

    name = "badreducer"
    extensions = (".bad",)
    escapes = EscapeCodec()
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


def test_cache_key_folds_content_no_stale_serve():
    """The same cache_key with different text never serves a stale grammar.

    The explicit key is prepended to the content key, so distinct source
    under one key yields distinct entries — each parses its own input.
    """
    first = compile_text('g ::= "1"\n', cache_key="shared-key")
    second = compile_text('g ::= "2"\n', cache_key="shared-key")
    assert first is not second
    assert first.parse("1").to_text() == "1"
    assert second.parse("2").to_text() == "2"


def test_compiled_grammar_parse_roundtrips():
    """CompiledGrammar.parse() should round-trip."""
    cg = compile_from_path(GROUND_TRUTH / "arithmetic.gbnf")
    inst = cg.parse("x=1\n")
    assert inst.to_text() == "x=1\n"


def test_compiled_grammar_grammar_field_is_the_canonical_ast():
    """CompiledGrammar.grammar is the canonical grammar AST (the re-emit
    source), and codegen_grammar the post-pass grammar the fold binds against."""
    cg = compile_from_path(GROUND_TRUTH / "arithmetic.gbnf")
    assert isinstance(cg.grammar, IrAst)
    assert isinstance(cg.codegen_grammar, IrAst)
    text = (GROUND_TRUTH / "arithmetic.gbnf").read_text(encoding="utf-8")
    assert cg.grammar == canonical_grammar(text, GBNF_FLAVOUR)


def test_compiled_grammar_fold_field_is_positional_fold():
    """CompiledGrammar.fold is the ParseTree -> model-instance ModelFold."""
    cg = compile_from_path(GROUND_TRUTH / "arithmetic.gbnf")
    assert isinstance(cg.fold, ModelFold)


@pytest.mark.parametrize(
    ("grammar_file", "text"),
    [
        ("arithmetic.gbnf", "x=1\n"),
        ("json_ws.gbnf", '{"n":1}'),  # "1" is genuinely ambiguous (number's grammar)
    ],
)
def test_collapsed_and_plain_tables_parse_to_the_same_model(grammar_file, text):
    """CompiledGrammar's built-in PDA-first parse (cg.parse) matches the forced
    Earley completion (``earley_model`` over the instance grammar) on
    dump()/to_text().

    The fold-config run-collapse licence changes the packed chart shape
    (fewer, longer terminal leaves) but must never change observable output —
    this is the in-suite spot-check of the author's full equality harness.
    """
    cg = compile_from_path(GROUND_TRUTH / grammar_file)
    p = prod(cg)
    collapsed_model = cg.parse(text)
    plain_model = earley_model(p.instance_grammar, text, cg.fold)
    assert isinstance(plain_model, GrammarModel)
    assert collapsed_model.dump() == plain_model.dump()
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


# ── compile_text/compile_from_path memoisation (content/path + flavour keyed) ──
#
# Synthesis writes no files and imports no modules, so there is no out_dir
# parameter and no output directory to key the cache on any more (the whole
# out_dir dimension of the cache — and every test built around it — died with
# the file-emitting codegen path). The remaining cache dimensions are content
# (compile_text) or path/mtime/size (compile_from_path), plus flavour; those
# are covered here and by the earlier memoisation tests
# (test_compile_from_path_memoises_by_path_mtime_size,
# test_compile_from_path_invalidates_on_mtime_change,
# test_compile_from_path_invalidates_on_size_change_same_mtime,
# test_compile_memoizes_by_content_by_default,
# test_reset_cache_for_tests_clears_default_memo,
# test_cache_key_folds_content_no_stale_serve — the last of which also proves
# distinct content never shares a memo entry).


def test_compile_text_same_content_and_flavour_hits_the_memo():
    """Same content, same explicit flavour: cache-hit, no double compile."""
    text = 'root ::= "w"\n'
    cg1 = compile_text(text, flavour="gbnf")
    cg2 = compile_text(text, flavour="gbnf")
    assert cg1 is cg2


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
        canonical_grammar('root ::= "x"\n', FlavourWithBadReducer())


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
        parse_grammar('root ::= "x"\n', FlavourWithBadReducer())


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
    assert _scan_directives("", GBNF_FLAVOUR) == (None, frozenset())


def test_scan_directives_no_directives_in_grammar_returns_empty():
    """A grammar with no comments at all has no directives."""
    text = "root ::= expr\nexpr ::= [0-9]+"
    start, non_semantic = _scan_directives(text, GBNF_FLAVOUR)
    assert start is None
    assert non_semantic == frozenset()


def test_scan_directives_non_semantic_single_arg():
    """A single @non-semantic directive extracts one rule name."""
    text = "# @non-semantic ws\nroot ::= ws value"
    _start, non_semantic = _scan_directives(text, GBNF_FLAVOUR)
    assert non_semantic == frozenset({"ws"})


def test_scan_directives_non_semantic_multiple_args():
    """Multiple @non-semantic arguments are all collected."""
    text = "# @non-semantic ws comment_block\nroot ::= ws value"
    _start, non_semantic = _scan_directives(text, GBNF_FLAVOUR)
    assert non_semantic == frozenset({"ws", "comment_block"})


def test_scan_directives_requires_at_marker():
    """Comments without @<name> are not directives."""
    text = "# this is just a comment\nroot ::= x"
    start, non_semantic = _scan_directives(text, GBNF_FLAVOUR)
    assert start is None
    assert non_semantic == frozenset()


def test_scan_directives_respects_line_comment_marker():
    """ABNF uses ';' — '#' is just data inside an ABNF source."""
    text = "; @non-semantic WSP\nroot = WSP value"
    _start, non_semantic = _scan_directives(text, ABNF_FLAVOUR)
    assert non_semantic == frozenset({"WSP"})


def test_scan_directives_unknown_directive_is_ignored():
    """Unknown directive names are silently ignored."""
    text = "# @future-thing foo\n# @non-semantic ws"
    _start, non_semantic = _scan_directives(text, GBNF_FLAVOUR)
    assert non_semantic == frozenset({"ws"})


def test_scan_directives_allows_leading_whitespace_before_marker():
    """`  # @non-semantic ws` is the same as `# @non-semantic ws`."""
    text = "  # @non-semantic ws\nroot ::= ws value"
    _start, non_semantic = _scan_directives(text, GBNF_FLAVOUR)
    assert non_semantic == frozenset({"ws"})


def test_scan_directives_empty_line_comment_disables_directive_parsing():
    """A flavour with no comment marker (line_comment='') has no directive channel."""
    text = "# @non-semantic ws\nroot ::= ws value"
    start, non_semantic = _scan_directives(text, EBNF_FLAVOUR)
    assert start is None
    assert non_semantic == frozenset()


def test_scan_directives_start_last_wins():
    """Multiple @start directives: the last value wins."""
    text = "# @start a\n# @start b\n"
    start, _non_semantic = _scan_directives(text, GBNF_FLAVOUR)
    assert start == "b"


def test_scan_directives_start_and_non_semantic_coexist():
    """@start and @non-semantic directives in the same source both apply."""
    text = "# @start root\n# @non-semantic ws\nroot ::= ws value\n"
    start, non_semantic = _scan_directives(text, GBNF_FLAVOUR)
    assert start == "root"
    assert non_semantic == frozenset({"ws"})


# ── the reduce product (grammar-text): built + memoised in the engine ──────


def test_reduce_product_builds_for_gbnf():
    """GBNF's self-grammar compiles to a real reduce PDA (its start rule,
    "grammar", is not itself an island)."""
    product = _reduce_product(GBNF_FLAVOUR.grammar, GBNF_FLAVOUR.reducer)
    assert isinstance(product.pda, PdaTables)
    assert product.pda.reduce is not None
    assert not isinstance(product.pda.start_key, IslandRef)


def test_reduce_product_builds_for_abnf():
    """ABNF's self-grammar compiles to a real reduce PDA since the
    ``rulelist`` boundary-shift left-factor removed the start island."""
    product = _reduce_product(ABNF_FLAVOUR.grammar, ABNF_FLAVOUR.reducer)
    assert isinstance(product.pda, PdaTables)
    assert product.pda.reduce is not None
    assert not isinstance(product.pda.start_key, IslandRef)


def test_reduce_product_is_memoised_per_identity():
    """A second call for the same (grammar, reducer) identity returns the
    identical compiled product — no recompilation."""
    first = _reduce_product(GBNF_FLAVOUR.grammar, GBNF_FLAVOUR.reducer)
    second = _reduce_product(GBNF_FLAVOUR.grammar, GBNF_FLAVOUR.reducer)
    assert first is second


# PARSEGRAMMAR


def test_parse_grammar_matches_earley_reduce():
    """parse_grammar's result equals the Earley reduce completion over the
    flavour's own normalised self-grammar and reducer — the PDA-first product
    and its completion agree (byte-equal IrAst)."""
    text = 'root ::= "abc"\n'
    reducer = getattr(compile_module, "_flavour_reducer")(GBNF_FLAVOUR)
    expected = earley_reduce(normalize(GBNF_FLAVOUR.grammar), text, reducer)
    assert parse_grammar(text, GBNF_FLAVOUR) == expected


def test_parse_grammar_pda_and_earley_agree_on_an_alternation():
    """The PDA route (parse_grammar) and the forced Earley route agree on an
    alternation input — the differential guard, no PdaFail divergence."""
    text = 'root ::= "abc" | "def"\n'
    reducer = getattr(compile_module, "_flavour_reducer")(GBNF_FLAVOUR)
    assert parse_grammar(text, GBNF_FLAVOUR) == earley_reduce(
        normalize(GBNF_FLAVOUR.grammar), text, reducer
    )


# ── CompiledGrammar.parse: PDA-first product, Earley + fold the completion ──


def test_compiledgrammar_parse_returns_a_model():
    """A compiled grammar parses to the expected model and round-trips."""
    cg = compile_from_path(GROUND_TRUTH / "arithmetic.gbnf")
    inst = cg.parse("x=1\n")
    assert isinstance(inst, GrammarModel)
    assert inst.to_text() == "x=1\n"


def test_compiledgrammar_pda_and_earley_agree():
    """cg.parse (PDA-first) yields the same model as the forced Earley
    completion (``earley_model`` over the instance grammar) — the fallback path
    is behaviour-identical, not a raised error reaching the caller."""
    cg = compile_from_path(GROUND_TRUTH / "arithmetic.gbnf")
    p = prod(cg)
    text = "x=1\n"
    model = cg.parse(text)
    expected = earley_model(p.instance_grammar, text, cg.fold, p.tables)
    assert isinstance(expected, GrammarModel)
    assert model.dump() == expected.dump()
    assert model.to_text() == text


def test_compiledgrammar_parse_start_island_completes_on_earley():
    """A start rule that is itself an island compiles to an immediate-PdaFail
    start (its ``start_key`` is an ``IslandRef``); ``cg.parse`` still parses
    correctly, completing on the Earley engine per parse — no ``None`` channel.
    The start island is LEFT-RECURSIVE — the island class no attempt order can
    settle (the digit-prefix overlap shape now legitimately attempts)."""
    text = 'root ::= root "a" | "b"\n'
    cg = compile_text(text, flavour="gbnf")
    assert isinstance(prod(cg).pda.start_key, IslandRef)
    assert cg.parse("baa").to_text() == "baa"
    assert cg.parse("b").to_text() == "b"


# ── _flavour_reducer: the single home for the Reducer narrowing check ──────


def test_flavour_reducer_returns_the_flavours_own_reducer():
    """_flavour_reducer(flavour) returns exactly the flavour's reducer ClassVar."""
    reducer = getattr(compile_module, "_flavour_reducer")(GBNF_FLAVOUR)
    assert reducer is GBNF_FLAVOUR.reducer


def test_load_ir_reexported_from_compile_package() -> None:
    """``load_ir`` is reachable off the package root (the notation seam)."""
    assert compile_module.load_ir("IrLiteral('a')") == IrLiteral("a")
    assert hasattr(compile_module, "load_ir_from_path")


def test_parse_module_reexported_from_compile_package() -> None:
    """``parse_module`` is reachable off the package root (the self-grammar
    seam) and parses a real export to a module model."""
    cg = compile_from_path(GROUND_TRUTH / "list.gbnf")
    module = compile_module.parse_module(compile_module.export_source(cg))
    assert module.grammar == cg.grammar


def test_verify_module_reexported_from_compile_package() -> None:
    """``verify_module`` is reachable off the package root and cross-checks
    a real export against its own compiled grammar."""
    cg = compile_from_path(GROUND_TRUTH / "list.gbnf")
    module = compile_module.verify_module(cg, compile_module.export_source(cg))
    assert module.grammar == cg.grammar


# ── parse_instance / parse_instance_from_path (ported from test_artifact_parse.py) ──


def test_arithmetic_type_dispatch():
    """The path entry returns a concrete GrammarModel with a non-None dump."""
    inst = parse_instance_from_path("x=1\n", GROUND_TRUTH / "arithmetic.gbnf")
    assert isinstance(inst, GrammarModel)
    assert inst.dump() is not None


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
        "x=1\n", GROUND_TRUTH / "arithmetic.gbnf", flavour="gbnf"
    )
    assert inst.to_text() == "x=1\n"


# ── bind_module ──────────────────────────────────────────────────────────

BIND_MODULE_TEXT = 'root ::= "a" mid "b"\nmid ::= "x" | "y"\n'


class HandMid(GrammarModel):
    """A hand-built twin of the compiled ``mid`` class (a value_str rule)."""

    value: str


class HandRoot(GrammarModel):
    """A hand-built twin of the compiled ``root`` class (a sequence rule)."""

    mid: HandMid


def test_bind_module_binds_a_hand_built_namespace_successfully():
    """A hand-authored namespace binds exactly like the runtime compile's own
    classes — same ``__grammar__``/``__binds__``, and ``_child_attrs`` is left
    untouched (the class-body annotations already derived it)."""
    cg = compile_text(BIND_MODULE_TEXT, cache_key="bind-module-happy")
    before_root_child_attrs = getattr(HandRoot, "_child_attrs")
    before_mid_child_attrs = getattr(HandMid, "_child_attrs")

    bind_module(cg.grammar, {"Root": HandRoot, "Mid": HandMid})

    assert HandRoot.__grammar__ == cg.classes["Root"].__grammar__
    assert HandMid.__grammar__ == cg.classes["Mid"].__grammar__
    assert HandRoot.__binds__ == cg.classes["Root"].__binds__
    assert HandMid.__binds__ == cg.classes["Mid"].__binds__
    assert getattr(HandRoot, "_child_attrs") == before_root_child_attrs
    assert getattr(HandMid, "_child_attrs") == before_mid_child_attrs

    inst = HandRoot(mid=HandMid(value="x"))
    assert inst.to_text() == "axb"


def test_bind_module_raises_when_a_class_is_missing_from_the_namespace():
    """A namespace missing a rule's class names the rule and the class."""
    cg = compile_text(BIND_MODULE_TEXT, cache_key="bind-module-missing")
    with pytest.raises(UnsupportedConstructError) as exc_info:
        bind_module(cg.grammar, {"Root": HandRoot})
    message = str(exc_info.value)
    assert "mid" in message
    assert "Mid" in message


def test_bind_module_raises_when_the_namespace_class_is_not_a_grammar_model():
    """A namespace entry that exists but is not a GrammarModel subclass is
    rejected the same way as a missing entry."""
    cg = compile_text(BIND_MODULE_TEXT, cache_key="bind-module-not-a-model")
    with pytest.raises(UnsupportedConstructError) as exc_info:
        bind_module(cg.grammar, {"Root": HandRoot, "Mid": object})
    assert "Mid" in str(exc_info.value)


def test_bind_module_raises_on_a_field_shape_mismatch():
    """A class whose declared fields do not match its rule's binding names
    both the declared and the expected fields in the error message."""

    class _WrongFieldMid(GrammarModel):
        wrong_field: str

    cg = compile_text(BIND_MODULE_TEXT, cache_key="bind-module-mismatch")
    with pytest.raises(UnsupportedConstructError) as exc_info:
        bind_module(cg.grammar, {"Root": HandRoot, "Mid": _WrongFieldMid})
    message = str(exc_info.value)
    assert "('wrong_field',)" in message
    assert "('value',)" in message


# ── directives are not a GBNF/ABNF privilege ──────────────────────────


def test_a_block_comment_flavour_can_carry_a_directive():
    """EBNF has only `(* *)` comments, and must still be able to say @non-semantic.

    A mechanism GBNF and ABNF can express and EBNF structurally cannot is a
    privileged formulation. It was not academic: `json.ebnf` could not mark `ws`
    structural, so `ws` stayed semantic, compiled to a fail-island, and EVERY
    parse of that grammar escaped the predictive path at position 0.
    """
    text = '(* @non-semantic ws *)\nroot = ws ;\nws = { " " } ;\n'
    ast = canonical_grammar(text, EBNF_FLAVOUR)
    assert ast.non_semantic == frozenset({"ws"})


def test_a_block_comment_flavour_can_carry_a_start_directive():
    """The same door opens for @start, not just @non-semantic."""
    text = '(* @start second *)\nfirst = "a" ;\nsecond = "b" ;\n'
    ast = canonical_grammar(text, EBNF_FLAVOUR)
    assert ast.start == "second"


@pytest.mark.parametrize(
    ("text", "flavour"),
    [
        ("root ::= [\\U00110000]\n", "gbnf"),
        ("a = %xFFFFFFFF\r\n", "abnf"),
        ("a = %d4294967295\r\n", "abnf"),
    ],
)
def test_a_codepoint_past_unicode_never_leaves_as_a_builtin_error(text, flavour):
    """An out-of-range code point is refused as a LexicError, in every context.

    `chr()`'s bare `ValueError` reached callers of `compile_text` naming neither
    the value nor the grammar. It was also inconsistent WITHIN a flavour: in a
    char-class context the out-of-range `IrChr` was built silently, re-emitted
    faithfully, and only detonated later.
    """
    with pytest.raises(LexicError):
        compile_text(text, flavour=flavour)


def test_directives_are_reachable_from_the_public_entry_point():
    """A caller who knows a rule is noise can say so without editing the grammar.

    `non_semantic_rules` existed on `canonical_grammar` and stopped there, so
    for an EBNF grammar — which could carry no directive at all until the
    block-comment channel landed — there was no sanctioned way to say it.
    """
    compiled = compile_text(
        "root ::= ws\nws ::= [ ]*\n",
        directives=Directives(non_semantic=frozenset({"ws"})),
    )
    assert not next(r for r in compiled.grammar.rules if r.name == "ws").semantic


def test_directives_key_the_compile_memo():
    """One source compiled two ways must not hand back the first.

    The memo is keyed by content, so a directive that changes what was compiled
    has to be part of that key or the second call silently returns the first
    artefact.
    """
    text = "root ::= ws\nws ::= [ ]*\n"
    plain = compile_text(text)
    marked = compile_text(text, directives=Directives(non_semantic=frozenset({"ws"})))
    assert plain is not marked
    assert next(r for r in plain.grammar.rules if r.name == "ws").semantic
    assert not next(r for r in marked.grammar.rules if r.name == "ws").semantic


def test_a_vocabulary_is_one_lens_not_two_channels():
    """`tokenizer` and `registry` compose; the record is what they always were."""
    assert Vocabulary().tokenizer is None
    assert Vocabulary().registry is None
