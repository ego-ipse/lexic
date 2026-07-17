"""Generate the flavour manifests (`grammars/*.flavour.ir`).

A manifest is one IR-constructor-notation expression — an ``IrMap`` of the seven
sections :func:`lexic.compile.loader.load_flavour` consumes. This dev-time tool
repr-generates them (the demo_05 licence): the ``grammar``/``reductions``/
``actions`` sections come straight off the authored singletons via :func:`repr`
(a superset of the notation), and the ``escapes`` section is spelled as the five
IR dyad tables (ruling D1). It NEVER reprs a ``Reducer`` or a noise map —
``IrLambda.__repr__`` can raise, and a manifest carries no noise section (the
loader derives noise from the self-grammar's ``semantic=False`` flags).

GBNF and ABNF are generated from their shipped singletons. EBNF has no shipped
singleton — its authoritative IR (a small EBNF-subset self-grammar + lambda-free
reductions + emit actions) lives HERE, so the demo flavour ships as pure manifest
text only.

Run: ``uv run python tools/gen_manifests.py`` (writes into ``src/lexic/grammars/``
and ``resources/ground_truth/arithmetic.ebnf``).
"""

from __future__ import annotations

from pathlib import Path
from typing import ClassVar

from lexic.grammars.abnf import (
    ABNF_ACTIONS,
    ABNF_ESCAPES,
    ABNF_GRAMMAR,
    ABNF_REDUCTIONS,
)
from lexic.grammars.gbnf import (
    GBNF_ACTIONS,
    GBNF_ESCAPES,
    GBNF_GRAMMAR,
    GBNF_REDUCTIONS,
)
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
    IrLen,
    IrPipe,
    IrThis,
)
from lexic.ir.base import IrInt, IrNone, IrNoneType, IrSelf, IrSeq, IrStr, IrTuple
from lexic.ir.escapes import EscapeCodec
from lexic.ir.flavour import IrEscape, IrEscapePoint
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
from lexic.ir.operators import IrOp
from lexic.parsing.earley.reduce import YIELD

# ── section spelling ──────────────────────────────────────────────────────


def escapes_as_ir(codec: EscapeCodec) -> IrMap:
    """The five codec tables spelled as IR dyads (ruling D1).

    :param codec: The escape codec to serialize.
    :returns: The ``escapes`` section ``IrMap`` of the five named tables.
    """
    return IrMap(
        IrTuple(
            IrStr("short"),
            IrMap(
                *(IrTuple(IrStr(k), IrStr(v)) for k, v in codec.SHORT_ESCAPES.items())
            ),
        ),
        IrTuple(
            IrStr("hex"),
            IrTuple(*(IrTuple(IrStr(t), IrInt(n)) for t, n in codec.HEX_ESCAPES)),
        ),
        IrTuple(
            IrStr("class-short"),
            IrMap(*(IrTuple(IrInt(k), IrStr(v)) for k, v in codec.CLASS_SHORT.items())),
        ),
        IrTuple(
            IrStr("class-meta"),
            IrTuple(*(IrStr(c) for c in sorted(codec.CLASS_META))),
        ),
        IrTuple(
            IrStr("quote-safe"),
            IrTuple(*(IrTuple(IrInt(a), IrInt(b)) for a, b in codec.QUOTE_SAFE)),
        ),
    )


def format_manifest(
    name: str,
    extensions: tuple[str, ...],
    line_comment: str,
    codec: EscapeCodec,
    grammar: IrAst,
    reductions: IrMap,
    actions: IrTypeMap,
) -> str:
    """One manifest as readable notation text — each section on its own line.

    Section values are ``repr``'d (a superset of the notation); the surrounding
    ``IrMap(...)`` is laid out by hand so the file is greppable and hand-editable.
    """
    sections = [
        ("name", repr(IrStr(name))),
        ("extensions", repr(IrTuple(*(IrStr(e) for e in extensions)))),
        ("line-comment", repr(IrStr(line_comment))),
        ("escapes", repr(escapes_as_ir(codec))),
        ("grammar", repr(grammar)),
        ("reductions", repr(reductions)),
        ("actions", repr(actions)),
    ]
    lines = [f"    IrTuple(IrStr({key!r}), {value})" for key, value in sections]
    return "IrMap(\n" + ",\n".join(lines) + "\n)\n"


# ── the EBNF-subset flavour (authoritative source for the manifest) ────────
#
# A demo EBNF flavour: ISO-family surface (``=``/``;`` rules, ``,`` concatenation,
# ``(* *)`` comments, ``'``/``"`` terminals, ``..`` char ranges, ``{ }``/``[ ]``
# repetition/option, ``( )`` grouping, postfix ``* + ?``). No char-class syntax —
# a char class is spelled as an alternation of single-char terminals/ranges, and
# canonicalisation merges it. Reductions are lambda-free IR algebra (the gbnf/abnf
# idiom); emit actions render canonical IR back to postfix EBNF.

_STAR = IrQuantifier(0, IrNone)


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
        _rule("esc-n", IrSequence(_lit("\\n"))),
        _rule("esc-t", IrSequence(_lit("\\t"))),
        _rule("esc-r", IrSequence(_lit("\\r"))),
        _rule("esc-bs", IrSequence(_lit("\\\\"))),
        _rule("esc-dq", IrSequence(_lit('\\"'))),
        _rule("esc-sq", IrSequence(_lit("\\'"))),
        # Accept the class-context escapes the emit side spells via IrEscapePoint
        # (CLASS_META ``\- \^ \]``) so an emitted grammar reparses.
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
    IrTuple(IrRuleRef("dq"), IrBuild(IrLiteral, IrTuple(IrJoin(IrArgs())))),
    IrTuple(IrRuleRef("sq"), IrBuild(IrLiteral, IrTuple(IrJoin(IrArgs())))),
    IrTuple(IrRuleRef("dqunit"), IrArg(0)),
    IrTuple(IrRuleRef("squnit"), IrArg(0)),
    IrTuple(IrRuleRef("esc"), IrArg(0)),
    IrTuple(IrRuleRef("esc-n"), IrStr("\n")),
    IrTuple(IrRuleRef("esc-t"), IrStr("\t")),
    IrTuple(IrRuleRef("esc-r"), IrStr("\r")),
    IrTuple(IrRuleRef("esc-bs"), IrStr("\\")),
    IrTuple(IrRuleRef("esc-dq"), IrStr('"')),
    IrTuple(IrRuleRef("esc-sq"), IrStr("'")),
    IrTuple(IrRuleRef("esc-dash"), IrStr("-")),
    IrTuple(IrRuleRef("esc-caret"), IrStr("^")),
    IrTuple(IrRuleRef("esc-rb"), IrStr("]")),
    IrTuple(IR_DEFAULT, YIELD),
)


# EBNF emit: canonical IR → postfix EBNF text.
_EBNF_QUANTIFIERS: IrMap[IrQuantifier, IrLiteral] = IrMap(
    IrTuple(IrQuantifier(1, 1), IrLiteral("")),
    IrTuple(IrQuantifier(0, 1), IrLiteral("?")),
    IrTuple(IrQuantifier(0, IrNone), IrLiteral("*")),
    IrTuple(IrQuantifier(1, IrNone), IrLiteral("+")),
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
            else_op=IrConcat(
                parts=IrTuple(
                    IrLiteral("("),
                    IrJoin(parts=IrChildren(), separator=IrLiteral(" | ")),
                    IrLiteral(")"),
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
    IrAction(IrRuleRef, IrEmit()),
    IrAction(IrQuantifier, _EBNF_QUANTIFIERS),
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
        IrJoin(parts=IrChildren(), separator=IrLiteral(", "), empty=IrLiteral('""')),
    ),
    IrAction(
        IrAlternation,
        IrJoin(parts=IrChildren(), separator=IrLiteral(" | "), empty=IrLiteral("")),
    ),
    IrAction(
        IrRule,
        IrConcat(
            parts=IrTuple(
                IrField("name"), IrLiteral(" = "), IrChild("body"), IrLiteral(" ;")
            )
        ),
    ),
    IrAction(IrAst, IrConcat(parts=IrTuple(IrChild("rules"), IrLiteral("\n")))),
    IrAction(
        IrTuple,
        IrJoin(parts=IrChildren(), separator=IrLiteral("\n"), empty=IrLiteral("")),
    ),
)


ARITHMETIC_EBNF = """\
(* arithmetic — an EBNF-subset demo flavour; parses to the same canonical IR
   as arithmetic.gbnf *)
root  = ( expr, "=", ws, term, "\\n" )+ ;
expr  = term, { ("-" | "+" | "*" | "/"), term } ;
term  = ident | num | ( "(", ws, expr, ")", ws ) ;
ident = "a".."z", { "a".."z" | "0".."9" | "_" }, ws ;
num   = "0".."9"+, ws ;
ws    = { " " | "\\t" | "\\n" } ;
"""


# ── entry ──────────────────────────────────────────────────────────────────

_GRAMMARS = Path("src/lexic/grammars")
_GROUND_TRUTH = Path("resources/ground_truth")


def _write(path: Path, text: str) -> None:
    path.write_text(text, encoding="utf-8")
    print(f"wrote {path} ({len(text)} bytes)")


def main() -> None:
    """Generate the three manifests + the demo EBNF corpus grammar."""
    _write(
        _GRAMMARS / "gbnf.flavour.ir",
        format_manifest(
            "gbnf",
            (".gbnf",),
            "#",
            GBNF_ESCAPES,
            GBNF_GRAMMAR,
            GBNF_REDUCTIONS,
            GBNF_ACTIONS,
        ),
    )
    _write(
        _GRAMMARS / "abnf.flavour.ir",
        format_manifest(
            "abnf",
            (".abnf",),
            ";",
            ABNF_ESCAPES,
            ABNF_GRAMMAR,
            ABNF_REDUCTIONS,
            ABNF_ACTIONS,
        ),
    )
    _write(
        _GRAMMARS / "ebnf.flavour.ir",
        format_manifest(
            "ebnf",
            (".ebnf",),
            "",
            _EbnfEscapes(),
            EBNF_GRAMMAR,
            EBNF_REDUCTIONS,
            EBNF_ACTIONS,
        ),
    )
    _write(_GROUND_TRUTH / "arithmetic.ebnf", ARITHMETIC_EBNF)


class _EbnfEscapes(EscapeCodec):
    """EBNF escape tables — the demo flavour's quoted-terminal / class codec."""

    SHORT_ESCAPES: ClassVar[dict[str, str]] = {
        "n": "\n",
        "t": "\t",
        "r": "\r",
        '"': '"',
        "'": "'",
        "\\": "\\",
    }
    HEX_ESCAPES: ClassVar[tuple[tuple[str, int], ...]] = ()
    CLASS_SHORT: ClassVar[dict[int, str]] = {0x0A: "\\n", 0x09: "\\t", 0x0D: "\\r"}
    CLASS_META: ClassVar[frozenset[str]] = frozenset("\\]-^")


if __name__ == "__main__":
    main()
