"""Tests for lexic.grammars.abnf_2 — ABNF_GRAMMAR and ABNF_REDUCTIONS.

API changes:

- ``EarleyParser().parse(g, t)`` → module-level ``parse(g, t)``.
- ``Reducer(...).reduce(tree)`` → ``Reducer(...).apply(tree)``.
"""

from __future__ import annotations

from lexic.grammars.abnf import ABNF_FLAVOUR
from lexic.grammars.abnf_2 import ABNF_GRAMMAR, ABNF_REDUCTIONS
from lexic.ir.base import IrSeq, IrStr
from lexic.ir.mapping import IrMap
from lexic.ir.nodes import (
    IrAst,
    IrCharClass,
    IrLiteral,
    IrQuantifier,
    IrRange,
    IrRuleRef,
)
from lexic.parsing_2 import recognize
from lexic.parsing_2.engine import parse
from lexic.parsing_2.forest import ParseTree
from lexic.parsing_2.normalize import (
    desugar_quantifiers,
    flatten_groups,
    split_literals,
)
from lexic.parsing_2.reduce import Reducer

# ── Helpers ───────────────────────────────────────────────────────────


def _normalize(g: IrAst) -> IrAst:
    """Full normalization pipeline."""
    return split_literals(desugar_quantifiers(flatten_groups(g)))


# ── ABNF_GRAMMAR structure ────────────────────────────────────────────


def test_abnf_grammar_is_ir_ast():
    """ABNF_GRAMMAR is an IrAst."""
    assert isinstance(ABNF_GRAMMAR, IrAst)


def test_abnf_grammar_start_rule_is_rulelist():
    """ABNF_GRAMMAR start rule is 'rulelist'."""
    assert ABNF_GRAMMAR.start == "rulelist"


def test_abnf_grammar_has_expected_rule_count():
    """ABNF_GRAMMAR has at least 20 rules (RFC 5234 §4 subset)."""
    assert len(list(ABNF_GRAMMAR.rules)) >= 20


def test_abnf_grammar_rule_names_include_core():
    """ABNF_GRAMMAR contains expected core rule names."""
    names = {r.name for r in ABNF_GRAMMAR.rules}
    for expected in (
        "rulelist",
        "rule",
        "rulename",
        "alternation",
        "concatenation",
        "repetition",
    ):
        assert expected in names, f"Missing rule: {expected}"


# ── ABNF_GRAMMAR emits as well-formed ABNF ───────────────────────────


def test_abnf_grammar_emits_non_empty_string():
    """ABNF_FLAVOUR.apply(ABNF_GRAMMAR) returns a non-empty string."""
    result = str(ABNF_FLAVOUR.apply(ABNF_GRAMMAR))
    assert isinstance(result, str)
    assert len(result.strip()) > 0


def test_abnf_grammar_emitted_text_contains_rulelist():
    """The emitted ABNF text contains the 'rulelist' rule definition."""
    text = str(ABNF_FLAVOUR.apply(ABNF_GRAMMAR))
    assert "rulelist" in text


def test_abnf_grammar_emitted_text_contains_equals():
    """The emitted ABNF text contains '=' rule assignments."""
    text = str(ABNF_FLAVOUR.apply(ABNF_GRAMMAR))
    assert " = " in text


# ── ABNF_REDUCTIONS structure ─────────────────────────────────────────


def test_abnf_reductions_is_ir_map():
    """ABNF_REDUCTIONS is an IrMap."""
    assert isinstance(ABNF_REDUCTIONS, IrMap)


def test_abnf_reductions_covers_all_structural_rules():
    """ABNF_REDUCTIONS has entries for all structural rules."""
    for rule_name in (
        "rulelist",
        "rule",
        "rulename",
        "alternation",
        "concatenation",
        "repetition",
        "element",
        "group",
        "char-val",
        "num-val",
    ):
        assert ABNF_REDUCTIONS[IrRuleRef(rule_name)] is not None, (
            f"Missing reduction for {rule_name!r}"
        )


def test_abnf_reductions_covers_terminal_rules():
    """ABNF_REDUCTIONS has entries for all terminal/character rules."""
    for rule_name in ("ALPHA", "DIGIT", "HEXDIG", "CR", "LF", "SP", "HTAB", "DQUOTE"):
        assert ABNF_REDUCTIONS[IrRuleRef(rule_name)] is not None, (
            f"Missing reduction for {rule_name!r}"
        )


# ── ABNF_REDUCTIONS leaf reductions on simple trees ───────────────────


def test_rulename_reduction_yields_irruleref():
    """rulename reduction: children joined -> IrRuleRef."""
    reducer = Reducer(reductions=ABNF_REDUCTIONS)
    tree = ParseTree(IrRuleRef("rulename"), IrSeq(IrLiteral("a"), IrLiteral("b")))
    result = reducer.apply(tree)
    assert isinstance(result, IrRuleRef)
    assert str(result) == "ab"


def test_char_val_reduction_yields_irliteral_without_quotes():
    """char-val reduction: strips surrounding DQUOTE chars, returns IrLiteral."""
    reducer = Reducer(reductions=ABNF_REDUCTIONS)
    tree = ParseTree(
        IrRuleRef("char-val"),
        IrSeq(IrLiteral('"'), IrLiteral("a"), IrLiteral("b"), IrLiteral('"')),
    )
    result = reducer.apply(tree)
    assert isinstance(result, IrLiteral)
    assert result == IrLiteral("ab")


def test_num_val_hex_range_yields_ircharclass_range():
    """num-val reduction on '%x41-5A' yields IrCharClass(IrRange('A','Z'))."""
    reducer = Reducer(reductions=ABNF_REDUCTIONS)
    tree = ParseTree(
        IrRuleRef("num-val"),
        IrSeq(
            IrLiteral("%"),
            IrLiteral("x"),
            IrLiteral("4"),
            IrLiteral("1"),
            IrLiteral("-"),
            IrLiteral("5"),
            IrLiteral("A"),
        ),
    )
    result = reducer.apply(tree)
    assert isinstance(result, IrCharClass)
    assert result == IrCharClass(IrRange("A", "Z"))


def test_num_val_single_hex_yields_ircharclass_str():
    """num-val reduction on '%x41' yields IrCharClass(IrStr('A'))."""
    reducer = Reducer(reductions=ABNF_REDUCTIONS)
    tree = ParseTree(
        IrRuleRef("num-val"),
        IrSeq(IrLiteral("%"), IrLiteral("x"), IrLiteral("4"), IrLiteral("1")),
    )
    result = reducer.apply(tree)
    assert isinstance(result, IrCharClass)
    assert result == IrCharClass(IrStr("A"))


# ── In-subset single-rule parse+reduce ───────────────────────────────


def test_parse_reduce_single_literal_rule():
    """'s = \"ab\"' parses and reduces to IrAst with IrLiteral('ab') item."""
    g = _normalize(ABNF_GRAMMAR)
    tree = parse(g, 's = "ab"\n')
    result = Reducer(reductions=ABNF_REDUCTIONS).apply(tree)
    assert isinstance(result, IrAst)
    assert result.start == "s"
    rules = list(result.rules)
    assert rules[0].name == "s"
    arm = list(rules[0].body)[0]
    item = arm[0]
    assert item.atom == IrLiteral("ab")
    assert item.quantifier == IrQuantifier(1, 1)


def test_parse_reduce_alternation_rule():
    """'s = foo / bar' reduces to two-arm IrAlternation of IrRuleRef atoms."""
    g = _normalize(ABNF_GRAMMAR)
    text = 's = foo / bar\nfoo = "x"\nbar = "y"\n'
    tree = parse(g, text)
    result = Reducer(reductions=ABNF_REDUCTIONS).apply(tree)
    assert isinstance(result, IrAst)
    s_rule = list(result.rules)[0]
    assert s_rule.name == "s"
    arms = list(s_rule.body)
    assert len(arms) == 2
    assert arms[0][0].atom == IrRuleRef("foo")
    assert arms[1][0].atom == IrRuleRef("bar")


def test_parse_reduce_charclass_rule():
    """'x = %x41-5A' reduces to IrCharClass(IrRange('A','Z'))."""
    g = _normalize(ABNF_GRAMMAR)
    text = "x = %x41-5A\n"
    tree = parse(g, text)
    result = Reducer(reductions=ABNF_REDUCTIONS).apply(tree)
    assert isinstance(result, IrAst)
    rules = list(result.rules)
    item = list(rules[0].body)[0][0]
    assert isinstance(item.atom, IrCharClass)
    assert item.atom == IrCharClass(IrRange("A", "Z"))


# ── THE SELF-HOSTING FIXPOINT ─────────────────────────────────────────


def test_self_hosting_recognize():
    """normalize(ABNF_GRAMMAR) recognizes its own emitted text."""
    g = _normalize(ABNF_GRAMMAR)
    text = str(ABNF_FLAVOUR.apply(ABNF_GRAMMAR))
    assert recognize(g, text) is True


def test_self_hosting_fixpoint():
    """The headline test: parse(normalize(ABNF_GRAMMAR), emitted_text) reduced
    through ABNF_REDUCTIONS equals ABNF_GRAMMAR."""
    g = _normalize(ABNF_GRAMMAR)
    text = str(ABNF_FLAVOUR.apply(ABNF_GRAMMAR))
    tree = parse(g, text)
    result = Reducer(reductions=ABNF_REDUCTIONS).apply(tree)
    assert result == ABNF_GRAMMAR


def test_self_hosting_fixpoint_idempotent():
    """Reduce → re-emit → re-parse → re-reduce: result is the same IrAst."""
    g = _normalize(ABNF_GRAMMAR)
    text = str(ABNF_FLAVOUR.apply(ABNF_GRAMMAR))
    reducer = Reducer(reductions=ABNF_REDUCTIONS)

    # First round
    tree1 = parse(g, text)
    result1 = reducer.apply(tree1)
    assert isinstance(result1, IrAst)

    # Re-emit and re-parse
    text2 = str(ABNF_FLAVOUR.apply(result1))
    tree2 = parse(g, text2)
    result2 = reducer.apply(tree2)

    assert result2 == result1
    assert result2 == ABNF_GRAMMAR


def test_self_hosting_crlf_recognized():
    """CRLF line endings in the emitted text are recognized and parse correctly."""
    g = _normalize(ABNF_GRAMMAR)
    text = str(ABNF_FLAVOUR.apply(ABNF_GRAMMAR))
    text_crlf = text.replace("\n", "\r\n")
    assert recognize(g, text_crlf) is True


def test_self_hosting_crlf_reduces_to_abnf_grammar():
    """CRLF-terminated emitted text reduces back to ABNF_GRAMMAR."""
    g = _normalize(ABNF_GRAMMAR)
    text = str(ABNF_FLAVOUR.apply(ABNF_GRAMMAR))
    text_crlf = text.replace("\n", "\r\n")
    tree = parse(g, text_crlf)
    result = Reducer(reductions=ABNF_REDUCTIONS).apply(tree)
    assert result == ABNF_GRAMMAR
