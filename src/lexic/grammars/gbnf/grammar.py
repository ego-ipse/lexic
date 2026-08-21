"""Native GBNF self-grammar, rooted at the grammar rule."""

# Declarative grammar tables intentionally share structural forms.
# pylint: disable=duplicate-code

from lexic.grammars.gbnf.grammar_tail import GBNF_TAIL
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
        *GBNF_TAIL,
    ),
    "grammar",
)
