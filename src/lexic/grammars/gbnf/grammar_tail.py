"""Late canonical rules of the native GBNF self-grammar."""

# Declarative grammar tables intentionally share structural forms.
# pylint: disable=duplicate-code

from lexic.ir import (
    IrAlternation,
    IrCharClass,
    IrChr,
    IrItem,
    IrLiteral,
    IrRange,
    IrRule,
    IrRuleRef,
    IrSequence,
)


GBNF_TAIL = (
    IrRule(
        "digit",
        IrAlternation(IrSequence(IrItem(IrCharClass(IrRange(IrChr(48), IrChr(57)))))),
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
)
