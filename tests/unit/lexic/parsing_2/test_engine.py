"""Tests for lexic.parsing_2.engine — EarleyParser, recognize, parse.

API changes:

- ``EarleyParser().parse(g, t)`` / ``EarleyParser().recognize(g, t)`` removed
  (methods on the instance are ``eval`` and dunders only).  All calls updated to
  the module-level entry points ``parse(g, t)`` / ``recognize(g, t)``.

- Tests ``test_module_recognize_agrees_with_instance_method`` and
  ``test_module_parse_agrees_with_instance_method`` are removed: the instance
  methods no longer exist (they were exactly the old entry points that are now
  the module-level functions).  The behavioral coverage (recognize/parse
  correctness) is fully preserved by the other tests in this file.

New symbols tested: ``RuleIndex``, ``NullableRules``, ``Matches``,
``AcceptingItem``, ``BuildChart`` (and their singletons).

New lazy-engine tests: ``IsAmbiguous`` short-circuit, Catalan oracle parametrize,
round-trip proofs.
"""

from __future__ import annotations

import pytest

import lexic.parsing_2.engine as engine_mod
import lexic.parsing_2.forest as forest_mod
from lexic.exceptions import UnsupportedConstructError
from lexic.ir.base import (
    IrInt,
    IrNone,
    IrNoneType,
    IrSelf,
    IrSeq,
    IrStr,
    IrTuple,
)
from lexic.ir.mapping import IrMultiMap
from lexic.ir.nodes import (
    IrAlternation,
    IrAst,
    IrCharClass,
    IrChr,
    IrItem,
    IrLiteral,
    IrQuantifier,
    IrRange,
    IrRule,
    IrRuleRef,
    IrSequence,
)
from lexic.parsing_2 import (
    EarleyParser,
    ParseTree,
    derivations,
    is_ambiguous,
    parse,
    parse_forest,
    recognize,
)
from lexic.parsing_2.engine import (
    ACCEPT,
)
from lexic.parsing_2.engine import ACCEPTING as _ACCEPTING
from lexic.parsing_2.engine import (
    BUILD_CHART,
    IS_AMBIGUOUS,
    MATCHES,
    NULLABLE,
    RULE_INDEX,
    AcceptingItem,
    BuildChart,
    Matches,
    NullableRules,
    RuleIndex,
)
from lexic.parsing_2.forest import (
    DERIVATIONS,
    DerivationStream,
    IrStream,
    SppfNode,
)
from lexic.parsing_2.normalize import (
    desugar_quantifiers,
    flatten_groups,
    split_literals,
)

# ── Grammar builders ──────────────────────────────────────────────────


def _normalize(g: IrAst) -> IrAst:
    return split_literals(desugar_quantifiers(flatten_groups(g)))


def _quant_grammar(lo: int, hi: int | IrNoneType) -> IrAst:
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


# ── Nullable completer — quantifier desugaring + recognize ────────────


def test_nullable_star_accepts_empty():
    """* (0,IrNone) normalized: accepts empty string."""
    g = _normalize(_quant_grammar(0, IrNone))
    assert recognize(g, "")


def test_nullable_star_accepts_one():
    """* (0,IrNone) normalized: accepts 'a'."""
    g = _normalize(_quant_grammar(0, IrNone))
    assert recognize(g, "a")


def test_nullable_star_accepts_many():
    """* (0,IrNone) normalized: accepts 'aaa'."""
    g = _normalize(_quant_grammar(0, IrNone))
    assert recognize(g, "aaa")


def test_plus_rejects_empty():
    """+ (1,IrNone) normalized: rejects empty string."""
    g = _normalize(_quant_grammar(1, IrNone))
    assert not recognize(g, "")


def test_plus_accepts_one():
    """+ (1,IrNone) normalized: accepts 'a'."""
    g = _normalize(_quant_grammar(1, IrNone))
    assert recognize(g, "a")


def test_plus_accepts_many():
    """+ (1,IrNone) normalized: accepts 'aaa'."""
    g = _normalize(_quant_grammar(1, IrNone))
    assert recognize(g, "aaa")


def test_optional_accepts_empty():
    """? (0,1) normalized: accepts empty string."""
    g = _normalize(_quant_grammar(0, 1))
    assert recognize(g, "")


def test_optional_accepts_one():
    """? (0,1) normalized: accepts 'a'."""
    g = _normalize(_quant_grammar(0, 1))
    assert recognize(g, "a")


def test_optional_rejects_two():
    """? (0,1) normalized: rejects 'aa'."""
    g = _normalize(_quant_grammar(0, 1))
    assert not recognize(g, "aa")


def test_exact_two_rejects_one():
    """{2,2} normalized: rejects 'a' (too short)."""
    g = _normalize(_quant_grammar(2, 2))
    assert not recognize(g, "a")


def test_exact_two_accepts_two():
    """{2,2} normalized: accepts 'aa'."""
    g = _normalize(_quant_grammar(2, 2))
    assert recognize(g, "aa")


def test_exact_two_rejects_three():
    """{2,2} normalized: rejects 'aaa' (too long)."""
    g = _normalize(_quant_grammar(2, 2))
    assert not recognize(g, "aaa")


def test_bounded_two_to_four_rejects_one():
    """{2,4} normalized: rejects 'a'."""
    g = _normalize(_quant_grammar(2, 4))
    assert not recognize(g, "a")


def test_bounded_two_to_four_accepts_two():
    """{2,4} normalized: accepts 'aa'."""
    g = _normalize(_quant_grammar(2, 4))
    assert recognize(g, "aa")


def test_bounded_two_to_four_accepts_four():
    """{2,4} normalized: accepts 'aaaa'."""
    g = _normalize(_quant_grammar(2, 4))
    assert recognize(g, "aaaa")


def test_bounded_two_to_four_rejects_five():
    """{2,4} normalized: rejects 'aaaaa'."""
    g = _normalize(_quant_grammar(2, 4))
    assert not recognize(g, "aaaaa")


# ── split_literals integration ────────────────────────────────────────


def test_split_literals_true_keyword_recognized():
    """split_literals turns 'true' into 4 single-char items; recognizes 'true'."""
    rule = IrRule("s", IrAlternation(IrSequence(IrItem(IrLiteral("true")))))
    g = split_literals(IrAst(rules=IrSeq(rule), start="s"))
    assert recognize(g, "true")


def test_split_literals_true_keyword_rejects_partial():
    """After split_literals, 'tru' (missing last char) is rejected."""
    rule = IrRule("s", IrAlternation(IrSequence(IrItem(IrLiteral("true")))))
    g = split_literals(IrAst(rules=IrSeq(rule), start="s"))
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


# ── New engine nodes ──────────────────────────────────────────────────


def test_rule_index_singleton_is_rule_index_instance():
    """RULE_INDEX is a RuleIndex instance."""
    assert isinstance(RULE_INDEX, RuleIndex)


def test_nullable_singleton_is_nullable_rules_instance():
    """NULLABLE is a NullableRules instance."""
    assert isinstance(NULLABLE, NullableRules)


def test_matches_singleton_is_matches_instance():
    """MATCHES is a Matches instance."""
    assert isinstance(MATCHES, Matches)


def test_accept_singleton_is_accepting_item_instance():
    """ACCEPT is an AcceptingItem instance."""
    assert isinstance(ACCEPT, AcceptingItem)


def test_build_chart_singleton_is_build_chart_instance():
    """BUILD_CHART is a BuildChart instance."""
    assert isinstance(BUILD_CHART, BuildChart)


def test_matches_literal_matches_same_char():
    """Matches.eval returns IrInt(1) when the literal matches the char."""
    parser = EarleyParser()
    result = MATCHES.eval(parser, IrLiteral("x"), IrTuple(IrStr("x")))
    assert result == IrInt(1)


def test_matches_literal_rejects_different_char():
    """Matches.eval returns IrInt(0) when the literal does not match."""
    parser = EarleyParser()
    result = MATCHES.eval(parser, IrLiteral("x"), IrTuple(IrStr("y")))
    assert result == IrInt(0)


def test_matches_charclass_range_matches():
    """Matches.eval returns IrInt(1) for a char inside a range."""
    parser = EarleyParser()
    atom = IrCharClass(IrRange(IrChr("a"), IrChr("z")))
    result = MATCHES.eval(parser, atom, IrTuple(IrStr("m")))
    assert result == IrInt(1)


def test_matches_charclass_range_rejects():
    """Matches.eval returns IrInt(0) for a char outside a range."""
    parser = EarleyParser()
    atom = IrCharClass(IrRange(IrChr("a"), IrChr("z")))
    result = MATCHES.eval(parser, atom, IrTuple(IrStr("0")))
    assert result == IrInt(0)


def test_nullable_rules_returns_irmultimap():
    """NullableRules.eval returns an IrMultiMap (used as a set) of nullable rule names."""
    parser = EarleyParser()
    g = _normalize(_quant_grammar(0, IrNone))
    result = NULLABLE.eval(parser, g, ())
    assert isinstance(result, IrMultiMap)


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
    g = _normalize(_quant_grammar(0, IrNone))
    result = derivations(g, "")
    assert len(result) == 1
    assert not is_ambiguous(g, "")


def test_nullable_star_derivations_single_for_one():
    """'a'* over 'a' is unambiguous — exactly one derivation, is_ambiguous False."""
    g = _normalize(_quant_grammar(0, IrNone))
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
    g = _normalize(_quant_grammar(0, IrNone))
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


def _make_exploding_deriv_stream(t1: ParseTree, t2: ParseTree) -> DerivationStream:
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
    """
    parser = EarleyParser()
    chart, item = _ACCEPTING.eval(parser, sss_grammar, IrTuple(IrStr("aaa")))
    ds = DERIVATIONS.eval(parser, item, IrTuple(chart))
    exploding = _make_exploding_deriv_stream(ds[0], ds[1])
    orig_forest = forest_mod.DERIVATION_STREAM
    orig_engine = engine_mod.DERIVATION_STREAM
    forest_mod.DERIVATION_STREAM = exploding
    engine_mod.DERIVATION_STREAM = exploding
    try:
        result = IS_AMBIGUOUS.eval(parser, sss_grammar, IrTuple(IrStr("aaa")))
        assert result == IrInt(1)
    finally:
        forest_mod.DERIVATION_STREAM = orig_forest
        engine_mod.DERIVATION_STREAM = orig_engine


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

_CATALAN = [1, 1, 2, 5, 14, 42, 132]
"""Catalan(n-1) for n in 1..7: exact derivation count for sss 'a'*n."""


@pytest.mark.parametrize("n,expected", list(enumerate(_CATALAN, start=1)))
def test_derivations_matches_catalan(sss_grammar: IrAst, n: int, expected: int) -> None:
    """len(derivations(sss, 'a'*n)) == Catalan(n-1) for n in 1..7."""
    result = derivations(sss_grammar, "a" * n)
    assert len(result) == expected


# ── Round-trip: flattened tree text equals original input ─────────────


def _tree_to_text(node: object) -> str:
    """Recursively flatten a ParseTree to its original text."""
    if isinstance(node, ParseTree):
        return "".join(_tree_to_text(k) for k in node.kids)
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
    assert _tree_to_text(tree) == text
