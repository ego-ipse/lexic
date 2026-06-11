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

from lexic.exceptions import UnsupportedConstructError
from lexic.grammars.flavour import IrFlavour
from lexic.ir.action import (
    IrAction,
    IrChild,
    IrChildren,
    IrConcat,
    IrEmit,
    IrField,
    IrJoin,
)
from lexic.ir.base import IrCallable, IrStr, IrTuple
from lexic.ir.escapes import EscapeCodec
from lexic.ir.mapping import IrTypeMap
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

rule: NAME "=" alternation        -> ir_rule
alternation: sequence ("/" sequence)*  -> ir_alternation
sequence: item*                   -> ir_sequence
item: QUANTIFIER? atom            -> ir_item

atom: LITERAL                     -> ir_literal
    | HEXCC                       -> ir_charclass
    | NAME                        -> ir_ruleref
    | "(" alternation ")"         -> ir_group

NAME: /[A-Za-z][A-Za-z0-9_-]*/
LITERAL: /"[^"\r\n]*"/
HEXCC: /%x[0-9A-Fa-f]+(?:-[0-9A-Fa-f]+)?/
QUANTIFIER: /[0-9]+\*[0-9]*|\*[0-9]+|\*|[0-9]+/

%ignore /[ \t\r\n]+/
%ignore /;[^\n]*/
"""
"""ABNF (subset) meta-grammar with canonical IR-AST tags.

Subset:
  - `name = body` (single =, not ::=)
  - alternation by `/`
  - prefix quantifiers `*N`, `n*`, `n*m`, `n`
  - charclasses via `%xNN` or `%xNN-MM`
  - case-insensitive `"abc"` literals (expansion via normalize_literal)
  - groups `(...)`, comments starting with `;`
"""


class _AbnfEscapes(EscapeCodec):
    """Identity codec — ABNF literals are canonical Python."""

    SHORT_ESCAPES: ClassVar[dict[str, str]] = {}
    HEX_ESCAPES: ClassVar[tuple[tuple[str, int], ...]] = ()


ABNF_ESCAPES = _AbnfEscapes()
"""Singleton escape codec for ABNF."""


def _abnf_format_quantifier(lo: int, hi: int | None) -> str:
    """Return the ABNF *prefix* quantifier string. Empty when ``(1, 1)``."""
    if lo == 1 and hi == 1:
        return ""
    if lo == hi:
        return f"{lo}"
    if hi is None:
        return f"{lo}*" if lo != 0 else "*"
    return f"{lo}*{hi}" if lo != 0 else f"*{hi}"


def _hex_range_segment(seg: str) -> str:
    """Convert one POSIX range segment (``a-z`` or single char) to ABNF hex."""
    if len(seg) == 3 and seg[1] == "-":
        lo, hi = seg[0], seg[2]
        return f"%x{ord(lo):02X}-{ord(hi):02X}"
    if len(seg) == 1:
        return f"%x{ord(seg):02X}"
    return " / ".join(f"%x{ord(c):02X}" for c in seg)


def _split_charclass_segments(pattern: str) -> list[str]:
    """Split a POSIX bracket interior into 3-char ranges and 1-char literals."""
    segments: list[str] = []
    i = 0
    while i < len(pattern):
        if i + 2 < len(pattern) and pattern[i + 1] == "-":
            segments.append(pattern[i : i + 3])
            i += 3
        else:
            segments.append(pattern[i])
            i += 1
    return segments


def _abnf_encode_literal(_d, n, _nc) -> IrStr:
    """Wrap the literal value in double quotes."""
    return IrStr(f'"{ABNF_ESCAPES.encode(n)}"')


def _abnf_charclass(_d, n, _nc) -> IrStr:
    """Render a char class as ABNF hex range(s)."""
    segments = _split_charclass_segments(n)
    rendered = [_hex_range_segment(s) for s in segments]
    if len(rendered) == 1:
        return IrStr(rendered[0])
    return IrStr("(" + " / ".join(rendered) + ")")


def _abnf_not(_d, n, _nc) -> IrStr:
    """ABNF has no native negation."""
    raise UnsupportedConstructError(
        f"ABNF does not support IrNot (got {type(n[0]).__name__})"
    )


def _abnf_quantifier(_d, n, _nc) -> IrStr:
    """Compute the ABNF prefix-quantifier symbol from ``(min, max)``."""
    return IrStr(_abnf_format_quantifier(n.min, n.max))


def _abnf_ast(d, n, _nc) -> IrStr:
    """Render an IrAst as newline-joined rules with a trailing newline."""
    parts = [str(d.eval(d, rule, ())) for rule in n.rules]
    return IrStr("\n".join(parts) + "\n")


def _abnf_item(d, n, _nc) -> IrStr:
    """Render ABNF prefix ``quantifier`` then ``atom``; parenthesise an alternation atom."""
    atom = str(d.eval(d, n.atom, ()))
    if isinstance(n.atom, IrAlternation):
        atom = f"({atom})"
    return IrStr(str(d.eval(d, n.quantifier, ())) + atom)


ABNF_ACTIONS = IrTypeMap(
    IrAction(IrLiteral, IrCallable(_abnf_encode_literal)),
    IrAction(IrCharClass, IrCallable(_abnf_charclass)),
    IrAction(IrNot, IrCallable(_abnf_not)),
    IrAction(IrRuleRef, IrEmit()),
    IrAction(IrQuantifier, IrCallable(_abnf_quantifier)),
    # Prefix quantifier ordering: quantifier before atom.
    IrAction(IrItem, IrCallable(_abnf_item)),
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
    IrAction(IrAst, IrCallable(_abnf_ast)),
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
            return IrQuantifier(0, None)
        if text.startswith("*"):
            return IrQuantifier(0, int(text[1:]))
        if "*" in text:
            lo_str, hi_str = text.split("*", 1)
            lo = int(lo_str)
            hi = int(hi_str) if hi_str else None
            return IrQuantifier(lo, hi)
        n = int(text)
        return IrQuantifier(n, n)

    @staticmethod
    def parse_charclass(text: str) -> tuple[str, bool]:
        """ABNF charclass parser. ``text`` is ``%xNN`` or ``%xNN-MM``."""
        body = text[2:]
        if "-" in body:
            lo_hex, hi_hex = body.split("-", 1)
            return f"{chr(int(lo_hex, 16))}-{chr(int(hi_hex, 16))}", False
        return chr(int(body, 16)), False

    @classmethod
    def normalize_literal(cls, decoded: str) -> IrLiteral | IrAlternation:
        """Case-insensitive expansion: ``abc`` → ``([aA][bB][cC])``; leave non-alpha as-is."""
        if not any(c.isalpha() for c in decoded):
            return IrLiteral(decoded)
        items: list[IrItem] = []
        for c in decoded:
            if c.isalpha():
                items.append(IrItem(atom=IrCharClass(f"{c.lower()}{c.upper()}")))
            else:
                items.append(IrItem(atom=IrLiteral(c)))
        return IrAlternation(IrSequence(*items))


ABNF_FLAVOUR = _AbnfFlavour()
"""Singleton ABNF flavour."""
