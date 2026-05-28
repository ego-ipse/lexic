"""GBNF flavour for Lexic.

Bundles the escape codec, action tuple, and parse helpers in one module.
:data:`GBNF_FLAVOUR` is the singleton :class:`IrFlavour`/:class:`IrEmitter`
consumed by :func:`lexic.grammars.get_flavour`.

Explicit disable of duplicate-code. The end-goal is to have this file be
completely auto-generated.
"""

# pylint: disable=duplicate-code

from __future__ import annotations

from dataclasses import dataclass
from typing import ClassVar

from lexic.exceptions import UnsupportedConstructError
from lexic.grammars.flavour import IrFlavour
from lexic.ir.action import (
    IrAction,
    IrCallable,
    IrChild,
    IrChildren,
    IrConcat,
    IrField,
    IrJoin,
)
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
    IrStr,
)
from lexic.utils.quantifiers import quantifier_to_bounds

META_GRAMMAR = r"""
start: rule+

rule: NAME "::=" alternation     -> ir_rule
alternation: sequence ("|" sequence)*  -> ir_alternation
sequence: item*                  -> ir_sequence
item: atom QUANTIFIER?           -> ir_item

atom: LITERAL                    -> ir_literal
    | CHARCLASS                  -> ir_charclass
    | NAME                       -> ir_ruleref
    | "(" alternation ")"        -> ir_group

NAME: /[a-zA-Z_][a-zA-Z0-9_-]*/
LITERAL: /"([^"\\]|\\.)*"/
CHARCLASS: /\[(?:\^)?(?:[^\]\\]|\\.)*\]/
QUANTIFIER: /[?*+]|\{[0-9]+(?:,[0-9]*)?\}/

%ignore /[ \t\n\r]+/
%ignore /#[^\n]*/
"""
"""GBNF meta-grammar — Lark grammar string with canonical IR-AST tags.

The MetaGrammarParser dispatches productions tagged `ir_rule`, `ir_literal`,
etc. to its generic IR-AST constructor. This file is data; no logic.
"""


class _GbnfEscapes(EscapeCodec):
    """GBNF escape tables for quoted string literals."""

    SHORT_ESCAPES = {"n": "\n", "t": "\t", "r": "\r", '"': '"', "\\": "\\"}
    HEX_ESCAPES = (("x", 2), ("u", 4), ("U", 8))


GBNF_ESCAPES = _GbnfEscapes()
"""Singleton escape codec for GBNF."""


GBNF_QUANT_SYMBOLS: dict[tuple[int, int | None], str] = {
    (1, 1): "",
    (0, 1): "?",
    (0, None): "*",
    (1, None): "+",
}


def _gbnf_encode_literal(_d, n, _nc) -> IrStr:
    """Escape the literal value per GBNF rules and wrap in quotes."""
    return IrStr(f'"{GBNF_ESCAPES.encode(n.value)}"')


def _gbnf_charclass(_d, n, _nc) -> IrStr:
    """Render a char class as ``[value]``."""
    return IrStr(f"[{n.value}]")


def _gbnf_not(_d, n, _nc) -> IrStr:
    """Render ``IrNot(IrCharClass(...))`` as ``[^value]``."""
    inner = n.body
    if isinstance(inner, IrCharClass):
        return IrStr(f"[^{inner.value}]")
    raise UnsupportedConstructError(
        f"GBNF IrNot only supports IrCharClass body, got {type(inner).__name__}"
    )


def _gbnf_quantifier(_d, n, _nc) -> IrStr:
    """Look up the GBNF quantifier symbol for the ``(min, max)`` pair."""
    key = (n.min, n.max)
    try:
        return IrStr(GBNF_QUANT_SYMBOLS[key])
    except KeyError as exc:
        raise UnsupportedConstructError(
            f"GBNF does not support quantifier {key}"
        ) from exc


def _gbnf_ast(d, n, _nc) -> IrStr:
    """Render an IrAst as newline-joined rules with a trailing newline."""
    parts = [str(d.eval(d, rule, ())) for rule in n.rules]
    return IrStr("\n".join(parts) + "\n")


GBNF_ACTIONS = (
    IrAction(IrLiteral, IrCallable(_gbnf_encode_literal)),
    IrAction(IrCharClass, IrCallable(_gbnf_charclass)),
    IrAction(IrNot, IrCallable(_gbnf_not)),
    IrAction(IrRuleRef, IrField("value")),
    IrAction(
        IrGroup,
        IrConcat(parts=(IrLiteral("("), IrChild("body"), IrLiteral(")"))),
    ),
    IrAction(IrQuantifier, IrCallable(_gbnf_quantifier)),
    IrAction(IrItem, IrConcat(parts=(IrChild("atom"), IrChild("quantifier")))),
    IrAction(
        IrSequence,
        IrJoin(
            parts=IrChildren("items"),
            separator=IrLiteral(" "),
            empty=IrLiteral('""'),
        ),
    ),
    IrAction(
        IrAlternation,
        IrJoin(
            parts=IrChildren("arms"),
            separator=IrLiteral(" | "),
            empty=IrLiteral(""),
        ),
    ),
    IrAction(
        IrRule,
        IrConcat(parts=(IrField("name"), IrLiteral(" ::= "), IrChild("body"))),
    ),
    IrAction(IrAst, IrCallable(_gbnf_ast)),
)


@dataclass(frozen=True, slots=True, init=False, repr=False)
class _GbnfFlavour(IrFlavour):
    """GBNF flavour singleton class."""

    actions: tuple[IrAction, ...] = GBNF_ACTIONS

    name: ClassVar[str] = "gbnf"
    extensions: ClassVar[tuple[str, ...]] = (".gbnf",)
    meta_grammar: ClassVar[str] = META_GRAMMAR
    escapes: ClassVar[EscapeCodec] = GBNF_ESCAPES
    line_comment: ClassVar[str] = "#"

    @staticmethod
    def parse_quantifier(text: str) -> IrQuantifier:
        """GBNF quantifier parser."""
        lo, hi = quantifier_to_bounds(text)
        return IrQuantifier(min=lo, max=hi)

    @staticmethod
    def parse_charclass(text: str) -> tuple[str, bool]:
        """GBNF charclass parser. ``text`` includes the brackets."""
        inner = text[1:-1]
        if inner.startswith("^"):
            return inner[1:], True
        return inner, False


GBNF_FLAVOUR = _GbnfFlavour()
"""Singleton GBNF flavour."""
