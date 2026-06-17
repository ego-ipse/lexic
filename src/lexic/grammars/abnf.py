"""ABNF flavour for Lexic.

Bundles the escape codec, action tuple, and parse helpers in one module.
:data:`ABNF_FLAVOUR` is the singleton :class:`IrFlavour`/:class:`IrEmitter`
consumed by :func:`lexic.grammars.get_flavour`.

ABNF differs from GBNF in two key ways: prefix quantifier ordering on
:class:`IrItem` (the quantifier emits before the atom) and ``%xNN``-style
hex char-class rendering. ABNF has no native negated char classes — IrNot
raises.

Explicit disable of duplicate-code. The end-goal is to have this file be
completely auto-generated.
"""

# pylint: disable=duplicate-code

from __future__ import annotations

from typing import ClassVar

from lexic.grammars.flavour import IrEscape, IrFlavour
from lexic.ir.action import (
    IrAction,
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
from lexic.ir.base import IrCallable, IrInt, IrNone, IrNoneType, IrStr, IrTuple
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

rule: NAME "=" alternation             -> ir_rule
    | NAME INCREMENTAL alternation     -> ir_rule_inc

alternation: sequence ("/" sequence)*  -> ir_alternation
sequence: item*                        -> ir_sequence

item: QUANTIFIER? element              -> ir_item
    | "[" alternation "]"              -> ir_option

element: LITERAL                       -> ir_literal
    | CS_STRING                        -> ir_literal_cs
    | CI_STRING                        -> ir_literal_ci
    | NUMSEQ                           -> ir_numseq
    | NUMVAL                           -> ir_charclass
    | PROSE                            -> ir_prose
    | NAME                             -> ir_ruleref
    | "(" alternation ")"              -> ir_group

INCREMENTAL.2: /=\//
NAME: /[A-Za-z][A-Za-z0-9_-]*/
LITERAL: /"[^"\r\n]*"/
CS_STRING: /%[sS]"[^"\r\n]*"/
CI_STRING: /%[iI]"[^"\r\n]*"/
NUMSEQ.2: /%[bdxBDX][0-9A-Fa-f]+(?:\.[0-9A-Fa-f]+)+/
NUMVAL: /%[bdxBDX][0-9A-Fa-f]+(?:-[0-9A-Fa-f]+)?/
PROSE: /<[^>\r\n]*>/
QUANTIFIER: /[0-9]*\*[0-9]*|[0-9]+/

%ignore /[ \t\r\n]+/
%ignore /;[^\n]*/
"""
"""Full ABNF (RFC 5234 + RFC 7405) meta-grammar with canonical IR-AST tags.

Covers:
  - `name = body` rules and `name =/ body` incremental alternatives (merged)
  - alternation `/`, concatenation by juxtaposition
  - prefix repetition `*`, `*m`, `n*`, `n*m`, `n`; optional `[...]` → (0, 1)
  - num-val `%x`/`%d`/`%b`: single value and range (`-`) → IrCharClass;
    value-sequence (`.`) → case-sensitive IrLiteral
  - char-val: case-insensitive `"abc"` / `%i"abc"` (expanded via
    normalize_literal); case-sensitive `%s"abc"` → raw IrLiteral
  - groups `(...)`, prose-val `<...>` (recognised, rejected as non-formal),
    comments starting with `;`
"""

CORE_RULES = r"""
ALPHA  = %x41-5A / %x61-7A
BIT    = "0" / "1"
CHAR   = %x01-7F
CR     = %x0D
CRLF   = CR LF
CTL    = %x00-1F / %x7F
DIGIT  = %x30-39
DQUOTE = %x22
HEXDIG = DIGIT / "A" / "B" / "C" / "D" / "E" / "F"
HTAB   = %x09
LF     = %x0A
LWSP   = *(WSP / CRLF WSP)
OCTET  = %x00-FF
SP     = %x20
VCHAR  = %x21-7E
WSP    = SP / HTAB
"""
"""RFC 5234 Appendix B.1 core rules, in ABNF itself.

Part of the ABNF definition: a grammar may reference these without defining
them. The meta-parser injects only those a grammar transitively references
(a user definition of the same name wins). Lark-era source — it disappears
with the metagrammars when the IR-native parser lands.
"""


class _AbnfEscapes(EscapeCodec):
    """Identity codec — ABNF literals are canonical Python."""

    SHORT_ESCAPES: ClassVar[dict[str, str]] = {}
    HEX_ESCAPES: ClassVar[tuple[tuple[str, int], ...]] = ()


ABNF_ESCAPES = _AbnfEscapes()
"""Singleton escape codec for ABNF."""


ABNF_PREFIX_QUANTIFIER: IrMap = IrMap(
    # The two canonicalization specials are exact-value keys — and exactly the
    # closed forms GBNF_QUANTIFIERS also pins. Open/parameterized forms miss the
    # map and fall to the IrNone default: branch + integer interpolation (bounds
    # read via IrField, int payload stringified by wrapping in IrStr).
    IrTuple(IrQuantifier(1, 1), IrLiteral("")),
    IrTuple(IrQuantifier(0, IrNone), IrLiteral("*")),
    IrTuple(
        IR_DEFAULT,
        IrCond(
            # open upper bound, lo != 0 ((0, ∞) is an exact key) → "{lo}*"
            test=IrIsA("hi", IrNoneType),
            then_op=IrConcat(IrTuple(IrField("lo", IrStr), IrLiteral("*"))),
            else_op=IrCond(
                # closed lo == hi (lo != 1 here — (1, 1) is an exact key) → "{lo}"
                test=IrCompare(IrField("lo", IrInt), IrOp("=="), IrField("hi", IrInt)),
                then_op=IrField("lo", IrStr),
                else_op=IrCond(
                    # "{lo}*{hi}", or "*{hi}" when lo == 0
                    test=IrCompare(IrField("lo", IrInt), IrOp("=="), IrInt(0)),
                    then_op=IrConcat(IrTuple(IrLiteral("*"), IrField("hi", IrStr))),
                    else_op=IrConcat(
                        IrTuple(
                            IrField("lo", IrStr), IrLiteral("*"), IrField("hi", IrStr)
                        )
                    ),
                ),
            ),
        ),
    ),
)
"""Quantifier bounds → ABNF prefix string: an :class:`IrMap
ABNF quantifiers are an open set (``N``, ``N*M``, ``*N``, ``N*``), so — unlike
GBNF's wholly-finite ``IrMap`` — only the two canonicalization specials
(``(1,1) → ""``, ``(0,∞) → "*"``, shared with ``GBNF_QUANTIFIERS``) are
exact-value keys. Every open/parameterized form misses and resolves to the
:data:`IrNone` default, a nested :class:`IrCond` over the remaining ``lo``/``hi``
predicates; pulling the two specials out collapses its inner branches.
"""


def _abnf_charclass(_d, n, _nc) -> IrStr:
    """Render a structured char class as ABNF hex atom(s)/range(s).

    One ``%xNN-MM`` per :class:`IrRange` element; one ``%xNN`` per char of
    an :class:`~lexic.ir.base.IrStr` run; parenthesised alternation when
    more than one atom results.
    """
    rendered: list[str] = []
    for element in n:
        if isinstance(element, IrRange):
            rendered.append(f"%x{ord(str(element.lo)):02X}-{ord(str(element.hi)):02X}")
        else:
            rendered.extend(f"%x{ord(c):02X}" for c in str(element))
    if len(rendered) == 1:
        return IrStr(rendered[0])
    return IrStr("(" + " / ".join(rendered) + ")")


ABNF_ACTIONS = IrTypeMap(
    IrAction(
        IrLiteral,
        IrConcat(parts=IrTuple(IrLiteral('"'), IrEscape(), IrLiteral('"'))),
    ),
    IrAction(IrCharClass, IrCallable(_abnf_charclass)),
    # ABNF has no native negation — strict declarative refusal.
    IrAction(
        IrNot,
        IrRaise(message="{dispatcher}: ABNF does not support {node_type!r}"),
    ),
    IrAction(IrRuleRef, IrEmit()),
    IrAction(IrQuantifier, ABNF_PREFIX_QUANTIFIER),
    # Prefix quantifier ordering: quantifier before atom.
    IrAction(
        IrItem,
        IrConcat(
            parts=IrTuple(
                IrChild("quantifier"),
                IrCond(
                    test=IrIsA("atom", IrAlternation),
                    then_op=IrConcat(
                        parts=IrTuple(IrLiteral("("), IrChild("atom"), IrLiteral(")"))
                    ),
                    else_op=IrChild("atom"),
                ),
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
            separator=IrLiteral(" / "),
            empty=IrLiteral(""),
        ),
    ),
    IrAction(
        IrRule,
        IrConcat(parts=IrTuple(IrField("name"), IrLiteral(" = "), IrChild("body"))),
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


class _AbnfFlavour(IrFlavour):
    """ABNF flavour singleton class."""

    actions: IrTypeMap = ABNF_ACTIONS

    name: ClassVar[str] = "abnf"
    extensions: ClassVar[tuple[str, ...]] = (".abnf",)
    meta_grammar: ClassVar[str] = META_GRAMMAR
    escapes: ClassVar[EscapeCodec] = ABNF_ESCAPES
    line_comment: ClassVar[str] = ";"

    @staticmethod
    def parse_quantifier(text: str) -> IrQuantifier:
        """ABNF quantifier parser. Forms: ``*``, ``*N``, ``N*``, ``N*M``, ``N``."""
        if text == "*":
            return IrQuantifier(0, IrNone)
        if text.startswith("*"):
            return IrQuantifier(0, int(text[1:]))
        if "*" in text:
            lo_str, hi_str = text.split("*", 1)
            lo = int(lo_str)
            hi = int(hi_str) if hi_str else IrNone
            return IrQuantifier(lo, hi)
        n = int(text)
        return IrQuantifier(n, n)

    @staticmethod
    def parse_charclass(text: str) -> tuple[str, bool]:
        """Parse an ABNF num-val single value or range.

        ``text`` is ``%x41`` / ``%d65`` / ``%b1000001`` (single) or its ``-``
        range form. The radix marker (``x``/``d``/``b``, any case) selects base
        16/10/2. ABNF has no negation, so the flag is always ``False``.
        """
        radix = {"b": 2, "d": 10, "x": 16}[text[1].lower()]
        body = text[2:]
        if "-" in body:
            lo_s, hi_s = body.split("-", 1)
            return f"{chr(int(lo_s, radix))}-{chr(int(hi_s, radix))}", False
        return chr(int(body, radix)), False

    @classmethod
    def normalize_literal(cls, decoded: str) -> IrLiteral | IrAlternation:
        """Case-insensitive expansion: ``abc`` → ``([aA][bB][cC])``; leave non-alpha as-is."""
        if not any(c.isalpha() for c in decoded):
            return IrLiteral(decoded)
        items: list[IrItem] = []
        for c in decoded:
            if c.isalpha():
                items.append(IrItem(atom=IrCharClass(IrStr(f"{c.lower()}{c.upper()}"))))
            else:
                items.append(IrItem(atom=IrLiteral(c)))
        return IrAlternation(IrSequence(*items))


ABNF_FLAVOUR = _AbnfFlavour()
"""Singleton ABNF flavour."""
