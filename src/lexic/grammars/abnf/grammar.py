"""Native ABNF self-grammar."""

# Declarative grammar tables intentionally share structural forms.
# pylint: disable=duplicate-code

from lexic.ir import (
    IrAlternation,
    IrAst,
    IrCharClass,
    IrChr,
    IrItem,
    IrLiteral,
    IrNone,
    IrQuantifier,
    IrRange,
    IrRule,
    IrRuleRef,
    IrSeq,
    IrSequence,
)


def _mark(letter: str) -> IrCharClass:
    """Return the case-insensitive marker-letter class for ``letter``."""
    return IrCharClass(IrChr(letter.upper()), IrChr(letter))


MARK_X, MARK_D, MARK_B = _mark("x"), _mark("d"), _mark("b")
MARK_S, MARK_I = _mark("s"), _mark("i")

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
        IrRule("smark", IrAlternation(IrSequence(IrItem(MARK_S))), False),
        IrRule(
            "csbody",
            IrAlternation(
                IrSequence(IrItem(IrRuleRef("qchar"), IrQuantifier(0, IrNone)))
            ),
        ),
        IrRule("imark", IrAlternation(IrSequence(IrItem(MARK_I))), False),
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
        IrRule("xmark", IrAlternation(IrSequence(IrItem(MARK_X))), False),
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
        IrRule("dmark", IrAlternation(IrSequence(IrItem(MARK_D))), False),
        IrRule(
            "d-tail",
            IrAlternation(
                IrSequence(),
                IrSequence(IrItem(IrRuleRef("d-range"))),
                IrSequence(IrItem(IrRuleRef("d-seq"))),
            ),
        ),
        IrRule("bmark", IrAlternation(IrSequence(IrItem(MARK_B))), False),
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
