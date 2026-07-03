"""JSON grammar as native IR — the canonical, flavour-neutral representation.

This is the JSON grammar (RFC 8259) authored directly as :class:`IrAst`, not
parsed from GBNF/ABNF source. It is the ground-truth target the GBNF and ABNF
front-ends should both reduce to, and it stands on its own once the Lark
metagrammars are retired.

Canonical-form choices (the cross-flavour canonicalizations):

- single code points (``{``, ``}``, ``:``, the ``\\`` escape, …) are
  :class:`IrLiteral`, not one-member char classes;
- multi-char keywords (``false``/``null``/``true``) are :class:`IrLiteral`;
- the ``unescaped`` set is **positive** ``IrRange`` spans (the complement of
  ``"``/``\\``/controls), since ABNF cannot express negation;
- sets of single chars (whitespace, ``eE``, hex digits) are one
  :class:`IrCharClass`.
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
    rules=IrSeq(
        IrRule(
            "JSON-text",
            IrAlternation(
                IrSequence(
                    IrItem(IrRuleRef("ws")),
                    IrItem(IrRuleRef("value")),
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
            "end-array",
            IrAlternation(
                IrSequence(
                    IrItem(IrRuleRef("ws")),
                    IrItem(IrLiteral("]")),
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
            "name-separator",
            IrAlternation(
                IrSequence(
                    IrItem(IrRuleRef("ws")),
                    IrItem(IrLiteral(":")),
                    IrItem(IrRuleRef("ws")),
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
            "ws",
            IrAlternation(
                IrSequence(
                    IrItem(
                        IrCharClass(IrChr(" "), IrChr("\t"), IrChr("\n"), IrChr("\r")),
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
                        IrQuantifier(0, 1),
                    ),
                    IrItem(IrRuleRef("end-object")),
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
                        IrQuantifier(0, 1),
                    ),
                    IrItem(IrRuleRef("end-array")),
                )
            ),
        ),
        IrRule(
            "number",
            IrAlternation(
                IrSequence(
                    IrItem(IrRuleRef("minus"), IrQuantifier(0, 1)),
                    IrItem(IrRuleRef("int")),
                    IrItem(IrRuleRef("frac"), IrQuantifier(0, 1)),
                    IrItem(IrRuleRef("exp"), IrQuantifier(0, 1)),
                )
            ),
        ),
        IrRule("decimal-point", IrAlternation(IrSequence(IrItem(IrLiteral("."))))),
        IrRule(
            "digit1-9",
            IrAlternation(
                IrSequence(IrItem(IrCharClass(IrRange(IrChr("1"), IrChr("9")))))
            ),
        ),
        IrRule(
            "e",
            IrAlternation(IrSequence(IrItem(IrCharClass(IrChr("e"), IrChr("E"))))),
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
                        IrQuantifier(0, 1),
                    ),
                    IrItem(IrRuleRef("digit"), IrQuantifier(1, IrNone)),
                )
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
            "int",
            IrAlternation(
                IrSequence(IrItem(IrRuleRef("zero"))),
                IrSequence(
                    IrItem(IrRuleRef("digit1-9")),
                    IrItem(IrRuleRef("digit"), IrQuantifier(0, IrNone)),
                ),
            ),
        ),
        IrRule("minus", IrAlternation(IrSequence(IrItem(IrLiteral("-"))))),
        IrRule("plus", IrAlternation(IrSequence(IrItem(IrLiteral("+"))))),
        IrRule("zero", IrAlternation(IrSequence(IrItem(IrLiteral("0"))))),
        IrRule(
            "digit",
            IrAlternation(
                IrSequence(IrItem(IrCharClass(IrRange(IrChr("0"), IrChr("9")))))
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
                                        IrChr('"'),
                                        IrChr("\\"),
                                        IrChr("/"),
                                        IrChr("b"),
                                        IrChr("f"),
                                        IrChr("n"),
                                        IrChr("r"),
                                        IrChr("t"),
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
        IrRule("escape", IrAlternation(IrSequence(IrItem(IrLiteral("\\"))))),
        IrRule("quotation-mark", IrAlternation(IrSequence(IrItem(IrLiteral('"'))))),
        IrRule(
            "unescaped",
            IrAlternation(
                IrSequence(
                    IrItem(
                        IrCharClass(
                            IrRange(IrChr(chr(0x20)), IrChr(chr(0x21))),
                            IrRange(IrChr(chr(0x23)), IrChr(chr(0x5B))),
                            IrRange(IrChr(chr(0x5D)), IrChr(chr(0x10FFFF))),
                        )
                    )
                )
            ),
        ),
        IrRule(
            "hexdig",
            IrAlternation(
                IrSequence(
                    IrItem(
                        IrCharClass(
                            IrRange(IrChr("0"), IrChr("9")),
                            IrRange(IrChr("A"), IrChr("F")),
                            IrRange(IrChr("a"), IrChr("f")),
                        )
                    )
                )
            ),
        ),
    ),
    start="JSON-text",
)
"""The JSON grammar (RFC 8259) as a canonical :class:`IrAst`."""
