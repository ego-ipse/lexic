"""Lark-based GBNF parser.

Parses GBNF text into a list of Rule AST nodes using an Earley meta-grammar.
"""

from __future__ import annotations

from lark import Lark, Transformer as LarkTransformer

from lexic.grammars.gbnf.ast import (
    Alternation,
    CharClass,
    Group,
    Item,
    Literal,
    Rule,
    RuleRef,
    Sequence,
)

_GBNF_META_GRAMMAR = r"""
start: rule+

rule: NAME "::=" alternation

alternation: sequence ("|" sequence)*

sequence: item*

item: atom QUANTIFIER  -> item_q
    | atom REPEAT      -> item_repeat
    | atom             -> item_bare

atom: LITERAL   -> literal
    | CHARCLASS -> charclass
    | NAME      -> ruleref
    | "(" alternation ")" -> group

NAME: /[a-zA-Z_][a-zA-Z0-9_-]*/
LITERAL: /"([^"\\]|\\.)*"/
CHARCLASS: /\[(?:\^)?(?:[^\]\\]|\\.)*\]/
QUANTIFIER: /[?*+]/
REPEAT: /\{[0-9]+(?:,[0-9]*)?\}/

%ignore /[ \t\n\r]+/
%ignore /#[^\n]*/
"""

_lark_parser = Lark(_GBNF_META_GRAMMAR, parser="earley", ambiguity="resolve")


class _GBNFTransformer(LarkTransformer):
    """Transform Lark parse tree into AST types."""

    def start(self, items: list) -> list[Rule]:
        return items

    def rule(self, items: list) -> Rule:
        return Rule(str(items[0]), items[1])

    def alternation(self, items: list) -> Alternation:
        return Alternation(items)

    def sequence(self, items: list) -> Sequence:
        return Sequence(items)

    def item_q(self, items: list) -> Item:
        return Item(items[0], str(items[1]))

    def item_repeat(self, items: list) -> Item:
        return Item(items[0], str(items[1]))

    def item_bare(self, items: list) -> Item:
        return Item(items[0], None)

    def literal(self, items: list) -> Literal:
        return Literal(str(items[0])[1:-1])

    def charclass(self, items: list) -> CharClass:
        return CharClass(str(items[0]))

    def ruleref(self, items: list) -> RuleRef:
        return RuleRef(str(items[0]))

    def group(self, items: list) -> Group:
        return Group(items[0])


_transformer = _GBNFTransformer()


def parse_gbnf(text: str) -> list[Rule]:
    """Parse GBNF text into a list of Rule AST nodes."""
    tree = _lark_parser.parse(text)
    return _transformer.transform(tree)


class GbnfParser:
    """GBNF flavour parser.

    Thin class wrapper around parse_gbnf for the FlavourParser protocol.
    Phase 2 extends this with IR-construction responsibilities (today they
    live in IRBuilder, consuming the AST parse_gbnf returns).
    """

    def parse(self, text: str):
        """Return list[Rule] — the GBNF AST. Phase 2 will return list[RuleSpec]."""
        return parse_gbnf(text)
