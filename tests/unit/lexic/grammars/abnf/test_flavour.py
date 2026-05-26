# tests/unit/lexic/grammars/abnf/test_flavour.py
"""AbnfFlavour — full IrFlavour binding for the minimal-ABNF subset."""

from __future__ import annotations

from lexic.grammars.abnf.flavour import AbnfFlavour
from lexic.grammars.flavour import IrFlavour
from lexic.ir.nodes import IrCharClass, IrGroup, IrLiteral, IrQuantifier
from lexic.parsing.meta_parser import MetaGrammarParser


def test_abnf_flavour_is_a_flavour():
    """`AbnfFlavour` is a `IrFlavour"""
    assert issubclass(AbnfFlavour, IrFlavour)


def test_abnf_flavour_metadata():
    """`AbnfFlavour` has expected metadata"""
    assert AbnfFlavour.name == "abnf"
    assert ".abnf" in AbnfFlavour.extensions
    assert AbnfFlavour.line_comment == ";"


# ── parse_quantifier ─────────────────────────────────────────────────


def test_parse_quantifier_star_means_zero_or_more():
    """`"*"` -> `IrQuantifier(0, None)`"""
    assert AbnfFlavour.parse_quantifier("*") == IrQuantifier(0, None)


def test_parse_quantifier_n_star_means_n_or_more():
    """`"1*"` -> `IrQuantifier(1, None)`"""
    assert AbnfFlavour.parse_quantifier("1*") == IrQuantifier(1, None)
    assert AbnfFlavour.parse_quantifier("3*") == IrQuantifier(3, None)


def test_parse_quantifier_star_n_means_zero_to_n():
    """`"*5"` -> `IrQuantifier(0, 5)`"""
    assert AbnfFlavour.parse_quantifier("*5") == IrQuantifier(0, 5)


def test_parse_quantifier_n_star_m_means_n_to_m():
    """`"2*5"` -> `IrQuantifier(2, 5)`"""
    assert AbnfFlavour.parse_quantifier("2*5") == IrQuantifier(2, 5)


def test_parse_quantifier_n_alone_means_exactly_n():
    """`"3"` -> `IrQuantifier(3, 3)"""
    assert AbnfFlavour.parse_quantifier("3") == IrQuantifier(3, 3)


# ── parse_charclass ──────────────────────────────────────────────────


def test_parse_charclass_single_hex():
    """`%x41` → POSIX 'A'."""
    pattern, negated = AbnfFlavour.parse_charclass("%x41")
    assert pattern == "A"
    assert negated is False


def test_parse_charclass_hex_range():
    """`%x41-5A` → POSIX 'A-Z'."""
    pattern, negated = AbnfFlavour.parse_charclass("%x41-5A")
    assert pattern == "A-Z"
    assert negated is False


# ── normalize_literal — case-insensitive expansion ───────────────────


def test_normalize_literal_alpha_expands_to_charclass_group():
    """`"abc"` in ABNF is case-insensitive; expand to ([aA] [bB] [cC])."""
    out = AbnfFlavour.normalize_literal("abc")
    assert isinstance(out, IrGroup)
    items = out.body.arms[0].items
    assert items[0].atom == IrCharClass("aA")
    assert items[1].atom == IrCharClass("bB")
    assert items[2].atom == IrCharClass("cC")


def test_normalize_literal_all_caps_still_expands():
    """All-caps is still case-expanded."""
    out = AbnfFlavour.normalize_literal("XY")
    assert isinstance(out, IrGroup)
    items = out.body.arms[0].items
    assert items[0].atom == IrCharClass("xX")
    assert items[1].atom == IrCharClass("yY")


def test_normalize_literal_non_alpha_stays_literal():
    """Punctuation has no case; keep as IrLiteral."""
    out = AbnfFlavour.normalize_literal("(){}")
    assert out == IrLiteral("(){}")


def test_normalize_literal_mixed_alphanumeric():
    """Letters case-expanded, digits stay literal — emit as group with mixed leaves."""
    out = AbnfFlavour.normalize_literal("a1")
    assert isinstance(out, IrGroup)
    items = out.body.arms[0].items
    assert items[0].atom == IrCharClass("aA")
    assert items[1].atom == IrLiteral("1")


# ── End-to-end: parse a small ABNF sample ────────────────────────────


def test_parse_simple_abnf_grammar_via_meta_parser():
    """Parse a small ABNF sample via MetaGrammarParser."""
    text = (
        "; @non-semantic WSP\n"
        "root = expr\n"
        "expr = num *(op num)\n"
        "num  = 1*DIGIT\n"
        "DIGIT = %x30-39\n"
        'op   = "+" / "-"\n'
        "WSP  = %x20 / %x09\n"
    )
    ast = MetaGrammarParser(AbnfFlavour).parse(text)
    rule_names = {r.name for r in ast.rules}
    assert rule_names == {"root", "expr", "num", "DIGIT", "op", "WSP"}
