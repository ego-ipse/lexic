"""ABNF flavour for Lexic.

Bundles the escape codec, emit action tuple, and the native-IR self-grammar +
reducer in one module. :data:`ABNF_FLAVOUR` is the singleton
:class:`IrFlavour`/:class:`IrEmitter` consumed by
:func:`lexic.grammars.get_flavour`.

ABNF differs from GBNF in three key ways: prefix quantifier ordering on
:class:`IrItem` (the quantifier emits before the atom), ``%xNN``-style hex
char-class rendering, and literal spelling — a case-sensitive
:class:`~lexic.ir.nodes.IrLiteral` renders as an RFC 7405 ``%s"..."`` char-val
when every character is char-val-spellable (printable ASCII bar the double
quote), and falls back to ``%x`` num-val (``%xNN`` / dot-joined ``%xNN.NN``)
for quotes, control points, or non-ASCII. Vanilla case-insensitive char-val is
never *emitted* (it would lose the canonical literal's case), only *accepted*.
ABNF has no native negated char classes, but canonicalisation rewrites every
``IrNot`` to a positive span before emission, so the raising ``IrNot`` action
is unreachable on canonical input.

:data:`ABNF_GRAMMAR` is the ABNF grammar of ABNF (RFC 5234 §4 + Appendix
B.1), authored directly as :class:`~lexic.ir.nodes.IrAst` — no construction
helpers, no Lark — and **stored in canonical form**
(``canonicalize(ABNF_GRAMMAR) == ABNF_GRAMMAR``). Driven by
:mod:`lexic.parsing` it parses ABNF source into a derivation; the self-hosting
fixpoint is ``canonicalize(reduce(parse(ABNF_GRAMMAR, emitted)))`` returning
``ABNF_GRAMMAR`` — the canonical pass closes the loop, since a merged char
class re-emits as a parenthesised num-val alternation that reparses un-merged.
:data:`ABNF_REDUCTIONS` is the "meta notation": an
:class:`~lexic.ir.mapping.IrMap` from each rule's
:class:`~lexic.ir.nodes.IrRuleRef` to a body that folds that rule's
parse-tree children into an IR node — the mirror of the emit table
``ABNF_ACTIONS`` (IR→text), pointed the other way (tree→IR).

**One adaptation survives canonicalisation:** *line ending is ``[CR] LF``.*
RFC's ``c-nl = comment / CRLF``; this subset omits comments and accepts a bare
LF (the ``ABNF_FLAVOUR`` emitter joins rules with ``"\\n"``), with the optional
CR keeping CRLF input parseable too.

The grammar covers the full RFC 5234 + 7405 surface: ``bin-val``/``dec-val``
alongside ``hex-val`` (single/range), value ``num-seq`` (``%x0D.0A``),
``option`` (``[...]``), incremental ``=/`` (arms merged into the earlier
same-named rule), ``%s``/``%i`` strings, ``prose-val`` (recognised then
refused), comments (leading, trailing, inline), and ``c-wsp`` line folding.
The constructs beyond the flavour's own emitted output leave the self-hosting
fixpoint unaffected — the grammar only *accepts* more. Radix and case markers
are lowercase only (``%x``/``%d``/``%b``/``%s``/``%i``; the emitter never
produces the uppercase forms). Rule names are hyphenated and folded lowercase
(``char-val``, ``dquote``); ``rulename`` admits ``alpha / digit / "-"``.

**Every reduction is pure ``IrSelf``.** Text rules (the character/terminal
rules) reduce with the shared :data:`YIELD`. Structural rules build typed
nodes from clean ``nc`` with :class:`~lexic.ir.action.IrBuild`. The numeric
rules decode their digit runs with :class:`~lexic.ir.action.IrUnradix` (the
inverse of the emit-side radix spelling) and build over code points — the
whole reduce side is IR action algebra, no procedural parse helpers.

Explicit disable of duplicate-code and too-many-lines. The end-goal is to have
this file be completely auto-generated.

Over the pylint module-line cap, exempted (user ruling 2026-07-03, as with
:mod:`gbnf`): the full RFC 5234 + 7405 self-grammar authored here (folding,
options, num-sequence/``%d``/``%b``, ``%s``/``%i`` strings, incremental ``=/``)
keeps the module large.
"""

# pylint: disable=duplicate-code
# pylint: disable=too-many-lines

from __future__ import annotations

import string
from typing import ClassVar

from lexic.ir.action import (
    IrAction,
    IrArg,
    IrArgs,
    IrBuild,
    IrChild,
    IrChildren,
    IrCompare,
    IrConcat,
    IrCond,
    IrEach,
    IrEmit,
    IrField,
    IrGlyph,
    IrIsA,
    IrJoin,
    IrLen,
    IrMerge,
    IrOrd,
    IrPipe,
    IrRadix,
    IrRaise,
    IrThis,
    IrUnradix,
)
from lexic.ir.base import (
    IrChr,
    IrInt,
    IrNone,
    IrNoneType,
    IrSelf,
    IrSeq,
    IrStr,
    IrTuple,
)
from lexic.ir.escapes import EscapeCodec
from lexic.ir.flavour import IrFlavour, IrSpellable
from lexic.ir.layout import IrDocConcat, IrDocJoin, IrGroup, IrLine, IrNest, IrText
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
from lexic.parsing.earley.reduce import DROP, KEEP_REDUCED, YIELD, Reducer


class _AbnfEscapes(EscapeCodec):
    """Identity codec — ABNF literals are canonical Python; the quoted
    char-val body admits printable ASCII except the double quote (RFC 7405)."""

    SHORT_ESCAPES: ClassVar[dict[str, str]] = {}
    HEX_ESCAPES: ClassVar[tuple[tuple[str, int], ...]] = ()
    QUOTE_SAFE: ClassVar[tuple[tuple[int, int], ...]] = ((0x20, 0x21), (0x23, 0x7E))


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


ABNF_ACTIONS = IrTypeMap(
    # A literal whose characters all fit the codec's QUOTE_SAFE ranges emits
    # as an RFC 7405 case-sensitive char-val (%s"...") — no case folding on
    # reparse; anything else (quote, control point, non-ASCII) falls back to
    # %x num-val, dot-joined per code point (num-seq), which the reducer
    # decodes back to the identical case-sensitive literal.
    IrAction(
        IrLiteral,
        IrCond(
            test=IrSpellable(),
            then_op=IrConcat(parts=IrTuple(IrLiteral('%s"'), IrEmit(), IrLiteral('"'))),
            else_op=IrConcat(
                parts=IrTuple(
                    IrLiteral("%x"),
                    IrJoin(
                        parts=IrEach(IrPipe(IrOrd(), IrRadix(16, 2))),
                        separator=IrLiteral("."),
                    ),
                )
            ),
        ),
    ),
    # One %xNN / %xNN-MM per class element (the IrChr/IrRange actions below);
    # a single element emits bare, several parenthesise as an alternation.
    IrAction(
        IrCharClass,
        IrCond(
            test=IrCompare(IrLen(), IrOp("=="), IrInt(1)),
            then_op=IrJoin(parts=IrChildren()),
            else_op=IrConcat(
                parts=IrTuple(
                    IrLiteral("("),
                    IrJoin(parts=IrChildren(), separator=IrLiteral(" / ")),
                    IrLiteral(")"),
                )
            ),
        ),
    ),
    IrAction(IrChr, IrConcat(parts=IrTuple(IrLiteral("%x"), IrRadix(16, 2)))),
    IrAction(
        IrRange,
        IrConcat(
            parts=IrTuple(
                IrLiteral("%x"),
                IrPipe(IrField("lo", IrInt), IrRadix(16, 2)),
                IrLiteral("-"),
                IrPipe(IrField("hi", IrInt), IrRadix(16, 2)),
            )
        ),
    ),
    # ABNF has no native negation — strict declarative refusal.
    IrAction(
        IrNot,
        IrRaise(message="{dispatcher}: ABNF does not support {node_type!r}"),
    ),
    IrAction(IrRuleRef, IrEmit()),
    IrAction(IrQuantifier, ABNF_PREFIX_QUANTIFIER),
    # Prefix quantifier ordering: quantifier before atom. STRUCTURE levels
    # build layout docs (the GBNF table's shape, ABNF spellings):
    # trailing-slash continuations, one width-group per rule. The broken
    # continuation lines start with WSP — the wrap IS RFC 5234 folding, so
    # the wrapped form reparses through c-wsp.
    IrAction(
        IrItem,
        IrDocConcat(
            parts=IrTuple(
                IrChild("quantifier"),
                IrCond(
                    test=IrIsA("atom", IrAlternation),
                    then_op=IrDocConcat(
                        parts=IrTuple(IrText("("), IrChild("atom"), IrText(")"))
                    ),
                    else_op=IrChild("atom"),
                ),
            )
        ),
    ),
    IrAction(
        IrSequence,
        IrGroup(
            IrDocJoin(
                parts=IrChildren(),
                separator=IrLine(" "),
                empty=IrText('""'),
            )
        ),
    ),
    IrAction(
        IrAlternation,
        IrDocJoin(
            parts=IrChildren(),
            separator=IrLine(" / ", " /"),
            empty=IrText(""),
        ),
    ),
    IrAction(
        IrRule,
        IrGroup(
            IrNest(
                6,
                IrDocConcat(
                    parts=IrTuple(IrField("name"), IrText(" = "), IrChild("body"))
                ),
            )
        ),
    ),
    IrAction(
        IrAst,
        IrDocConcat(parts=IrTuple(IrChild("rules"), IrLine())),
    ),
    # The rules collection is the only bare tuple ever dispatched; concrete
    # subclasses (IrSequence, IrAlternation, records) win by MRO.
    IrAction(
        IrTuple,
        IrDocJoin(
            parts=IrChildren(),
            separator=IrLine(),
            empty=IrText(""),
        ),
    ),
)


# ── ABNF grammar as native IR + reducer ────────────────────────────────────
#
# The text→IR half of the flavour, with no Lark: ABNF_GRAMMAR is the ABNF
# grammar of ABNF authored directly as IrAst (see the module docstring for
# the round-trip adaptations); ABNF_REDUCTIONS is the reduce-side mirror of
# ABNF_ACTIONS above, folding a parse tree back into IR.


def _mark(letter: str) -> IrCharClass:
    """A case-insensitive marker-letter class (RFC 5234 rulenames are
    case-insensitive, so ``%X``/``%D``/``%B``/``%S``/``%I`` parse too);
    members in canonical order (uppercase code point first). The marks are
    noise rules — nothing reads the text, emit stays canonical lowercase."""
    return IrCharClass(IrChr(letter.upper()), IrChr(letter))


_MARK_X, _MARK_D, _MARK_B = _mark("x"), _mark("d"), _mark("b")
_MARK_S, _MARK_I = _mark("s"), _mark("i")

ABNF_GRAMMAR = IrAst(
    IrSeq(
        IrRule(
            "rulelist",
            IrAlternation(
                IrSequence(
                    IrItem(IrRuleRef("filler"), IrQuantifier(0, IrNone)),
                    IrItem(IrRuleRef("rule")),
                    IrItem(IrRuleRef("rl-cont"), IrQuantifier(0, IrNone)),
                    IrItem(IrRuleRef("c-wsp"), IrQuantifier(0, IrNone)),
                    IrItem(IrRuleRef("c-nl"), IrQuantifier(0)),
                )
            ),
        ),
        IrRule(
            "filler",
            IrAlternation(
                IrSequence(IrItem(IrRuleRef("comment"))),
                IrSequence(IrItem(IrRuleRef("blank"))),
            ),
            False,
        ),
        IrRule(
            "rule",
            IrAlternation(
                IrSequence(
                    IrItem(IrRuleRef("rulename")),
                    IrItem(IrRuleRef("c-wsp"), IrQuantifier(0, IrNone)),
                    IrItem(IrRuleRef("defined")),
                    IrItem(IrRuleRef("c-wsp"), IrQuantifier(0, IrNone)),
                    IrItem(IrRuleRef("alternation")),
                )
            ),
        ),
        IrRule(
            "rl-cont",
            IrAlternation(
                IrSequence(
                    IrItem(IrRuleRef("c-wsp"), IrQuantifier(0, IrNone)),
                    IrItem(IrRuleRef("c-nl")),
                    IrItem(IrRuleRef("filler"), IrQuantifier(0, IrNone)),
                    IrItem(IrRuleRef("rule")),
                )
            ),
        ),
        IrRule(
            "c-wsp",
            IrAlternation(
                IrSequence(IrItem(IrRuleRef("wsp"))),
                IrSequence(IrItem(IrRuleRef("c-nl")), IrItem(IrRuleRef("wsp"))),
            ),
            False,
        ),
        IrRule(
            "c-nl",
            IrAlternation(
                IrSequence(IrItem(IrRuleRef("comment"))),
                IrSequence(IrItem(IrRuleRef("crlf"))),
            ),
            False,
        ),
        IrRule(
            "comment",
            IrAlternation(
                IrSequence(
                    IrItem(IrLiteral(";")),
                    IrItem(IrRuleRef("cchar"), IrQuantifier(0, IrNone)),
                    IrItem(IrRuleRef("crlf")),
                )
            ),
            False,
        ),
        IrRule(
            "blank",
            IrAlternation(
                IrSequence(
                    IrItem(IrRuleRef("wsp"), IrQuantifier(0, IrNone)),
                    IrItem(IrRuleRef("crlf")),
                )
            ),
            False,
        ),
        IrRule(
            "rulename",
            IrAlternation(
                IrSequence(
                    IrItem(IrRuleRef("alpha")),
                    IrItem(IrRuleRef("namechar"), IrQuantifier(0, IrNone)),
                )
            ),
        ),
        IrRule(
            "defined",
            IrAlternation(
                IrSequence(IrItem(IrLiteral("="))), IrSequence(IrItem(IrLiteral("=/")))
            ),
            False,
        ),
        IrRule(
            "alternation",
            IrAlternation(
                IrSequence(
                    IrItem(IrRuleRef("concatenation")),
                    IrItem(IrRuleRef("altrest"), IrQuantifier(0, IrNone)),
                )
            ),
        ),
        IrRule(
            "wsp",
            IrAlternation(
                IrSequence(IrItem(IrRuleRef("sp"))),
                IrSequence(IrItem(IrRuleRef("htab"))),
            ),
            False,
        ),
        IrRule(
            "crlf",
            IrAlternation(
                IrSequence(
                    IrItem(IrRuleRef("cr"), IrQuantifier(0)), IrItem(IrRuleRef("lf"))
                )
            ),
            False,
        ),
        IrRule(
            "cchar",
            IrAlternation(
                IrSequence(IrItem(IrRuleRef("htab"))),
                IrSequence(IrItem(IrCharClass(IrRange(IrChr(32), IrChr(126))))),
            ),
        ),
        IrRule(
            "alpha",
            IrAlternation(
                IrSequence(
                    IrItem(
                        IrCharClass(
                            IrRange(IrChr(65), IrChr(90)),
                            IrRange(IrChr(97), IrChr(122)),
                        )
                    )
                )
            ),
        ),
        IrRule(
            "namechar",
            IrAlternation(
                IrSequence(IrItem(IrRuleRef("alpha"))),
                IrSequence(IrItem(IrRuleRef("digit"))),
                IrSequence(IrItem(IrLiteral("-"))),
            ),
        ),
        IrRule(
            "concatenation",
            IrAlternation(
                IrSequence(
                    IrItem(IrRuleRef("repetition")),
                    IrItem(IrRuleRef("catrest"), IrQuantifier(0, IrNone)),
                )
            ),
        ),
        IrRule(
            "altrest",
            IrAlternation(
                IrSequence(
                    IrItem(IrRuleRef("c-wsp"), IrQuantifier(0, IrNone)),
                    IrItem(IrLiteral("/")),
                    IrItem(IrRuleRef("c-wsp"), IrQuantifier(0, IrNone)),
                    IrItem(IrRuleRef("concatenation")),
                )
            ),
        ),
        IrRule("sp", IrAlternation(IrSequence(IrItem(IrLiteral(" ")))), False),
        IrRule("htab", IrAlternation(IrSequence(IrItem(IrLiteral("\t")))), False),
        IrRule("cr", IrAlternation(IrSequence(IrItem(IrLiteral("\r")))), False),
        IrRule("lf", IrAlternation(IrSequence(IrItem(IrLiteral("\n")))), False),
        IrRule(
            "digit",
            IrAlternation(
                IrSequence(IrItem(IrCharClass(IrRange(IrChr(48), IrChr(57)))))
            ),
        ),
        IrRule(
            "repetition",
            IrAlternation(
                IrSequence(IrItem(IrRuleRef("rep-core"))),
                IrSequence(IrItem(IrRuleRef("option"))),
            ),
        ),
        IrRule(
            "catrest",
            IrAlternation(
                IrSequence(
                    IrItem(IrRuleRef("c-wsp"), IrQuantifier(1, IrNone)),
                    IrItem(IrRuleRef("repetition")),
                )
            ),
        ),
        IrRule(
            "rep-core",
            IrAlternation(
                IrSequence(
                    IrItem(IrRuleRef("repeat-opt")), IrItem(IrRuleRef("element"))
                )
            ),
        ),
        IrRule(
            "option",
            IrAlternation(
                IrSequence(
                    IrItem(IrLiteral("[")),
                    IrItem(IrRuleRef("c-wsp"), IrQuantifier(0, IrNone)),
                    IrItem(IrRuleRef("alternation")),
                    IrItem(IrRuleRef("c-wsp"), IrQuantifier(0, IrNone)),
                    IrItem(IrLiteral("]")),
                )
            ),
        ),
        IrRule(
            "repeat-opt",
            IrAlternation(IrSequence(IrItem(IrRuleRef("repeat"), IrQuantifier(0)))),
        ),
        IrRule(
            "element",
            IrAlternation(
                IrSequence(IrItem(IrRuleRef("rulename"))),
                IrSequence(IrItem(IrRuleRef("char-val"))),
                IrSequence(IrItem(IrRuleRef("cs-string"))),
                IrSequence(IrItem(IrRuleRef("ci-string"))),
                IrSequence(IrItem(IrRuleRef("num-val"))),
                IrSequence(IrItem(IrRuleRef("group"))),
                IrSequence(IrItem(IrRuleRef("prose"))),
            ),
        ),
        IrRule(
            "repeat",
            IrAlternation(
                IrSequence(IrItem(IrRuleRef("repeat-num"))),
                IrSequence(IrItem(IrRuleRef("repeat-nolo"))),
            ),
        ),
        IrRule(
            "char-val",
            IrAlternation(
                IrSequence(
                    IrItem(IrRuleRef("dquote")),
                    IrItem(IrRuleRef("cvbody")),
                    IrItem(IrRuleRef("dquote")),
                )
            ),
        ),
        IrRule(
            "cs-string",
            IrAlternation(
                IrSequence(
                    IrItem(IrLiteral("%")),
                    IrItem(IrRuleRef("smark")),
                    IrItem(IrRuleRef("dquote")),
                    IrItem(IrRuleRef("csbody")),
                    IrItem(IrRuleRef("dquote")),
                )
            ),
        ),
        IrRule(
            "ci-string",
            IrAlternation(
                IrSequence(
                    IrItem(IrLiteral("%")),
                    IrItem(IrRuleRef("imark")),
                    IrItem(IrRuleRef("char-val")),
                )
            ),
        ),
        IrRule(
            "num-val",
            IrAlternation(
                IrSequence(IrItem(IrRuleRef("num-x"))),
                IrSequence(IrItem(IrRuleRef("num-d"))),
                IrSequence(IrItem(IrRuleRef("num-b"))),
            ),
        ),
        IrRule(
            "group",
            IrAlternation(
                IrSequence(
                    IrItem(IrLiteral("(")),
                    IrItem(IrRuleRef("c-wsp"), IrQuantifier(0, IrNone)),
                    IrItem(IrRuleRef("alternation")),
                    IrItem(IrRuleRef("c-wsp"), IrQuantifier(0, IrNone)),
                    IrItem(IrLiteral(")")),
                )
            ),
        ),
        IrRule(
            "prose",
            IrAlternation(
                IrSequence(
                    IrItem(IrLiteral("<")),
                    IrItem(IrRuleRef("prose-char"), IrQuantifier(0, IrNone)),
                    IrItem(IrLiteral(">")),
                )
            ),
        ),
        IrRule(
            "repeat-num",
            IrAlternation(
                IrSequence(
                    IrItem(IrRuleRef("decits")), IrItem(IrRuleRef("repeat-tail"))
                )
            ),
        ),
        IrRule(
            "repeat-nolo",
            IrAlternation(
                IrSequence(IrItem(IrLiteral("*")), IrItem(IrRuleRef("hi-bound")))
            ),
        ),
        IrRule("dquote", IrAlternation(IrSequence(IrItem(IrLiteral('"')))), False),
        IrRule(
            "cvbody",
            IrAlternation(
                IrSequence(
                    IrItem(IrRuleRef("cvnac"), IrQuantifier(0, IrNone)),
                    IrItem(
                        IrAlternation(
                            IrSequence(
                                IrItem(IrRuleRef("cvalpha")),
                                IrItem(IrRuleRef("cvany"), IrQuantifier(0, IrNone)),
                            )
                        ),
                        IrQuantifier(0, 1),
                    ),
                )
            ),
        ),
        IrRule("smark", IrAlternation(IrSequence(IrItem(_MARK_S))), False),
        IrRule(
            "csbody",
            IrAlternation(
                IrSequence(IrItem(IrRuleRef("qchar"), IrQuantifier(0, IrNone)))
            ),
        ),
        IrRule("imark", IrAlternation(IrSequence(IrItem(_MARK_I))), False),
        IrRule(
            "num-x",
            IrAlternation(
                IrSequence(
                    IrItem(IrLiteral("%")),
                    IrItem(IrRuleRef("xmark")),
                    IrItem(IrRuleRef("hexits")),
                    IrItem(IrRuleRef("x-tail")),
                )
            ),
        ),
        IrRule(
            "num-d",
            IrAlternation(
                IrSequence(
                    IrItem(IrLiteral("%")),
                    IrItem(IrRuleRef("dmark")),
                    IrItem(IrRuleRef("hexits")),
                    IrItem(IrRuleRef("d-tail")),
                )
            ),
        ),
        IrRule(
            "num-b",
            IrAlternation(
                IrSequence(
                    IrItem(IrLiteral("%")),
                    IrItem(IrRuleRef("bmark")),
                    IrItem(IrRuleRef("hexits")),
                    IrItem(IrRuleRef("b-tail")),
                )
            ),
        ),
        IrRule(
            "prose-char",
            IrAlternation(
                IrSequence(
                    IrItem(
                        IrCharClass(
                            IrRange(IrChr(32), IrChr(61)),
                            IrRange(IrChr(63), IrChr(126)),
                        )
                    )
                )
            ),
        ),
        IrRule(
            "decits",
            IrAlternation(
                IrSequence(IrItem(IrRuleRef("digit"), IrQuantifier(1, IrNone)))
            ),
        ),
        IrRule(
            "repeat-tail",
            IrAlternation(
                IrSequence(),
                IrSequence(IrItem(IrLiteral("*")), IrItem(IrRuleRef("hi-bound"))),
            ),
        ),
        IrRule(
            "hi-bound",
            IrAlternation(IrSequence(IrItem(IrRuleRef("decits"), IrQuantifier(0)))),
        ),
        IrRule(
            "cvnac",
            IrAlternation(
                IrSequence(
                    IrItem(
                        IrCharClass(
                            IrRange(IrChr(32), IrChr(33)),
                            IrRange(IrChr(35), IrChr(64)),
                            IrRange(IrChr(91), IrChr(96)),
                            IrRange(IrChr(123), IrChr(126)),
                        )
                    )
                )
            ),
        ),
        IrRule("cvalpha", IrAlternation(IrSequence(IrItem(IrRuleRef("alpha"))))),
        IrRule(
            "cvany",
            IrAlternation(
                IrSequence(IrItem(IrRuleRef("cvalpha"))),
                IrSequence(IrItem(IrRuleRef("cvnai"))),
            ),
        ),
        IrRule(
            "qchar",
            IrAlternation(
                IrSequence(
                    IrItem(
                        IrCharClass(
                            IrRange(IrChr(32), IrChr(33)),
                            IrRange(IrChr(35), IrChr(126)),
                        )
                    )
                )
            ),
        ),
        IrRule("xmark", IrAlternation(IrSequence(IrItem(_MARK_X))), False),
        IrRule(
            "hexits",
            IrAlternation(
                IrSequence(IrItem(IrRuleRef("hexdig"), IrQuantifier(1, IrNone)))
            ),
        ),
        IrRule(
            "x-tail",
            IrAlternation(
                IrSequence(),
                IrSequence(IrItem(IrRuleRef("x-range"))),
                IrSequence(IrItem(IrRuleRef("x-seq"))),
            ),
        ),
        IrRule("dmark", IrAlternation(IrSequence(IrItem(_MARK_D))), False),
        IrRule(
            "d-tail",
            IrAlternation(
                IrSequence(),
                IrSequence(IrItem(IrRuleRef("d-range"))),
                IrSequence(IrItem(IrRuleRef("d-seq"))),
            ),
        ),
        IrRule("bmark", IrAlternation(IrSequence(IrItem(_MARK_B))), False),
        IrRule(
            "b-tail",
            IrAlternation(
                IrSequence(),
                IrSequence(IrItem(IrRuleRef("b-range"))),
                IrSequence(IrItem(IrRuleRef("b-seq"))),
            ),
        ),
        IrRule(
            "cvnai",
            IrAlternation(
                IrSequence(
                    IrItem(
                        IrCharClass(
                            IrRange(IrChr(32), IrChr(33)),
                            IrRange(IrChr(35), IrChr(64)),
                            IrRange(IrChr(91), IrChr(96)),
                            IrRange(IrChr(123), IrChr(126)),
                        )
                    )
                )
            ),
        ),
        IrRule(
            "hexdig",
            IrAlternation(
                IrSequence(IrItem(IrRuleRef("digit"))),
                IrSequence(
                    IrItem(
                        IrCharClass(
                            IrRange(IrChr(65), IrChr(70)),
                            IrRange(IrChr(97), IrChr(102)),
                        )
                    )
                ),
            ),
        ),
        IrRule(
            "x-range",
            IrAlternation(
                IrSequence(IrItem(IrLiteral("-")), IrItem(IrRuleRef("hexits")))
            ),
        ),
        IrRule(
            "x-seq",
            IrAlternation(
                IrSequence(IrItem(IrRuleRef("hexdot"), IrQuantifier(1, IrNone)))
            ),
        ),
        IrRule(
            "d-range",
            IrAlternation(
                IrSequence(IrItem(IrLiteral("-")), IrItem(IrRuleRef("hexits")))
            ),
        ),
        # RFC 5234 dot-sequences at radix 10 / 2 (%d13.10, %b1101.1010) —
        # the x-seq shape with strict per-radix digit runs.
        IrRule(
            "d-seq",
            IrAlternation(
                IrSequence(IrItem(IrRuleRef("decdot"), IrQuantifier(1, IrNone)))
            ),
        ),
        IrRule(
            "b-range",
            IrAlternation(
                IrSequence(IrItem(IrLiteral("-")), IrItem(IrRuleRef("hexits")))
            ),
        ),
        IrRule(
            "b-seq",
            IrAlternation(
                IrSequence(IrItem(IrRuleRef("bindot"), IrQuantifier(1, IrNone)))
            ),
        ),
        IrRule(
            "hexdot",
            IrAlternation(
                IrSequence(IrItem(IrLiteral(".")), IrItem(IrRuleRef("hexglyph")))
            ),
        ),
        IrRule(
            "decdot",
            IrAlternation(
                IrSequence(IrItem(IrLiteral(".")), IrItem(IrRuleRef("decglyph")))
            ),
        ),
        IrRule(
            "bindot",
            IrAlternation(
                IrSequence(IrItem(IrLiteral(".")), IrItem(IrRuleRef("binglyph")))
            ),
        ),
        IrRule(
            "hexglyph",
            IrAlternation(
                IrSequence(IrItem(IrRuleRef("hexdig"), IrQuantifier(1, IrNone)))
            ),
        ),
        IrRule(
            "decglyph",
            IrAlternation(
                IrSequence(IrItem(IrRuleRef("digit"), IrQuantifier(1, IrNone)))
            ),
        ),
        IrRule(
            "binglyph",
            IrAlternation(
                IrSequence(IrItem(IrRuleRef("bit"), IrQuantifier(1, IrNone)))
            ),
        ),
        IrRule(
            "bit",
            IrAlternation(
                IrSequence(IrItem(IrCharClass(IrRange(IrChr("0"), IrChr("1")))))
            ),
        ),
    ),
    "rulelist",
)
"""The ABNF grammar of ABNF (RFC 5234 §4 + B.1 subset) as a canonical
:class:`IrAst`.

Stored in canonical form (``canonicalize(ABNF_GRAMMAR) == ABNF_GRAMMAR``):
rule names fold lowercase, char classes are in normal form, and rules sit in
first-reference order from the start rule. See the module docstring for the
round-trip adaptations the RFC surface required."""


def _core(name: str, *arms: IrSequence | IrCharClass) -> IrTuple:
    """One prelude entry: ``(IrRuleRef(name), IrRule(name, ...))``."""
    return IrTuple(IrRuleRef(name), IrRule(name, IrAlternation(*arms)))


ABNF_CORE_RULES: IrMap = IrMap(
    _core(
        "alpha",
        IrCharClass(
            IrRange(IrChr(0x41), IrChr(0x5A)), IrRange(IrChr(0x61), IrChr(0x7A))
        ),
    ),
    _core("bit", IrCharClass(IrRange(IrChr(0x30), IrChr(0x31)))),
    _core("char", IrCharClass(IrRange(IrChr(0x01), IrChr(0x7F)))),
    _core("cr", IrCharClass(IrChr(0x0D))),
    _core("crlf", IrSequence(IrItem(IrRuleRef("cr")), IrItem(IrRuleRef("lf")))),
    _core("ctl", IrCharClass(IrRange(IrChr(0x00), IrChr(0x1F)), IrChr(0x7F))),
    _core("digit", IrCharClass(IrRange(IrChr(0x30), IrChr(0x39)))),
    _core("dquote", IrCharClass(IrChr(0x22))),
    _core(
        "hexdig",
        IrCharClass(
            IrRange(IrChr(0x30), IrChr(0x39)),
            IrRange(IrChr(0x41), IrChr(0x46)),
            IrRange(IrChr(0x61), IrChr(0x66)),
        ),
    ),
    _core("htab", IrCharClass(IrChr(0x09))),
    _core("lf", IrCharClass(IrChr(0x0A))),
    _core(
        "lwsp",
        IrSequence(
            IrItem(
                IrAlternation(
                    IrSequence(IrItem(IrRuleRef("wsp"))),
                    IrSequence(IrItem(IrRuleRef("crlf")), IrItem(IrRuleRef("wsp"))),
                ),
                IrQuantifier(0, IrNone),
            )
        ),
    ),
    _core("octet", IrCharClass(IrRange(IrChr(0x00), IrChr(0xFF)))),
    _core("sp", IrCharClass(IrChr(0x20))),
    _core("vchar", IrCharClass(IrRange(IrChr(0x21), IrChr(0x7E)))),
    _core("wsp", IrCharClass(IrChr(0x09), IrChr(0x20))),
)
"""The RFC 5234 B.1 core rules — the flavour's std-namespace prelude
(user ruling 2026-07-18: reserved slots, the flavour's ground truth).
Names lowercase (rulenames fold); bodies in canonical shape (merged char
classes; ``crlf``/``lwsp`` structural, closing over ``cr``/``lf``/``wsp``).
Injected by dangling-ref resolution only — see
:attr:`~lexic.ir.flavour.IrFlavour.core_rules`."""


# ── Cleaning policy: which child rules are noise ──────────────────────────

ABNF_NOISE: IrMap = IrMap(
    *(IrTuple(IrRuleRef(name), DROP) for name in ABNF_GRAMMAR.non_semantic),
    IrTuple(IR_DEFAULT, KEEP_REDUCED),
)
"""Child-contribution policy: non-semantic rules drop, every other rule is
reduced and kept. The reduce-side mirror of the emit ``IrMap`` tables."""


# ── Decode helpers: hex code points off args; joined decimal count ────────

_cp0 = IrPipe(IrArg(0), IrUnradix(16, IrChr))
"""The leading hex digit-run arg → an ``IrChr`` code point (num-range hi)."""
_dp0 = IrPipe(IrArg(0), IrUnradix(10, IrChr))
_bp0 = IrPipe(IrArg(0), IrUnradix(2, IrChr))
"""``%d``/``%b`` range-hi endpoints — the leading digit-run arg decoded in
base 10 / base 2."""
_hex_glyph = IrPipe(IrJoin(IrArgs()), IrPipe(IrUnradix(16, IrInt), IrGlyph()))
_dec_glyph = IrPipe(IrJoin(IrArgs()), IrPipe(IrUnradix(10, IrInt), IrGlyph()))
_bin_glyph = IrPipe(IrJoin(IrArgs()), IrPipe(IrUnradix(2, IrInt), IrGlyph()))
"""Joined digit-run args → the decoded character (num-seq glyph), per radix."""
_dec = IrPipe(IrJoin(IrArgs()), IrUnradix(10, IrInt))
"""Joined decimal digit-run args → an ``IrInt`` count."""

_R_MIRROR = IrStr("=")
"""``repeat-tail`` empty-arm marker: the ``N`` exact upper bound mirrors ``lo``."""

_R_LO = IrPipe(IrArg(0), IrUnradix(10, IrInt))
"""The digit-led ``repeat``'s leading ``1*DIGIT`` arg decoded to the lower bound."""

_R_HI = IrTypeMap(
    IrAction(IrInt, IrThis()),
    IrAction(IrNoneType, IrThis()),
    IrAction(IrStr, _R_LO),
)
"""``repeat-num`` tail marker → the upper bound: a decoded ``N*M`` bound or the
open ``N*`` ``IrNone`` rides through; the ``_R_MIRROR`` sentinel mirrors ``lo``."""

_x_glyph = IrPipe(IrArg(0), IrPipe(IrUnradix(16, IrInt), IrGlyph()))
"""The leading hex-run arg decoded to its glyph (a num-seq's first character)."""

_NUM_X = IrTypeMap(
    IrAction(IrNoneType, IrBuild(IrCharClass, IrTuple(_cp0))),
    IrAction(
        IrChr,
        IrBuild(IrCharClass, IrTuple(IrBuild(IrRange, IrTuple(_cp0, IrThis())))),
    ),
    IrAction(
        IrStr,
        IrBuild(IrLiteral, IrTuple(IrConcat(parts=IrTuple(_x_glyph, IrThis())))),
    ),
)
"""``%x`` tail marker → the num-val: empty (``IrNone``) → a single-point class,
an ``IrChr`` range hi → a range class, joined ``.``-glyphs → the num-seq literal."""

_d_glyph = IrPipe(IrArg(0), IrPipe(IrUnradix(10, IrInt), IrGlyph()))
_b_glyph = IrPipe(IrArg(0), IrPipe(IrUnradix(2, IrInt), IrGlyph()))
"""The leading digit-run arg decoded at radix 10 / 2 (a num-seq's first char)."""

_NUM_D = IrTypeMap(
    IrAction(IrNoneType, IrBuild(IrCharClass, IrTuple(_dp0))),
    IrAction(
        IrChr,
        IrBuild(IrCharClass, IrTuple(IrBuild(IrRange, IrTuple(_dp0, IrThis())))),
    ),
    IrAction(
        IrStr,
        IrBuild(IrLiteral, IrTuple(IrConcat(parts=IrTuple(_d_glyph, IrThis())))),
    ),
)
_NUM_B = IrTypeMap(
    IrAction(IrNoneType, IrBuild(IrCharClass, IrTuple(_bp0))),
    IrAction(
        IrChr,
        IrBuild(IrCharClass, IrTuple(IrBuild(IrRange, IrTuple(_bp0, IrThis())))),
    ),
    IrAction(
        IrStr,
        IrBuild(IrLiteral, IrTuple(IrConcat(parts=IrTuple(_b_glyph, IrThis())))),
    ),
)
"""``%d``/``%b`` tail markers → single-point / range classes, or — for a joined
dot-sequence (``IrStr``) — the num-seq literal, base 10 / 2."""

_CV_LIT = IrBuild(IrLiteral, IrTuple(IrJoin(IrArgs())))
"""All-non-alpha char-val body — one literal of the joined characters."""

# Case-insensitive char-val: each letter maps to a build-expression that
# constructs ``IrItem(IrCharClass(IrChr(lower), IrChr(upper)))`` — the RFC 7405
# expansion. The value is an ``IrBuild`` expression, not a pre-built node, so
# ``eval`` constructs it fresh (embedding a built node would re-eval and
# mangle IrChr).
_CV_CASE: IrMap[IrStr, IrSelf] = IrMap(
    *(
        IrTuple(
            IrStr(c),
            IrBuild(
                IrItem,
                IrTuple(
                    IrBuild(
                        IrCharClass,
                        IrTuple(
                            IrBuild(IrChr, IrTuple(IrStr(c.lower()))),
                            IrBuild(IrChr, IrTuple(IrStr(c.upper()))),
                        ),
                    )
                ),
            ),
        )
        for c in string.ascii_letters
    ),
    IrTuple(
        IR_DEFAULT,
        IrRaise(message="{dispatcher}: char-val case expansion of a non-letter"),
    ),
)
"""Letter → the per-char case-class item build-expression (RFC 7405)."""


# Dyads in an annotated tuple so each value widens to ``IrSelf`` (the invariant
# ``IrTuple`` would otherwise reject the heterogeneous bodies under ``IrMap``).
ABNF_REDUCTIONS: IrMap[IrRuleRef, IrSelf] = IrMap(
    # RFC 5234 §3.3 incremental (=/) arms extend an existing rule: both = and
    # =/ reduce to a plain IrRule, and IrMerge appends a re-seen name's arms
    # to the earlier rule. The start rule is the first name defined.
    IrTuple(IrRuleRef("rulelist"), IrMerge()),
    IrTuple(IrRuleRef("rl-cont"), IrArg(0)),
    IrTuple(IrRuleRef("rule"), IrBuild(IrRule)),
    IrTuple(IrRuleRef("alternation"), IrBuild(IrAlternation)),
    IrTuple(IrRuleRef("altrest"), IrArg(0)),
    IrTuple(IrRuleRef("concatenation"), IrBuild(IrSequence)),
    IrTuple(IrRuleRef("catrest"), IrArg(0)),
    IrTuple(IrRuleRef("repetition"), IrArg(0)),
    # rep-core: repeat-opt is child 0, element is child 1 → IrItem(atom, quant).
    IrTuple(IrRuleRef("rep-core"), IrBuild(IrItem, IrTuple(IrArg(1), IrArg(0)))),
    # option `[...]`: the inner alternation as an atom, bound to (0, 1).
    IrTuple(
        IrRuleRef("option"),
        IrBuild(
            IrItem,
            IrTuple(IrArg(0), IrBuild(IrQuantifier, IrTuple(IrInt(0), IrInt(1)))),
        ),
    ),
    # repeat-opt: present → forward the quantifier; empty → a built default (1,1).
    IrTuple(
        IrRuleRef("repeat-opt"),
        IrCond(
            test=IrArgs(),
            then_op=IrArg(0),
            else_op=IrBuild(IrQuantifier, IrTuple()),
        ),
    ),
    IrTuple(IrRuleRef("repeat"), IrArg(0)),
    IrTuple(
        IrRuleRef("repeat-num"),
        IrBuild(IrQuantifier, IrTuple(_R_LO, IrPipe(IrArg(1), _R_HI))),
    ),
    IrTuple(
        IrRuleRef("repeat-nolo"),
        IrBuild(IrQuantifier, IrTuple(IrInt(0), IrArg(0))),
    ),
    # present → forward the range hi (an IrInt bound or IrNone); empty → the
    # exact-form sentinel (the bound mirrors lo).
    IrTuple(
        IrRuleRef("repeat-tail"),
        IrCond(test=IrArgs(), then_op=IrArg(0), else_op=_R_MIRROR),
    ),
    # bounds own their own emptiness: IrArgs() is falsy when the rule matched empty.
    IrTuple(
        IrRuleRef("hi-bound"),
        IrCond(test=IrArgs(), then_op=_dec, else_op=IrNone),
    ),
    # digit-run rules: join the scattered single-char args into one string.
    IrTuple(IrRuleRef("decits"), IrJoin(IrArgs())),
    IrTuple(IrRuleRef("hexits"), IrJoin(IrArgs())),
    IrTuple(IrRuleRef("element"), IrArg(0)),
    IrTuple(IrRuleRef("group"), IrArg(0)),
    # RFC 7405 strings: `%s"..."` → a raw case-sensitive IrLiteral;
    # `%i"..."` → the char-val case-insensitive expansion, reused verbatim.
    IrTuple(IrRuleRef("cs-string"), IrArg(0)),
    IrTuple(IrRuleRef("ci-string"), IrArg(0)),
    IrTuple(IrRuleRef("csbody"), IrBuild(IrLiteral, IrTuple(IrJoin(IrArgs())))),
    # prose-val is recognised then refused — it has no formal semantics.
    IrTuple(
        IrRuleRef("prose"),
        IrRaise(message="{dispatcher}: ABNF prose-val has no formal semantics"),
    ),
    # Text rules — wrap the subtree text as the leaf type (quotes skipped).
    IrTuple(IrRuleRef("rulename"), IrBuild(IrRuleRef, IrTuple(YIELD))),
    # char-val (RFC 7405 case-insensitive): forward the body's reduction.
    IrTuple(IrRuleRef("char-val"), IrArg(0)),
    # The channel is the leading run's IrLiteral chars, then — when an alpha
    # made it the RFC 7405 expansion — the group's spliced case items. The last
    # arg's type picks the branch: an IrItem closes the expansion (leading
    # literals coerce to items under IrSequence), an IrLiteral joins into the
    # plain case-sensitive literal; an empty channel is the empty literal.
    IrTuple(
        IrRuleRef("cvbody"),
        IrCond(
            test=IrArgs(),
            then_op=IrPipe(
                IrArg(-1),
                IrTypeMap(
                    IrAction(
                        IrItem,
                        IrBuild(IrAlternation, IrTuple(IrBuild(IrSequence))),
                    ),
                    IrAction(IrLiteral, _CV_LIT),
                ),
            ),
            else_op=_CV_LIT,
        ),
    ),
    IrTuple(IrRuleRef("cvany"), IrArg(0)),
    # a letter → its case-class item; a non-letter → an IrLiteral item.
    IrTuple(IrRuleRef("cvalpha"), IrPipe(YIELD, _CV_CASE)),
    IrTuple(
        IrRuleRef("cvnai"),
        IrBuild(IrItem, IrTuple(IrBuild(IrLiteral, IrTuple(YIELD)))),
    ),
    IrTuple(IrRuleRef("cvnac"), IrBuild(IrLiteral, IrTuple(YIELD))),
    # num-val → IrCharClass over code points (IrChr endpoints), one branch
    # per radix (base 16 / 10 / 2); num-seq → a case-sensitive IrLiteral.
    IrTuple(IrRuleRef("num-val"), IrArg(0)),
    IrTuple(IrRuleRef("num-x"), IrPipe(IrArg(1), _NUM_X)),
    IrTuple(IrRuleRef("num-d"), IrPipe(IrArg(1), _NUM_D)),
    IrTuple(IrRuleRef("num-b"), IrPipe(IrArg(1), _NUM_B)),
    # tails: present → forward the range hi / seq glyphs; empty → IrNone (single).
    IrTuple(
        IrRuleRef("x-tail"),
        IrCond(test=IrArgs(), then_op=IrArg(0), else_op=IrNone),
    ),
    IrTuple(
        IrRuleRef("d-tail"),
        IrCond(test=IrArgs(), then_op=IrArg(0), else_op=IrNone),
    ),
    IrTuple(
        IrRuleRef("b-tail"),
        IrCond(test=IrArgs(), then_op=IrArg(0), else_op=IrNone),
    ),
    IrTuple(IrRuleRef("x-range"), _cp0),
    IrTuple(IrRuleRef("x-seq"), IrJoin(IrArgs())),
    IrTuple(IrRuleRef("d-range"), _dp0),
    IrTuple(IrRuleRef("d-seq"), IrJoin(IrArgs())),
    IrTuple(IrRuleRef("b-range"), _bp0),
    IrTuple(IrRuleRef("b-seq"), IrJoin(IrArgs())),
    IrTuple(IrRuleRef("hexdot"), IrArg(0)),
    IrTuple(IrRuleRef("hexglyph"), _hex_glyph),
    IrTuple(IrRuleRef("decdot"), IrArg(0)),
    IrTuple(IrRuleRef("decglyph"), _dec_glyph),
    IrTuple(IrRuleRef("bindot"), IrArg(0)),
    IrTuple(IrRuleRef("binglyph"), _bin_glyph),
    IrTuple(IR_DEFAULT, YIELD),
)
"""Per-rule reductions: parse tree → IR. Numeric rules decode their clean digit
runs with :class:`~lexic.ir.action.IrUnradix`; structural rules build from clean
``nc``; every char/terminal rule falls through ``IR_DEFAULT`` to :data:`YIELD`.
Paired with :data:`ABNF_NOISE`."""


ABNF_REDUCER = Reducer(reductions=ABNF_REDUCTIONS, noise=ABNF_NOISE, literal=DROP)
"""The configured ABNF reducer: ``ABNF_REDUCTIONS`` plus the cleaning policy."""


class _AbnfFlavour(IrFlavour):
    """ABNF flavour singleton class."""

    actions: IrTypeMap = ABNF_ACTIONS

    name: ClassVar[str] = "abnf"
    extensions: ClassVar[tuple[str, ...]] = (".abnf",)
    escapes: ClassVar[EscapeCodec] = ABNF_ESCAPES
    line_comment: ClassVar[str] = ";"
    grammar: ClassVar[IrAst] = ABNF_GRAMMAR
    reducer: ClassVar[Reducer] = ABNF_REDUCER
    core_rules: ClassVar[IrMap] = ABNF_CORE_RULES


ABNF_FLAVOUR = _AbnfFlavour()
"""Singleton ABNF flavour."""
