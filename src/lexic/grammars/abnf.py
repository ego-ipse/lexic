"""ABNF flavour for Lexic.

Bundles the escape codec, emit action tuple, and the native-IR self-grammar +
reducer in one module. :data:`ABNF_FLAVOUR` is the singleton
:class:`IrFlavour`/:class:`IrEmitter` consumed by
:func:`lexic.grammars.get_flavour`.

ABNF differs from GBNF in two key ways: prefix quantifier ordering on
:class:`IrItem` (the quantifier emits before the atom) and ``%xNN``-style
hex char-class rendering. ABNF has no native negated char classes — IrNot
raises.

:data:`ABNF_GRAMMAR` is the ABNF grammar of ABNF (RFC 5234 §4 + Appendix
B.1), authored directly as :class:`~lexic.ir.nodes.IrAst` — no construction
helpers, no Lark. Driven by :mod:`lexic.parsing` it parses ABNF source into
a derivation; the self-hosting fixpoint is
``parse(ABNF_GRAMMAR, abnf_source)`` reducing back to ``ABNF_GRAMMAR``.
:data:`ABNF_REDUCTIONS` is the "meta notation": an
:class:`~lexic.ir.mapping.IrMap` from each rule's
:class:`~lexic.ir.nodes.IrRuleRef` to a body that folds that rule's
parse-tree children into an IR node — the mirror of the emit table
``ABNF_ACTIONS`` (IR→text), pointed the other way (tree→IR).

**``ABNF_GRAMMAR`` is authored to round-trip through this flavour, not
byte-for-byte RFC.** Three deliberate adaptations so it survives
``emit → parse → reduce`` against ``ABNF_FLAVOUR``:

- *char classes are alternations of single ranges.* ``ABNF_FLAVOUR`` renders
  a multi-element :class:`~lexic.ir.nodes.IrCharClass` as a parenthesised
  group (``(%x41-5A / %x61-7A)``) but a single-element one as a bare ``%x``.
  So the RFC core rules that are alternations (``ALPHA``, ``HEXDIG``) are
  authored as alternations, and the structural class ``vchar-nq`` likewise —
  each arm a one-range class that emits bare and parses back identically.
- *control/quote core rules are num-vals.* ``HTAB``/``DQUOTE``/``CR``/``LF``
  are ``%x09``/``%x22``/``%x0D``/``%x0A`` (not char-vals), because
  ``char-val`` excludes those code points — a literal ``"\\t"`` could not be
  re-parsed.
- *line ending is ``[CR] LF``.* RFC's ``c-nl = comment / CRLF``; this subset
  omits comments and accepts a bare LF (the ``ABNF_FLAVOUR`` emitter joins
  rules with ``"\\n"``), with the optional CR keeping CRLF input parseable
  too.

The grammar covers the full RFC 5234 + 7405 surface: ``bin-val``/``dec-val``
alongside ``hex-val`` (single/range), value ``num-seq`` (``%x0D.0A``),
``option`` (``[...]``), incremental ``=/`` (arms merged into the earlier
same-named rule), ``%s``/``%i`` strings, ``prose-val`` (recognised then
refused), comments (leading, trailing, inline), and ``c-wsp`` line folding.
The constructs beyond the flavour's own emitted output leave the self-hosting
fixpoint unaffected — the grammar only *accepts* more. Radix and case markers
are lowercase only (``%x``/``%d``/``%b``/``%s``/``%i``; the emitter never
produces the uppercase forms). Rule names are hyphenated per RFC
(``char-val``, not ``char_val``); ``rulename`` admits ``ALPHA / DIGIT / "-"``.

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
from typing import ClassVar, cast

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
    IrEmit,
    IrField,
    IrGlyph,
    IrIsA,
    IrJoin,
    IrPipe,
    IrRaise,
    IrUnradix,
)
from lexic.ir.base import (
    IrChr,
    IrInt,
    IrLambda,
    IrNone,
    IrNoneType,
    IrSelf,
    IrSeq,
    IrStr,
    IrTuple,
)
from lexic.ir.escapes import EscapeCodec
from lexic.ir.flavour import IrEscape, IrFlavour
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
from lexic.parsing.reduce import DROP, KEEP_REDUCED, YIELD, Reducer


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

    One ``%xNN-MM`` per :class:`IrRange` element; one ``%xNN`` per single
    :class:`~lexic.ir.base.IrChr` code point; parenthesised alternation when
    more than one atom results.
    """
    rendered: list[str] = []
    for element in n:
        if isinstance(element, IrRange):
            rendered.append(f"%x{int(element.lo):02X}-{int(element.hi):02X}")
        else:
            rendered.append(f"%x{int(element):02X}")
    if len(rendered) == 1:
        return IrStr(rendered[0])
    return IrStr("(" + " / ".join(rendered) + ")")


ABNF_ACTIONS = IrTypeMap(
    IrAction(
        IrLiteral,
        IrConcat(parts=IrTuple(IrLiteral('"'), IrEscape(), IrLiteral('"'))),
    ),
    IrAction(IrCharClass, IrLambda(_abnf_charclass)),
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


# ── ABNF grammar as native IR + reducer ────────────────────────────────────
#
# The text→IR half of the flavour, with no Lark: ABNF_GRAMMAR is the ABNF
# grammar of ABNF authored directly as IrAst (see the module docstring for
# the round-trip adaptations); ABNF_REDUCTIONS is the reduce-side mirror of
# ABNF_ACTIONS above, folding a parse tree back into IR.

_CV_NA_BODY = IrAlternation(
    IrSequence(IrItem(IrCharClass(IrRange(IrChr(0x20), IrChr(0x21))))),
    IrSequence(IrItem(IrCharClass(IrRange(IrChr(0x23), IrChr(0x40))))),
    IrSequence(IrItem(IrCharClass(IrRange(IrChr(0x5B), IrChr(0x60))))),
    IrSequence(IrItem(IrCharClass(IrRange(IrChr(0x7B), IrChr(0x7E))))),
)
"""Printable char-val characters excluding ``"`` (0x22) and the letters
(0x41-5A, 0x61-7A) — the non-alpha units of a case-insensitive literal body.
Authored as an alternation of single-range classes (each emits a bare ``%x``
and round-trips) rather than one multi-range class (which ABNF renders as a
parenthesised group)."""

ABNF_GRAMMAR = IrAst(
    rules=IrSeq(
        # rulelist is any number of terminated rl-items followed by a final
        # rl-item whose rule may omit its line ending (a file need not end in a
        # newline — json.abnf does not). Only the last rule's terminator is
        # optional, so no internal rule/blank-line ambiguity arises.
        IrRule(
            "rulelist",
            IrAlternation(
                IrSequence(
                    IrItem(IrRuleRef("rl-item"), IrQuantifier(0, IrNone)),
                    IrItem(IrRuleRef("rl-final")),
                )
            ),
        ),
        # rl-item owns any comment/blank filler lines preceding a rule (RFC
        # 5234's `*c-wsp c-nl` filler); the filler drops, leaving the rule. A
        # filler line is a comment (starts ";") or blank (whitespace only); a
        # rule starts with a letter, so filler and rule never collide.
        IrRule(
            "rl-item",
            IrAlternation(
                IrSequence(
                    IrItem(IrRuleRef("filler"), IrQuantifier(0, IrNone)),
                    IrItem(IrRuleRef("rule")),
                )
            ),
        ),
        IrRule(
            "rl-final",
            IrAlternation(
                IrSequence(
                    IrItem(IrRuleRef("filler"), IrQuantifier(0, IrNone)),
                    IrItem(IrRuleRef("endrule")),
                )
            ),
        ),
        # endrule is `rule` with an optional terminator — the final rule of a
        # file may end at EOF instead of a line ending.
        IrRule(
            "endrule",
            IrAlternation(
                IrSequence(
                    IrItem(IrRuleRef("rulename")),
                    IrItem(IrRuleRef("c-wsp"), IrQuantifier(0, IrNone)),
                    IrItem(IrRuleRef("defined")),
                    IrItem(IrRuleRef("c-wsp"), IrQuantifier(0, IrNone)),
                    IrItem(IrRuleRef("alternation")),
                    IrItem(IrRuleRef("c-wsp"), IrQuantifier(0, IrNone)),
                    IrItem(IrRuleRef("c-nl"), IrQuantifier(0, 1)),
                )
            ),
        ),
        IrRule(
            "filler",
            IrAlternation(
                IrSequence(IrItem(IrRuleRef("comment"))),
                IrSequence(IrItem(IrRuleRef("blank"))),
            ),
            semantic=False,
        ),
        # A blank line: optional horizontal whitespace then a line ending.
        IrRule(
            "blank",
            IrAlternation(
                IrSequence(
                    IrItem(IrRuleRef("wsp"), IrQuantifier(0, IrNone)),
                    IrItem(IrRuleRef("crlf")),
                )
            ),
            semantic=False,
        ),
        # A comment runs from ";" to (and including) its line ending.
        IrRule(
            "comment",
            IrAlternation(
                IrSequence(
                    IrItem(IrLiteral(";")),
                    IrItem(IrRuleRef("cchar"), IrQuantifier(0, IrNone)),
                    IrItem(IrRuleRef("crlf")),
                )
            ),
            semantic=False,
        ),
        IrRule(
            "cchar",
            IrAlternation(
                IrSequence(IrItem(IrRuleRef("HTAB"))),
                IrSequence(IrItem(IrCharClass(IrRange(IrChr(0x20), IrChr(0x7E))))),
            ),
        ),
        # `defined` is `=` or the incremental `=/` (RFC 5234 §3.3). Both drop;
        # incremental arms are merged into the earlier same-named rule by the
        # rulelist reduction (same-name rules coalesce). The `=/` arm only
        # completes on `=/` (a bare `=` leaves a stray `/` no alternation can
        # start), so the two never ambiguate.
        IrRule(
            "defined",
            IrAlternation(
                IrSequence(IrItem(IrLiteral("="))),
                IrSequence(IrItem(IrLiteral("=/"))),
            ),
            semantic=False,
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
                    IrItem(IrRuleRef("c-wsp"), IrQuantifier(0, IrNone)),
                    IrItem(IrRuleRef("c-nl")),
                )
            ),
        ),
        IrRule(
            "rulename",
            IrAlternation(
                IrSequence(
                    IrItem(IrRuleRef("ALPHA")),
                    IrItem(IrRuleRef("namechar"), IrQuantifier(0, IrNone)),
                )
            ),
        ),
        IrRule(
            "namechar",
            IrAlternation(
                IrSequence(IrItem(IrRuleRef("ALPHA"))),
                IrSequence(IrItem(IrRuleRef("DIGIT"))),
                IrSequence(IrItem(IrLiteral("-"))),
            ),
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
            "catrest",
            IrAlternation(
                IrSequence(
                    IrItem(IrRuleRef("c-wsp"), IrQuantifier(1, IrNone)),
                    IrItem(IrRuleRef("repetition")),
                )
            ),
        ),
        # repetition is either a (possibly repeated) element or an option
        # `[...]` (RFC 5234's optional-sequence — an item bound to (0, 1)).
        IrRule(
            "repetition",
            IrAlternation(
                IrSequence(IrItem(IrRuleRef("rep-core"))),
                IrSequence(IrItem(IrRuleRef("option"))),
            ),
        ),
        IrRule(
            "rep-core",
            IrAlternation(
                IrSequence(
                    IrItem(IrRuleRef("repeat-opt")),
                    IrItem(IrRuleRef("element")),
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
            IrAlternation(IrSequence(IrItem(IrRuleRef("repeat"), IrQuantifier(0, 1)))),
        ),
        IrRule(
            "repeat",
            IrAlternation(
                IrSequence(IrItem(IrRuleRef("repeat-exact"))),
                IrSequence(IrItem(IrRuleRef("repeat-range"))),
            ),
        ),
        IrRule(
            "repeat-exact",
            IrAlternation(IrSequence(IrItem(IrRuleRef("decits")))),
        ),
        IrRule(
            "repeat-range",
            IrAlternation(
                IrSequence(
                    IrItem(IrRuleRef("lo-bound")),
                    IrItem(IrLiteral("*")),
                    IrItem(IrRuleRef("hi-bound")),
                )
            ),
        ),
        IrRule(
            "lo-bound",
            IrAlternation(IrSequence(IrItem(IrRuleRef("decits"), IrQuantifier(0, 1)))),
        ),
        IrRule(
            "hi-bound",
            IrAlternation(IrSequence(IrItem(IrRuleRef("decits"), IrQuantifier(0, 1)))),
        ),
        IrRule(
            "decits",
            IrAlternation(
                IrSequence(IrItem(IrRuleRef("DIGIT"), IrQuantifier(1, IrNone)))
            ),
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
            "char-val",
            IrAlternation(
                IrSequence(
                    IrItem(IrRuleRef("DQUOTE")),
                    IrItem(IrRuleRef("cvbody")),
                    IrItem(IrRuleRef("DQUOTE")),
                )
            ),
        ),
        # A char-val is case-insensitive (RFC 7405): a body with any letter
        # expands to an alternation of per-char classes; an all-non-alpha body
        # stays one literal. The two arms partition by content (≥1 alpha vs
        # none), pivoting on the FIRST alpha, so the parse is unambiguous.
        IrRule(
            "cvbody",
            IrAlternation(
                IrSequence(IrItem(IrRuleRef("cvexp"))),
                IrSequence(IrItem(IrRuleRef("cvlit"))),
            ),
        ),
        IrRule(
            "cvexp",
            IrAlternation(
                IrSequence(
                    IrItem(IrRuleRef("cvnai"), IrQuantifier(0, IrNone)),
                    IrItem(IrRuleRef("cvalpha")),
                    IrItem(IrRuleRef("cvany"), IrQuantifier(0, IrNone)),
                )
            ),
        ),
        IrRule(
            "cvlit",
            IrAlternation(
                IrSequence(IrItem(IrRuleRef("cvnac"), IrQuantifier(0, IrNone)))
            ),
        ),
        IrRule(
            "cvany",
            IrAlternation(
                IrSequence(IrItem(IrRuleRef("cvalpha"))),
                IrSequence(IrItem(IrRuleRef("cvnai"))),
            ),
        ),
        IrRule(
            "cvalpha",
            IrAlternation(IrSequence(IrItem(IrRuleRef("ALPHA")))),
        ),
        IrRule("cvnai", _CV_NA_BODY),
        IrRule("cvnac", _CV_NA_BODY),
        # RFC 7405 case-sensitive string `%s"..."`: a raw IrLiteral, no
        # case expansion. `smark` (the "s") drops; the quoted body's chars
        # join verbatim.
        IrRule(
            "cs-string",
            IrAlternation(
                IrSequence(
                    IrItem(IrLiteral("%")),
                    IrItem(IrRuleRef("smark")),
                    IrItem(IrRuleRef("DQUOTE")),
                    IrItem(IrRuleRef("csbody")),
                    IrItem(IrRuleRef("DQUOTE")),
                )
            ),
        ),
        # RFC 7405 case-insensitive string `%i"..."`: identical to a bare
        # char-val — `imark` (the "i") drops and the char-val body expands.
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
            "csbody",
            IrAlternation(
                IrSequence(IrItem(IrRuleRef("qchar"), IrQuantifier(0, IrNone)))
            ),
        ),
        # A quoted-string char (RFC 7405): any printable except `"` (0x22).
        # Authored as single-range arms so each emits a bare `%x` and
        # round-trips (see the module docstring's char-class adaptation).
        IrRule(
            "qchar",
            IrAlternation(
                IrSequence(IrItem(IrCharClass(IrRange(IrChr(0x20), IrChr(0x21))))),
                IrSequence(IrItem(IrCharClass(IrRange(IrChr(0x23), IrChr(0x7E))))),
            ),
        ),
        IrRule(
            "smark",
            IrAlternation(IrSequence(IrItem(IrCharClass(IrChr("s"))))),
            semantic=False,
        ),
        IrRule(
            "imark",
            IrAlternation(IrSequence(IrItem(IrCharClass(IrChr("i"))))),
            semantic=False,
        ),
        # prose-val `<...>` is recognised then rejected at reduce time: it has
        # no machine-readable meaning (RFC 5234 §4).
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
            "prose-char",
            IrAlternation(
                IrSequence(IrItem(IrCharClass(IrRange(IrChr(0x20), IrChr(0x3D))))),
                IrSequence(IrItem(IrCharClass(IrRange(IrChr(0x3F), IrChr(0x7E))))),
            ),
        ),
        IrRule(
            "num-val",
            IrAlternation(
                IrSequence(IrItem(IrRuleRef("num-single"))),
                IrSequence(IrItem(IrRuleRef("num-range"))),
                IrSequence(IrItem(IrRuleRef("num-seq"))),
                IrSequence(IrItem(IrRuleRef("dec-single"))),
                IrSequence(IrItem(IrRuleRef("dec-range"))),
                IrSequence(IrItem(IrRuleRef("bin-single"))),
                IrSequence(IrItem(IrRuleRef("bin-range"))),
            ),
        ),
        IrRule(
            "num-single",
            IrAlternation(
                IrSequence(
                    IrItem(IrLiteral("%")),
                    IrItem(IrRuleRef("xmark")),
                    IrItem(IrRuleRef("hexits")),
                )
            ),
        ),
        IrRule(
            "num-range",
            IrAlternation(
                IrSequence(
                    IrItem(IrLiteral("%")),
                    IrItem(IrRuleRef("xmark")),
                    IrItem(IrRuleRef("hexits")),
                    IrItem(IrLiteral("-")),
                    IrItem(IrRuleRef("hexits")),
                )
            ),
        ),
        # num-seq `%x0D.0A`: a dot-joined value sequence → a case-sensitive
        # IrLiteral of the decoded code points. Each dot-part decodes to one
        # glyph (`hexglyph`) and the parts join. The `.` requires ≥2 parts, so
        # it never collides with num-single/num-range.
        IrRule(
            "num-seq",
            IrAlternation(
                IrSequence(
                    IrItem(IrLiteral("%")),
                    IrItem(IrRuleRef("xmark")),
                    IrItem(IrRuleRef("hexglyph")),
                    IrItem(IrRuleRef("hexdot"), IrQuantifier(1, IrNone)),
                )
            ),
        ),
        IrRule(
            "hexdot",
            IrAlternation(
                IrSequence(IrItem(IrLiteral(".")), IrItem(IrRuleRef("hexglyph")))
            ),
        ),
        IrRule(
            "hexglyph",
            IrAlternation(
                IrSequence(IrItem(IrRuleRef("HEXDIG"), IrQuantifier(1, IrNone)))
            ),
        ),
        # dec-val / bin-val (RFC 5234): the digit run is `hexits` reused (Lark's
        # regex likewise admits any hex digit after the marker), and the base
        # 10 / 2 is applied in the reduction.
        IrRule(
            "dec-single",
            IrAlternation(
                IrSequence(
                    IrItem(IrLiteral("%")),
                    IrItem(IrRuleRef("dmark")),
                    IrItem(IrRuleRef("hexits")),
                )
            ),
        ),
        IrRule(
            "dec-range",
            IrAlternation(
                IrSequence(
                    IrItem(IrLiteral("%")),
                    IrItem(IrRuleRef("dmark")),
                    IrItem(IrRuleRef("hexits")),
                    IrItem(IrLiteral("-")),
                    IrItem(IrRuleRef("hexits")),
                )
            ),
        ),
        IrRule(
            "bin-single",
            IrAlternation(
                IrSequence(
                    IrItem(IrLiteral("%")),
                    IrItem(IrRuleRef("bmark")),
                    IrItem(IrRuleRef("hexits")),
                )
            ),
        ),
        IrRule(
            "bin-range",
            IrAlternation(
                IrSequence(
                    IrItem(IrLiteral("%")),
                    IrItem(IrRuleRef("bmark")),
                    IrItem(IrRuleRef("hexits")),
                    IrItem(IrLiteral("-")),
                    IrItem(IrRuleRef("hexits")),
                )
            ),
        ),
        IrRule(
            "xmark",
            IrAlternation(IrSequence(IrItem(IrCharClass(IrChr("x"))))),
            semantic=False,
        ),
        IrRule(
            "dmark",
            IrAlternation(IrSequence(IrItem(IrCharClass(IrChr("d"))))),
            semantic=False,
        ),
        IrRule(
            "bmark",
            IrAlternation(IrSequence(IrItem(IrCharClass(IrChr("b"))))),
            semantic=False,
        ),
        IrRule(
            "hexits",
            IrAlternation(
                IrSequence(IrItem(IrRuleRef("HEXDIG"), IrQuantifier(1, IrNone)))
            ),
        ),
        # Line ending and folding (RFC 5234 §4). c-nl is a comment or a bare
        # line ending; c-wsp is folding whitespace — plain horizontal space,
        # or a line ending followed by continuation indentation (which lets a
        # rule body span lines and carry trailing/inline comments).
        IrRule(
            "c-nl",
            IrAlternation(
                IrSequence(IrItem(IrRuleRef("comment"))),
                IrSequence(IrItem(IrRuleRef("crlf"))),
            ),
            semantic=False,
        ),
        IrRule(
            "crlf",
            IrAlternation(
                IrSequence(
                    IrItem(IrRuleRef("CR"), IrQuantifier(0, 1)),
                    IrItem(IrRuleRef("LF")),
                )
            ),
            semantic=False,
        ),
        IrRule(
            "c-wsp",
            IrAlternation(
                IrSequence(IrItem(IrRuleRef("wsp"))),
                IrSequence(
                    IrItem(
                        IrAlternation(
                            IrSequence(
                                IrItem(IrRuleRef("c-nl")), IrItem(IrRuleRef("wsp"))
                            )
                        )
                    )
                ),
            ),
            semantic=False,
        ),
        IrRule(
            "wsp",
            IrAlternation(
                IrSequence(IrItem(IrRuleRef("SP"))),
                IrSequence(IrItem(IrRuleRef("HTAB"))),
            ),
            semantic=False,
        ),
        IrRule(
            "ALPHA",
            IrAlternation(
                IrSequence(IrItem(IrCharClass(IrRange(IrChr("A"), IrChr("Z"))))),
                IrSequence(IrItem(IrCharClass(IrRange(IrChr("a"), IrChr("z"))))),
            ),
        ),
        IrRule(
            "DIGIT",
            IrAlternation(
                IrSequence(IrItem(IrCharClass(IrRange(IrChr("0"), IrChr("9")))))
            ),
        ),
        # HEXDIG admits lowercase a-f too (RFC 5234 is uppercase-only, but the
        # Lark path's regex — and real grammars, e.g. json.abnf's `%x66.61.6c`
        # — use either case; IrUnradix decodes both).
        IrRule(
            "HEXDIG",
            IrAlternation(
                IrSequence(IrItem(IrRuleRef("DIGIT"))),
                IrSequence(IrItem(IrCharClass(IrRange(IrChr("A"), IrChr("F"))))),
                IrSequence(IrItem(IrCharClass(IrRange(IrChr("a"), IrChr("f"))))),
            ),
        ),
        IrRule(
            "CR",
            IrAlternation(IrSequence(IrItem(IrCharClass(IrChr("\r"))))),
            semantic=False,
        ),
        IrRule(
            "LF",
            IrAlternation(IrSequence(IrItem(IrCharClass(IrChr("\n"))))),
            semantic=False,
        ),
        IrRule(
            "SP",
            IrAlternation(IrSequence(IrItem(IrCharClass(IrChr(" "))))),
            semantic=False,
        ),
        IrRule(
            "HTAB",
            IrAlternation(IrSequence(IrItem(IrCharClass(IrChr("\t"))))),
            semantic=False,
        ),
        IrRule(
            "DQUOTE",
            IrAlternation(IrSequence(IrItem(IrCharClass(IrChr('"'))))),
            semantic=False,
        ),
    ),
    start="rulelist",
    # Noise rules carry semantic=False on their own IrRule (see below):
    # whitespace and folding, line endings, comments/blank filler, the char-val
    # quote delimiter, and the radix/case markers (%x/%d/%b/%s/%i). That per-rule
    # flag is the single source of truth — ABNF_GRAMMAR.non_semantic (a derived
    # property) collects the names, drives ABNF_NOISE (below), and reaches
    # derive_specs and semantic_dump for user grammars via @non-semantic.
)
"""The ABNF grammar of ABNF (RFC 5234 §4 + B.1 subset) as a canonical :class:`IrAst`."""


# ── Cleaning policy: which child rules are noise ──────────────────────────

ABNF_NOISE: IrMap = IrMap(
    *(IrTuple(IrRuleRef(name), DROP) for name in ABNF_GRAMMAR.non_semantic),
    IrTuple(IR_DEFAULT, KEEP_REDUCED),
)
"""Child-contribution policy: non-semantic rules drop, every other rule is
reduced and kept. The reduce-side mirror of the emit ``IrMap`` tables."""


# ── Decode helpers: hex code points off args; joined decimal count ────────

_cp0 = IrPipe(IrArg(0), IrUnradix(16, IrChr))
"""First hex digit-run arg → an ``IrChr`` code point."""
_cp1 = IrPipe(IrArg(1), IrUnradix(16, IrChr))
"""Second hex digit-run arg → an ``IrChr`` code point."""
_dp0 = IrPipe(IrArg(0), IrUnradix(10, IrChr))
_dp1 = IrPipe(IrArg(1), IrUnradix(10, IrChr))
_bp0 = IrPipe(IrArg(0), IrUnradix(2, IrChr))
_bp1 = IrPipe(IrArg(1), IrUnradix(2, IrChr))
"""``%d``/``%b`` code-point endpoints — the same first/second digit-run args
decoded in base 10 / base 2."""
_hex_glyph = IrPipe(IrJoin(IrArgs()), IrPipe(IrUnradix(16, IrInt), IrGlyph()))
"""Joined hex digit-run args → the decoded character (num-seq glyph)."""
_dec = IrPipe(IrJoin(IrArgs()), IrUnradix(10, IrInt))
"""Joined decimal digit-run args → an ``IrInt`` count."""

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


def _merge_rules(_d: IrSelf, _n: IrSelf, nc: IrTuple) -> IrAst:
    """Fold the parsed rules into an :class:`IrAst`, merging same-named ones.

    RFC 5234 §3.3 incremental (``=/``) arms extend an existing rule; both ``=``
    and ``=/`` reduce to a plain :class:`IrRule`, so a rule whose name was
    already seen has its alternation arms appended to that earlier rule (the
    Lark path's ``_build_start`` merge, pointed the other way). The start rule
    is the first name defined.

    :param nc: the reduced rules, in source order.
    :returns: the assembled ``IrAst``.
    """
    merged: list[IrRule] = []
    position: dict[str, int] = {}
    for ruleobj in nc:
        rule = cast(IrRule, ruleobj)
        if rule.name in position:
            base = merged[position[rule.name]]
            merged[position[rule.name]] = IrRule(
                base.name, IrAlternation(*base.body, *rule.body)
            )
        else:
            position[rule.name] = len(merged)
            merged.append(rule)
    return IrAst(IrSeq(*merged), merged[0].name if merged else IrStr(""))


# Dyads in an annotated tuple so each value widens to ``IrSelf`` (the invariant
# ``IrTuple`` would otherwise reject the heterogeneous bodies under ``IrMap``).
ABNF_REDUCTIONS: IrMap[IrRuleRef, IrSelf] = IrMap(
    IrTuple(IrRuleRef("rulelist"), IrLambda(_merge_rules)),
    IrTuple(IrRuleRef("rl-item"), IrArg(0)),
    IrTuple(IrRuleRef("rl-final"), IrArg(0)),
    IrTuple(IrRuleRef("rule"), IrBuild(IrRule)),
    IrTuple(IrRuleRef("endrule"), IrBuild(IrRule)),
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
        IrRuleRef("repeat-exact"),
        IrBuild(
            IrQuantifier,
            IrTuple(
                IrPipe(IrArg(0), IrUnradix(10, IrInt)),
                IrPipe(IrArg(0), IrUnradix(10, IrInt)),
            ),
        ),
    ),
    IrTuple(
        IrRuleRef("repeat-range"),
        IrBuild(IrQuantifier, IrTuple(IrArg(0), IrArg(1))),
    ),
    # bounds own their own emptiness: IrArgs() is falsy when the rule matched empty.
    IrTuple(
        IrRuleRef("lo-bound"),
        IrCond(test=IrArgs(), then_op=_dec, else_op=IrInt(0)),
    ),
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
    IrTuple(IrRuleRef("cvbody"), IrArg(0)),
    # ≥1 letter → IrAlternation(IrSequence(per-char items)).
    IrTuple(
        IrRuleRef("cvexp"),
        IrBuild(IrAlternation, IrTuple(IrBuild(IrSequence))),
    ),
    # all non-alpha → one IrLiteral of the joined characters.
    IrTuple(IrRuleRef("cvlit"), IrBuild(IrLiteral, IrTuple(IrJoin(IrArgs())))),
    IrTuple(IrRuleRef("cvany"), IrArg(0)),
    # a letter → its case-class item; a non-letter → an IrLiteral item.
    IrTuple(IrRuleRef("cvalpha"), IrPipe(YIELD, _CV_CASE)),
    IrTuple(
        IrRuleRef("cvnai"),
        IrBuild(IrItem, IrTuple(IrBuild(IrLiteral, IrTuple(YIELD)))),
    ),
    IrTuple(IrRuleRef("cvnac"), YIELD),
    # num-val → IrCharClass over code points (IrChr endpoints), one branch
    # per radix (base 16 / 10 / 2); num-seq → a case-sensitive IrLiteral.
    IrTuple(IrRuleRef("num-val"), IrArg(0)),
    IrTuple(IrRuleRef("num-single"), IrBuild(IrCharClass, IrTuple(_cp0))),
    IrTuple(
        IrRuleRef("num-range"),
        IrBuild(IrCharClass, IrTuple(IrBuild(IrRange, IrTuple(_cp0, _cp1)))),
    ),
    IrTuple(IrRuleRef("dec-single"), IrBuild(IrCharClass, IrTuple(_dp0))),
    IrTuple(
        IrRuleRef("dec-range"),
        IrBuild(IrCharClass, IrTuple(IrBuild(IrRange, IrTuple(_dp0, _dp1)))),
    ),
    IrTuple(IrRuleRef("bin-single"), IrBuild(IrCharClass, IrTuple(_bp0))),
    IrTuple(
        IrRuleRef("bin-range"),
        IrBuild(IrCharClass, IrTuple(IrBuild(IrRange, IrTuple(_bp0, _bp1)))),
    ),
    IrTuple(IrRuleRef("num-seq"), IrBuild(IrLiteral, IrTuple(IrJoin(IrArgs())))),
    IrTuple(IrRuleRef("hexdot"), IrArg(0)),
    IrTuple(IrRuleRef("hexglyph"), _hex_glyph),
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


ABNF_FLAVOUR = _AbnfFlavour()
"""Singleton ABNF flavour."""
