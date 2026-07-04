"""JSON grammar as native IR — the canonical, flavour-neutral representation.

This is the JSON grammar (RFC 8259) authored directly as :class:`IrAst`, the
ground-truth target the GBNF and ABNF front-ends both reduce to. It is stored in
**canonical form** — the exact shape :func:`~lexic.ir.canonical.canonicalize`
produces — so ``canonicalize(JSON_GRAMMAR) == JSON_GRAMMAR`` and
``canonicalize(parse(json.gbnf)) == canonicalize(parse(json.abnf)) == JSON_GRAMMAR``.

Canonical-form choices: names are lowercase/hyphenated; single code points are
:class:`IrLiteral`; multi-char keywords are :class:`IrLiteral`; char-point sets
are one normalised :class:`IrCharClass` (sorted, ranges coalesced); negation is
expressed as positive :class:`IrRange` spans; rules are in canonical order
(start first, first-reference order).
"""

from __future__ import annotations

from lexic.ir.base import IrNone, IrSeq
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

JSON_GRAMMAR = IrAst(
    IrSeq(
        IrRule(
            "json-text",
            IrAlternation(
                IrSequence(
                    IrItem(IrRuleRef("ws")),
                    IrItem(IrRuleRef("value")),
                    IrItem(IrRuleRef("ws")),
                )
            ),
        ),
        IrRule(
            "ws",
            IrAlternation(
                IrSequence(
                    IrItem(
                        IrCharClass(IrRange(IrChr(9), IrChr(10)), IrChr(13), IrChr(32)),
                        IrQuantifier(0, IrNone),
                    )
                )
            ),
        ),
        IrRule(
            "value",
            IrAlternation(
                IrSequence(IrItem(IrRuleRef("false"))),
                IrSequence(IrItem(IrRuleRef("null"))),
                IrSequence(IrItem(IrRuleRef("true"))),
                IrSequence(IrItem(IrRuleRef("object"))),
                IrSequence(IrItem(IrRuleRef("array"))),
                IrSequence(IrItem(IrRuleRef("number"))),
                IrSequence(IrItem(IrRuleRef("string"))),
            ),
        ),
        IrRule("false", IrAlternation(IrSequence(IrItem(IrLiteral("false"))))),
        IrRule("null", IrAlternation(IrSequence(IrItem(IrLiteral("null"))))),
        IrRule("true", IrAlternation(IrSequence(IrItem(IrLiteral("true"))))),
        IrRule(
            "object",
            IrAlternation(
                IrSequence(
                    IrItem(IrRuleRef("begin-object")),
                    IrItem(
                        IrAlternation(
                            IrSequence(
                                IrItem(IrRuleRef("member")),
                                IrItem(
                                    IrAlternation(
                                        IrSequence(
                                            IrItem(IrRuleRef("value-separator")),
                                            IrItem(IrRuleRef("member")),
                                        )
                                    ),
                                    IrQuantifier(0, IrNone),
                                ),
                            )
                        ),
                        IrQuantifier(0),
                    ),
                    IrItem(IrRuleRef("end-object")),
                )
            ),
        ),
        IrRule(
            "array",
            IrAlternation(
                IrSequence(
                    IrItem(IrRuleRef("begin-array")),
                    IrItem(
                        IrAlternation(
                            IrSequence(
                                IrItem(IrRuleRef("value")),
                                IrItem(
                                    IrAlternation(
                                        IrSequence(
                                            IrItem(IrRuleRef("value-separator")),
                                            IrItem(IrRuleRef("value")),
                                        )
                                    ),
                                    IrQuantifier(0, IrNone),
                                ),
                            )
                        ),
                        IrQuantifier(0),
                    ),
                    IrItem(IrRuleRef("end-array")),
                )
            ),
        ),
        IrRule(
            "number",
            IrAlternation(
                IrSequence(
                    IrItem(IrRuleRef("minus"), IrQuantifier(0)),
                    IrItem(IrRuleRef("int")),
                    IrItem(IrRuleRef("frac"), IrQuantifier(0)),
                    IrItem(IrRuleRef("exp"), IrQuantifier(0)),
                )
            ),
        ),
        IrRule(
            "string",
            IrAlternation(
                IrSequence(
                    IrItem(IrRuleRef("quotation-mark")),
                    IrItem(IrRuleRef("char"), IrQuantifier(0, IrNone)),
                    IrItem(IrRuleRef("quotation-mark")),
                )
            ),
        ),
        IrRule(
            "begin-object",
            IrAlternation(
                IrSequence(
                    IrItem(IrRuleRef("ws")),
                    IrItem(IrLiteral("{")),
                    IrItem(IrRuleRef("ws")),
                )
            ),
        ),
        IrRule(
            "member",
            IrAlternation(
                IrSequence(
                    IrItem(IrRuleRef("string")),
                    IrItem(IrRuleRef("name-separator")),
                    IrItem(IrRuleRef("value")),
                )
            ),
        ),
        IrRule(
            "value-separator",
            IrAlternation(
                IrSequence(
                    IrItem(IrRuleRef("ws")),
                    IrItem(IrLiteral(",")),
                    IrItem(IrRuleRef("ws")),
                )
            ),
        ),
        IrRule(
            "end-object",
            IrAlternation(
                IrSequence(
                    IrItem(IrRuleRef("ws")),
                    IrItem(IrLiteral("}")),
                    IrItem(IrRuleRef("ws")),
                )
            ),
        ),
        IrRule(
            "begin-array",
            IrAlternation(
                IrSequence(
                    IrItem(IrRuleRef("ws")),
                    IrItem(IrLiteral("[")),
                    IrItem(IrRuleRef("ws")),
                )
            ),
        ),
        IrRule(
            "end-array",
            IrAlternation(
                IrSequence(
                    IrItem(IrRuleRef("ws")),
                    IrItem(IrLiteral("]")),
                    IrItem(IrRuleRef("ws")),
                )
            ),
        ),
        IrRule("minus", IrAlternation(IrSequence(IrItem(IrLiteral("-"))))),
        IrRule(
            "int",
            IrAlternation(
                IrSequence(IrItem(IrRuleRef("zero"))),
                IrSequence(
                    IrItem(IrRuleRef("digit1-9")),
                    IrItem(IrRuleRef("digit"), IrQuantifier(0, IrNone)),
                ),
            ),
        ),
        IrRule(
            "frac",
            IrAlternation(
                IrSequence(
                    IrItem(IrRuleRef("decimal-point")),
                    IrItem(IrRuleRef("digit"), IrQuantifier(1, IrNone)),
                )
            ),
        ),
        IrRule(
            "exp",
            IrAlternation(
                IrSequence(
                    IrItem(IrRuleRef("e")),
                    IrItem(
                        IrAlternation(
                            IrSequence(IrItem(IrRuleRef("minus"))),
                            IrSequence(IrItem(IrRuleRef("plus"))),
                        ),
                        IrQuantifier(0),
                    ),
                    IrItem(IrRuleRef("digit"), IrQuantifier(1, IrNone)),
                )
            ),
        ),
        IrRule("quotation-mark", IrAlternation(IrSequence(IrItem(IrLiteral('"'))))),
        IrRule(
            "char",
            IrAlternation(
                IrSequence(IrItem(IrRuleRef("unescaped"))),
                IrSequence(
                    IrItem(IrRuleRef("escape")),
                    IrItem(
                        IrAlternation(
                            IrSequence(
                                IrItem(
                                    IrCharClass(
                                        IrChr(34),
                                        IrChr(47),
                                        IrChr(92),
                                        IrChr(98),
                                        IrChr(102),
                                        IrChr(110),
                                        IrChr(114),
                                        IrChr(116),
                                    )
                                )
                            ),
                            IrSequence(
                                IrItem(IrLiteral("u")),
                                IrItem(IrRuleRef("hexdig"), IrQuantifier(4, 4)),
                            ),
                        )
                    ),
                ),
            ),
        ),
        IrRule(
            "name-separator",
            IrAlternation(
                IrSequence(
                    IrItem(IrRuleRef("ws")),
                    IrItem(IrLiteral(":")),
                    IrItem(IrRuleRef("ws")),
                )
            ),
        ),
        IrRule("zero", IrAlternation(IrSequence(IrItem(IrLiteral("0"))))),
        IrRule(
            "digit1-9",
            IrAlternation(
                IrSequence(IrItem(IrCharClass(IrRange(IrChr(49), IrChr(57)))))
            ),
        ),
        IrRule(
            "digit",
            IrAlternation(
                IrSequence(IrItem(IrCharClass(IrRange(IrChr(48), IrChr(57)))))
            ),
        ),
        IrRule("decimal-point", IrAlternation(IrSequence(IrItem(IrLiteral("."))))),
        IrRule(
            "e", IrAlternation(IrSequence(IrItem(IrCharClass(IrChr(69), IrChr(101)))))
        ),
        IrRule("plus", IrAlternation(IrSequence(IrItem(IrLiteral("+"))))),
        IrRule(
            "unescaped",
            IrAlternation(
                IrSequence(
                    IrItem(
                        IrCharClass(
                            IrRange(IrChr(32), IrChr(33)),
                            IrRange(IrChr(35), IrChr(91)),
                            IrRange(IrChr(93), IrChr(1114111)),
                        )
                    )
                )
            ),
        ),
        IrRule("escape", IrAlternation(IrSequence(IrItem(IrLiteral("\\"))))),
        IrRule(
            "hexdig",
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
    ),
    "json-text",
)
"""The JSON grammar (RFC 8259) as a canonical :class:`IrAst`."""
