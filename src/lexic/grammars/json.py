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

from lexic.ir.action import (
    IrArg,
    IrArgs,
    IrBuild,
    IrGlyph,
    IrJoin,
    IrPipe,
    IrRaise,
    IrUnradix,
)
from lexic.ir.base import IrInt, IrNone, IrSelf, IrSeq, IrStr, IrTuple
from lexic.ir.encoding import IrUtf
from lexic.ir.mapping import IR_DEFAULT, IrMap
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
from lexic.parsing.earley.reduce import DROP, KEEP_REDUCED, YIELD, Reducer

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
            semantic=False,
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
            semantic=False,
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
            semantic=False,
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
            semantic=False,
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
            semantic=False,
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
            semantic=False,
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
        IrRule(
            "quotation-mark",
            IrAlternation(IrSequence(IrItem(IrLiteral('"')))),
            semantic=False,
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
            semantic=False,
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


# ── the reduction kit (a reducer is something any grammar can have) ───────

_HEX4 = IrPipe(
    IrPipe(
        IrJoin(IrTuple(IrArg(1), IrArg(2), IrArg(3), IrArg(4))),
        IrUnradix(16, IrInt),
    ),
    IrGlyph(),
)
"""The ``\\uXXXX`` escape's four hex-digit args → one code-unit char."""

_CHAR = IrPipe(
    YIELD,
    IrMap(
        *(
            IrTuple(IrStr("\\" + key), IrStr(val))
            for key, val in (
                ('"', '"'),
                ("\\", "\\"),
                ("/", "/"),
                ("b", "\b"),
                ("f", "\f"),
                ("n", "\n"),
                ("r", "\r"),
                ("t", "\t"),
            )
        ),
        IrTuple(
            IR_DEFAULT,
            IrPipe(
                IrArg(0),
                IrMap(
                    IrTuple(IrStr("\\"), _HEX4),
                    IrTuple(IR_DEFAULT, IrArg(0)),
                ),
            ),
        ),
    ),
)
"""One string char, decoded by value-keyed dispatch on its source text.

The eight short escapes are exact two-char keys of the char's ``YIELD`` text
(the anonymous short-class terminal never reaches the channel under
``literal=DROP`` — its text does). Everything else is either an unescaped
char (the channel's one ``unescaped`` arg) or the ``\\uXXXX`` unit escape —
told apart by the channel's ``escape`` marker (``unescaped`` excludes the
backslash, so the marker is unambiguous), with the four ``hexdig`` args
decoding through :data:`_HEX4`."""

JSON_REDUCTIONS: IrMap[IrRuleRef, IrSelf] = IrMap(
    IrTuple(IrRuleRef("json-text"), IrArg(0)),
    IrTuple(IrRuleRef("value"), IrArg(0)),
    IrTuple(IrRuleRef("object"), IrBuild(IrMap)),
    IrTuple(IrRuleRef("member"), IrBuild(IrTuple)),
    IrTuple(IrRuleRef("array"), IrBuild(IrTuple)),
    # A json string's escapes denote UTF-16 code units — each decodes
    # per-unit in _CHAR, then the assembled string passes through the IrUtf
    # codec once (surrogate pairs combine into their code points).
    IrTuple(IrRuleRef("string"), IrPipe(IrJoin(IrArgs()), IrUtf())),
    IrTuple(IrRuleRef("char"), _CHAR),
    IrTuple(IrRuleRef("escape"), IrStr("\\")),
    IrTuple(IrRuleRef("true"), IrInt(1)),
    IrTuple(IrRuleRef("false"), IrInt(0)),
    IrTuple(IrRuleRef("null"), IrNone),
    # Integer forms decode to IrInt (IrInt('-12') == -12 — the scalar
    # constructor IS the sign-aware decode). Fractional / exponent forms
    # refuse loudly: the IR carries no float leaf (a pending vocabulary
    # decision), and a raw-string stand-in would be indistinguishable from
    # a json string — value-space fidelity beats partial coverage.
    IrTuple(IrRuleRef("number"), IrBuild(IrInt, IrTuple(IrJoin(IrArgs())))),
    IrTuple(IrRuleRef("int"), IrJoin(IrArgs())),
    IrTuple(
        IrRuleRef("frac"),
        IrRaise(message="json: fractional numbers have no IR value (no float leaf)"),
    ),
    IrTuple(
        IrRuleRef("exp"),
        IrRaise(message="json: exponent numbers have no IR value (no float leaf)"),
    ),
    IrTuple(IrRuleRef("minus"), IrStr("-")),
    IrTuple(IrRuleRef("plus"), IrStr("+")),
    IrTuple(IrRuleRef("zero"), IrStr("0")),
    IrTuple(IrRuleRef("decimal-point"), IrStr(".")),
    IrTuple(IR_DEFAULT, YIELD),
)
"""Per-rule reductions: parse tree → the json value as IR (objects ``IrMap``,
arrays ``IrTuple``, strings decoded ``IrStr``, truth ``IrInt``, null
``IrNone``). Paired with :data:`JSON_NOISE`."""

JSON_NOISE: IrMap = IrMap(
    *(IrTuple(IrRuleRef(name), DROP) for name in JSON_GRAMMAR.non_semantic),
    IrTuple(IR_DEFAULT, KEEP_REDUCED),
)
"""Child-contribution policy, derived from the grammar's own noise flags
(``escape`` stays semantic — it is :data:`_CHAR`'s dispatch marker)."""

JSON_REDUCER = Reducer(reductions=JSON_REDUCTIONS, noise=JSON_NOISE, literal=DROP)
"""The configured json reducer — the grammar's parse half."""
