"""Sanity tests for the ABNF meta-grammar string."""

from __future__ import annotations

from lark import Lark

from lexic.grammars.abnf.meta_grammar import META_GRAMMAR


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
