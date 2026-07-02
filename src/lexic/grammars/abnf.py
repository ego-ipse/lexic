"""ABNF flavour for Lexic.

Bundles the escape codec, emit action tuple, and parse machinery (the Lark
meta-grammar, plus the native-IR self-grammar + reducer) in one module.
:data:`ABNF_FLAVOUR` is the singleton :class:`IrFlavour`/:class:`IrEmitter`
consumed by :func:`lexic.grammars.get_flavour`.

ABNF differs from GBNF in two key ways: prefix quantifier ordering on
:class:`IrItem` (the quantifier emits before the atom) and ``%xNN``-style
hex char-class rendering. ABNF has no native negated char classes — IrNot
raises.

:data:`ABNF_GRAMMAR` is the ABNF grammar of ABNF (RFC 5234 §4 + Appendix
B.1), authored directly as :class:`~lexic.ir.nodes.IrAst` — no construction
helpers, no Lark. Driven by :mod:`lexic.parsing_2` it parses ABNF source into
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

It is a subset: ``bin-val``/``dec-val``, ``prose-val``, ``option`` (``[...]``),
incremental ``=/``, comments, and ``c-wsp`` line-continuation are omitted —
none appear in the flavour's own emitted output, so none is needed for the
fixpoint. Rule names are hyphenated per RFC (``char-val``, not ``char_val``);
``rulename`` admits ``ALPHA / DIGIT / "-"`` only.

**Every reduction is pure ``IrSelf``.** Text rules (the character/terminal
rules) reduce with the shared :data:`YIELD`. Structural rules build typed
nodes from clean ``nc`` with :class:`~lexic.ir.action.IrBuild`. The numeric
rules decode their digit runs with :class:`~lexic.ir.action.IrUnradix` (the
inverse of the emit-side radix spelling) and build over code points — no
``parse_charclass`` / ``parse_quantifier`` call remains on the reduce side.

Explicit disable of duplicate-code. The end-goal is to have this file be
completely auto-generated.
"""

# pylint: disable=duplicate-code

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
    IrEmit,
    IrField,
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
from lexic.parsing_2.reduce import DROP, KEEP_REDUCED, YIELD, Reducer

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
                items.append(
                    IrItem(atom=IrCharClass(IrChr(c.lower()), IrChr(c.upper())))
                )
            else:
                items.append(IrItem(atom=IrLiteral(c)))
        return IrAlternation(IrSequence(*items))


ABNF_FLAVOUR = _AbnfFlavour()
"""Singleton ABNF flavour."""


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
        IrRule(
            "rulelist",
            IrAlternation(
                IrSequence(IrItem(IrRuleRef("rl-item"), IrQuantifier(1, IrNone)))
            ),
        ),
        # rl-item owns any comment/blank lines preceding a rule (RFC 5234's
        # `*c-wsp c-nl` filler); the comment lines drop, leaving the rule. A
        # comment line starts with ";" and a rule with a letter, so the two
        # never collide.
        IrRule(
            "rl-item",
            IrAlternation(
                IrSequence(
                    IrItem(IrRuleRef("comment-line"), IrQuantifier(0, IrNone)),
                    IrItem(IrRuleRef("rule")),
                )
            ),
        ),
        IrRule(
            "comment-line",
            IrAlternation(
                IrSequence(
                    IrItem(IrLiteral(";")),
                    IrItem(IrRuleRef("cchar"), IrQuantifier(0, IrNone)),
                    IrItem(IrRuleRef("c-nl")),
                )
            ),
        ),
        IrRule(
            "cchar",
            IrAlternation(
                IrSequence(IrItem(IrRuleRef("HTAB"))),
                IrSequence(IrItem(IrCharClass(IrRange(IrChr(0x20), IrChr(0x7E))))),
            ),
        ),
        IrRule(
            "rule",
            IrAlternation(
                IrSequence(
                    IrItem(IrRuleRef("rulename")),
                    IrItem(IrRuleRef("wsp"), IrQuantifier(0, IrNone)),
                    IrItem(IrLiteral("=")),
                    IrItem(IrRuleRef("wsp"), IrQuantifier(0, IrNone)),
                    IrItem(IrRuleRef("alternation")),
                    IrItem(IrRuleRef("wsp"), IrQuantifier(0, IrNone)),
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
                    IrItem(IrRuleRef("wsp"), IrQuantifier(0, IrNone)),
                    IrItem(IrLiteral("/")),
                    IrItem(IrRuleRef("wsp"), IrQuantifier(0, IrNone)),
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
                    IrItem(IrRuleRef("wsp"), IrQuantifier(1, IrNone)),
                    IrItem(IrRuleRef("repetition")),
                )
            ),
        ),
        IrRule(
            "repetition",
            IrAlternation(
                IrSequence(
                    IrItem(IrRuleRef("repeat-opt")),
                    IrItem(IrRuleRef("element")),
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
                IrSequence(IrItem(IrRuleRef("num-val"))),
                IrSequence(IrItem(IrRuleRef("group"))),
            ),
        ),
        IrRule(
            "group",
            IrAlternation(
                IrSequence(
                    IrItem(IrLiteral("(")),
                    IrItem(IrRuleRef("wsp"), IrQuantifier(0, IrNone)),
                    IrItem(IrRuleRef("alternation")),
                    IrItem(IrRuleRef("wsp"), IrQuantifier(0, IrNone)),
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
        IrRule(
            "num-val",
            IrAlternation(
                IrSequence(IrItem(IrRuleRef("num-single"))),
                IrSequence(IrItem(IrRuleRef("num-range"))),
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
        IrRule(
            "xmark",
            IrAlternation(IrSequence(IrItem(IrCharClass(IrChr("x"))))),
        ),
        IrRule(
            "hexits",
            IrAlternation(
                IrSequence(IrItem(IrRuleRef("HEXDIG"), IrQuantifier(1, IrNone)))
            ),
        ),
        IrRule(
            "c-nl",
            IrAlternation(
                IrSequence(
                    IrItem(IrRuleRef("CR"), IrQuantifier(0, 1)),
                    IrItem(IrRuleRef("LF")),
                )
            ),
        ),
        IrRule(
            "wsp",
            IrAlternation(
                IrSequence(IrItem(IrRuleRef("SP"))),
                IrSequence(IrItem(IrRuleRef("HTAB"))),
            ),
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
        IrRule(
            "HEXDIG",
            IrAlternation(
                IrSequence(IrItem(IrRuleRef("DIGIT"))),
                IrSequence(IrItem(IrCharClass(IrRange(IrChr("A"), IrChr("F"))))),
            ),
        ),
        IrRule("CR", IrAlternation(IrSequence(IrItem(IrCharClass(IrChr("\r")))))),
        IrRule("LF", IrAlternation(IrSequence(IrItem(IrCharClass(IrChr("\n")))))),
        IrRule("SP", IrAlternation(IrSequence(IrItem(IrCharClass(IrChr(" ")))))),
        IrRule("HTAB", IrAlternation(IrSequence(IrItem(IrCharClass(IrChr("\t")))))),
        IrRule("DQUOTE", IrAlternation(IrSequence(IrItem(IrCharClass(IrChr('"')))))),
    ),
    start="rulelist",
)
"""The ABNF grammar of ABNF (RFC 5234 §4 + B.1 subset) as a canonical :class:`IrAst`."""


# ── Cleaning policy: which child rules are noise ──────────────────────────

_NON_SEMANTIC = (
    "wsp",
    "SP",
    "HTAB",
    "c-nl",
    "CR",
    "LF",
    "DQUOTE",
    "xmark",
    "comment-line",
)
"""Whitespace, line endings, the char-val quote delimiter, the ``%x`` radix
marker, and comment lines. Dropped from a structural rule's children and
skipped by :data:`~lexic.parsing_2.reduce.YIELD`."""

ABNF_NOISE: IrMap = IrMap(
    *(IrTuple(IrRuleRef(name), DROP) for name in _NON_SEMANTIC),
    IrTuple(IR_DEFAULT, KEEP_REDUCED),
)
"""Child-contribution policy: non-semantic rules drop, every other rule is
reduced and kept. The reduce-side mirror of the emit ``IrMap`` tables."""


# ── Decode helpers: hex code points off args; joined decimal count ────────

_cp0 = IrPipe(IrArg(0), IrUnradix(16, IrChr))
"""First hex digit-run arg → an ``IrChr`` code point."""
_cp1 = IrPipe(IrArg(1), IrUnradix(16, IrChr))
"""Second hex digit-run arg → an ``IrChr`` code point."""
_dec = IrPipe(IrJoin(IrArgs()), IrUnradix(10, IrInt))
"""Joined decimal digit-run args → an ``IrInt`` count."""

# Case-insensitive char-val: each letter maps to a build-expression that
# constructs ``IrItem(IrCharClass(IrChr(lower), IrChr(upper)))`` — the RFC 7405
# expansion, exactly as the Lark path's ``normalize_literal`` produces. The
# value is an ``IrBuild`` expression, not a pre-built node, so ``eval``
# constructs it fresh (embedding a built node would re-eval and mangle IrChr).
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
    IrTuple(
        IrRuleRef("rulelist"),
        IrBuild(IrAst, IrTuple(IrBuild(IrSeq), IrPipe(IrArg(0), IrField("name")))),
    ),
    IrTuple(IrRuleRef("rl-item"), IrArg(0)),
    IrTuple(IrRuleRef("rule"), IrBuild(IrRule)),
    IrTuple(IrRuleRef("alternation"), IrBuild(IrAlternation)),
    IrTuple(IrRuleRef("altrest"), IrArg(0)),
    IrTuple(IrRuleRef("concatenation"), IrBuild(IrSequence)),
    IrTuple(IrRuleRef("catrest"), IrArg(0)),
    # repetition: repeat-opt is child 0, element is child 1 → IrItem(atom, quant).
    IrTuple(IrRuleRef("repetition"), IrBuild(IrItem, IrTuple(IrArg(1), IrArg(0)))),
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
    # num-val → IrCharClass over code points (IrChr endpoints).
    IrTuple(IrRuleRef("num-val"), IrArg(0)),
    IrTuple(IrRuleRef("num-single"), IrBuild(IrCharClass, IrTuple(_cp0))),
    IrTuple(
        IrRuleRef("num-range"),
        IrBuild(IrCharClass, IrTuple(IrBuild(IrRange, IrTuple(_cp0, _cp1)))),
    ),
    IrTuple(IR_DEFAULT, YIELD),
)
"""Per-rule reductions: parse tree → IR. Numeric rules decode their clean digit
runs with :class:`~lexic.ir.action.IrUnradix`; structural rules build from clean
``nc``; every char/terminal rule falls through ``IR_DEFAULT`` to :data:`YIELD`.
Paired with :data:`ABNF_NOISE`."""


ABNF_REDUCER = Reducer(reductions=ABNF_REDUCTIONS, noise=ABNF_NOISE, literal=DROP)
"""The configured ABNF reducer: ``ABNF_REDUCTIONS`` plus the cleaning policy."""
