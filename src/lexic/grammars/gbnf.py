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

from lexic.grammars.flavour import IrEscape, IrFlavour
from lexic.ir.action import (
    IrAction,
    IrApply,
    IrArgs,
    IrAt,
    IrChild,
    IrChildren,
    IrCompare,
    IrConcat,
    IrCond,
    IrEmit,
    IrField,
    IrIsA,
    IrJoin,
    IrRaise,
)
from lexic.ir.base import IrInt, IrNone, IrNoneType, IrSelf, IrStr, IrTuple
from lexic.ir.escapes import EscapeCodec
from lexic.ir.mapping import IR_DEFAULT, IrMap, IrTypeMap
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
from lexic.ir.operators import IrNot, IrOp

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
    IrTuple(IrQuantifier(0, IrNone), IrLiteral("*")),
    IrTuple(IrQuantifier(1, IrNone), IrLiteral("+")),
    # Counted forms — GBNF spells repetition natively as {n} / {n,} / {n,m}.
    IrTuple(
        IR_DEFAULT,
        IrCond(
            # open upper bound (n > 1, ∞) → "{n,}"
            test=IrIsA("hi", IrNoneType),
            then_op=IrConcat(
                parts=IrTuple(IrLiteral("{"), IrField("lo", IrStr), IrLiteral(",}"))
            ),
            else_op=IrCond(
                # closed exact (n, n) → "{n}"
                test=IrCompare(IrField("lo", IrInt), IrOp("=="), IrField("hi", IrInt)),
                then_op=IrConcat(
                    parts=IrTuple(IrLiteral("{"), IrField("lo", IrStr), IrLiteral("}"))
                ),
                # bounded (m, n) → "{m,n}" (covers (0, n) too)
                else_op=IrConcat(
                    parts=IrTuple(
                        IrLiteral("{"),
                        IrField("lo", IrStr),
                        IrLiteral(","),
                        IrField("hi", IrStr),
                        IrLiteral("}"),
                    )
                ),
            ),
        ),
    ),
)
"""Quantifier bounds ⇄ GBNF postfix symbol — the data map IS the action body.

The four closed forms are exact-value keys; every counted form (``{n}``,
``{n,}``, ``{m,n}``) resolves to the :data:`IR_DEFAULT` branch, a nested
:class:`IrCond` over the ``lo``/``hi`` bounds. ``parse_quantifier`` inverts the
exact-key dyads (and parses the counted forms by regex), so the table exists
once.
"""


GBNF_ACTIONS = IrTypeMap(
    IrAction(
        IrLiteral,
        IrConcat(parts=IrTuple(IrLiteral('"'), IrEscape(), IrLiteral('"'))),
    ),
    # Brackets are strictly this action's; the mark-slot (IrArgs) right after
    # the opening bracket is where GBNF's surface syntax puts received marks;
    # the interior is the dispatched join of the class's own elements.
    IrAction(
        IrCharClass,
        IrConcat(
            parts=IrTuple(
                IrLiteral("["),
                IrJoin(parts=IrArgs()),
                IrJoin(parts=IrChildren()),
                IrLiteral("]"),
            )
        ),
    ),
    IrAction(
        IrRange,
        IrJoin(
            parts=IrTuple(IrField("lo"), IrField("hi")),
            separator=IrLiteral("-"),
        ),
    ),
    # Bare IrStr: the run leaf inside a class — encoded units emit verbatim.
    # Concrete str-leaves (IrLiteral/IrRuleRef) win by MRO.
    IrAction(IrStr, IrEmit()),
    # IrNot contributes its mark and delegates: the operand's own action
    # places it. The IrTypeMap is the guard — IrSelf is the MRO catch-all.
    IrAction(
        IrNot,
        IrAt(
            0,
            IrTypeMap(
                IrAction(IrCharClass, IrApply(IrTuple(IrLiteral("^")))),
                IrAction(
                    IrSelf,
                    IrRaise(message="{dispatcher}: cannot negate {node_type!r}"),
                ),
            ),
        ),
    ),
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
        symbol_to_bounds = {
            str(sym): q
            for q, sym in GBNF_QUANTIFIERS.items()
            if isinstance(sym, IrLiteral)
        }
        quantifier = symbol_to_bounds.get(text or "")
        if quantifier is not None:
            return quantifier
        inner = text[1:-1]
        if "," in inner:
            lo_str, hi_str = inner.split(",", 1)
            return IrQuantifier(int(lo_str), int(hi_str) if hi_str else IrNone)
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
