"""EBNF flavour for Lexic.

Bundles the escape codec, emit action table, and the native-IR self-grammar +
reducer in one module — the :mod:`gbnf`/:mod:`abnf` shape. :data:`EBNF_FLAVOUR`
is the singleton :class:`IrFlavour`/:class:`IrEmitter` consumed by
:func:`lexic.grammars.get_flavour`.

The surface is ISO-family EBNF: ``=``/``;`` rules, ``,`` concatenation, ``|``
alternation, ``{ }`` repetition, ``[ ]`` option, ``( )`` grouping, postfix
``* + ?``, integer multiplication ``3 * x`` (exact repetition), ``".."`` char
ranges on quoted terminals, ``'``/``"`` terminals with backslash escapes, and
``(* *)`` block comments. There is no line comment (``line_comment`` empty ⇒
no ``@directive`` scan) and no native char-class or negation syntax:

- a char class emits as a parenthesised ``|`` alternation of quoted
  terminals/``..`` ranges (a single member emits bare) and reparses through
  canonicalisation back to the merged class;
- :class:`~lexic.ir.grammar.operators.IrNot` refuses declaratively (the ABNF
  precedent) — canonicalisation rewrites negation to positive spans first,
  so the raising action is unreachable on canonical input;
- an open or bounded counted quantifier (``{n,}``/``{m,n}``) refuses at emit:
  ISO EBNF has no spelling for it. Exact ``(n, n)`` repetition emits as the
  prefix multiplication ``n * x`` (owned by the ``IrItem`` action — the
  quantifier slot itself is postfix-only).

STRUCTURE-level emit actions build layout docs (the flavour-layout shape):
trailing-comma/-pipe continuations, one width-group per rule and per
sequence arm.
"""

from __future__ import annotations

from typing import ClassVar

from lexic.ir import (
    IR_DEFAULT,
    EscapeCodec,
    IrAction,
    IrAlphabet,
    IrAlternation,
    IrAnd,
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
    IrLen,
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
)
from lexic.parsing.earley.reduce.policy import DROP, KEEP_REDUCED, YIELD
from lexic.parsing.earley.reduce.reducer import Reducer

# EBNF escape tables — quoted-terminal body + ``..``-endpoint spelling. The
# EBNF "class context" is a double-quoted ``..`` endpoint / member terminal —
# its metas are the QUOTE and the backslash (not GBNF's bracket metas; the parse
# side still accepts ``\-``/``\^``/``\]``).
EBNF_ESCAPES = EscapeCodec.from_tables(
    short={"n": "\n", "t": "\t", "r": "\r", '"': '"', "'": "'", "\\": "\\"},
    hexes=(("x", 2), ("u", 4), ("U", 8)),
    class_short={0x0A: "\\n", 0x09: "\\t", 0x0D: "\\r"},
    class_meta='\\"',
)
"""Singleton escape codec for EBNF."""


# ── EBNF grammar as native IR ──────────────────────────────────────────────

_STAR = IrQuantifier(0, IrNone)
_PLUS = IrQuantifier(1, IrNone)


def _lit(text: str) -> IrItem:
    return IrItem(IrLiteral(text))


def _ref(name: str) -> IrItem:
    return IrItem(IrRuleRef(name))


def _rep(name: str) -> IrItem:
    return IrItem(IrRuleRef(name), _STAR)


def _rule(name: str, *arms: IrSequence, semantic: bool = True) -> IrRule:
    return IrRule(name, IrAlternation(*arms), semantic)


_WS_CC = IrCharClass(IrChr(9), IrChr(10), IrChr(13), IrChr(32))
_NOT_STAR = IrCharClass(
    IrRange(IrChr(0), IrChr(41)), IrRange(IrChr(43), IrChr(1114111))
)
_DQ_PLAIN = IrCharClass(
    IrRange(IrChr(0), IrChr(33)),
    IrRange(IrChr(35), IrChr(91)),
    IrRange(IrChr(93), IrChr(1114111)),
)
_SQ_PLAIN = IrCharClass(
    IrRange(IrChr(0), IrChr(38)),
    IrRange(IrChr(40), IrChr(91)),
    IrRange(IrChr(93), IrChr(1114111)),
)
_NAME_FIRST = IrCharClass(
    IrRange(IrChr("a"), IrChr("z")), IrRange(IrChr("A"), IrChr("Z"))
)
_NAME_REST = IrCharClass(
    IrRange(IrChr("a"), IrChr("z")),
    IrRange(IrChr("A"), IrChr("Z")),
    IrRange(IrChr("0"), IrChr("9")),
    IrChr("-"),
    IrChr("_"),
)
_DIGIT = IrCharClass(IrRange(IrChr("0"), IrChr("9")))
_HEXD = IrCharClass(
    IrRange(IrChr("0"), IrChr("9")),
    IrRange(IrChr("A"), IrChr("F")),
    IrRange(IrChr("a"), IrChr("f")),
)


EBNF_GRAMMAR = IrAst(
    IrSeq(
        _rule("grammar", IrSequence(_ref("ws"), _ref("rule"), _rep("rrest"))),
        _rule("rrest", IrSequence(_ref("rule"))),
        _rule(
            "rule",
            IrSequence(
                _ref("rulename"),
                _ref("ws"),
                _lit("="),
                _ref("ws"),
                _ref("alternation"),
                _ref("ws"),
                _lit(";"),
                _ref("ws"),
            ),
        ),
        _rule("rulename", IrSequence(IrItem(_NAME_FIRST), IrItem(_NAME_REST, _STAR))),
        _rule("alternation", IrSequence(_ref("concat"), _rep("altrest"))),
        _rule("altrest", IrSequence(_lit("|"), _ref("ws"), _ref("concat"))),
        _rule("concat", IrSequence(_ref("factor"), _rep("catrest"))),
        _rule("catrest", IrSequence(_lit(","), _ref("ws"), _ref("factor"))),
        _rule(
            "factor",
            IrSequence(_ref("repetition")),
            IrSequence(_ref("option")),
            IrSequence(_ref("multiplied")),
            IrSequence(_ref("quantified")),
        ),
        _rule(
            "repetition",
            IrSequence(
                _lit("{"), _ref("ws"), _ref("alternation"), _lit("}"), _ref("ws")
            ),
        ),
        _rule(
            "option",
            IrSequence(
                _lit("["), _ref("ws"), _ref("alternation"), _lit("]"), _ref("ws")
            ),
        ),
        # ISO integer multiplication — exact repetition ``3 * x``.
        _rule(
            "multiplied",
            IrSequence(_ref("count"), _lit("*"), _ref("ws"), _ref("primary")),
        ),
        _rule("count", IrSequence(IrItem(IrRuleRef("digit"), _PLUS), _ref("ws"))),
        _rule("digit", IrSequence(IrItem(_DIGIT))),
        _rule("quantified", IrSequence(_ref("primary"), _ref("quant-opt"))),
        _rule(
            "quant-opt",
            IrSequence(_ref("q-star")),
            IrSequence(_ref("q-plus")),
            IrSequence(_ref("q-opt")),
            IrSequence(),
        ),
        _rule("q-star", IrSequence(_lit("*"), _ref("ws"))),
        _rule("q-plus", IrSequence(_lit("+"), _ref("ws"))),
        _rule("q-opt", IrSequence(_lit("?"), _ref("ws"))),
        _rule(
            "primary",
            IrSequence(_ref("strprim")),
            IrSequence(_ref("group")),
            IrSequence(_ref("ruleref")),
        ),
        _rule("strprim", IrSequence(_ref("terminal"), _ref("rangetail-opt"))),
        _rule("rangetail-opt", IrSequence(_ref("rangetail")), IrSequence()),
        _rule("rangetail", IrSequence(_lit(".."), _ref("ws"), _ref("terminal"))),
        _rule(
            "group",
            IrSequence(
                _lit("("), _ref("ws"), _ref("alternation"), _lit(")"), _ref("ws")
            ),
        ),
        _rule("ruleref", IrSequence(_ref("rulename"), _ref("ws"))),
        _rule("terminal", IrSequence(_ref("dq")), IrSequence(_ref("sq"))),
        _rule("dq", IrSequence(_lit('"'), _rep("dqunit"), _lit('"'), _ref("ws"))),
        _rule("sq", IrSequence(_lit("'"), _rep("squnit"), _lit("'"), _ref("ws"))),
        _rule("dqunit", IrSequence(_ref("dqplain")), IrSequence(_ref("esc"))),
        _rule("squnit", IrSequence(_ref("sqplain")), IrSequence(_ref("esc"))),
        _rule("dqplain", IrSequence(IrItem(_DQ_PLAIN))),
        _rule("sqplain", IrSequence(IrItem(_SQ_PLAIN))),
        _rule(
            "esc",
            IrSequence(_ref("esc-x")),
            IrSequence(_ref("esc-u")),
            IrSequence(_ref("esc-bigu")),
            IrSequence(_ref("esc-n")),
            IrSequence(_ref("esc-t")),
            IrSequence(_ref("esc-r")),
            IrSequence(_ref("esc-bs")),
            IrSequence(_ref("esc-dq")),
            IrSequence(_ref("esc-sq")),
            IrSequence(_ref("esc-dash")),
            IrSequence(_ref("esc-caret")),
            IrSequence(_ref("esc-rb")),
        ),
        # Hex escapes (the codec's HEX_ESCAPES parse-side mirror) — required
        # so emitted range endpoints beyond the short table reparse.
        _rule(
            "esc-x",
            IrSequence(_lit("\\x"), IrItem(IrRuleRef("hexd"), IrQuantifier(2, 2))),
        ),
        _rule(
            "esc-u",
            IrSequence(_lit("\\u"), IrItem(IrRuleRef("hexd"), IrQuantifier(4, 4))),
        ),
        _rule(
            "esc-bigu",
            IrSequence(_lit("\\U"), IrItem(IrRuleRef("hexd"), IrQuantifier(8, 8))),
        ),
        _rule("hexd", IrSequence(IrItem(_HEXD))),
        _rule("esc-n", IrSequence(_lit("\\n"))),
        _rule("esc-t", IrSequence(_lit("\\t"))),
        _rule("esc-r", IrSequence(_lit("\\r"))),
        _rule("esc-bs", IrSequence(_lit("\\\\"))),
        _rule("esc-dq", IrSequence(_lit('\\"'))),
        _rule("esc-sq", IrSequence(_lit("\\'"))),
        # Accept the class-context escapes the emit side spells via
        # IrEscapePoint (CLASS_META ``\- \^ \]``) so an emitted grammar
        # reparses.
        _rule("esc-dash", IrSequence(_lit("\\-"))),
        _rule("esc-caret", IrSequence(_lit("\\^"))),
        _rule("esc-rb", IrSequence(_lit("\\]"))),
        _rule("ws", IrSequence(_rep("wsunit")), semantic=False),
        _rule(
            "wsunit",
            IrSequence(IrItem(_WS_CC)),
            IrSequence(_ref("comment")),
            semantic=False,
        ),
        _rule(
            "comment",
            IrSequence(_lit("(*"), IrItem(_NOT_STAR, _STAR), _lit("*)")),
            semantic=False,
        ),
    ),
    "grammar",
)
"""The EBNF grammar of EBNF, authored directly as :class:`IrAst`."""


# ── reductions: parse tree → IR ────────────────────────────────────────────

# strprim tail dispatch: IrNone → the plain literal; IrChr → a single-range class.
_RANGE = IrTypeMap(
    IrAction(IrNoneType, IrArg(0)),
    IrAction(
        IrChr,
        IrBuild(
            IrCharClass,
            IrTuple(
                IrBuild(IrRange, IrTuple(IrBuild(IrChr, IrTuple(IrArg(0))), IrThis()))
            ),
        ),
    ),
)

_HEX_GLYPH = IrPipe(IrJoin(parts=IrArgs()), IrPipe(IrUnradix(16, IrInt), IrGlyph()))
"""Joined hex-digit args -> the decoded character."""

EBNF_REDUCTIONS: IrMap[IrRuleRef, IrSelf] = IrMap(
    IrTuple(
        IrRuleRef("grammar"),
        IrBuild(IrAst, IrTuple(IrBuild(IrSeq), IrPipe(IrArg(0), IrField("name")))),
    ),
    IrTuple(IrRuleRef("rrest"), IrArg(0)),
    IrTuple(IrRuleRef("rule"), IrBuild(IrRule)),
    IrTuple(IrRuleRef("rulename"), IrBuild(IrRuleRef, IrTuple(YIELD))),
    IrTuple(IrRuleRef("alternation"), IrBuild(IrAlternation)),
    IrTuple(IrRuleRef("altrest"), IrArg(0)),
    IrTuple(IrRuleRef("concat"), IrBuild(IrSequence)),
    IrTuple(IrRuleRef("catrest"), IrArg(0)),
    IrTuple(IrRuleRef("factor"), IrArg(0)),
    IrTuple(
        IrRuleRef("repetition"),
        IrBuild(
            IrItem, IrTuple(IrArg(0), IrBuild(IrQuantifier, IrTuple(IrInt(0), IrNone)))
        ),
    ),
    IrTuple(
        IrRuleRef("option"),
        IrBuild(
            IrItem,
            IrTuple(IrArg(0), IrBuild(IrQuantifier, IrTuple(IrInt(0), IrInt(1)))),
        ),
    ),
    IrTuple(
        IrRuleRef("multiplied"),
        IrBuild(
            IrItem,
            IrTuple(IrArg(1), IrBuild(IrQuantifier, IrTuple(IrArg(0), IrArg(0)))),
        ),
    ),
    IrTuple(IrRuleRef("count"), IrPipe(IrJoin(parts=IrArgs()), IrUnradix(10, IrInt))),
    IrTuple(IrRuleRef("quantified"), IrBuild(IrItem)),
    IrTuple(
        IrRuleRef("quant-opt"),
        IrCond(
            test=IrArgs(), then_op=IrArg(0), else_op=IrBuild(IrQuantifier, IrTuple())
        ),
    ),
    IrTuple(IrRuleRef("q-star"), IrBuild(IrQuantifier, IrTuple(IrInt(0), IrNone))),
    IrTuple(IrRuleRef("q-plus"), IrBuild(IrQuantifier, IrTuple(IrInt(1), IrNone))),
    IrTuple(IrRuleRef("q-opt"), IrBuild(IrQuantifier, IrTuple(IrInt(0), IrInt(1)))),
    IrTuple(IrRuleRef("primary"), IrArg(0)),
    IrTuple(IrRuleRef("strprim"), IrPipe(IrArg(1), _RANGE)),
    IrTuple(
        IrRuleRef("rangetail-opt"),
        IrCond(
            test=IrArgs(), then_op=IrBuild(IrChr, IrTuple(IrArg(0))), else_op=IrNone
        ),
    ),
    IrTuple(IrRuleRef("rangetail"), IrArg(0)),
    IrTuple(IrRuleRef("group"), IrArg(0)),
    IrTuple(IrRuleRef("ruleref"), IrArg(0)),
    IrTuple(IrRuleRef("terminal"), IrArg(0)),
    IrTuple(IrRuleRef("dq"), IrBuild(IrLiteral, IrTuple(IrJoin(parts=IrArgs())))),
    IrTuple(IrRuleRef("sq"), IrBuild(IrLiteral, IrTuple(IrJoin(parts=IrArgs())))),
    IrTuple(IrRuleRef("dqunit"), IrArg(0)),
    IrTuple(IrRuleRef("squnit"), IrArg(0)),
    IrTuple(IrRuleRef("esc"), IrArg(0)),
    IrTuple(IrRuleRef("esc-x"), _HEX_GLYPH),
    IrTuple(IrRuleRef("esc-u"), _HEX_GLYPH),
    IrTuple(IrRuleRef("esc-bigu"), _HEX_GLYPH),
    IrTuple(IrRuleRef("esc-n"), IrStr("\n")),
    IrTuple(IrRuleRef("esc-t"), IrStr("\t")),
    IrTuple(IrRuleRef("esc-r"), IrStr("\r")),
    IrTuple(IrRuleRef("esc-bs"), IrStr("\\")),
    IrTuple(IrRuleRef("esc-dq"), IrStr('"')),
    IrTuple(IrRuleRef("esc-sq"), IrStr("'")),
    IrTuple(IrRuleRef("esc-dash"), IrStr("-")),
    IrTuple(IrRuleRef("esc-caret"), IrStr("^")),
    IrTuple(IrRuleRef("esc-rb"), IrStr("]")),
)
"""Per-rule reductions: parse tree → IR (pure IR algebra, the gbnf/abnf idiom)."""


EBNF_NOISE: IrMap = IrMap(
    *(IrTuple(IrRuleRef(name), DROP) for name in EBNF_GRAMMAR.non_semantic),
    IrTuple(IR_DEFAULT, KEEP_REDUCED),
)
"""Child-contribution policy: noise drops, every other rule is kept reduced."""


EBNF_REDUCER = Reducer(
    actions=EBNF_REDUCTIONS, default=YIELD, noise=EBNF_NOISE, literal=DROP
)
"""The configured EBNF reducer."""


# ── emit: canonical IR → EBNF text (doc-producing at structure levels) ─────

_EBNF_QUANTIFIERS: IrMap = IrMap(
    IrTuple(IrQuantifier(1, 1), IrLiteral("")),
    IrTuple(IrQuantifier(0, 1), IrLiteral("?")),
    IrTuple(IrQuantifier(0, IrNone), IrLiteral("*")),
    IrTuple(IrQuantifier(1, IrNone), IrLiteral("+")),
    # Exact (n, n) repetition is the ITEM action's prefix ``n * x``; an open
    # or bounded counted form has no ISO spelling — declarative refusal.
    IrTuple(
        IR_DEFAULT,
        IrRaise(message="{dispatcher}: EBNF cannot spell counted {node_type!r}"),
    ),
)
"""Quantifier → postfix symbol; counted forms refuse (see the item action)."""

# The item's atom half, shared by both quantifier spellings below.
_ATOM_PART = IrCond(
    test=IrIsA("atom", IrAlternation),
    then_op=IrDocConcat(parts=IrTuple(IrText("("), IrChild("atom"), IrText(")"))),
    else_op=IrChild("atom"),
)

# Exact-n test: quantifier lo == hi and lo > 1 ((1,1) is the empty postfix;
# an open bound guards first — its ``hi`` is IrNone, unreadable as IrInt).
# IrAt(1, …) rebinds the focus to the item's RAW quantifier child.
_IS_EXACT_N = IrAt(
    1,
    IrCond(
        test=IrIsA("hi", IrNoneType),
        then_op=IrInt(0),
        else_op=IrAnd(
            IrCompare(IrField("lo", IrInt), IrOp("=="), IrField("hi", IrInt)),
            IrCompare(IrField("lo", IrInt), IrOp(">"), IrInt(1)),
        ),
    ),
)

EBNF_ACTIONS = IrTypeMap(
    IrAction(
        IrLiteral, IrConcat(parts=IrTuple(IrLiteral('"'), IrEscape(), IrLiteral('"')))
    ),
    # No native class syntax: a single member emits bare, several as a
    # parenthesised ``..``/``|`` alternation of terminals/ranges.
    IrAction(
        IrCharClass,
        IrCond(
            test=IrCompare(IrLen(), IrOp("=="), IrInt(1)),
            then_op=IrJoin(parts=IrChildren()),
            # A wide class expansion is its own fit group, so its member
            # alternation wraps like any other (unlike GBNF/ABNF, whose
            # class spellings are compact single tokens).
            else_op=IrGroup(
                IrDocConcat(
                    parts=IrTuple(
                        IrText("("),
                        IrDocJoin(parts=IrChildren(), separator=IrLine(" | ", " |")),
                        IrText(")"),
                    )
                )
            ),
        ),
    ),
    IrAction(
        IrChr, IrConcat(parts=IrTuple(IrLiteral('"'), IrEscapePoint(), IrLiteral('"')))
    ),
    IrAction(
        IrRange,
        IrConcat(
            parts=IrTuple(
                IrLiteral('"'),
                IrPipe(IrField("lo", IrInt), IrEscapePoint()),
                IrLiteral('".."'),
                IrPipe(IrField("hi", IrInt), IrEscapePoint()),
                IrLiteral('"'),
            )
        ),
    ),
    # Bare IrStr: the run leaf inside a class — concrete leaves win by MRO.
    IrAction(IrStr, IrEmit()),
    # No native negation — strict declarative refusal (the ABNF precedent).
    IrAction(
        IrNot,
        IrRaise(message="{dispatcher}: EBNF does not support {node_type!r}"),
    ),
    # Token terminals (`<…>`) are a GBNF surface; EBNF refuses declaratively.
    IrAction(
        IrAlphabet,
        IrRaise(message="{dispatcher}: token terminals (<…>) are GBNF-only, not EBNF"),
    ),
    IrAction(IrRuleRef, IrEmit()),
    IrAction(IrQuantifier, _EBNF_QUANTIFIERS),
    # Exact-n rides prefix (``3 * x``); everything else is atom + postfix.
    IrAction(
        IrItem,
        IrCond(
            test=_IS_EXACT_N,
            then_op=IrDocConcat(
                parts=IrTuple(
                    IrAt(1, IrField("lo", IrStr)),
                    IrText(" * "),
                    _ATOM_PART,
                )
            ),
            else_op=IrDocConcat(parts=IrTuple(_ATOM_PART, IrChild("quantifier"))),
        ),
    ),
    IrAction(
        IrSequence,
        IrGroup(
            IrDocJoin(
                parts=IrChildren(),
                separator=IrLine(", ", ","),
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
                    parts=IrTuple(
                        IrField("name"), IrText(" = "), IrChild("body"), IrText(" ;")
                    )
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
"""The emit half: per-IR-type actions, doc-producing at structure levels."""


class _EbnfFlavour(IrFlavour):
    """EBNF flavour singleton class."""

    actions: IrTypeMap = EBNF_ACTIONS

    name: ClassVar[str] = "ebnf"
    extensions: ClassVar[tuple[str, ...]] = (".ebnf",)
    escapes: ClassVar[EscapeCodec] = EBNF_ESCAPES
    line_comment: ClassVar[str] = ""
    grammar: ClassVar[IrAst] = EBNF_GRAMMAR
    reducer: ClassVar[Reducer] = EBNF_REDUCER


EBNF_FLAVOUR = _EbnfFlavour()
"""The EBNF flavour singleton."""
