# tests/unit/lexic/grammars/abnf/test_flavour.py
"""ABNF_FLAVOUR — full IrFlavour binding for the minimal-ABNF subset."""

from __future__ import annotations

from lark import Lark

from lexic.grammars.abnf.flavour import ABNF_ESCAPES, ABNF_FLAVOUR, META_GRAMMAR
from lexic.grammars.flavour import IrFlavour
from lexic.ir.base import IrNone
from lexic.ir.escapes import EscapeCodec
from lexic.ir.nodes import (
    IrAlternation,
    IrCharClass,
    IrLiteral,
    IrQuantifier,
)
from lexic.parsing.meta_parser import MetaGrammarParser
from tests.unit.lexic.conftest import GRAMMAR_AST_TYPES


def test_abnf_flavour_is_a_flavour():
    """`ABNF_FLAVOUR` is an `IrFlavour` singleton."""
    assert isinstance(ABNF_FLAVOUR, IrFlavour)


def test_abnf_flavour_metadata():
    """`ABNF_FLAVOUR` has expected metadata"""
    assert ABNF_FLAVOUR.name == "abnf"
    assert ".abnf" in ABNF_FLAVOUR.extensions
    assert ABNF_FLAVOUR.line_comment == ";"


# ── parse_quantifier ─────────────────────────────────────────────────


def test_parse_quantifier_star_means_zero_or_more():
    """`"*"` -> `IrQuantifier(0, IrNone)`"""
    assert ABNF_FLAVOUR.parse_quantifier("*") == IrQuantifier(0, IrNone)


def test_parse_quantifier_n_star_means_n_or_more():
    """`"1*"` -> `IrQuantifier(1, IrNone)`"""
    assert ABNF_FLAVOUR.parse_quantifier("1*") == IrQuantifier(1, IrNone)
    assert ABNF_FLAVOUR.parse_quantifier("3*") == IrQuantifier(3, IrNone)


def test_parse_quantifier_star_n_means_zero_to_n():
    """`"*5"` -> `IrQuantifier(0, 5)`"""
    assert ABNF_FLAVOUR.parse_quantifier("*5") == IrQuantifier(0, 5)


def test_parse_quantifier_n_star_m_means_n_to_m():
    """`"2*5"` -> `IrQuantifier(2, 5)`"""
    assert ABNF_FLAVOUR.parse_quantifier("2*5") == IrQuantifier(2, 5)


def test_parse_quantifier_n_alone_means_exactly_n():
    """`"3"` -> `IrQuantifier(3, 3)"""
    assert ABNF_FLAVOUR.parse_quantifier("3") == IrQuantifier(3, 3)


# ── parse_charclass ──────────────────────────────────────────────────


def test_parse_charclass_single_hex():
    """`%x41` → POSIX 'A'."""
    pattern, negated = ABNF_FLAVOUR.parse_charclass("%x41")
    assert pattern == "A"
    assert negated is False


def test_parse_charclass_hex_range():
    """`%x41-5A` → POSIX 'A-Z'."""
    pattern, negated = ABNF_FLAVOUR.parse_charclass("%x41-5A")
    assert pattern == "A-Z"
    assert negated is False


# ── normalize_literal — case-insensitive expansion ───────────────────


def test_normalize_literal_alpha_expands_to_charclass_group():
    """`"abc"` in ABNF is case-insensitive; expand to ([aA] [bB] [cC])."""
    out = ABNF_FLAVOUR.normalize_literal("abc")
    assert isinstance(out, IrAlternation)
    arm = out[0]
    assert arm[0].atom == IrCharClass("aA")
    assert arm[1].atom == IrCharClass("bB")
    assert arm[2].atom == IrCharClass("cC")


def test_normalize_literal_all_caps_still_expands():
    """All-caps is still case-expanded."""
    out = ABNF_FLAVOUR.normalize_literal("XY")
    assert isinstance(out, IrAlternation)
    arm = out[0]
    assert arm[0].atom == IrCharClass("xX")
    assert arm[1].atom == IrCharClass("yY")


def test_normalize_literal_non_alpha_stays_literal():
    """Punctuation has no case; keep as IrLiteral."""
    out = ABNF_FLAVOUR.normalize_literal("(){}")
    assert out == IrLiteral("(){}")


def test_normalize_literal_mixed_alphanumeric():
    """Letters case-expanded, digits stay literal — emit as group with mixed leaves."""
    out = ABNF_FLAVOUR.normalize_literal("a1")
    assert isinstance(out, IrAlternation)
    arm = out[0]
    assert arm[0].atom == IrCharClass("aA")
    assert arm[1].atom == IrLiteral("1")


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
    ast = MetaGrammarParser(ABNF_FLAVOUR).parse(text)
    rule_names = {r.name for r in ast.rules}
    assert rule_names == {"root", "expr", "num", "DIGIT", "op", "WSP"}


def test_abnf_escapes_is_an_escape_codec():
    """ABNF_ESCAPES is an EscapeCodec singleton."""
    assert isinstance(ABNF_ESCAPES, EscapeCodec)


def test_decode_is_identity():
    """Decode is identity. ABNF literals are already canonical Python strings."""
    assert ABNF_ESCAPES.decode("hello") == "hello"
    assert ABNF_ESCAPES.decode("") == ""
    assert ABNF_ESCAPES.decode("ab\\cd") == "ab\\cd"
    assert ABNF_ESCAPES.decode("\\n") == "\\n"
    assert ABNF_ESCAPES.decode("\\t") == "\\t"


def test_encode_is_identity():
    """Encode is identity. ABNF literals are already canonical Python strings."""
    assert ABNF_ESCAPES.encode("hello") == "hello"
    assert ABNF_ESCAPES.encode("") == ""
    assert ABNF_ESCAPES.encode("ab\\cd") == "ab\\cd"
    assert ABNF_ESCAPES.encode("\n") == "\n"


def test_read_escape_passes_through_unknown():
    """read_escape on an unrecognised sequence returns the raw follow-char."""
    char, new_i = ABNF_ESCAPES.read_escape("\\n", 0)
    assert char == "n"
    assert new_i == 2


def test_meta_grammar_is_a_string():
    """The meta-grammar must be a string."""
    assert isinstance(META_GRAMMAR, str)


def test_meta_grammar_is_nonempty():
    """The meta-grammar must not be empty or whitespace-only."""
    assert len(META_GRAMMAR.strip()) > 0


def test_meta_grammar_uses_canonical_tag_names():
    """The grammar must use ir_rule / ir_alternation / ir_sequence / ir_item /
    ir_literal / ir_charclass / ir_ruleref / ir_group tags."""
    for tag in (
        "ir_rule",
        "ir_alternation",
        "ir_sequence",
        "ir_item",
        "ir_literal",
        "ir_charclass",
        "ir_ruleref",
        "ir_group",
    ):
        assert f"-> {tag}" in META_GRAMMAR, f"missing tag {tag}"


def test_meta_grammar_constructs_a_valid_lark():
    """No syntax errors in the meta-grammar."""
    Lark(META_GRAMMAR, parser="earley", ambiguity="resolve")


def test_meta_grammar_ignores_comments_and_whitespace():
    """The meta-grammar must ignore ABNF semicolon comments and whitespace."""
    parser = Lark(META_GRAMMAR, parser="earley", ambiguity="resolve")
    parser.parse('; a comment\nfoo = "x"\n')


def test_meta_grammar_parses_hex_charclass():
    """The meta-grammar must parse %xNN and %xNN-MM hex character classes."""
    parser = Lark(META_GRAMMAR, parser="earley", ambiguity="resolve")
    parser.parse("DIGIT = %x30-39\n")
    parser.parse("SP = %x20\n")


def test_meta_grammar_parses_prefix_quantifiers():
    """The meta-grammar must parse ABNF prefix quantifier forms."""
    parser = Lark(META_GRAMMAR, parser="earley", ambiguity="resolve")
    parser.parse('foo = *bar\nbaz = 1*bar\nqux = 2*5bar\nbar = "x"\n')


def test_meta_grammar_parses_alternation_with_slash():
    """ABNF alternation uses `/` not `|`."""
    parser = Lark(META_GRAMMAR, parser="earley", ambiguity="resolve")
    parser.parse('foo = "a" / "b" / "c"\n')


def test_abnf_emitter_iremit_default_unreachable():
    """Every IR-AST node type has an explicit action — IrEmit default never fires.

    If any type is missing an action, the emitter would fall through to its
    IrEmit default body and silently emit ``str(n)`` instead of raising.
    This test locks that the default is structurally unreachable for ABNF.
    """
    registered = set(ABNF_FLAVOUR.actions.keys())
    missing = GRAMMAR_AST_TYPES - registered
    assert not missing, f"ABNF_FLAVOUR missing explicit actions for: {missing}"
