"""Tests for lexic.parsing.earley.engine — EarleyParser, recognize, parse, and the
lazy readers (parse_forest, derivations, is_ambiguous).

API changes from the int-kernel rework:

- ``RuleIndex``/``NullableRules``/``Matches``/``AcceptingItem``/``BuildChart``
  (and singletons ``RULE_INDEX``/``NULLABLE``/``MATCHES``/``ACCEPT``/
  ``BUILD_CHART``), plus ``ACCEPTING``, are ALL GONE — that per-item IR
  dispatch is compiled away into :mod:`lexic.parsing.earley.kernel.tables` and
  :mod:`lexic.parsing.earley.kernel.kernel`'s int tables. Their identity/dispatch tests
  are dropped; there is no new home for testing "is this singleton an
  instance of its class" once the class no longer exists.
- Everything else in this file — the overwhelming majority — is pure
  behavioral testing through the 5 public functions
  (``recognize``/``parse``/``parse_forest``/``derivations``/``is_ambiguous``)
  plus ``EarleyParser``, and is preserved unchanged.
- ``test_is_ambiguous_short_circuits`` still monkeypatches
  ``engine_mod.DERIVATION_STREAM`` — current ``engine.py`` still imports
  ``DERIVATION_STREAM`` directly from ``forest`` at module level (verified by
  grep), so ``IsAmbiguous.eval`` resolves the name through ``engine_mod``'s
  own binding and patching it there is both necessary and sufficient.
"""

from __future__ import annotations

import pytest

import lexic.parsing.earley.engine as engine_mod
from lexic.exceptions import UnsupportedConstructError
from lexic.ir import (
    IrAlternation,
    IrArgs,
    IrAst,
    IrCharClass,
    IrChr,
    IrInt,
    IrItem,
    IrJoin,
    IrLiteral,
    IrMap,
    IrNone,
    IrNoneType,
    IrNot,
    IrQuantifier,
    IrRule,
    IrRuleRef,
    IrSelf,
    IrSeq,
    IrSequence,
    IrTuple,
)
from lexic.parsing import (
    EarleyParser,
    ParseTree,
    derivations,
    is_ambiguous,
    parse,
    parse_first,
    parse_forest,
    recognize,
)
from lexic.parsing.earley.engine import (
    PARSE_FIRST,
    PARSE_REDUCED,
    ParseFirst,
    ParseReduced,
)
from lexic.parsing.earley.kernel.forest import (
    DerivationStream,
    IrStream,
    SppfNode,
)
from lexic.parsing.earley.kernel.tables.atoms import RunTerm
from lexic.parsing.earley.kernel.tables.builder import build_tables, compile_tables
from lexic.parsing.earley.kernel.tables.records import RUN_STR
from lexic.parsing.earley.lexruns import run_candidates
from lexic.parsing.earley.normalize import normalize
from lexic.parsing.earley.reduce.reducer import Reducer
from lexic.parsing.products import earley_reduce
from tests.unit.lexic.parsing.ir_fixtures import digits_plus_grammar

# ── Grammar builders ──────────────────────────────────────────────────


def normalize_grammar(g: IrAst) -> IrAst:
    """The real normalize(), named for this file's grammar-builder set."""
    return normalize(g)


def quant_grammar(lo: int, hi: int | IrNoneType) -> IrAst:
    """s = 'a'<lo,hi> — one rule with one quantified literal."""
    q = IrQuantifier(lo, hi)
    rule = IrRule("s", IrAlternation(IrSequence(IrItem(IrLiteral("a"), q))))
    return IrAst(rules=IrSeq(rule), start="s")


# ── Recognizer — basic ────────────────────────────────────────────────


def test_recognize_accepts_single_char(digit_grammar: IrAst):
    """digit grammar accepts a single digit character."""
    assert recognize(digit_grammar, "5")


def test_recognize_rejects_wrong_char(digit_grammar: IrAst):
    """digit grammar rejects a non-digit character."""
    assert not recognize(digit_grammar, "z")


def test_recognize_rejects_empty_for_non_nullable(digit_grammar: IrAst):
    """digit grammar rejects the empty string."""
    assert not recognize(digit_grammar, "")


def test_recognize_rejects_multi_char_for_single_rule(digit_grammar: IrAst):
    """digit grammar rejects more than one character."""
    assert not recognize(digit_grammar, "12")


# ── Recognizer — recursive grammar ───────────────────────────────────


def test_recognize_accepts_bare_digit_in_expr(expr_grammar: IrAst):
    """expr grammar accepts a bare digit."""
    assert recognize(expr_grammar, "5")


def test_recognize_accepts_single_parens(expr_grammar: IrAst):
    """expr grammar accepts '(7)'."""
    assert recognize(expr_grammar, "(7)")


def test_recognize_accepts_double_parens(expr_grammar: IrAst):
    """expr grammar accepts '((3))'."""
    assert recognize(expr_grammar, "((3))")


def test_recognize_rejects_unclosed_paren(expr_grammar: IrAst):
    """expr grammar rejects '(8' — missing closing paren."""
    assert not recognize(expr_grammar, "(8")


def test_recognize_rejects_empty_string(expr_grammar: IrAst):
    """expr grammar rejects the empty string."""
    assert not recognize(expr_grammar, "")


def test_recognize_rejects_empty_parens(expr_grammar: IrAst):
    """expr grammar rejects '(())' — no digit inside."""
    assert not recognize(expr_grammar, "(())")


# ── Negated char-class — the JSON-string shape ────────────────────────


def json_string_grammar() -> IrAst:
    """s = '"' [^"]* '"' — a quoted run of any non-quote chars."""
    quote = IrItem(IrLiteral('"'))
    body_chars = IrItem(IrNot(IrCharClass(IrChr('"'))), IrQuantifier(0, IrNone))
    rule = IrRule("s", IrAlternation(IrSequence(quote, body_chars, quote)))
    return IrAst(rules=IrSeq(rule), start="s")


def test_negated_class_recognizes_empty_body():
    """The JSON-string grammar accepts '""'."""
    g = normalize_grammar(json_string_grammar())
    assert recognize(g, '""')


def test_negated_class_recognizes_multi_char_body():
    """The JSON-string grammar accepts '"abc"'."""
    g = normalize_grammar(json_string_grammar())
    assert recognize(g, '"abc"')


def test_negated_class_recognizes_non_alnum_body():
    """The JSON-string grammar accepts a body of spaces and symbols."""
    g = normalize_grammar(json_string_grammar())
    assert recognize(g, '"a b!"')


def test_negated_class_rejects_quote_in_body():
    """A quote inside the negated set is not matched — '"a"b"' fails."""
    g = normalize_grammar(json_string_grammar())
    assert not recognize(g, '"a"b"')


def test_negated_class_rejects_unterminated():
    """The JSON-string grammar rejects an unterminated body."""
    g = normalize_grammar(json_string_grammar())
    assert not recognize(g, '"abc')


def test_negated_class_parses_single_derivation():
    """parse over a negated-class grammar yields one derivation tree."""
    g = normalize_grammar(json_string_grammar())
    tree = parse(g, '"abc"')
    assert isinstance(tree, ParseTree)


# ── Nullable completer — quantifier desugaring + recognize ────────────


def test_nullable_star_accepts_empty():
    """* (0,IrNone) normalized: accepts empty string."""
    g = normalize_grammar(quant_grammar(0, IrNone))
    assert recognize(g, "")


def test_nullable_star_accepts_one():
    """* (0,IrNone) normalized: accepts 'a'."""
    g = normalize_grammar(quant_grammar(0, IrNone))
    assert recognize(g, "a")


def test_nullable_star_accepts_many():
    """* (0,IrNone) normalized: accepts 'aaa'."""
    g = normalize_grammar(quant_grammar(0, IrNone))
    assert recognize(g, "aaa")


def test_plus_rejects_empty():
    """+ (1,IrNone) normalized: rejects empty string."""
    g = normalize_grammar(quant_grammar(1, IrNone))
    assert not recognize(g, "")


def test_plus_accepts_one():
    """+ (1,IrNone) normalized: accepts 'a'."""
    g = normalize_grammar(quant_grammar(1, IrNone))
    assert recognize(g, "a")


def test_plus_accepts_many():
    """+ (1,IrNone) normalized: accepts 'aaa'."""
    g = normalize_grammar(quant_grammar(1, IrNone))
    assert recognize(g, "aaa")


def test_optional_accepts_empty():
    """? (0,1) normalized: accepts empty string."""
    g = normalize_grammar(quant_grammar(0, 1))
    assert recognize(g, "")


def test_optional_accepts_one():
    """? (0,1) normalized: accepts 'a'."""
    g = normalize_grammar(quant_grammar(0, 1))
    assert recognize(g, "a")


def test_optional_rejects_two():
    """? (0,1) normalized: rejects 'aa'."""
    g = normalize_grammar(quant_grammar(0, 1))
    assert not recognize(g, "aa")


def test_exact_two_rejects_one():
    """{2,2} normalized: rejects 'a' (too short)."""
    g = normalize_grammar(quant_grammar(2, 2))
    assert not recognize(g, "a")


def test_exact_two_accepts_two():
    """{2,2} normalized: accepts 'aa'."""
    g = normalize_grammar(quant_grammar(2, 2))
    assert recognize(g, "aa")


def test_exact_two_rejects_three():
    """{2,2} normalized: rejects 'aaa' (too long)."""
    g = normalize_grammar(quant_grammar(2, 2))
    assert not recognize(g, "aaa")


def test_bounded_two_to_four_rejects_one():
    """{2,4} normalized: rejects 'a'."""
    g = normalize_grammar(quant_grammar(2, 4))
    assert not recognize(g, "a")


def test_bounded_two_to_four_accepts_two():
    """{2,4} normalized: accepts 'aa'."""
    g = normalize_grammar(quant_grammar(2, 4))
    assert recognize(g, "aa")


def test_bounded_two_to_four_accepts_four():
    """{2,4} normalized: accepts 'aaaa'."""
    g = normalize_grammar(quant_grammar(2, 4))
    assert recognize(g, "aaaa")


def test_bounded_two_to_four_rejects_five():
    """{2,4} normalized: rejects 'aaaaa'."""
    g = normalize_grammar(quant_grammar(2, 4))
    assert not recognize(g, "aaaaa")


# ── multi-char literal integration (atomic scan, no split_literals) ───


def test_multichar_literal_true_keyword_recognized():
    """A multi-char literal atom ('true') is scanned atomically; recognizes 'true'."""
    rule = IrRule("s", IrAlternation(IrSequence(IrItem(IrLiteral("true")))))
    g = normalize(IrAst(rules=IrSeq(rule), start="s"))
    assert recognize(g, "true")


def test_multichar_literal_true_keyword_rejects_partial():
    """A multi-char literal atom rejects 'tru' (missing last char) — no partial match."""
    rule = IrRule("s", IrAlternation(IrSequence(IrItem(IrLiteral("true")))))
    g = normalize(IrAst(rules=IrSeq(rule), start="s"))
    assert not recognize(g, "tru")


# ── parse — derivation tree ───────────────────────────────────────────


def test_parse_returns_parse_tree(digit_grammar: IrAst):
    """parse() returns a ParseTree for a valid input."""
    tree = parse(digit_grammar, "7")
    assert isinstance(tree, ParseTree)


def test_parse_tree_symbol_is_start_rule(digit_grammar: IrAst):
    """Root ParseTree symbol is the start rule's IrRuleRef."""
    tree = parse(digit_grammar, "3")
    assert tree.symbol == IrRuleRef("digit")


def test_parse_raises_on_invalid_input(digit_grammar: IrAst):
    """parse() raises UnsupportedConstructError on input that does not derive."""
    with pytest.raises(UnsupportedConstructError):
        parse(digit_grammar, "z")


def test_parse_raises_on_empty_for_non_nullable(digit_grammar: IrAst):
    """parse() raises UnsupportedConstructError on empty input for a non-nullable rule."""
    with pytest.raises(UnsupportedConstructError):
        parse(digit_grammar, "")


def test_parse_builds_nested_tree_for_recursive_input(expr_grammar: IrAst):
    """parse() builds a correctly nested ParseTree for '((7))'."""
    tree = parse(expr_grammar, "((7))")
    # Root: expr; kids: '(', inner-expr, ')'
    assert tree.symbol == IrRuleRef("expr")
    assert len(tree.kids) == 3
    inner = tree.kids[1]
    assert isinstance(inner, ParseTree)
    assert inner.symbol == IrRuleRef("expr")
    assert len(inner.kids) == 3
    innermost = inner.kids[1]
    assert isinstance(innermost, ParseTree)
    assert innermost.symbol == IrRuleRef("expr")


def test_parse_single_char_tree_leaf_is_literal(digit_grammar: IrAst):
    """parse() on a single digit produces a tree whose leaf is IrLiteral."""
    tree = parse(digit_grammar, "9")
    assert tree.kids[0] == IrLiteral("9")


# ── EarleyParser façade ────────────────────────────────────────────────


def test_earley_parser_is_constructible():
    """EarleyParser() constructs without arguments."""
    parser = EarleyParser()
    assert isinstance(parser, EarleyParser)


# ── parse_forest ──────────────────────────────────────────────────────


def test_parse_forest_returns_sppf_node_on_valid_input(digit_grammar: IrAst):
    """parse_forest() returns an SppfNode for parseable input."""
    g = digit_grammar
    result = parse_forest(g, "5")
    assert isinstance(result, SppfNode)


def test_parse_forest_returns_ir_none_on_no_parse(digit_grammar: IrAst):
    """parse_forest() returns IrNone when the input does not parse."""
    g = digit_grammar
    result = parse_forest(g, "z")
    assert isinstance(result, IrNoneType)


# ── derivations ───────────────────────────────────────────────────────


def test_derivations_empty_on_no_parse(digit_grammar: IrAst):
    """derivations() returns an empty IrSeq when the input does not parse."""
    g = digit_grammar
    result = derivations(g, "z")
    assert isinstance(result, IrSeq)
    assert len(result) == 0


def test_derivations_singleton_for_unambiguous(digit_grammar: IrAst):
    """derivations() returns a length-1 IrSeq for unambiguous input."""
    g = digit_grammar
    result = derivations(g, "7")
    assert isinstance(result, IrSeq)
    assert len(result) == 1
    assert isinstance(result[0], ParseTree)


def test_derivations_singleton_equals_parse_result(digit_grammar: IrAst):
    """The lone derivation equals parse()'s result for unambiguous input."""
    g = digit_grammar
    result = derivations(g, "7")
    expected = parse(g, "7")
    assert result[0] == expected


def test_derivations_two_trees_for_sss_aaa(sss_grammar: IrAst):
    """derivations() returns 2 distinct ParseTrees for 's=ss/a' over 'aaa'."""
    result = derivations(sss_grammar, "aaa")
    assert len(result) == 2
    assert result[0] != result[1]


def test_derivations_two_trees_for_expr_plus_a_plus_a(expr_plus_grammar: IrAst):
    """derivations() returns 2 distinct ParseTrees for 'e=e+e/a' over 'a+a+a'."""
    result = derivations(expr_plus_grammar, "a+a+a")
    assert len(result) == 2
    assert result[0] != result[1]


# ── is_ambiguous ──────────────────────────────────────────────────────


def test_is_ambiguous_false_for_unambiguous_input(digit_grammar: IrAst):
    """is_ambiguous() returns False for unambiguous input."""
    g = digit_grammar
    assert not is_ambiguous(g, "3")


def test_is_ambiguous_false_for_no_parse(digit_grammar: IrAst):
    """is_ambiguous() returns False when the input does not parse."""
    g = digit_grammar
    assert not is_ambiguous(g, "z")


def test_is_ambiguous_true_for_sss_aaa(sss_grammar: IrAst):
    """is_ambiguous() returns True for 's=ss/a' over 'aaa' (2 derivations)."""
    assert is_ambiguous(sss_grammar, "aaa")


def test_is_ambiguous_true_for_expr_plus(expr_plus_grammar: IrAst):
    """is_ambiguous() returns True for 'e=e+e/a' over 'a+a+a'."""
    assert is_ambiguous(expr_plus_grammar, "a+a+a")


# ── parse strict raises on ambiguous ─────────────────────────────────


def test_parse_raises_on_ambiguous_sss(sss_grammar: IrAst):
    """parse() raises UnsupportedConstructError on ambiguous 's=ss/a' over 'aaa'."""
    with pytest.raises(UnsupportedConstructError):
        parse(sss_grammar, "aaa")


def test_parse_raises_on_ambiguous_expr_plus(expr_plus_grammar: IrAst):
    """parse() raises UnsupportedConstructError on ambiguous 'e=e+e/a' over 'a+a+a'."""
    with pytest.raises(UnsupportedConstructError):
        parse(expr_plus_grammar, "a+a+a")


# ── Nullable regression — star/nullable must not be ambiguous ─────────


def test_nullable_star_derivations_single_for_empty():
    """'a'* over '' is unambiguous — exactly one derivation, is_ambiguous False."""
    g = normalize_grammar(quant_grammar(0, IrNone))
    result = derivations(g, "")
    assert len(result) == 1
    assert not is_ambiguous(g, "")


def test_nullable_star_derivations_single_for_one():
    """'a'* over 'a' is unambiguous — exactly one derivation, is_ambiguous False."""
    g = normalize_grammar(quant_grammar(0, IrNone))
    result = derivations(g, "a")
    assert len(result) == 1
    assert not is_ambiguous(g, "a")


def test_nullable_star_derivations_single_for_three():
    """'a'* over 'aaa' is unambiguous — exactly one derivation, is_ambiguous False.

    This is the nullable-fix regression guard: a naive SPPF that doesn't
    properly dedup nullable families accumulates spurious ambiguity on right-
    recursive 'a'* expansions.  If is_ambiguous returns True here, the
    nullable dedup invariant is broken.
    """
    g = normalize_grammar(quant_grammar(0, IrNone))
    result = derivations(g, "aaa")
    assert len(result) == 1
    assert not is_ambiguous(g, "aaa")


def test_transitively_nullable_unambiguous():
    """X = Y ; Y = '' / 'a' parses 'a' with exactly one derivation.

    Tests that a transitively-nullable rule (X derives empty through Y)
    does not accumulate spurious ambiguity.
    """
    y_rule = IrRule(
        "y",
        IrAlternation(IrSequence(), IrSequence(IrItem(IrLiteral("a")))),
    )
    x_rule = IrRule(
        "x",
        IrAlternation(IrSequence(IrItem(IrRuleRef("y")))),
    )
    g = IrAst(rules=IrSeq(x_rule, y_rule), start="x")
    result = derivations(g, "a")
    assert len(result) == 1
    assert not is_ambiguous(g, "a")


# ── IsAmbiguous short-circuit ─────────────────────────────────────────


def make_exploding_deriv_stream(t1: ParseTree, t2: ParseTree) -> DerivationStream:
    """Build a DerivationStream that raises AssertionError if driven past 2 elements."""

    class _ExplodingDerivStream(DerivationStream):
        def eval(self, _d: IrSelf, n: IrSelf, nc: object, /) -> IrStream[ParseTree]:
            def _src():
                yield t1
                yield t2
                raise AssertionError("over-enumerated: drove past 2 derivations")

            return IrStream(_src())

    return _ExplodingDerivStream()


def test_is_ambiguous_short_circuits(sss_grammar: IrAst) -> None:
    """is_ambiguous stops after the 2nd derivation and does not drive a 3rd element.

    An exploding source raises AssertionError if iterated past 2 elements.
    We assert IrInt(1) is returned, NOT AssertionError — proving early exit.

    ``engine.IsAmbiguous.eval`` calls ``DERIVATION_STREAM.eval(...)`` through
    its own module-level import binding (``engine.py`` does
    ``from lexic.parsing.earley.kernel.forest import (..., DERIVATION_STREAM, ...)``), so
    the patch target is ``engine_mod.DERIVATION_STREAM`` — patching only
    ``forest_mod.DERIVATION_STREAM`` would not affect the already-bound name
    ``IsAmbiguous.eval`` actually calls.
    """
    real_derivations = derivations(sss_grammar, "aaa")
    assert len(real_derivations) == 2
    exploding = make_exploding_deriv_stream(real_derivations[0], real_derivations[1])
    orig = engine_mod.DERIVATION_STREAM
    engine_mod.DERIVATION_STREAM = exploding
    try:
        result = is_ambiguous(sss_grammar, "aaa")
        assert result == IrInt(1)
    finally:
        engine_mod.DERIVATION_STREAM = orig


def test_is_ambiguous_counts(
    digit_grammar: IrAst,
    expr_grammar: IrAst,
    sss_grammar: IrAst,
    expr_plus_grammar: IrAst,
) -> None:
    """is_ambiguous truthiness matches reality across several grammars and inputs."""
    assert not is_ambiguous(digit_grammar, "5")
    assert not is_ambiguous(expr_grammar, "(5)")
    assert not is_ambiguous(digit_grammar, "z")
    assert is_ambiguous(sss_grammar, "aaa")
    assert is_ambiguous(expr_plus_grammar, "a+a+a")


# ── Catalan oracle — parametrized derivation count ────────────────────

CATALAN = [1, 1, 2, 5, 14, 42, 132]
"""Catalan(n-1) for n in 1..7: exact derivation count for sss 'a'*n."""


@pytest.mark.parametrize("n,expected", list(enumerate(CATALAN, start=1)))
def test_derivations_matches_catalan(sss_grammar: IrAst, n: int, expected: int) -> None:
    """len(derivations(sss, 'a'*n)) == Catalan(n-1) for n in 1..7."""
    result = derivations(sss_grammar, "a" * n)
    assert len(result) == expected


# ── Round-trip: flattened tree text equals original input ─────────────


def tree_to_text(node: object) -> str:
    """Recursively flatten a ParseTree to its original text."""
    if isinstance(node, ParseTree):
        return "".join(tree_to_text(k) for k in node.kids)
    if isinstance(node, IrLiteral):
        return str(node)
    return ""


@pytest.mark.parametrize(
    "grammar_name,text",
    [
        ("digit", "7"),
        ("expr", "(3)"),
        ("expr", "((5))"),
        ("expr", "9"),
    ],
)
def test_parse_single_derivation_unambiguous_roundtrip(
    grammar_name: str,
    text: str,
    digit_grammar: IrAst,
    expr_grammar: IrAst,
) -> None:
    """parse(g,t) produces a tree whose flattened text equals the original input."""
    grammar = digit_grammar if grammar_name == "digit" else expr_grammar
    tree = parse(grammar, text)
    assert tree_to_text(tree) == text


# ── ParseReduced / PARSE_REDUCED / earley_reduce ──────────────────────

YIELD = IrJoin(parts=IrArgs(), separator=IrLiteral(""), empty=IrLiteral(""))
"""Concatenate reduced children — the string-yield body (mirrors test_reduce.py)."""


def digit_reducer() -> Reducer:
    """A Reducer whose reduction table covers the digit_grammar's 'digit' rule."""
    return Reducer(actions=IrMap(IrTuple(IrRuleRef("digit"), YIELD)))


def s_reducer() -> Reducer:
    """A Reducer whose reduction table covers the sss_grammar's 's' rule."""
    return Reducer(actions=IrMap(IrTuple(IrRuleRef("s"), YIELD)))


def test_parse_reduced_singleton_is_parse_reduced_instance():
    """PARSE_REDUCED is a ParseReduced instance — the shared singleton."""
    assert isinstance(PARSE_REDUCED, ParseReduced)


def test_parse_reduced_matches_reducer_apply_parse(digit_grammar: IrAst):
    """earley_reduce(g, t, reducer) equals reducer.apply(parse(g, t)) — unambiguous."""
    reducer = digit_reducer()
    result = earley_reduce(digit_grammar, "7", reducer)
    expected = reducer.apply(parse(digit_grammar, "7"))
    assert str(result) == str(expected)


def test_parse_reduced_raises_on_invalid_input(digit_grammar: IrAst):
    """earley_reduce() raises UnsupportedConstructError when the input does not parse."""
    reducer = digit_reducer()
    with pytest.raises(UnsupportedConstructError):
        earley_reduce(digit_grammar, "z", reducer)


def test_parse_reduced_raises_on_ambiguous_input(sss_grammar: IrAst):
    """earley_reduce() raises UnsupportedConstructError on ambiguous input."""
    reducer = s_reducer()
    with pytest.raises(UnsupportedConstructError):
        earley_reduce(sss_grammar, "aaa", reducer)


def test_parse_reduced_raises_on_non_reducer_argument(digit_grammar: IrAst):
    """earley_reduce() raises UnsupportedConstructError when reducer isn't a Reducer."""
    with pytest.raises(UnsupportedConstructError, match="Reducer"):
        # Testing a wrong type.
        earley_reduce(digit_grammar, "5", "not a reducer")  # type: ignore


# ── ParseFirst / PARSE_FIRST / parse_first ─────────────────────────────


def test_parse_first_singleton_is_parse_first_instance():
    """PARSE_FIRST is a ParseFirst instance — the shared singleton."""
    assert isinstance(PARSE_FIRST, ParseFirst)


def test_parse_first_matches_parse_for_unambiguous_input(digit_grammar: IrAst):
    """parse_first() equals parse() when the input has a single derivation."""
    assert parse_first(digit_grammar, "7") == parse(digit_grammar, "7")


def test_parse_first_matches_parse_for_recursive_unambiguous_input(
    expr_grammar: IrAst,
):
    """parse_first() equals parse() over a recursive, still-unambiguous grammar."""
    assert parse_first(expr_grammar, "((7))") == parse(expr_grammar, "((7))")


def test_parse_first_returns_one_tree_where_parse_raises_sss(sss_grammar: IrAst):
    """parse_first() returns a single ParseTree for ambiguous input; parse() raises."""
    with pytest.raises(UnsupportedConstructError):
        parse(sss_grammar, "aaa")
    tree = parse_first(sss_grammar, "aaa")
    assert isinstance(tree, ParseTree)


def test_parse_first_returns_one_tree_where_parse_raises_expr_plus(
    expr_plus_grammar: IrAst,
):
    """parse_first() returns a single ParseTree for ambiguous input; parse() raises."""
    with pytest.raises(UnsupportedConstructError):
        parse(expr_plus_grammar, "a+a+a")
    tree = parse_first(expr_plus_grammar, "a+a+a")
    assert isinstance(tree, ParseTree)


def test_parse_first_is_deterministic_across_calls(sss_grammar: IrAst):
    """parse_first() picks the same derivation every time for the same input."""
    first = parse_first(sss_grammar, "aaa")
    second = parse_first(sss_grammar, "aaa")
    assert first == second


def test_parse_first_raises_on_no_parse(digit_grammar: IrAst):
    """parse_first() raises UnsupportedConstructError when the input does not derive."""
    with pytest.raises(UnsupportedConstructError):
        parse_first(digit_grammar, "z")


def test_parse_first_raises_on_empty_for_non_nullable(digit_grammar: IrAst):
    """parse_first() raises UnsupportedConstructError on empty input for a
    non-nullable rule."""
    with pytest.raises(UnsupportedConstructError):
        parse_first(digit_grammar, "")


# ── ParseFirst: optional pre-built tables parameter (Task 4) ────────────


def collapsed_digits_plus_tables(g: IrAst):
    """The grammar-proved run collapse of ``g``, built via RunTerm/build_tables."""
    plain = compile_tables(g)
    candidates = run_candidates(plain)
    runs = {
        name: (RunTerm(charset, 1, RUN_STR), has_empty)
        for name, (charset, has_empty, _unit_rid) in candidates.items()
    }
    return build_tables(g, runs)


def test_parse_first_tables_none_matches_omitted_argument():
    """Passing tables=None explicitly behaves exactly like omitting it."""
    g = digits_plus_grammar()
    assert parse_first(g, "123", tables=None) == parse_first(g, "123")


def test_parse_first_with_explicit_plain_tables_matches_default():
    """Passing the exact plain compile_tables() object changes nothing."""
    g = digits_plus_grammar()
    plain = compile_tables(g)
    assert parse_first(g, "123", tables=plain) == parse_first(g, "123")


def test_parse_first_with_collapsed_tables_still_parses():
    """A run-collapsed tables object still yields a valid derivation for
    unambiguous input, even though the packed chart shape differs from the
    plain per-char tables."""
    g = digits_plus_grammar()
    collapsed = collapsed_digits_plus_tables(g)
    assert any(length == 0 for length in collapsed.terms.lens)  # a run really collapsed
    tree = parse_first(g, "123", tables=collapsed)
    assert isinstance(tree, ParseTree)
    assert tree.symbol == IrRuleRef("s")


def test_parse_first_with_collapsed_tables_falls_back_on_ambiguity(
    sss_grammar: IrAst,
):
    """A fast-path miss (ambiguity) with collapsed tables passed re-parses over
    plain tables and still returns a first derivation — the fold-back mirrors
    ParseReduced's, not a crash."""
    plain = compile_tables(sss_grammar)
    collapsed = build_tables(sss_grammar, runs={})  # a distinct object, no runs
    assert collapsed is not plain
    with pytest.raises(UnsupportedConstructError):
        parse(sss_grammar, "aaa")
    tree = parse_first(sss_grammar, "aaa", tables=collapsed)
    assert isinstance(tree, ParseTree)
