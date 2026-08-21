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

from lexic.ir import (
    DROP,
    KEEP_REDUCED,
    YIELD,
    IR_DEFAULT,
    EscapeCodec,
    IrAction,
    IrAlphabet,
    IrAlternation,
    IrApply,
    IrArg,
    IrArgs,
    IrAst,
    IrAt,
    IrBuild,
    IrCharClass,
    IrChild,
    IrChildren,
    IrChr,
    IrCompare,
    IrConcat,
    IrCond,
    IrDocConcat,
    IrDocJoin,
    IrEmit,
    IrEscape,
    IrEscapePoint,
    IrField,
    IrFlavour,
    IrGlyph,
    IrGroup,
    IrInt,
    IrIsA,
    IrItem,
    IrJoin,
    IrLine,
    IrLiteral,
    IrMap,
    IrNest,
    IrNone,
    IrNoneType,
    IrNot,
    IrOp,
    IrPipe,
    IrQuantifier,
    IrRadix,
    IrRaise,
    IrRange,
    IrRule,
    IrRuleRef,
    IrSelf,
    IrSeq,
    IrSequence,
    IrStr,
    IrText,
    IrThis,
    IrTuple,
    IrTypeMap,
    IrUnradix,
    Reducer,
)

# GBNF escape tables — quoted string literals + bracket-class members.
GBNF_ESCAPES = EscapeCodec.from_tables(
    short={"n": "\n", "t": "\t", "r": "\r", '"': '"', "\\": "\\"},
    hexes=(("x", 2), ("u", 4), ("U", 8)),
    class_short={0x0A: "\\n", 0x09: "\\t", 0x0D: "\\r"},
    class_meta="\\]-^",
)
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


_TOKEN_ID = IrConcat(
    parts=IrTuple(
        IrLiteral("<["),
        IrAt(
            0,
            IrTypeMap(
                IrAction(IrChr, IrRadix(10)),
                IrAction(
                    IrRange,
                    IrConcat(
                        parts=IrTuple(
                            IrPipe(IrField("lo", IrInt), IrRadix(10)),
                            IrLiteral("-"),
                            IrPipe(IrField("hi", IrInt), IrRadix(10)),
                        )
                    ),
                ),
            ),
        ),
        IrLiteral("]>"),
    )
)
"""Id-form token render: ``<[`` + the decimal id + ``]>`` for a single
``IrChr``, ``<[`` + lo + ``-`` + hi + ``]>`` for an inclusive ``IrRange`` —
the inner charclass holds exactly one element either way. Shared by the
positive and negated alphabet branches."""

_TOKEN_FORM = IrTypeMap(
    IrAction(IrLiteral, IrEmit()),
    IrAction(IrCharClass, _TOKEN_ID),
)
"""Dispatch a token alphabet's *positive* inner: a text-form ``IrLiteral`` emits
verbatim (the ``<…>`` key), an id-form ``IrCharClass`` renders via
:data:`_TOKEN_ID`. Reused as the nested dispatch under a negated (``IrNot``) inner."""


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
        IrCond(
            # An unmarked full-Unicode class IS `.` (any char) — restore that
            # surface (README §Tokens `.*`); `[^]`/`[\x00-\U0010ffff]` collapse
            # to it, the same language. A marked (negated) class is never
            # full-span (canonicalize folds `IrNot(full)` to the empty class),
            # so the mark channel and the `.` branch never coincide.
            test=IrField("is_any", IrInt),
            then_op=IrLiteral("."),
            else_op=IrConcat(
                parts=IrTuple(
                    IrLiteral("["),
                    IrJoin(parts=IrArgs()),
                    IrJoin(parts=IrChildren()),
                    IrLiteral("]"),
                )
            ),
        ),
    ),
    # Class members escape per GBNF class-context rules (mirrors ccesc-*/cchex*
    # on the reduce side): a raw glyph would let '\', ']', '-' corrupt the class
    # on reparse. The codec's CLASS_SHORT/CLASS_META tables carry the data;
    # IrEscapePoint reaches them via the dispatcher, like IrEscape.
    IrAction(
        IrRange,
        IrConcat(
            parts=IrTuple(
                IrPipe(IrField("lo", IrInt), IrEscapePoint()),
                IrLiteral("-"),
                IrPipe(IrField("hi", IrInt), IrEscapePoint()),
            )
        ),
    ),
    IrAction(IrChr, IrEscapePoint()),
    # Bare IrStr: the run leaf inside a class — encoded units emit verbatim.
    # Concrete str-leaves (IrLiteral/IrRuleRef) win by MRO.
    IrAction(IrStr, IrEmit()),
    # IrNot contributes its mark and delegates: the operand's own action
    # places it. Only a negated CHAR class reaches here (token negation lives
    # INSIDE the alphabet, handled by the IrAlphabet action). The IrTypeMap is
    # the guard — IrSelf is the MRO catch-all.
    IrAction(
        IrNot,
        IrAt(
            0,
            IrTypeMap(
                # A negated EMPTY class is any-char → `.` (the raw parse of `.`/
                # `[^]`); a negated non-empty class marks `^` and delegates to
                # the class's own action.
                IrAction(
                    IrCharClass,
                    IrCond(
                        test=IrField("is_empty", IrInt),
                        then_op=IrLiteral("."),
                        else_op=IrApply(IrTuple(IrLiteral("^"))),
                    ),
                ),
                IrAction(
                    IrSelf,
                    IrRaise(message="{dispatcher}: cannot negate {node_type!r}"),
                ),
            ),
        ),
    ),
    # A token terminal, dispatched on its inner atom (negation is INSIDE the
    # alphabet): a text-form IrLiteral emits verbatim (the "<…>" key), an id-form
    # IrCharClass emits "<[" id "]>", and a negated inner (IrNot) emits "!" then
    # the positive form of ITS inner.
    IrAction(
        IrAlphabet,
        IrAt(
            0,
            IrTypeMap(
                IrAction(IrLiteral, IrEmit()),
                IrAction(IrCharClass, _TOKEN_ID),
                IrAction(
                    IrNot,
                    IrConcat(parts=IrTuple(IrLiteral("!"), IrAt(0, _TOKEN_FORM))),
                ),
            ),
        ),
    ),
    IrAction(IrRuleRef, IrEmit()),
    IrAction(IrQuantifier, GBNF_QUANTIFIERS),
    # STRUCTURE levels build layout docs (atoms above stay str-tier, lifted
    # at the doc joins): each sequence arm is its own fit group, arms break
    # onto trailing-pipe continuations, a rule is one width-group nested at
    # the continuation indent. Top-level renders at flat=False, so the
    # inter-rule IrLines are hard breaks and width=None reproduces the flat
    # single-line form byte-for-byte.
    IrAction(
        IrItem,
        IrDocConcat(
            parts=IrTuple(
                IrCond(
                    test=IrIsA("atom", IrAlternation),
                    then_op=IrDocConcat(
                        parts=IrTuple(IrText("("), IrChild("atom"), IrText(")"))
                    ),
                    else_op=IrChild("atom"),
                ),
                IrChild("quantifier"),
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
            separator=IrLine(" | ", " |"),
            empty=IrText(""),
        ),
    ),
    IrAction(
        IrRule,
        IrGroup(
            IrNest(
                6,
                IrDocConcat(
                    parts=IrTuple(IrField("name"), IrText(" ::= "), IrChild("body"))
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
    IrSeq(
        IrRule(
            "grammar",
            IrAlternation(
                IrSequence(
                    IrItem(IrRuleRef("n"), IrQuantifier(0)),
                    IrItem(IrRuleRef("rule")),
                    IrItem(IrRuleRef("rules-rest"), IrQuantifier(0, IrNone)),
                    IrItem(IrRuleRef("n"), IrQuantifier(0)),
                    IrItem(IrRuleRef("tail-comment"), IrQuantifier(0)),
                )
            ),
        ),
        IrRule(
            "n",
            IrAlternation(
                IrSequence(IrItem(IrRuleRef("nunit"), IrQuantifier(1, IrNone)))
            ),
            False,
        ),
        IrRule(
            "rule",
            IrAlternation(
                IrSequence(
                    IrItem(IrRuleRef("rulename")),
                    IrItem(IrRuleRef("n"), IrQuantifier(0)),
                    IrItem(IrLiteral("::=")),
                    IrItem(IrRuleRef("alternation")),
                )
            ),
        ),
        IrRule(
            "rules-rest",
            IrAlternation(
                IrSequence(IrItem(IrRuleRef("n")), IrItem(IrRuleRef("rule")))
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
            False,
        ),
        IrRule(
            "nunit",
            IrAlternation(
                IrSequence(IrItem(IrRuleRef("wschar"))),
                IrSequence(IrItem(IrRuleRef("comment-line"))),
            ),
            False,
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
            "alternation",
            IrAlternation(
                IrSequence(
                    IrItem(IrRuleRef("arm")),
                    IrItem(IrRuleRef("bar-arm"), IrQuantifier(0, IrNone)),
                )
            ),
        ),
        IrRule(
            "cmchar",
            IrAlternation(
                IrSequence(
                    IrItem(
                        IrCharClass(
                            IrRange(IrChr(0), IrChr(9)),
                            IrRange(IrChr(11), IrChr(1114111)),
                        )
                    )
                )
            ),
        ),
        IrRule(
            "wschar",
            IrAlternation(
                IrSequence(
                    IrItem(
                        IrCharClass(IrRange(IrChr(9), IrChr(10)), IrChr(13), IrChr(32))
                    )
                )
            ),
        ),
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
            "namehead",
            IrAlternation(
                IrSequence(
                    IrItem(
                        IrCharClass(
                            IrRange(IrChr(65), IrChr(90)),
                            IrChr(95),
                            IrRange(IrChr(97), IrChr(122)),
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
                            IrChr(45),
                            IrRange(IrChr(48), IrChr(57)),
                            IrRange(IrChr(65), IrChr(90)),
                            IrChr(95),
                            IrRange(IrChr(97), IrChr(122)),
                        )
                    )
                )
            ),
        ),
        IrRule(
            "arm",
            IrAlternation(
                IrSequence(IrItem(IrRuleRef("sequence"))),
                IrSequence(IrItem(IrRuleRef("empty-seq"))),
            ),
        ),
        IrRule(
            "bar-arm",
            IrAlternation(
                IrSequence(
                    IrItem(IrRuleRef("n"), IrQuantifier(0)),
                    IrItem(IrLiteral("|")),
                    IrItem(IrRuleRef("arm")),
                )
            ),
        ),
        IrRule(
            "sequence",
            IrAlternation(
                IrSequence(
                    IrItem(IrRuleRef("first-item")),
                    IrItem(IrRuleRef("seq-rest"), IrQuantifier(0, IrNone)),
                )
            ),
        ),
        IrRule("empty-seq", IrAlternation(IrSequence())),
        IrRule(
            "first-item",
            IrAlternation(
                IrSequence(
                    IrItem(IrRuleRef("n"), IrQuantifier(0)), IrItem(IrRuleRef("item"))
                )
            ),
        ),
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
            "atom",
            IrAlternation(
                IrSequence(IrItem(IrRuleRef("literal"))),
                IrSequence(IrItem(IrRuleRef("charclass"))),
                IrSequence(IrItem(IrRuleRef("rulename"))),
                IrSequence(IrItem(IrRuleRef("group"))),
                IrSequence(IrItem(IrRuleRef("token"))),
                IrSequence(IrItem(IrRuleRef("token-not"))),
                IrSequence(IrItem(IrRuleRef("any-char"))),
            ),
        ),
        IrRule(
            "quant-opt",
            IrAlternation(IrSequence(IrItem(IrRuleRef("ws-quant"), IrQuantifier(0)))),
        ),
        IrRule(
            "atom-nonname",
            IrAlternation(
                IrSequence(IrItem(IrRuleRef("literal"))),
                IrSequence(IrItem(IrRuleRef("charclass"))),
                IrSequence(IrItem(IrRuleRef("group"))),
                IrSequence(IrItem(IrRuleRef("token"))),
                IrSequence(IrItem(IrRuleRef("token-not"))),
                IrSequence(IrItem(IrRuleRef("any-char"))),
            ),
        ),
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
            "charclass",
            IrAlternation(
                IrSequence(IrItem(IrRuleRef("cc-pos"))),
                IrSequence(IrItem(IrRuleRef("cc-neg"))),
            ),
        ),
        IrRule(
            "group",
            IrAlternation(
                IrSequence(
                    IrItem(IrLiteral("(")),
                    IrItem(IrRuleRef("alternation")),
                    IrItem(IrRuleRef("n"), IrQuantifier(0)),
                    IrItem(IrLiteral(")")),
                )
            ),
        ),
        IrRule(
            "token",
            IrAlternation(
                IrSequence(IrItem(IrRuleRef("tok-id"))),
                IrSequence(IrItem(IrRuleRef("tok-text"))),
            ),
        ),
        IrRule(
            "token-not",
            IrAlternation(
                IrSequence(IrItem(IrLiteral("!")), IrItem(IrRuleRef("token")))
            ),
        ),
        IrRule("any-char", IrAlternation(IrSequence(IrItem(IrLiteral("."))))),
        IrRule(
            "ws-quant",
            IrAlternation(
                IrSequence(
                    IrItem(IrRuleRef("n"), IrQuantifier(0)),
                    IrItem(IrRuleRef("quantifier")),
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
            "cc-pos",
            IrAlternation(
                IrSequence(
                    IrItem(IrLiteral("[")),
                    IrItem(IrRuleRef("cc-first")),
                    IrItem(IrRuleRef("cc-item"), IrQuantifier(0, IrNone)),
                    IrItem(IrRuleRef("cc-dash"), IrQuantifier(0)),
                    IrItem(IrLiteral("]")),
                ),
                IrSequence(IrItem(IrLiteral("[]"))),
            ),
        ),
        IrRule(
            "cc-neg",
            IrAlternation(
                IrSequence(
                    IrItem(IrLiteral("[^")),
                    IrItem(IrRuleRef("cc-nfirst")),
                    IrItem(IrRuleRef("cc-item"), IrQuantifier(0, IrNone)),
                    IrItem(IrRuleRef("cc-dash"), IrQuantifier(0)),
                    IrItem(IrLiteral("]")),
                ),
                IrSequence(IrItem(IrLiteral("[^]"))),
            ),
        ),
        # The id-range tail is left-factored like cc-tail: one `<[ decits`
        # prefix, then the tail separates on `]>` vs `- decits ]>` at k=1 —
        # FIRST-disjoint, so the token rules stay off the island path.
        IrRule(
            "tok-id",
            IrAlternation(
                IrSequence(
                    IrItem(IrLiteral("<[")),
                    IrItem(IrRuleRef("decits")),
                    IrItem(IrRuleRef("tok-id-tail")),
                )
            ),
        ),
        IrRule(
            "tok-text",
            IrAlternation(
                IrSequence(
                    IrItem(IrLiteral("<")),
                    IrItem(IrRuleRef("ttfirst")),
                    IrItem(IrRuleRef("ttchar"), IrQuantifier(0, IrNone)),
                    IrItem(IrLiteral(">")),
                )
            ),
        ),
        IrRule(
            "quantifier",
            IrAlternation(
                IrSequence(IrItem(IrRuleRef("q-opt"))),
                IrSequence(IrItem(IrRuleRef("q-star"))),
                IrSequence(IrItem(IrRuleRef("q-plus"))),
                IrSequence(IrItem(IrRuleRef("q-counted"))),
            ),
        ),
        IrRule(
            "lplain",
            IrAlternation(
                IrSequence(
                    IrItem(
                        IrCharClass(
                            IrRange(IrChr(0), IrChr(33)),
                            IrRange(IrChr(35), IrChr(91)),
                            IrRange(IrChr(93), IrChr(1114111)),
                        )
                    )
                )
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
        IrRule(
            "lesc-hex",
            IrAlternation(
                IrSequence(IrItem(IrRuleRef("hex2"))),
                IrSequence(IrItem(IrRuleRef("hex4"))),
                IrSequence(IrItem(IrRuleRef("hex8"))),
            ),
        ),
        IrRule(
            "lesc-other",
            IrAlternation(
                IrSequence(IrItem(IrLiteral("\\")), IrItem(IrRuleRef("lother")))
            ),
        ),
        # Class members left-factored like the counted-quantifier tail: a unit
        # is consumed once, then `cc-tail` decides whether a `-` opens a range
        # (`- cc-hi`) or the class element ends (ε). The empty arm overlaps
        # FOLLOW only through a trailing `-` (`[a-]`), which a 2-char FOLLOW
        # window separates from a real range's `- cc-hi` — so the `cc-*first`
        # arms separate at k=1 (`cc-unit` never leads with `-`) and the class
        # rules stay off the island path.
        IrRule(
            "cc-first",
            IrAlternation(
                IrSequence(IrItem(IrRuleRef("cc-item-nc"))),
                IrSequence(IrItem(IrRuleRef("cc-dash"))),
            ),
        ),
        IrRule(
            "cc-item",
            IrAlternation(
                IrSequence(IrItem(IrRuleRef("cc-unit")), IrItem(IrRuleRef("cc-tail")))
            ),
        ),
        IrRule("cc-dash", IrAlternation(IrSequence(IrItem(IrLiteral("-"))))),
        IrRule(
            "cc-nfirst",
            IrAlternation(
                IrSequence(IrItem(IrRuleRef("cc-item"))),
                IrSequence(IrItem(IrRuleRef("cc-dash"))),
            ),
        ),
        IrRule(
            "decits",
            IrAlternation(
                IrSequence(IrItem(IrRuleRef("digit"), IrQuantifier(1, IrNone)))
            ),
        ),
        IrRule(
            "tok-id-tail",
            IrAlternation(
                IrSequence(IrItem(IrLiteral("]>"))),
                IrSequence(
                    IrItem(IrLiteral("-")),
                    IrItem(IrRuleRef("decits")),
                    IrItem(IrLiteral("]>")),
                ),
            ),
        ),
        IrRule(
            "ttfirst",
            IrAlternation(
                IrSequence(
                    IrItem(
                        IrCharClass(
                            IrChr(">"), IrChr("["), IrChr("\n"), IrChr("\r")
                        ).complement()
                    )
                )
            ),
        ),
        IrRule(
            "ttchar",
            IrAlternation(
                IrSequence(
                    IrItem(
                        IrCharClass(IrChr(">"), IrChr("\n"), IrChr("\r")).complement()
                    )
                )
            ),
        ),
        IrRule("q-opt", IrAlternation(IrSequence(IrItem(IrLiteral("?"))))),
        IrRule("q-star", IrAlternation(IrSequence(IrItem(IrLiteral("*"))))),
        IrRule("q-plus", IrAlternation(IrSequence(IrItem(IrLiteral("+"))))),
        # Left-factored counted forms: the shared `{ decits` prefix is consumed
        # once, then `q-tail` decides the arm (`}` exact / `,}` at-least / `,`
        # decits `}` between) — so `quantifier`'s four arms separate at k=1.
        IrRule(
            "q-counted",
            IrAlternation(
                IrSequence(
                    IrItem(IrLiteral("{")),
                    IrItem(IrRuleRef("decits")),
                    IrItem(IrRuleRef("q-tail")),
                )
            ),
        ),
        IrRule("lesc-n", IrAlternation(IrSequence(IrItem(IrLiteral("\\n"))))),
        IrRule("lesc-t", IrAlternation(IrSequence(IrItem(IrLiteral("\\t"))))),
        IrRule("lesc-r", IrAlternation(IrSequence(IrItem(IrLiteral("\\r"))))),
        IrRule("lesc-dq", IrAlternation(IrSequence(IrItem(IrLiteral('\\"'))))),
        IrRule("lesc-bs", IrAlternation(IrSequence(IrItem(IrLiteral("\\\\"))))),
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
            "lother",
            IrAlternation(
                IrSequence(
                    IrItem(
                        IrCharClass(
                            IrRange(IrChr(0), IrChr(9)),
                            IrRange(IrChr(11), IrChr(33)),
                            IrRange(IrChr(35), IrChr(84)),
                            IrRange(IrChr(86), IrChr(91)),
                            IrRange(IrChr(93), IrChr(109)),
                            IrRange(IrChr(111), IrChr(113)),
                            IrChr(115),
                            IrRange(IrChr(118), IrChr(119)),
                            IrRange(IrChr(121), IrChr(1114111)),
                        )
                    )
                )
            ),
        ),
        IrRule(
            "cc-item-nc",
            IrAlternation(
                IrSequence(
                    IrItem(IrRuleRef("cc-unit-nc")), IrItem(IrRuleRef("cc-tail"))
                )
            ),
        ),
        IrRule(
            "cc-unit",
            IrAlternation(
                IrSequence(IrItem(IrRuleRef("cc-plain"))),
                IrSequence(IrItem(IrRuleRef("cc-esc"))),
            ),
        ),
        # The optional range tail: `- cc-hi` opens a range, the empty arm ends
        # the element. `cc-hi` is preserved; the empty-arm-vs-FOLLOW ambiguity
        # is resolved by a 2-char FOLLOW-window arm gate (a bare trailing `-`
        # is always followed by `]`, a range's `-` never is).
        IrRule(
            "cc-tail",
            IrAlternation(
                IrSequence(IrItem(IrLiteral("-")), IrItem(IrRuleRef("cc-hi"))),
                IrSequence(),
            ),
        ),
        IrRule(
            "digit",
            IrAlternation(
                IrSequence(IrItem(IrCharClass(IrRange(IrChr(48), IrChr(57)))))
            ),
        ),
        # The counted-quantifier tail after the shared `{ decits` prefix: `}`
        # (exact) / `,}` (at-least) / `,` decits `}` (between). `q-exact-t`
        # separates at k=1; `q-atleast-t` vs `q-between-t` at k=2 (`}` vs digit).
        IrRule(
            "q-tail",
            IrAlternation(
                IrSequence(IrItem(IrRuleRef("q-exact-t"))),
                IrSequence(IrItem(IrRuleRef("q-atleast-t"))),
                IrSequence(IrItem(IrRuleRef("q-between-t"))),
            ),
        ),
        IrRule(
            "hexch",
            IrAlternation(
                IrSequence(
                    IrItem(
                        IrCharClass(
                            IrRange(IrChr(48), IrChr(57)),
                            IrRange(IrChr(65), IrChr(70)),
                            IrRange(IrChr(97), IrChr(102)),
                        )
                    )
                )
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
                    IrItem(
                        IrCharClass(
                            IrRange(IrChr(0), IrChr(44)),
                            IrRange(IrChr(46), IrChr(91)),
                            IrRange(IrChr(94), IrChr(1114111)),
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
            "cc-hi",
            IrAlternation(
                IrSequence(IrItem(IrRuleRef("cc-unit"))),
                IrSequence(IrItem(IrRuleRef("cc-dash"))),
            ),
        ),
        IrRule("q-exact-t", IrAlternation(IrSequence(IrItem(IrLiteral("}"))))),
        IrRule("q-atleast-t", IrAlternation(IrSequence(IrItem(IrLiteral(",}"))))),
        IrRule(
            "q-between-t",
            IrAlternation(
                IrSequence(
                    IrItem(IrLiteral(",")),
                    IrItem(IrRuleRef("decits")),
                    IrItem(IrLiteral("}")),
                )
            ),
        ),
        IrRule(
            "cc-plain-nc",
            IrAlternation(
                IrSequence(
                    IrItem(
                        IrCharClass(
                            IrRange(IrChr(0), IrChr(44)),
                            IrRange(IrChr(46), IrChr(91)),
                            IrRange(IrChr(95), IrChr(1114111)),
                        )
                    )
                )
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
        IrRule(
            "cc-esc-hex",
            IrAlternation(
                IrSequence(IrItem(IrRuleRef("cchex2"))),
                IrSequence(IrItem(IrRuleRef("cchex4"))),
                IrSequence(IrItem(IrRuleRef("cchex8"))),
            ),
        ),
        IrRule(
            "cc-esc-other",
            IrAlternation(
                IrSequence(IrItem(IrLiteral("\\")), IrItem(IrRuleRef("cc-other")))
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
        IrRule(
            "cc-other",
            IrAlternation(
                IrSequence(
                    IrItem(
                        IrCharClass(
                            IrRange(IrChr(0), IrChr(9)),
                            IrRange(IrChr(11), IrChr(44)),
                            IrRange(IrChr(46), IrChr(84)),
                            IrRange(IrChr(86), IrChr(91)),
                            IrRange(IrChr(95), IrChr(109)),
                            IrRange(IrChr(111), IrChr(113)),
                            IrChr(115),
                            IrRange(IrChr(118), IrChr(119)),
                            IrRange(IrChr(121), IrChr(1114111)),
                        )
                    )
                )
            ),
        ),
    ),
    "grammar",
)

GBNF_NOISE: IrMap = IrMap(
    *(IrTuple(IrRuleRef(name), DROP) for name in GBNF_GRAMMAR.non_semantic),
    IrTuple(IR_DEFAULT, KEEP_REDUCED),
)

"""Child-contribution policy: noise drops, every other rule is kept reduced."""

_HEX_CHR = IrPipe(IrJoin(IrArgs()), IrUnradix(16, IrChr))
"""Joined hex digit-run args -> an ``IrChr`` code point (charclass units)."""

_HEX_GLYPH = IrPipe(IrPipe(IrJoin(IrArgs()), IrUnradix(16, IrInt)), IrGlyph())
"""Joined hex digit-run args -> the decoded character (literal text)."""

_DEC_INT = IrPipe(IrJoin(IrArgs()), IrUnradix(10, IrInt))
"""Joined decimal digit-run args -> an ``IrInt`` bound."""

GBNF_TOKEN_ENCODING = "tokens"
"""The registry name GBNF's single token alphabet binds to. A tokenizer supplied
at parse time is bound under this name; every ``<…>``/``<[…]>`` terminal reduces
to an :class:`~lexic.ir.grammar.nodes.IrAlphabet` referencing it."""

_TOK_LO = IrPipe(IrArg(0), IrUnradix(10, IrChr))
"""The id-form's shared ``<[ decits`` digit-run arg decoded to the (low) id."""

_TOK_UNIT = IrPipe(
    IrArg(1),
    IrTypeMap(
        IrAction(IrNoneType, _TOK_LO),
        IrAction(
            IrStr,
            IrBuild(IrRange, IrTuple(_TOK_LO, IrPipe(IrArg(1), IrUnradix(10, IrChr)))),
        ),
    ),
)
"""``tok-id``'s single charclass element, branched on the tail (the
:data:`_CC_ITEM` idiom): a bare ``]>`` tail (``IrNone``) keeps the single id,
a ``- decits ]>`` tail (the hi digit run) builds the inclusive ``IrRange``."""

_ALPHA_ID = IrBuild(
    IrAlphabet,
    IrTuple(IrStr(GBNF_TOKEN_ENCODING), IrBuild(IrCharClass, IrTuple(_TOK_UNIT))),
)
"""``<[decits]>`` -> ``IrAlphabet("tokens", IrCharClass(IrChr(id)))``;
``<[lo-hi]>`` -> the same alphabet over ``IrCharClass(IrRange(lo, hi))``."""

_ALPHA_TEXT = IrBuild(
    IrAlphabet,
    IrTuple(
        IrStr(GBNF_TOKEN_ENCODING),
        IrBuild(
            IrLiteral,
            IrTuple(IrJoin(IrTuple(IrStr("<"), IrJoin(IrArgs()), IrStr(">")))),
        ),
    ),
)
"""``<text>`` -> ``IrAlphabet("tokens", IrLiteral("<text>"))`` (text-form; the
angle brackets are part of the key — the GBNF token-text wart)."""

_ALPHA_NOT = IrBuild(
    IrAlphabet,
    IrTuple(
        IrStr(GBNF_TOKEN_ENCODING),
        IrBuild(IrNot, IrTuple(IrPipe(IrArg(0), IrAt(0, IrThis())))),
    ),
)
"""``!<…>`` -> ``IrAlphabet("tokens", IrNot(inner))`` — negation INSIDE the
alphabet (the encoding governs the token-universe complement). ``IrArg(0)`` is
the positive ``token`` result (an ``IrAlphabet``); ``IrAt(0, IrThis())`` reads
its raw inner atom, which is re-wrapped under an ``IrNot`` in a fresh alphabet."""

_Q_MIRROR = IrStr("=")
"""``q-exact-t`` marker: the ``{n}`` upper bound mirrors ``lo``."""

_Q_LO = IrPipe(IrArg(0), IrUnradix(10, IrInt))
"""The counted form's shared ``{n`` digit-run arg decoded to the lower bound."""

_Q_HI = IrTypeMap(
    IrAction(IrInt, IrThis()),
    IrAction(IrNoneType, IrThis()),
    IrAction(IrStr, _Q_LO),
)
"""Counted-tail marker → the upper bound: a decoded ``{m,n}`` bound or the open
``{n,}`` ``IrNone`` rides through; the ``_Q_MIRROR`` sentinel mirrors ``lo``."""

_CC_ITEM = IrPipe(
    IrArg(1),
    IrTypeMap(
        IrAction(IrNoneType, IrArg(0)),
        IrAction(IrChr, IrBuild(IrRange, IrTuple(IrArg(0), IrArg(1)))),
    ),
)
"""``cc-item``/``cc-item-nc`` (``cc-unit cc-tail``) → a bare unit or a range.

The piped subject is ``cc-tail``'s reduction: the empty tail rides through as
``IrNone`` (arm keeps the unit, :data:`IrArg(0)`), a ``- cc-hi`` tail is the hi
:class:`IrChr` (arm builds ``IrRange(unit, hi)``). ``IrArg(0)``/``IrArg(1)``
stay the original unit/tail inside the piped map."""

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
        IrRuleRef("q-counted"),
        IrBuild(IrQuantifier, IrTuple(_Q_LO, IrPipe(IrArg(1), _Q_HI))),
    ),
    IrTuple(IrRuleRef("q-tail"), IrArg(0)),
    IrTuple(IrRuleRef("q-exact-t"), _Q_MIRROR),
    IrTuple(IrRuleRef("q-atleast-t"), IrNone),
    IrTuple(IrRuleRef("q-between-t"), _DEC_INT),
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
    IrTuple(IrRuleRef("cc-item"), _CC_ITEM),
    IrTuple(IrRuleRef("cc-item-nc"), _CC_ITEM),
    IrTuple(
        IrRuleRef("cc-tail"),
        IrCond(test=IrArgs(), then_op=IrArg(0), else_op=IrNone),
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
    # ── token terminals (README §Tokens) ──────────────────────────────
    IrTuple(IrRuleRef("token"), IrArg(0)),
    IrTuple(IrRuleRef("tok-id"), _ALPHA_ID),
    IrTuple(
        IrRuleRef("tok-id-tail"),
        IrCond(test=IrArgs(), then_op=IrArg(0), else_op=IrNone),
    ),
    IrTuple(IrRuleRef("tok-text"), _ALPHA_TEXT),
    IrTuple(IrRuleRef("ttfirst"), YIELD),
    IrTuple(IrRuleRef("ttchar"), YIELD),
    IrTuple(IrRuleRef("token-not"), _ALPHA_NOT),
    IrTuple(
        IrRuleRef("any-char"),
        IrBuild(IrNot, IrTuple(IrBuild(IrCharClass, IrTuple()))),
    ),
)
"""Per-rule reductions: parse tree -> IR. Escapes decode structurally (one
rule per escape kind); numeric runs decode via :class:`IrUnradix`. Paired
with :data:`GBNF_NOISE`."""

GBNF_REDUCER = Reducer(
    actions=GBNF_REDUCTIONS, default=YIELD, noise=GBNF_NOISE, literal=DROP
)
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
