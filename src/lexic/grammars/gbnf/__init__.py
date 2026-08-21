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

from lexic.grammars.gbnf.grammar import GBNF_GRAMMAR
from lexic.ir import (
    DROP,
    IR_DEFAULT,
    KEEP_REDUCED,
    YIELD,
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
