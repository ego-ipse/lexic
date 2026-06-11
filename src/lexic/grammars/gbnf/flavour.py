"""GBNF flavour for Lexic.

Bundles the escape codec, action tuple, and parse helpers in one module.
:data:`GBNF_FLAVOUR` is the singleton :class:`IrFlavour`/:class:`IrEmitter`
consumed by :func:`lexic.grammars.get_flavour`.

Explicit disable of duplicate-code. The end-goal is to have this file be
completely auto-generated.
"""

# pylint: disable=duplicate-code

from __future__ import annotations

from typing import ClassVar

from lexic.exceptions import UnsupportedConstructError
from lexic.grammars.flavour import IrEscape, IrFlavour
from lexic.ir.action import (
    IrAction,
    IrChild,
    IrChildren,
    IrConcat,
    IrCond,
    IrEmit,
    IrField,
    IrIsA,
    IrJoin,
    IrThis,
)
from lexic.ir.base import IrCallable, IrStr, IrTuple
from lexic.ir.escapes import EscapeCodec
from lexic.ir.mapping import IrMap, IrTypeMap
from lexic.ir.nodes import (
    IrAlternation,
    IrAst,
    IrCharClass,
    IrItem,
    IrLiteral,
    IrQuantifier,
    IrRule,
    IrRuleRef,
    IrSequence,
)
from lexic.ir.operators import IrNot

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


GBNF_QUANTIFIERS: IrMap[IrQuantifier, IrLiteral] = IrMap(
    IrTuple(IrQuantifier(1, 1), IrLiteral("")),
    IrTuple(IrQuantifier(0, 1), IrLiteral("?")),
    IrTuple(IrQuantifier(0, None), IrLiteral("*")),
    IrTuple(IrQuantifier(1, None), IrLiteral("+")),
)
"""Quantifier bounds ⇄ GBNF postfix symbol — the data map IS the action body.

Under dispatch the quantifier node itself is the key; a miss (e.g. ``{2,5}``)
raises :exc:`~lexic.exceptions.IrKeyError`, an ``UnsupportedConstructError``.
``parse_quantifier`` inverts the same dyads, so the table exists once.
"""


def _gbnf_not(_d, n, _nc) -> IrStr:
    """Render ``IrNot(IrCharClass(...))`` as ``[^value]``.

    Residual procedural body: ``IrNot`` is tuple-shaped (no named field), so
    neither ``IrIsA`` nor ``IrChild`` can address its raw operand yet.
    """
    inner = n[0]
    if isinstance(inner, IrCharClass):
        return IrStr(f"[^{inner}]")
    raise UnsupportedConstructError(
        f"GBNF IrNot only supports IrCharClass body, got {type(inner).__name__}"
    )


GBNF_ACTIONS = IrTypeMap(
    IrAction(
        IrLiteral,
        IrConcat(parts=IrTuple(IrLiteral('"'), IrEscape(), IrLiteral('"'))),
    ),
    IrAction(
        IrCharClass,
        IrConcat(parts=IrTuple(IrLiteral("["), IrThis(), IrLiteral("]"))),
    ),
    IrAction(IrNot, IrCallable(_gbnf_not)),
    IrAction(IrRuleRef, IrEmit()),
    IrAction(IrQuantifier, GBNF_QUANTIFIERS),
    IrAction(
        IrItem,
        IrConcat(
            parts=IrTuple(
                IrCond(
                    test=IrIsA("atom", IrAlternation),
                    then_op=IrConcat(
                        parts=IrTuple(IrLiteral("("), IrChild("atom"), IrLiteral(")"))
                    ),
                    else_op=IrChild("atom"),
                ),
                IrChild("quantifier"),
            )
        ),
    ),
    IrAction(
        IrSequence,
        IrJoin(
            parts=IrChildren(),
            separator=IrLiteral(" "),
            empty=IrLiteral('""'),
        ),
    ),
    IrAction(
        IrAlternation,
        IrJoin(
            parts=IrChildren(),
            separator=IrLiteral(" | "),
            empty=IrLiteral(""),
        ),
    ),
    IrAction(
        IrRule,
        IrConcat(parts=IrTuple(IrField("name"), IrLiteral(" ::= "), IrChild("body"))),
    ),
    IrAction(
        IrAst,
        IrConcat(parts=IrTuple(IrChild("rules"), IrLiteral("\n"))),
    ),
    # The rules collection is the only bare tuple ever dispatched; concrete
    # subclasses (IrSequence, IrAlternation, records) win by MRO.
    IrAction(
        IrTuple,
        IrJoin(
            parts=IrChildren(),
            separator=IrLiteral("\n"),
            empty=IrLiteral(""),
        ),
    ),
)


class _GbnfFlavour(IrFlavour):
    """GBNF flavour singleton class."""

    actions: IrTypeMap = GBNF_ACTIONS

    name: ClassVar[str] = "gbnf"
    extensions: ClassVar[tuple[str, ...]] = (".gbnf",)
    meta_grammar: ClassVar[str] = META_GRAMMAR
    escapes: ClassVar[EscapeCodec] = GBNF_ESCAPES
    line_comment: ClassVar[str] = "#"

    @staticmethod
    def parse_quantifier(text: str) -> IrQuantifier:
        """GBNF quantifier parser.

        Forms: ``""``, ``?``, ``*``, ``+``, ``{N}``, ``{N,}``, ``{N,M}``.
        """
        symbol_to_bounds = {str(sym): q for q, sym in GBNF_QUANTIFIERS.items()}
        quantifier = symbol_to_bounds.get(text or "")
        if quantifier is not None:
            return quantifier
        inner = text[1:-1]
        if "," in inner:
            lo_str, hi_str = inner.split(",", 1)
            return IrQuantifier(int(lo_str), int(hi_str) if hi_str else None)
        n = int(inner)
        return IrQuantifier(n, n)

    @staticmethod
    def parse_charclass(text: str) -> tuple[str, bool]:
        """GBNF charclass parser. ``text`` includes the brackets."""
        inner = text[1:-1]
        if inner.startswith("^"):
            return inner[1:], True
        return inner, False


GBNF_FLAVOUR = _GbnfFlavour()
"""Singleton GBNF flavour."""
