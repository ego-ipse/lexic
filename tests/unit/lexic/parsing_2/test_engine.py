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
"""

from __future__ import annotations

import pytest

from lexic.exceptions import UnsupportedConstructError
from lexic.ir.base import IrInt, IrNone, IrNoneType, IrSeq, IrStr, IrTuple
from lexic.ir.nodes import (
    IrAlternation,
    IrAst,
    IrCharClass,
    IrItem,
    IrLiteral,
    IrQuantifier,
    IrRange,
    IrRule,
    IrRuleRef,
    IrSequence,
)
from lexic.parsing_2 import EarleyParser, ParseTree, parse, recognize
from lexic.parsing_2.engine import (
    ACCEPT,
    BUILD_CHART,
    MATCHES,
    NULLABLE,
    RULE_INDEX,
    AcceptingItem,
    BuildChart,
    Matches,
    NullableRules,
    RuleIndex,
)
from lexic.parsing_2.normalize import (
    desugar_quantifiers,
    flatten_groups,
    split_literals,
)

# ── Grammar builders ──────────────────────────────────────────────────


def _normalize(g: IrAst) -> IrAst:
    return split_literals(desugar_quantifiers(flatten_groups(g)))


def _digit_grammar() -> IrAst:
    """digit = [0-9] ; minimal single-rule grammar."""
    return IrAst(
        rules=IrSeq(
            IrRule(
                "digit",
                IrAlternation(IrSequence(IrItem(IrCharClass(IrRange("0", "9"))))),
            )
        ),
        start="digit",
    )


def _quant_grammar(lo: int, hi: int | IrNoneType) -> IrAst:
    """s = 'a'<lo,hi> — one rule with one quantified literal."""
    q = IrQuantifier(lo, hi)
    rule = IrRule("s", IrAlternation(IrSequence(IrItem(IrLiteral("a"), q))))
    return IrAst(rules=IrSeq(rule), start="s")


# ── Recognizer — basic ────────────────────────────────────────────────


def test_recognize_accepts_single_char():
    """digit grammar accepts a single digit character."""
    assert recognize(_digit_grammar(), "5") is True


def test_recognize_rejects_wrong_char():
    """digit grammar rejects a non-digit character."""
    assert recognize(_digit_grammar(), "z") is False


def test_recognize_rejects_empty_for_non_nullable():
    """digit grammar rejects the empty string."""
    assert recognize(_digit_grammar(), "") is False


def test_recognize_rejects_multi_char_for_single_rule():
    """digit grammar rejects more than one character."""
    assert recognize(_digit_grammar(), "12") is False


# ── Recognizer — recursive grammar ───────────────────────────────────


def test_recognize_accepts_bare_digit_in_expr(expr_grammar: IrAst):
    """expr grammar accepts a bare digit."""
    assert recognize(expr_grammar, "5") is True


def test_recognize_accepts_single_parens(expr_grammar: IrAst):
    """expr grammar accepts '(7)'."""
    assert recognize(expr_grammar, "(7)") is True


def test_recognize_accepts_double_parens(expr_grammar: IrAst):
    """expr grammar accepts '((3))'."""
    assert recognize(expr_grammar, "((3))") is True


def test_recognize_rejects_unclosed_paren(expr_grammar: IrAst):
    """expr grammar rejects '(8' — missing closing paren."""
    assert recognize(expr_grammar, "(8") is False


def test_recognize_rejects_empty_string(expr_grammar: IrAst):
    """expr grammar rejects the empty string."""
    assert recognize(expr_grammar, "") is False


def test_recognize_rejects_empty_parens(expr_grammar: IrAst):
    """expr grammar rejects '(())' — no digit inside."""
    assert recognize(expr_grammar, "(())") is False


# ── Nullable completer — quantifier desugaring + recognize ────────────


def test_nullable_star_accepts_empty():
    """* (0,IrNone) normalized: accepts empty string."""
    g = _normalize(_quant_grammar(0, IrNone))
    assert recognize(g, "") is True


def test_nullable_star_accepts_one():
    """* (0,IrNone) normalized: accepts 'a'."""
    g = _normalize(_quant_grammar(0, IrNone))
    assert recognize(g, "a") is True


def test_nullable_star_accepts_many():
    """* (0,IrNone) normalized: accepts 'aaa'."""
    g = _normalize(_quant_grammar(0, IrNone))
    assert recognize(g, "aaa") is True


def test_plus_rejects_empty():
    """+ (1,IrNone) normalized: rejects empty string."""
    g = _normalize(_quant_grammar(1, IrNone))
    assert recognize(g, "") is False


def test_plus_accepts_one():
    """+ (1,IrNone) normalized: accepts 'a'."""
    g = _normalize(_quant_grammar(1, IrNone))
    assert recognize(g, "a") is True


def test_plus_accepts_many():
    """+ (1,IrNone) normalized: accepts 'aaa'."""
    g = _normalize(_quant_grammar(1, IrNone))
    assert recognize(g, "aaa") is True


def test_optional_accepts_empty():
    """? (0,1) normalized: accepts empty string."""
    g = _normalize(_quant_grammar(0, 1))
    assert recognize(g, "") is True


def test_optional_accepts_one():
    """? (0,1) normalized: accepts 'a'."""
    g = _normalize(_quant_grammar(0, 1))
    assert recognize(g, "a") is True


def test_optional_rejects_two():
    """? (0,1) normalized: rejects 'aa'."""
    g = _normalize(_quant_grammar(0, 1))
    assert recognize(g, "aa") is False


def test_exact_two_rejects_one():
    """{2,2} normalized: rejects 'a' (too short)."""
    g = _normalize(_quant_grammar(2, 2))
    assert recognize(g, "a") is False


def test_exact_two_accepts_two():
    """{2,2} normalized: accepts 'aa'."""
    g = _normalize(_quant_grammar(2, 2))
    assert recognize(g, "aa") is True


def test_exact_two_rejects_three():
    """{2,2} normalized: rejects 'aaa' (too long)."""
    g = _normalize(_quant_grammar(2, 2))
    assert recognize(g, "aaa") is False


def test_bounded_two_to_four_rejects_one():
    """{2,4} normalized: rejects 'a'."""
    g = _normalize(_quant_grammar(2, 4))
    assert recognize(g, "a") is False


def test_bounded_two_to_four_accepts_two():
    """{2,4} normalized: accepts 'aa'."""
    g = _normalize(_quant_grammar(2, 4))
    assert recognize(g, "aa") is True


def test_bounded_two_to_four_accepts_four():
    """{2,4} normalized: accepts 'aaaa'."""
    g = _normalize(_quant_grammar(2, 4))
    assert recognize(g, "aaaa") is True


def test_bounded_two_to_four_rejects_five():
    """{2,4} normalized: rejects 'aaaaa'."""
    g = _normalize(_quant_grammar(2, 4))
    assert recognize(g, "aaaaa") is False


# ── split_literals integration ────────────────────────────────────────


def test_split_literals_true_keyword_recognized():
    """split_literals turns 'true' into 4 single-char items; recognizes 'true'."""
    rule = IrRule("s", IrAlternation(IrSequence(IrItem(IrLiteral("true")))))
    g = split_literals(IrAst(rules=IrSeq(rule), start="s"))
    assert recognize(g, "true") is True


def test_split_literals_true_keyword_rejects_partial():
    """After split_literals, 'tru' (missing last char) is rejected."""
    rule = IrRule("s", IrAlternation(IrSequence(IrItem(IrLiteral("true")))))
    g = split_literals(IrAst(rules=IrSeq(rule), start="s"))
    assert recognize(g, "tru") is False


# ── parse — derivation tree ───────────────────────────────────────────


def test_parse_returns_parse_tree():
    """parse() returns a ParseTree for a valid input."""
    tree = parse(_digit_grammar(), "7")
    assert isinstance(tree, ParseTree)


def test_parse_tree_symbol_is_start_rule():
    """Root ParseTree symbol is the start rule's IrRuleRef."""
    tree = parse(_digit_grammar(), "3")
    assert tree.symbol == IrRuleRef("digit")


def test_parse_raises_on_invalid_input():
    """parse() raises UnsupportedConstructError on input that does not derive."""
    with pytest.raises(UnsupportedConstructError):
        parse(_digit_grammar(), "z")


def test_parse_raises_on_empty_for_non_nullable():
    """parse() raises UnsupportedConstructError on empty input for a non-nullable rule."""
    with pytest.raises(UnsupportedConstructError):
        parse(_digit_grammar(), "")


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


def test_parse_single_char_tree_leaf_is_literal():
    """parse() on a single digit produces a tree whose leaf is IrLiteral."""
    tree = parse(_digit_grammar(), "9")
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
    atom = IrCharClass(IrRange("a", "z"))
    result = MATCHES.eval(parser, atom, IrTuple(IrStr("m")))
    assert result == IrInt(1)


def test_matches_charclass_range_rejects():
    """Matches.eval returns IrInt(0) for a char outside a range."""
    parser = EarleyParser()
    atom = IrCharClass(IrRange("a", "z"))
    result = MATCHES.eval(parser, atom, IrTuple(IrStr("0")))
    assert result == IrInt(0)


def test_nullable_rules_returns_irseq():
    """NullableRules.eval returns an IrSeq of nullable rule names."""
    parser = EarleyParser()
    g = _normalize(_quant_grammar(0, IrNone))
    result = NULLABLE.eval(parser, g, ())
    assert isinstance(result, IrSeq)
