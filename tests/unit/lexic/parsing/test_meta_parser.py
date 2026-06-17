# tests/unit/lexic/parsing/test_meta_parser.py
"""MetaGrammarParser — generic Lark + canonical-tag dispatch → IrAst.

Tested with a tiny stub flavour that exists only in this test file.
"""

from __future__ import annotations

import pytest

from lexic.exceptions import UnsupportedConstructError
from lexic.grammars.abnf import ABNF_FLAVOUR
from lexic.grammars.flavour import IrFlavour
from lexic.ir.base import IrNone, IrStr
from lexic.ir.escapes import EscapeCodec
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
from lexic.ir.operators import IrNot
from lexic.parsing.meta_parser import MetaGrammarParser, _build_charclass


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
            return IrQuantifier(0, IrNone)
        if text == "+":
            return IrQuantifier(1, IrNone)
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
    ast = MetaGrammarParser(_StubFlavour()).parse(text)
    return ast.rules[0]


# ── Basic shapes ─────────────────────────────────────────────────────


def test_parses_single_rule_with_literal():
    """Parse a single rule with a literal."""
    ast = MetaGrammarParser(_StubFlavour()).parse('foo = "hi"\n')
    assert isinstance(ast, IrAst)
    assert ast.rules[0].name == "foo"
    assert ast.rules[0].body == IrAlternation(IrSequence(IrItem(IrLiteral("hi"))))


def test_parses_charclass():
    """Parse a charclass"""
    rule = _ast_first_rule("digit = [0-9]\n")
    item = rule.body[0][0]
    assert item.atom == IrCharClass(IrRange("0", "9"))


def test_parses_negated_charclass():
    """Parse a negated charclass — atom is IrNot(IrCharClass(...))."""
    rule = _ast_first_rule(r'r = [^"\\]' + "\n")
    item = rule.body[0][0]
    assert isinstance(item.atom, IrNot)
    assert isinstance(item.atom[0], IrCharClass)


def test_parses_ruleref():
    """Parse a rule reference"""
    rule = _ast_first_rule("a = b\n")
    item = rule.body[0][0]
    assert item.atom == IrRuleRef("b")


def test_parses_alternation():
    """Parse an alternation"""
    rule = _ast_first_rule('op = "+" | "-"\n')
    assert len(rule.body) == 2
    assert rule.body[0][0].atom == IrLiteral("+")
    assert rule.body[1][0].atom == IrLiteral("-")


def test_parses_quantifiers():
    """Parse quantifiers"""
    rule = _ast_first_rule("expr = a? b* c+\n")
    items = rule.body[0]
    assert items[0].quantifier == IrQuantifier(0, 1)
    assert items[1].quantifier == IrQuantifier(0, IrNone)
    assert items[2].quantifier == IrQuantifier(1, IrNone)


def test_parses_group():
    """Parse a group"""
    rule = _ast_first_rule("expr = (a | b)\n")
    item = rule.body[0][0]
    assert isinstance(item.atom, IrAlternation)
    assert len(item.atom) == 2


def test_decodes_literal_escapes_via_flavour_codec():
    """`\\n` in source becomes a real newline in IrLiteral."""
    rule = _ast_first_rule(r'r = "a\nb"' + "\n")
    item = rule.body[0][0]
    assert item.atom == IrLiteral("a\nb")  # 3 chars: a, newline, b


# ── Start rule ───────────────────────────────────────────────────────


def test_start_rule_is_first_rule_in_source():
    """Parse a single rule with a literal."""
    ast = MetaGrammarParser(_StubFlavour()).parse('root = "x"\nfoo = "y"\n')
    assert ast.start == "root"


# ── Sugar expansion via normalize_literal ────────────────────────────


class _CaseInsensitiveStub(_StubFlavour):
    """Case-insensitive flavour: `a` becomes `[aA]`."""

    @classmethod
    def normalize_literal(cls, decoded: str):
        """`a` becomes `[aA]`."""
        seq = IrSequence(
            *(IrItem(IrCharClass(IrStr(f"{c.lower()}{c.upper()}"))) for c in decoded)
        )
        return IrAlternation(seq)


def test_normalize_literal_override_expands_to_group():
    """A flavour can override normalize_literal to expand sugar to canonical IR."""
    ast = MetaGrammarParser(_CaseInsensitiveStub()).parse('r = "ab"\n')
    item = ast.rules[0].body[0][0]
    assert isinstance(item.atom, IrAlternation)
    inner_items = item.atom[0]
    assert inner_items[0].atom == IrCharClass(IrStr("aA"))
    assert inner_items[1].atom == IrCharClass(IrStr("bB"))


# ── _build_charclass interior-splitter ───────────────────────────────


def test_build_charclass_single_range():
    """A ``x-y`` interior is split into a single IrRange element.

    :returns: ``IrCharClass(IrRange("a", "z"))``
    """
    result = _build_charclass(_StubFlavour(), ["[a-z]"])
    assert result == IrCharClass(IrRange("a", "z"))


def test_build_charclass_run_of_singles():
    """Consecutive single chars accumulate into one bare IrStr run.

    :returns: ``IrCharClass(IrStr("abc"))``
    """
    result = _build_charclass(_StubFlavour(), ["[abc]"])
    assert result == IrCharClass(IrStr("abc"))


def test_build_charclass_mixed_run_then_range():
    """A leading run followed by a range produces two elements.

    :returns: ``IrCharClass(IrStr("abc"), IrRange("0", "9"))``
    """
    result = _build_charclass(_StubFlavour(), ["[abc0-9]"])
    assert result == IrCharClass(IrStr("abc"), IrRange("0", "9"))


def test_build_charclass_encoded_hex_unit_range():
    """Hex escape units are kept verbatim as range endpoints.

    The splitter does not decode — ``\\\\x00`` and ``\\\\x1F`` are each a
    single unit (four source chars), so the result holds the encoded strings.

    :returns: ``IrCharClass(IrRange("\\\\x00", "\\\\x1F"))``
    """
    result = _build_charclass(_StubFlavour(), [r"[\x00-\x1F]"])
    assert result == IrCharClass(IrRange("\\x00", "\\x1F"))


def test_build_charclass_negation_produces_irnot():
    """A leading ``^`` causes the result to be wrapped in ``IrNot``.

    The negation is not stored inside the ``IrCharClass`` — the class itself
    is exactly ``IrCharClass(IrRange("a", "z"))`` and the ``IrNot`` is the
    outer wrapper.

    :returns: ``IrNot(IrCharClass(IrRange("a", "z")))``
    """
    result = _build_charclass(_StubFlavour(), ["[^a-z]"])
    assert isinstance(result, IrNot)
    assert result[0] == IrCharClass(IrRange("a", "z"))


def test_build_charclass_trailing_dash_is_literal():
    """A trailing ``-`` (no following char) is treated as a literal run char.

    The splitter peeks ahead: ``pattern[i] == "-"`` AND ``i + 1 < len``.
    A trailing dash fails the second condition, so it falls through to the
    run accumulator.

    :returns: ``IrCharClass(IrStr("a-"))``
    """
    result = _build_charclass(_StubFlavour(), ["[a-]"])
    assert result == IrCharClass(IrStr("a-"))


def test_build_charclass_leading_dash_is_literal():
    """A leading ``-`` (no preceding char consumed yet) is a literal run char.

    When ``-`` is at position 0 there is no range to complete, so it lands in
    the run accumulator alongside the next char.

    :returns: ``IrCharClass(IrStr("-+"))``
    """
    result = _build_charclass(_StubFlavour(), ["[-+]"])
    assert result == IrCharClass(IrStr("-+"))


# ── New builders (ABNF constructs) ───────────────────────────────────


def test_ir_rule_inc_via_abnf_flavour():
    """``ir_rule_inc`` (``=/``) merges arms through ABNF_FLAVOUR.

    :class:`_IncrementalRule` is an internal marker; test through the public
    ``MetaGrammarParser`` / ``ABNF_FLAVOUR`` API rather than instantiating it
    directly.
    """
    text = 'digits = "0"\ndigits =/ "1"\n'
    ast = MetaGrammarParser(ABNF_FLAVOUR).parse(text)
    assert len(ast.rules) == 1
    assert ast.rules[0].name == "digits"
    assert len(ast.rules[0].body) == 2


def test_ir_numseq_via_abnf_flavour():
    """``ir_numseq`` (``%xNN.NN``) produces a case-sensitive :class:`IrLiteral`."""
    ast = MetaGrammarParser(ABNF_FLAVOUR).parse("null = %x6e.75.6c.6c\n")
    item = ast.rules[0].body[0][0]
    assert item.atom == IrLiteral("null")


def test_ir_option_via_abnf_flavour():
    """``ir_option`` (``[ ... ]``) wraps the inner alternation with ``(0, 1)``."""
    ast = MetaGrammarParser(ABNF_FLAVOUR).parse('foo = bar [ "x" ]\nbar = "b"\n')
    seq = ast.rules[0].body[0]
    # second item in the sequence is the optional bracket
    opt_item = seq[1]
    assert isinstance(opt_item, IrItem)
    assert opt_item.quantifier == IrQuantifier(0, 1)


def test_ir_literal_cs_via_abnf_flavour():
    """``ir_literal_cs`` (``%s"..."`` case-sensitive string) → raw :class:`IrLiteral`."""
    ast = MetaGrammarParser(ABNF_FLAVOUR).parse('foo = %s"Hello"\n')
    item = ast.rules[0].body[0][0]
    assert item.atom == IrLiteral("Hello")


def test_ir_literal_ci_via_abnf_flavour():
    """``ir_literal_ci`` (``%i"..."`` explicit case-insensitive) → expanded alternation."""
    ast = MetaGrammarParser(ABNF_FLAVOUR).parse('foo = %i"AB"\n')
    item = ast.rules[0].body[0][0]
    assert isinstance(item.atom, IrAlternation)


def test_ir_prose_via_abnf_flavour_raises():
    """``ir_prose`` (``<...>``) always raises :class:`UnsupportedConstructError`."""
    with pytest.raises(UnsupportedConstructError):
        MetaGrammarParser(ABNF_FLAVOUR).parse("foo = <some prose>\n")
