"""GBNF flavour for Lexic.

Bundles the escape codec, emit action tuple, and the IR-native self-grammar +
reducer in one module. :data:`GBNF_FLAVOUR` is the singleton
:class:`IrFlavour`/:class:`IrEmitter` consumed by
:func:`lexic.grammars.get_flavour`; :data:`GBNF_GRAMMAR`/:data:`GBNF_REDUCER`
are the text→IR half driven by :mod:`lexic.parsing`.

Explicit disable of duplicate-code and too-many-lines. The end-goal is to have
this file be completely auto-generated.
"""

# pylint: disable=duplicate-code
# pylint: disable=too-many-lines

from __future__ import annotations

from typing import ClassVar

from lexic.ir.action import (
    IrAction,
    IrApply,
    IrArg,
    IrArgs,
    IrAt,
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
from lexic.ir.base import IrInt, IrNone, IrNoneType, IrSelf, IrSeq, IrStr, IrTuple
from lexic.ir.escapes import EscapeCodec
from lexic.ir.flavour import IrEscape, IrFlavour
from lexic.ir.mapping import IR_DEFAULT, IrMap, IrTypeMap
from lexic.ir.nodes import (
    IrAlternation,
    IrAst,
    IrCharClass,
    IrChr,
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
:class:`IrCond` over the ``lo``/``hi`` bounds. The GBNF reducer decodes the
same forms the other way (digit runs via :class:`IrUnradix`).
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


# ── GBNF grammar as native IR + reducer ────────────────────────────────────
#
# Authored like the ABNF block in abnf.py: fully explicit IrAst, no
# construction helpers. Pinned by tests/integration/test_gbnf_ir_equivalence.py
# (golden shapes + invariants over the seven resources/ground_truth grammars).
# Design notes:
# - Maximal munch is engineered structurally (no lexer to grant it for free):
#   adjacent items need real noise unless the next atom is non-name
#   (seq-rest), inter-rule noise is REQUIRED (rules-rest), and a bare '-' in a
#   class is positional (leading / trailing / range-hi only).
# - Leading-noise discipline: "::=" and "|" own only their own leading
#   noise; first-item owns each arm's; empty arms (empty-seq, an epsilon
#   rule) own none — that is what keeps nullable arms unambiguous.
# - Escapes decode structurally per R2: one grammar rule per escape kind,
#   reduced by constants or IrUnradix — no codec call on the reduce side.
# - A bare IrChr constant self-renders on eval (emit-time spelling), so
#   constant units are wrapped IrBuild(IrChr, IrTuple(IrStr(...))).

GBNF_GRAMMAR = IrAst(
    rules=IrSeq(
        # grammar: leading noise, rules separated by REQUIRED noise (a rule
        # ending in a name abutting the next rule's name would otherwise
        # re-segment the boundary — Lark's lexer made names maximal-munch),
        # optional trailing noise, optional unterminated EOF comment
        # (comment-line requires "\n"; tail-comment covers EOF).
        IrRule(
            "grammar",
            IrAlternation(
                IrSequence(
                    IrItem(IrRuleRef("n"), IrQuantifier(0, 1)),
                    IrItem(IrRuleRef("rule")),
                    IrItem(IrRuleRef("rules-rest"), IrQuantifier(0, IrNone)),
                    IrItem(IrRuleRef("n"), IrQuantifier(0, 1)),
                    IrItem(IrRuleRef("tail-comment"), IrQuantifier(0, 1)),
                )
            ),
        ),
        IrRule(
            "rules-rest",
            IrAlternation(
                IrSequence(IrItem(IrRuleRef("n")), IrItem(IrRuleRef("rule")))
            ),
        ),
        # rule: name ::= alternation; no noise slot after "::=" (the first
        # arm's first-item owns it) and none trailing (the grammar level owns
        # separation).
        IrRule(
            "rule",
            IrAlternation(
                IrSequence(
                    IrItem(IrRuleRef("rulename")),
                    IrItem(IrRuleRef("n"), IrQuantifier(0, 1)),
                    IrItem(IrLiteral("::=")),
                    IrItem(IrRuleRef("alternation")),
                )
            ),
        ),
        IrRule(
            "rulename",
            IrAlternation(
                IrSequence(
                    IrItem(IrRuleRef("namehead")),
                    IrItem(IrRuleRef("namechar"), IrQuantifier(0, IrNone)),
                )
            ),
        ),
        IrRule(
            "namehead",
            IrAlternation(
                IrSequence(
                    IrItem(
                        IrCharClass(
                            IrRange(IrChr("a"), IrChr("z")),
                            IrRange(IrChr("A"), IrChr("Z")),
                            IrChr("_"),
                        )
                    )
                )
            ),
        ),
        IrRule(
            "namechar",
            IrAlternation(
                IrSequence(
                    IrItem(
                        IrCharClass(
                            IrRange(IrChr("a"), IrChr("z")),
                            IrRange(IrChr("A"), IrChr("Z")),
                            IrRange(IrChr("0"), IrChr("9")),
                            IrChr("_"),
                            IrChr("-"),
                        )
                    )
                )
            ),
        ),
        IrRule(
            "alternation",
            IrAlternation(
                IrSequence(
                    IrItem(IrRuleRef("arm")),
                    IrItem(IrRuleRef("bar-arm"), IrQuantifier(0, IrNone)),
                )
            ),
        ),
        # An arm is a sequence or empty (GBNF allows `ws ::= | " " | ...`).
        # empty-seq owns no characters and no noise slots, which keeps
        # nullable arms from creating adjacent optional-noise ambiguity.
        IrRule(
            "arm",
            IrAlternation(
                IrSequence(IrItem(IrRuleRef("sequence"))),
                IrSequence(IrItem(IrRuleRef("empty-seq"))),
            ),
        ),
        IrRule("empty-seq", IrAlternation(IrSequence())),
        IrRule(
            "bar-arm",
            IrAlternation(
                IrSequence(
                    IrItem(IrRuleRef("n"), IrQuantifier(0, 1)),
                    IrItem(IrLiteral("|")),
                    IrItem(IrRuleRef("arm")),
                )
            ),
        ),
        # first-item owns the arm's leading noise (leading-noise discipline:
        # the "::=" / "|" tokens own only their own leading noise).
        IrRule(
            "sequence",
            IrAlternation(
                IrSequence(
                    IrItem(IrRuleRef("first-item")),
                    IrItem(IrRuleRef("seq-rest"), IrQuantifier(0, IrNone)),
                )
            ),
        ),
        IrRule(
            "first-item",
            IrAlternation(
                IrSequence(
                    IrItem(IrRuleRef("n"), IrQuantifier(0, 1)),
                    IrItem(IrRuleRef("item")),
                )
            ),
        ),
        # A following item either comes after real noise, or starts with a
        # non-name atom — bare name-after-name without separation would
        # re-segment what Lark's lexer read as ONE maximal-munch NAME.
        IrRule(
            "seq-rest",
            IrAlternation(
                IrSequence(IrItem(IrRuleRef("n")), IrItem(IrRuleRef("item"))),
                IrSequence(IrItem(IrRuleRef("item-nonname"))),
            ),
        ),
        IrRule(
            "item",
            IrAlternation(
                IrSequence(IrItem(IrRuleRef("atom")), IrItem(IrRuleRef("quant-opt")))
            ),
        ),
        IrRule(
            "item-nonname",
            IrAlternation(
                IrSequence(
                    IrItem(IrRuleRef("atom-nonname")), IrItem(IrRuleRef("quant-opt"))
                )
            ),
        ),
        IrRule(
            "atom-nonname",
            IrAlternation(
                IrSequence(IrItem(IrRuleRef("literal"))),
                IrSequence(IrItem(IrRuleRef("charclass"))),
                IrSequence(IrItem(IrRuleRef("group"))),
            ),
        ),
        # quant-opt/ws-quant: optional quantifier, possibly noise-separated
        # from its atom (Lark %ignore allowed `atom ?`).
        IrRule(
            "quant-opt",
            IrAlternation(
                IrSequence(IrItem(IrRuleRef("ws-quant"), IrQuantifier(0, 1)))
            ),
        ),
        IrRule(
            "ws-quant",
            IrAlternation(
                IrSequence(
                    IrItem(IrRuleRef("n"), IrQuantifier(0, 1)),
                    IrItem(IrRuleRef("quantifier")),
                )
            ),
        ),
        IrRule(
            "atom",
            IrAlternation(
                IrSequence(IrItem(IrRuleRef("literal"))),
                IrSequence(IrItem(IrRuleRef("charclass"))),
                IrSequence(IrItem(IrRuleRef("rulename"))),
                IrSequence(IrItem(IrRuleRef("group"))),
            ),
        ),
        IrRule(
            "group",
            IrAlternation(
                IrSequence(
                    IrItem(IrLiteral("(")),
                    IrItem(IrRuleRef("alternation")),
                    IrItem(IrRuleRef("n"), IrQuantifier(0, 1)),
                    IrItem(IrLiteral(")")),
                )
            ),
        ),
        # ── quantifiers ────────────────────────────────────────────────
        IrRule(
            "quantifier",
            IrAlternation(
                IrSequence(IrItem(IrRuleRef("q-opt"))),
                IrSequence(IrItem(IrRuleRef("q-star"))),
                IrSequence(IrItem(IrRuleRef("q-plus"))),
                IrSequence(IrItem(IrRuleRef("q-exact"))),
                IrSequence(IrItem(IrRuleRef("q-atleast"))),
                IrSequence(IrItem(IrRuleRef("q-between"))),
            ),
        ),
        IrRule("q-opt", IrAlternation(IrSequence(IrItem(IrLiteral("?"))))),
        IrRule("q-star", IrAlternation(IrSequence(IrItem(IrLiteral("*"))))),
        IrRule("q-plus", IrAlternation(IrSequence(IrItem(IrLiteral("+"))))),
        IrRule(
            "q-exact",
            IrAlternation(
                IrSequence(
                    IrItem(IrLiteral("{")),
                    IrItem(IrRuleRef("decits")),
                    IrItem(IrLiteral("}")),
                )
            ),
        ),
        IrRule(
            "q-atleast",
            IrAlternation(
                IrSequence(
                    IrItem(IrLiteral("{")),
                    IrItem(IrRuleRef("decits")),
                    IrItem(IrLiteral(",")),
                    IrItem(IrLiteral("}")),
                )
            ),
        ),
        IrRule(
            "q-between",
            IrAlternation(
                IrSequence(
                    IrItem(IrLiteral("{")),
                    IrItem(IrRuleRef("decits")),
                    IrItem(IrLiteral(",")),
                    IrItem(IrRuleRef("decits")),
                    IrItem(IrLiteral("}")),
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
            "digit",
            IrAlternation(
                IrSequence(IrItem(IrCharClass(IrRange(IrChr("0"), IrChr("9")))))
            ),
        ),
        # ── literals: '"' lunit* '"', escapes distinguished structurally ──
        IrRule(
            "literal",
            IrAlternation(
                IrSequence(
                    IrItem(IrLiteral('"')),
                    IrItem(IrRuleRef("lunit"), IrQuantifier(0, IrNone)),
                    IrItem(IrLiteral('"')),
                )
            ),
        ),
        IrRule(
            "lunit",
            IrAlternation(
                IrSequence(IrItem(IrRuleRef("lplain"))),
                IrSequence(IrItem(IrRuleRef("lesc-short"))),
                IrSequence(IrItem(IrRuleRef("lesc-hex"))),
                IrSequence(IrItem(IrRuleRef("lesc-other"))),
            ),
        ),
        IrRule(
            "lplain",
            IrAlternation(
                IrSequence(IrItem(IrNot(IrCharClass(IrChr('"'), IrChr("\\")))))
            ),
        ),
        IrRule(
            "lesc-short",
            IrAlternation(
                IrSequence(IrItem(IrRuleRef("lesc-n"))),
                IrSequence(IrItem(IrRuleRef("lesc-t"))),
                IrSequence(IrItem(IrRuleRef("lesc-r"))),
                IrSequence(IrItem(IrRuleRef("lesc-dq"))),
                IrSequence(IrItem(IrRuleRef("lesc-bs"))),
            ),
        ),
        IrRule("lesc-n", IrAlternation(IrSequence(IrItem(IrLiteral("\\n"))))),
        IrRule("lesc-t", IrAlternation(IrSequence(IrItem(IrLiteral("\\t"))))),
        IrRule("lesc-r", IrAlternation(IrSequence(IrItem(IrLiteral("\\r"))))),
        IrRule("lesc-dq", IrAlternation(IrSequence(IrItem(IrLiteral('\\"'))))),
        IrRule("lesc-bs", IrAlternation(IrSequence(IrItem(IrLiteral("\\\\"))))),
        IrRule(
            "lesc-hex",
            IrAlternation(
                IrSequence(IrItem(IrRuleRef("hex2"))),
                IrSequence(IrItem(IrRuleRef("hex4"))),
                IrSequence(IrItem(IrRuleRef("hex8"))),
            ),
        ),
        IrRule(
            "hex2",
            IrAlternation(
                IrSequence(
                    IrItem(IrLiteral("\\x")),
                    IrItem(IrRuleRef("hexch")),
                    IrItem(IrRuleRef("hexch")),
                )
            ),
        ),
        IrRule(
            "hex4",
            IrAlternation(
                IrSequence(
                    IrItem(IrLiteral("\\u")),
                    IrItem(IrRuleRef("hexch")),
                    IrItem(IrRuleRef("hexch")),
                    IrItem(IrRuleRef("hexch")),
                    IrItem(IrRuleRef("hexch")),
                )
            ),
        ),
        IrRule(
            "hex8",
            IrAlternation(
                IrSequence(
                    IrItem(IrLiteral("\\U")),
                    IrItem(IrRuleRef("hexch")),
                    IrItem(IrRuleRef("hexch")),
                    IrItem(IrRuleRef("hexch")),
                    IrItem(IrRuleRef("hexch")),
                    IrItem(IrRuleRef("hexch")),
                    IrItem(IrRuleRef("hexch")),
                    IrItem(IrRuleRef("hexch")),
                    IrItem(IrRuleRef("hexch")),
                )
            ),
        ),
        IrRule(
            "hexch",
            IrAlternation(
                IrSequence(
                    IrItem(
                        IrCharClass(
                            IrRange(IrChr("0"), IrChr("9")),
                            IrRange(IrChr("a"), IrChr("f")),
                            IrRange(IrChr("A"), IrChr("F")),
                        )
                    )
                )
            ),
        ),
        # unknown escape in a literal: GBNF_ESCAPES.decode keeps it verbatim
        # (backslash retained). Excludes short chars, hex tags, and newline.
        IrRule(
            "lesc-other",
            IrAlternation(
                IrSequence(IrItem(IrLiteral("\\")), IrItem(IrRuleRef("lother")))
            ),
        ),
        IrRule(
            "lother",
            IrAlternation(
                IrSequence(
                    IrItem(
                        IrNot(
                            IrCharClass(
                                IrChr("n"),
                                IrChr("t"),
                                IrChr("r"),
                                IrChr('"'),
                                IrChr("\\"),
                                IrChr("x"),
                                IrChr("u"),
                                IrChr("U"),
                                IrChr("\n"),
                            )
                        )
                    )
                )
            ),
        ),
        # ── charclasses: [...] / [^...]; units via CANONICAL escapes ─────
        # Bare '-' is positional (the linear scan's semantics): legal leading
        # (cc-first/cc-nfirst), trailing (the optional cc-dash before "]"),
        # or as a range's hi — never as a free interior item, which would
        # make every range ambiguous against unit-dash-unit.
        IrRule(
            "charclass",
            IrAlternation(
                IrSequence(IrItem(IrRuleRef("cc-pos"))),
                IrSequence(IrItem(IrRuleRef("cc-neg"))),
            ),
        ),
        IrRule(
            "cc-pos",
            IrAlternation(
                IrSequence(
                    IrItem(IrLiteral("[")),
                    IrItem(IrRuleRef("cc-first")),
                    IrItem(IrRuleRef("cc-item"), IrQuantifier(0, IrNone)),
                    IrItem(IrRuleRef("cc-dash"), IrQuantifier(0, 1)),
                    IrItem(IrLiteral("]")),
                ),
                IrSequence(IrItem(IrLiteral("[")), IrItem(IrLiteral("]"))),
            ),
        ),
        IrRule(
            "cc-neg",
            IrAlternation(
                IrSequence(
                    IrItem(IrLiteral("[^")),
                    IrItem(IrRuleRef("cc-nfirst")),
                    IrItem(IrRuleRef("cc-item"), IrQuantifier(0, IrNone)),
                    IrItem(IrRuleRef("cc-dash"), IrQuantifier(0, 1)),
                    IrItem(IrLiteral("]")),
                ),
                IrSequence(IrItem(IrLiteral("[^")), IrItem(IrLiteral("]"))),
            ),
        ),
        # first item of a positive class must not be a bare '^' (that spelling
        # is the negation marker); escaped or later '^' is an ordinary unit.
        IrRule(
            "cc-first",
            IrAlternation(
                IrSequence(IrItem(IrRuleRef("cc-range-nc"))),
                IrSequence(IrItem(IrRuleRef("cc-unit-nc"))),
                IrSequence(IrItem(IrRuleRef("cc-dash"))),
            ),
        ),
        IrRule(
            "cc-nfirst",
            IrAlternation(
                IrSequence(IrItem(IrRuleRef("cc-range"))),
                IrSequence(IrItem(IrRuleRef("cc-unit"))),
                IrSequence(IrItem(IrRuleRef("cc-dash"))),
            ),
        ),
        IrRule(
            "cc-item",
            IrAlternation(
                IrSequence(IrItem(IrRuleRef("cc-range"))),
                IrSequence(IrItem(IrRuleRef("cc-unit"))),
            ),
        ),
        # ranges: lo may not be a bare dash (corpus never leads a range with
        # '-' or '^'); hi may be.
        IrRule(
            "cc-range",
            IrAlternation(
                IrSequence(
                    IrItem(IrRuleRef("cc-unit")),
                    IrItem(IrLiteral("-")),
                    IrItem(IrRuleRef("cc-hi")),
                )
            ),
        ),
        IrRule(
            "cc-range-nc",
            IrAlternation(
                IrSequence(
                    IrItem(IrRuleRef("cc-unit-nc")),
                    IrItem(IrLiteral("-")),
                    IrItem(IrRuleRef("cc-hi")),
                )
            ),
        ),
        IrRule(
            "cc-hi",
            IrAlternation(
                IrSequence(IrItem(IrRuleRef("cc-unit"))),
                IrSequence(IrItem(IrRuleRef("cc-dash"))),
            ),
        ),
        IrRule("cc-dash", IrAlternation(IrSequence(IrItem(IrLiteral("-"))))),
        IrRule(
            "cc-unit",
            IrAlternation(
                IrSequence(IrItem(IrRuleRef("cc-plain"))),
                IrSequence(IrItem(IrRuleRef("cc-esc"))),
            ),
        ),
        IrRule(
            "cc-unit-nc",
            IrAlternation(
                IrSequence(IrItem(IrRuleRef("cc-plain-nc"))),
                IrSequence(IrItem(IrRuleRef("cc-esc"))),
            ),
        ),
        IrRule(
            "cc-plain",
            IrAlternation(
                IrSequence(
                    IrItem(IrNot(IrCharClass(IrChr("]"), IrChr("\\"), IrChr("-"))))
                )
            ),
        ),
        IrRule(
            "cc-plain-nc",
            IrAlternation(
                IrSequence(
                    IrItem(
                        IrNot(
                            IrCharClass(IrChr("]"), IrChr("\\"), IrChr("-"), IrChr("^"))
                        )
                    )
                )
            ),
        ),
        IrRule(
            "cc-esc",
            IrAlternation(
                IrSequence(IrItem(IrRuleRef("cc-esc-short"))),
                IrSequence(IrItem(IrRuleRef("cc-esc-hex"))),
                IrSequence(IrItem(IrRuleRef("cc-esc-other"))),
            ),
        ),
        IrRule(
            "cc-esc-short",
            IrAlternation(
                IrSequence(IrItem(IrRuleRef("ccesc-n"))),
                IrSequence(IrItem(IrRuleRef("ccesc-t"))),
                IrSequence(IrItem(IrRuleRef("ccesc-r"))),
                IrSequence(IrItem(IrRuleRef("ccesc-bs"))),
                IrSequence(IrItem(IrRuleRef("ccesc-rb"))),
                IrSequence(IrItem(IrRuleRef("ccesc-dash"))),
                IrSequence(IrItem(IrRuleRef("ccesc-caret"))),
            ),
        ),
        IrRule("ccesc-n", IrAlternation(IrSequence(IrItem(IrLiteral("\\n"))))),
        IrRule("ccesc-t", IrAlternation(IrSequence(IrItem(IrLiteral("\\t"))))),
        IrRule("ccesc-r", IrAlternation(IrSequence(IrItem(IrLiteral("\\r"))))),
        IrRule("ccesc-bs", IrAlternation(IrSequence(IrItem(IrLiteral("\\\\"))))),
        IrRule("ccesc-rb", IrAlternation(IrSequence(IrItem(IrLiteral("\\]"))))),
        IrRule("ccesc-dash", IrAlternation(IrSequence(IrItem(IrLiteral("\\-"))))),
        IrRule("ccesc-caret", IrAlternation(IrSequence(IrItem(IrLiteral("\\^"))))),
        IrRule(
            "cc-esc-hex",
            IrAlternation(
                IrSequence(IrItem(IrRuleRef("cchex2"))),
                IrSequence(IrItem(IrRuleRef("cchex4"))),
                IrSequence(IrItem(IrRuleRef("cchex8"))),
            ),
        ),
        IrRule(
            "cchex2",
            IrAlternation(
                IrSequence(
                    IrItem(IrLiteral("\\x")),
                    IrItem(IrRuleRef("hexch")),
                    IrItem(IrRuleRef("hexch")),
                )
            ),
        ),
        IrRule(
            "cchex4",
            IrAlternation(
                IrSequence(
                    IrItem(IrLiteral("\\u")),
                    IrItem(IrRuleRef("hexch")),
                    IrItem(IrRuleRef("hexch")),
                    IrItem(IrRuleRef("hexch")),
                    IrItem(IrRuleRef("hexch")),
                )
            ),
        ),
        IrRule(
            "cchex8",
            IrAlternation(
                IrSequence(
                    IrItem(IrLiteral("\\U")),
                    IrItem(IrRuleRef("hexch")),
                    IrItem(IrRuleRef("hexch")),
                    IrItem(IrRuleRef("hexch")),
                    IrItem(IrRuleRef("hexch")),
                    IrItem(IrRuleRef("hexch")),
                    IrItem(IrRuleRef("hexch")),
                    IrItem(IrRuleRef("hexch")),
                    IrItem(IrRuleRef("hexch")),
                )
            ),
        ),
        # unknown escape in a class: CANONICAL read_escape yields the bare char.
        IrRule(
            "cc-esc-other",
            IrAlternation(
                IrSequence(IrItem(IrLiteral("\\")), IrItem(IrRuleRef("cc-other")))
            ),
        ),
        IrRule(
            "cc-other",
            IrAlternation(
                IrSequence(
                    IrItem(
                        IrNot(
                            IrCharClass(
                                IrChr("n"),
                                IrChr("t"),
                                IrChr("r"),
                                IrChr("\\"),
                                IrChr("]"),
                                IrChr("-"),
                                IrChr("^"),
                                IrChr("x"),
                                IrChr("u"),
                                IrChr("U"),
                                IrChr("\n"),
                            )
                        )
                    )
                )
            ),
        ),
        # ── noise: whitespace and comments ────────────────────────────────
        IrRule(
            "n",
            IrAlternation(
                IrSequence(IrItem(IrRuleRef("nunit"), IrQuantifier(1, IrNone)))
            ),
        ),
        IrRule(
            "nunit",
            IrAlternation(
                IrSequence(IrItem(IrRuleRef("wschar"))),
                IrSequence(IrItem(IrRuleRef("comment-line"))),
            ),
        ),
        IrRule(
            "wschar",
            IrAlternation(
                IrSequence(
                    IrItem(
                        IrCharClass(IrChr(" "), IrChr("\t"), IrChr("\n"), IrChr("\r"))
                    )
                )
            ),
        ),
        # comment-line owns its terminating newline so consecutive comments
        # cannot re-segment (ambiguity guard); tail-comment covers a final
        # unterminated comment at EOF.
        IrRule(
            "comment-line",
            IrAlternation(
                IrSequence(
                    IrItem(IrLiteral("#")),
                    IrItem(IrRuleRef("cmchar"), IrQuantifier(0, IrNone)),
                    IrItem(IrLiteral("\n")),
                )
            ),
        ),
        IrRule(
            "tail-comment",
            IrAlternation(
                IrSequence(
                    IrItem(IrLiteral("#")),
                    IrItem(IrRuleRef("cmchar"), IrQuantifier(0, IrNone)),
                )
            ),
        ),
        IrRule(
            "cmchar", IrAlternation(IrSequence(IrItem(IrNot(IrCharClass(IrChr("\n"))))))
        ),
    ),
    start="grammar",
)
"""The GBNF grammar of GBNF as a canonical :class:`IrAst`."""

_NON_SEMANTIC = ("n", "tail-comment")
"""Noise rules: dropped from structural children and skipped by :data:`YIELD`."""

GBNF_NOISE: IrMap = IrMap(
    *(IrTuple(IrRuleRef(name), DROP) for name in _NON_SEMANTIC),
    IrTuple(IR_DEFAULT, KEEP_REDUCED),
)

"""Child-contribution policy: noise drops, every other rule is kept reduced."""

_HEX_CHR = IrPipe(IrJoin(IrArgs()), IrUnradix(16, IrChr))
"""Joined hex digit-run args -> an ``IrChr`` code point (charclass units)."""

_HEX_GLYPH = IrPipe(IrPipe(IrJoin(IrArgs()), IrUnradix(16, IrInt)), IrGlyph())
"""Joined hex digit-run args -> the decoded character (literal text)."""

_DEC_INT = IrPipe(IrJoin(IrArgs()), IrUnradix(10, IrInt))
"""Joined decimal digit-run args -> an ``IrInt`` bound."""

GBNF_REDUCTIONS: IrMap[IrRuleRef, IrSelf] = IrMap(
    IrTuple(
        IrRuleRef("grammar"),
        IrBuild(IrAst, IrTuple(IrBuild(IrSeq), IrPipe(IrArg(0), IrField("name")))),
    ),
    IrTuple(IrRuleRef("rules-rest"), IrArg(0)),
    IrTuple(IrRuleRef("rule"), IrBuild(IrRule)),
    IrTuple(IrRuleRef("rulename"), IrBuild(IrRuleRef, IrTuple(YIELD))),
    IrTuple(IrRuleRef("alternation"), IrBuild(IrAlternation)),
    IrTuple(IrRuleRef("arm"), IrArg(0)),
    IrTuple(IrRuleRef("empty-seq"), IrBuild(IrSequence)),
    IrTuple(IrRuleRef("bar-arm"), IrArg(0)),
    IrTuple(IrRuleRef("sequence"), IrBuild(IrSequence)),
    IrTuple(IrRuleRef("first-item"), IrArg(0)),
    IrTuple(IrRuleRef("seq-rest"), IrArg(0)),
    IrTuple(IrRuleRef("item"), IrBuild(IrItem)),
    IrTuple(IrRuleRef("item-nonname"), IrBuild(IrItem)),
    IrTuple(IrRuleRef("atom-nonname"), IrArg(0)),
    IrTuple(
        IrRuleRef("quant-opt"),
        IrCond(
            test=IrArgs(),
            then_op=IrArg(0),
            else_op=IrBuild(IrQuantifier, IrTuple()),
        ),
    ),
    IrTuple(IrRuleRef("ws-quant"), IrArg(0)),
    IrTuple(IrRuleRef("atom"), IrArg(0)),
    IrTuple(IrRuleRef("group"), IrArg(0)),
    IrTuple(IrRuleRef("quantifier"), IrArg(0)),
    IrTuple(IrRuleRef("q-opt"), IrBuild(IrQuantifier, IrTuple(IrInt(0), IrInt(1)))),
    IrTuple(IrRuleRef("q-star"), IrBuild(IrQuantifier, IrTuple(IrInt(0), IrNone))),
    IrTuple(IrRuleRef("q-plus"), IrBuild(IrQuantifier, IrTuple(IrInt(1), IrNone))),
    IrTuple(
        IrRuleRef("q-exact"),
        IrBuild(IrQuantifier, IrTuple(_DEC_INT, _DEC_INT)),
    ),
    IrTuple(
        IrRuleRef("q-atleast"),
        IrBuild(IrQuantifier, IrTuple(_DEC_INT, IrNone)),
    ),
    IrTuple(
        IrRuleRef("q-between"),
        IrBuild(
            IrQuantifier,
            IrTuple(
                IrPipe(IrArg(0), IrUnradix(10, IrInt)),
                IrPipe(IrArg(1), IrUnradix(10, IrInt)),
            ),
        ),
    ),
    IrTuple(IrRuleRef("decits"), IrJoin(IrArgs())),
    # ── literal assembly ──────────────────────────────────────────────
    IrTuple(IrRuleRef("literal"), IrBuild(IrLiteral, IrTuple(IrJoin(IrArgs())))),
    IrTuple(IrRuleRef("lunit"), IrArg(0)),
    IrTuple(IrRuleRef("lesc-short"), IrArg(0)),
    IrTuple(IrRuleRef("lesc-n"), IrLiteral("\n")),
    IrTuple(IrRuleRef("lesc-t"), IrLiteral("\t")),
    IrTuple(IrRuleRef("lesc-r"), IrLiteral("\r")),
    IrTuple(IrRuleRef("lesc-dq"), IrLiteral('"')),
    IrTuple(IrRuleRef("lesc-bs"), IrLiteral("\\")),
    IrTuple(IrRuleRef("lesc-hex"), IrArg(0)),
    IrTuple(IrRuleRef("hex2"), _HEX_GLYPH),
    IrTuple(IrRuleRef("hex4"), _HEX_GLYPH),
    IrTuple(IrRuleRef("hex8"), _HEX_GLYPH),
    # verbatim unknown escape: decode() leaves backslash + char in place.
    IrTuple(
        IrRuleRef("lesc-other"),
        IrJoin(IrTuple(IrLiteral("\\"), IrArg(0))),
    ),
    # ── charclass assembly ────────────────────────────────────────────
    IrTuple(IrRuleRef("charclass"), IrArg(0)),
    IrTuple(IrRuleRef("cc-pos"), IrBuild(IrCharClass)),
    IrTuple(IrRuleRef("cc-neg"), IrBuild(IrNot, IrTuple(IrBuild(IrCharClass)))),
    IrTuple(IrRuleRef("cc-first"), IrArg(0)),
    IrTuple(IrRuleRef("cc-nfirst"), IrArg(0)),
    IrTuple(IrRuleRef("cc-item"), IrArg(0)),
    IrTuple(
        IrRuleRef("cc-range"),
        IrBuild(IrRange, IrTuple(IrArg(0), IrArg(1))),
    ),
    IrTuple(
        IrRuleRef("cc-range-nc"),
        IrBuild(IrRange, IrTuple(IrArg(0), IrArg(1))),
    ),
    IrTuple(IrRuleRef("cc-hi"), IrArg(0)),
    IrTuple(IrRuleRef("cc-dash"), IrBuild(IrChr, IrTuple(IrStr("-")))),
    IrTuple(IrRuleRef("cc-unit"), IrArg(0)),
    IrTuple(IrRuleRef("cc-unit-nc"), IrArg(0)),
    IrTuple(IrRuleRef("cc-plain"), IrBuild(IrChr, IrTuple(YIELD))),
    IrTuple(IrRuleRef("cc-plain-nc"), IrBuild(IrChr, IrTuple(YIELD))),
    IrTuple(IrRuleRef("cc-esc"), IrArg(0)),
    IrTuple(IrRuleRef("cc-esc-short"), IrArg(0)),
    IrTuple(IrRuleRef("ccesc-n"), IrBuild(IrChr, IrTuple(IrStr("\n")))),
    IrTuple(IrRuleRef("ccesc-t"), IrBuild(IrChr, IrTuple(IrStr("\t")))),
    IrTuple(IrRuleRef("ccesc-r"), IrBuild(IrChr, IrTuple(IrStr("\r")))),
    IrTuple(IrRuleRef("ccesc-bs"), IrBuild(IrChr, IrTuple(IrStr("\\")))),
    IrTuple(IrRuleRef("ccesc-rb"), IrBuild(IrChr, IrTuple(IrStr("]")))),
    IrTuple(IrRuleRef("ccesc-dash"), IrBuild(IrChr, IrTuple(IrStr("-")))),
    IrTuple(IrRuleRef("ccesc-caret"), IrBuild(IrChr, IrTuple(IrStr("^")))),
    IrTuple(IrRuleRef("cc-esc-hex"), IrArg(0)),
    IrTuple(IrRuleRef("cchex2"), _HEX_CHR),
    IrTuple(IrRuleRef("cchex4"), _HEX_CHR),
    IrTuple(IrRuleRef("cchex8"), _HEX_CHR),
    IrTuple(IrRuleRef("cc-esc-other"), IrBuild(IrChr, IrTuple(IrArg(0)))),
    IrTuple(IR_DEFAULT, YIELD),
)
"""Per-rule reductions: parse tree -> IR. Escapes decode structurally (one
rule per escape kind); numeric runs decode via :class:`IrUnradix`. Paired
with :data:`GBNF_NOISE`."""

GBNF_REDUCER = Reducer(reductions=GBNF_REDUCTIONS, noise=GBNF_NOISE, literal=DROP)
"""The configured GBNF reducer: reductions plus the cleaning policy."""


class _GbnfFlavour(IrFlavour):
    """GBNF flavour singleton class."""

    actions: IrTypeMap = GBNF_ACTIONS

    name: ClassVar[str] = "gbnf"
    extensions: ClassVar[tuple[str, ...]] = (".gbnf",)
    escapes: ClassVar[EscapeCodec] = GBNF_ESCAPES
    line_comment: ClassVar[str] = "#"
    grammar: ClassVar[IrAst] = GBNF_GRAMMAR
    reducer: ClassVar[Reducer] = GBNF_REDUCER


GBNF_FLAVOUR = _GbnfFlavour()
"""Singleton GBNF flavour."""
