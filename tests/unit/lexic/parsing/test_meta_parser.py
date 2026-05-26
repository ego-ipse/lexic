# tests/unit/lexic/parsing/test_meta_parser.py
"""MetaGrammarParser — generic Lark + canonical-tag dispatch → IrAst.

Tested with a tiny stub flavour that exists only in this test file.
"""

from __future__ import annotations

from lexic.grammars.flavour import IrFlavour
from lexic.ir.escapes import EscapeCodec
from lexic.ir.nodes import (
    IrAlternation,
    IrAst,
    IrCharClass,
    IrGroup,
    IrItem,
    IrLiteral,
    IrNot,
    IrQuantifier,
    IrRule,
    IrRuleRef,
    IrSequence,
)
from lexic.parsing.meta_parser import MetaGrammarParser


class _StubEscapes(EscapeCodec):
    """An identity EscapeCodec subclass — empty tables, so encode/decode are no-ops."""

    SHORT_ESCAPES = {"n": "\n", "t": "\t", "\\": "\\", '"': '"'}
    HEX_ESCAPES = ()


class _StubFlavour(IrFlavour):
    """Mini-language: `name = body`; quantifiers `?`, `*`, `+`; charclasses `[...]`."""

    name = "stub"
    extensions = (".stub",)
    line_comment = "#"
    escapes = _StubEscapes()
    emitter = None  # type: ignore[assignment]
    meta_grammar = r"""
start: rule+
rule: NAME "=" alternation     -> ir_rule
alternation: sequence ("|" sequence)*  -> ir_alternation
sequence: item*                -> ir_sequence
item: atom QUANTIFIER?         -> ir_item
atom: LITERAL                  -> ir_literal
    | CHARCLASS                -> ir_charclass
    | NAME                     -> ir_ruleref
    | "(" alternation ")"      -> ir_group

NAME: /[a-zA-Z_][a-zA-Z0-9_-]*/
LITERAL: /"([^"\\]|\\.)*"/
CHARCLASS: /\[(?:\^)?(?:[^\]\\]|\\.)*\]/
QUANTIFIER: /[?*+]/

%ignore /[ \t\n\r]+/
%ignore /#[^\n]*/
"""

    @staticmethod
    def parse_quantifier(text: str) -> IrQuantifier:
        """Parse a quantifier string into a IrQuantifier object."""
        if text == "?":
            return IrQuantifier(0, 1)
        if text == "*":
            return IrQuantifier(0, None)
        if text == "+":
            return IrQuantifier(1, None)
        return IrQuantifier(1, 1)

    @staticmethod
    def parse_charclass(text: str) -> tuple[str, bool]:
        """Parse a charclass string into a tuple of (inner, negated)."""
        # Strip [ and ]; detect leading ^
        inner = text[1:-1]
        if inner.startswith("^"):
            return inner[1:], True
        return inner, False


def _ast_first_rule(text: str) -> IrRule:
    """Return the first rule in an ast."""
    ast = MetaGrammarParser(_StubFlavour).parse(text)
    return ast.rules[0]


# ── Basic shapes ─────────────────────────────────────────────────────


def test_parses_single_rule_with_literal():
    """Parse a single rule with a literal."""
    ast = MetaGrammarParser(_StubFlavour).parse('foo = "hi"\n')
    assert isinstance(ast, IrAst)
    assert ast.rules[0].name == "foo"
    assert ast.rules[0].body == IrAlternation((IrSequence((IrItem(IrLiteral("hi")),)),))


def test_parses_charclass():
    """Parse a charclass"""
    rule = _ast_first_rule("digit = [0-9]\n")
    item = rule.body.arms[0].items[0]
    assert item.atom == IrCharClass("0-9")


def test_parses_negated_charclass():
    """Parse a negated charclass — atom is IrNot(IrCharClass(...))."""
    rule = _ast_first_rule(r'r = [^"\\]' + "\n")
    item = rule.body.arms[0].items[0]
    assert isinstance(item.atom, IrNot)
    assert isinstance(item.atom.body, IrCharClass)


def test_parses_ruleref():
    """Parse a rule reference"""
    rule = _ast_first_rule("a = b\n")
    item = rule.body.arms[0].items[0]
    assert item.atom == IrRuleRef("b")


def test_parses_alternation():
    """Parse an alternation"""
    rule = _ast_first_rule('op = "+" | "-"\n')
    assert len(rule.body.arms) == 2
    assert rule.body.arms[0].items[0].atom == IrLiteral("+")
    assert rule.body.arms[1].items[0].atom == IrLiteral("-")


def test_parses_quantifiers():
    """Parse quantifiers"""
    rule = _ast_first_rule("expr = a? b* c+\n")
    items = rule.body.arms[0].items
    assert items[0].quantifier == IrQuantifier(0, 1)
    assert items[1].quantifier == IrQuantifier(0, None)
    assert items[2].quantifier == IrQuantifier(1, None)


def test_parses_group():
    """Parse a group"""
    rule = _ast_first_rule("expr = (a | b)\n")
    item = rule.body.arms[0].items[0]
    assert isinstance(item.atom, IrGroup)
    assert len(item.atom.body.arms) == 2


def test_decodes_literal_escapes_via_flavour_codec():
    """`\\n` in source becomes a real newline in IrLiteral.value."""
    rule = _ast_first_rule(r'r = "a\nb"' + "\n")
    item = rule.body.arms[0].items[0]
    assert item.atom == IrLiteral("a\nb")  # 3 chars: a, newline, b


# ── Start rule ───────────────────────────────────────────────────────


def test_start_rule_is_first_rule_in_source():
    """Parse a single rule with a literal."""
    ast = MetaGrammarParser(_StubFlavour).parse('root = "x"\nfoo = "y"\n')
    assert ast.start == "root"


# ── Sugar expansion via normalize_literal ────────────────────────────


class _CaseInsensitiveStub(_StubFlavour):
    """Case-insensitive flavour: `a` becomes `[aA]`."""

    @classmethod
    def normalize_literal(cls, decoded: str):
        """`a` becomes `[aA]`."""
        seq = IrSequence(
            tuple(IrItem(IrCharClass(f"{c.lower()}{c.upper()}")) for c in decoded)
        )
        return IrGroup(IrAlternation((seq,)))


def test_normalize_literal_override_expands_to_group():
    """A flavour can override normalize_literal to expand sugar to canonical IR."""

    ast = MetaGrammarParser(_CaseInsensitiveStub).parse('r = "ab"\n')
    item = ast.rules[0].body.arms[0].items[0]
    assert isinstance(item.atom, IrGroup)
    inner_items = item.atom.body.arms[0].items
    assert inner_items[0].atom == IrCharClass("aA")
    assert inner_items[1].atom == IrCharClass("bB")
