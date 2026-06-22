"""ABNF grammar as native IR, plus the reduction table that recovers IR from a
parse — the text→IR half of an ABNF flavour, with no Lark.

Two artifacts, mirroring how a flavour pairs structure with per-node rules:

- :data:`ABNF_GRAMMAR` — the ABNF grammar of ABNF (RFC 5234 §4 + Appendix B.1),
  authored directly as :class:`~lexic.ir.nodes.IrAst`, exactly as ``json.py``
  authors JSON (fully explicit, no construction helpers). Driven by
  :mod:`lexic.parsing_2` it parses ABNF source into a derivation; the
  self-hosting fixpoint is ``parse(ABNF_GRAMMAR, abnf_source)`` reducing back to
  ``ABNF_GRAMMAR``.
- :data:`ABNF_REDUCTIONS` — the "meta notation": an
  :class:`~lexic.ir.mapping.IrMap` from each rule's
  :class:`~lexic.ir.nodes.IrRuleRef` to a body that folds that rule's parse-tree
  children into an IR node. The mirror of the emit table ``abnf.ABNF_ACTIONS``
  (``IrTypeMap[type, body]``, IR→text), pointed the other way
  (``IrMap[IrRuleRef, body]``, tree→IR).

**Authored to round-trip through the lexic ABNF flavour, not byte-for-byte RFC.**
The grammar is faithful to RFC 5234 in structure, with three deliberate
adaptations so it survives ``emit → parse → reduce`` against ``ABNF_FLAVOUR``:

- *char classes are alternations of single ranges.* ``ABNF_FLAVOUR`` renders a
  multi-element :class:`~lexic.ir.nodes.IrCharClass` as a parenthesised group
  (``(%x41-5A / %x61-7A)``) but a single-element one as a bare ``%x``. So the RFC
  core rules that are alternations (``ALPHA``, ``HEXDIG``) are authored as
  alternations, and the structural class ``vchar-nq`` likewise — each arm a
  one-range class that emits bare and parses back identically.
- *control/quote core rules are num-vals.* ``HTAB``/``DQUOTE``/``CR``/``LF`` are
  ``%x09``/``%x22``/``%x0D``/``%x0A`` (not char-vals), because ``char-val``
  excludes those code points — a literal ``"\\t"`` could not be re-parsed.
- *line ending is ``[CR] LF``.* RFC's ``c-nl = comment / CRLF``; this subset omits
  comments and accepts a bare LF (the ``ABNF_FLAVOUR`` emitter joins rules with
  ``"\\n"``), with the optional CR keeping CRLF input parseable too.

It is a subset: ``bin-val``/``dec-val``, ``prose-val``, ``option`` (``[...]``),
incremental ``=/``, comments, and ``c-wsp`` line-continuation are omitted — none
appear in the flavour's own emitted output, so none is needed for the fixpoint.
Rule names are hyphenated per RFC (``char-val``, not ``char_val``); ``rulename``
admits ``ALPHA / DIGIT / "-"`` only.

**Every reduction is pure ``IrSelf``.** Text rules (the character/terminal rules)
reduce with the shared :data:`YIELD`. Structural rules build typed nodes from
clean ``nc`` with :class:`~lexic.ir.action.IrBuild`. The numeric rules decode
their digit runs with :class:`~lexic.ir.action.IrUnradix` (the inverse of the
emit-side radix spelling) and build over code points — no ``parse_charclass`` /
``parse_quantifier`` call remains on the reduce side.
"""

from __future__ import annotations

from lexic.ir.action import (
    IrArg,
    IrArgs,
    IrBuild,
    IrCond,
    IrField,
    IrJoin,
    IrPipe,
    IrUnradix,
)
from lexic.ir.base import IrInt, IrNone, IrSelf, IrSeq, IrTuple
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
from lexic.parsing_2.reduce import DROP, KEEP_REDUCED, YIELD, Reducer

# ── The ABNF grammar of ABNF (RFC 5234 §4 + B.1 subset), as IR ────────────

ABNF_GRAMMAR = IrAst(
    rules=IrSeq(
        IrRule(
            "rulelist",
            IrAlternation(
                IrSequence(IrItem(IrRuleRef("rule"), IrQuantifier(1, IrNone)))
            ),
        ),
        IrRule(
            "rule",
            IrAlternation(
                IrSequence(
                    IrItem(IrRuleRef("rulename")),
                    IrItem(IrRuleRef("wsp"), IrQuantifier(0, IrNone)),
                    IrItem(IrLiteral("=")),
                    IrItem(IrRuleRef("wsp"), IrQuantifier(0, IrNone)),
                    IrItem(IrRuleRef("alternation")),
                    IrItem(IrRuleRef("wsp"), IrQuantifier(0, IrNone)),
                    IrItem(IrRuleRef("c-nl")),
                )
            ),
        ),
        IrRule(
            "rulename",
            IrAlternation(
                IrSequence(
                    IrItem(IrRuleRef("ALPHA")),
                    IrItem(IrRuleRef("namechar"), IrQuantifier(0, IrNone)),
                )
            ),
        ),
        IrRule(
            "namechar",
            IrAlternation(
                IrSequence(IrItem(IrRuleRef("ALPHA"))),
                IrSequence(IrItem(IrRuleRef("DIGIT"))),
                IrSequence(IrItem(IrLiteral("-"))),
            ),
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
            "altrest",
            IrAlternation(
                IrSequence(
                    IrItem(IrRuleRef("wsp"), IrQuantifier(0, IrNone)),
                    IrItem(IrLiteral("/")),
                    IrItem(IrRuleRef("wsp"), IrQuantifier(0, IrNone)),
                    IrItem(IrRuleRef("concatenation")),
                )
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
            "catrest",
            IrAlternation(
                IrSequence(
                    IrItem(IrRuleRef("wsp"), IrQuantifier(1, IrNone)),
                    IrItem(IrRuleRef("repetition")),
                )
            ),
        ),
        IrRule(
            "repetition",
            IrAlternation(
                IrSequence(
                    IrItem(IrRuleRef("repeat-opt")),
                    IrItem(IrRuleRef("element")),
                )
            ),
        ),
        IrRule(
            "repeat-opt",
            IrAlternation(IrSequence(IrItem(IrRuleRef("repeat"), IrQuantifier(0, 1)))),
        ),
        IrRule(
            "repeat",
            IrAlternation(
                IrSequence(IrItem(IrRuleRef("repeat-exact"))),
                IrSequence(IrItem(IrRuleRef("repeat-range"))),
            ),
        ),
        IrRule(
            "repeat-exact",
            IrAlternation(IrSequence(IrItem(IrRuleRef("decits")))),
        ),
        IrRule(
            "repeat-range",
            IrAlternation(
                IrSequence(
                    IrItem(IrRuleRef("lo-bound")),
                    IrItem(IrLiteral("*")),
                    IrItem(IrRuleRef("hi-bound")),
                )
            ),
        ),
        IrRule(
            "lo-bound",
            IrAlternation(IrSequence(IrItem(IrRuleRef("decits"), IrQuantifier(0, 1)))),
        ),
        IrRule(
            "hi-bound",
            IrAlternation(IrSequence(IrItem(IrRuleRef("decits"), IrQuantifier(0, 1)))),
        ),
        IrRule(
            "decits",
            IrAlternation(
                IrSequence(IrItem(IrRuleRef("DIGIT"), IrQuantifier(1, IrNone)))
            ),
        ),
        IrRule(
            "element",
            IrAlternation(
                IrSequence(IrItem(IrRuleRef("rulename"))),
                IrSequence(IrItem(IrRuleRef("char-val"))),
                IrSequence(IrItem(IrRuleRef("num-val"))),
                IrSequence(IrItem(IrRuleRef("group"))),
            ),
        ),
        IrRule(
            "group",
            IrAlternation(
                IrSequence(
                    IrItem(IrLiteral("(")),
                    IrItem(IrRuleRef("wsp"), IrQuantifier(0, IrNone)),
                    IrItem(IrRuleRef("alternation")),
                    IrItem(IrRuleRef("wsp"), IrQuantifier(0, IrNone)),
                    IrItem(IrLiteral(")")),
                )
            ),
        ),
        IrRule(
            "char-val",
            IrAlternation(
                IrSequence(
                    IrItem(IrRuleRef("DQUOTE")),
                    IrItem(IrRuleRef("vchar-nq"), IrQuantifier(0, IrNone)),
                    IrItem(IrRuleRef("DQUOTE")),
                )
            ),
        ),
        IrRule(
            "vchar-nq",
            IrAlternation(
                IrSequence(
                    IrItem(IrCharClass(IrRange(IrChr(chr(0x20)), IrChr(chr(0x21)))))
                ),
                IrSequence(
                    IrItem(IrCharClass(IrRange(IrChr(chr(0x23)), IrChr(chr(0x7E)))))
                ),
            ),
        ),
        IrRule(
            "num-val",
            IrAlternation(
                IrSequence(IrItem(IrRuleRef("num-single"))),
                IrSequence(IrItem(IrRuleRef("num-range"))),
            ),
        ),
        IrRule(
            "num-single",
            IrAlternation(
                IrSequence(
                    IrItem(IrLiteral("%")),
                    IrItem(IrLiteral("x")),
                    IrItem(IrRuleRef("hexits")),
                )
            ),
        ),
        IrRule(
            "num-range",
            IrAlternation(
                IrSequence(
                    IrItem(IrLiteral("%")),
                    IrItem(IrLiteral("x")),
                    IrItem(IrRuleRef("hexits")),
                    IrItem(IrLiteral("-")),
                    IrItem(IrRuleRef("hexits")),
                )
            ),
        ),
        IrRule(
            "hexits",
            IrAlternation(
                IrSequence(IrItem(IrRuleRef("HEXDIG"), IrQuantifier(1, IrNone)))
            ),
        ),
        IrRule(
            "c-nl",
            IrAlternation(
                IrSequence(
                    IrItem(IrRuleRef("CR"), IrQuantifier(0, 1)),
                    IrItem(IrRuleRef("LF")),
                )
            ),
        ),
        IrRule(
            "wsp",
            IrAlternation(
                IrSequence(IrItem(IrRuleRef("SP"))),
                IrSequence(IrItem(IrRuleRef("HTAB"))),
            ),
        ),
        IrRule(
            "ALPHA",
            IrAlternation(
                IrSequence(IrItem(IrCharClass(IrRange(IrChr("A"), IrChr("Z"))))),
                IrSequence(IrItem(IrCharClass(IrRange(IrChr("a"), IrChr("z"))))),
            ),
        ),
        IrRule(
            "DIGIT",
            IrAlternation(
                IrSequence(IrItem(IrCharClass(IrRange(IrChr("0"), IrChr("9")))))
            ),
        ),
        IrRule(
            "HEXDIG",
            IrAlternation(
                IrSequence(IrItem(IrRuleRef("DIGIT"))),
                IrSequence(IrItem(IrLiteral("A"))),
                IrSequence(IrItem(IrLiteral("B"))),
                IrSequence(IrItem(IrLiteral("C"))),
                IrSequence(IrItem(IrLiteral("D"))),
                IrSequence(IrItem(IrLiteral("E"))),
                IrSequence(IrItem(IrLiteral("F"))),
            ),
        ),
        IrRule("CR", IrAlternation(IrSequence(IrItem(IrCharClass(IrChr("\r")))))),
        IrRule("LF", IrAlternation(IrSequence(IrItem(IrCharClass(IrChr("\n")))))),
        IrRule("SP", IrAlternation(IrSequence(IrItem(IrCharClass(IrChr(" ")))))),
        IrRule("HTAB", IrAlternation(IrSequence(IrItem(IrCharClass(IrChr("\t")))))),
        IrRule("DQUOTE", IrAlternation(IrSequence(IrItem(IrCharClass(IrChr('"')))))),
    ),
    start="rulelist",
)
"""The ABNF grammar of ABNF (RFC 5234 §4 + B.1 subset) as a canonical :class:`IrAst`."""


# ── Cleaning policy: which child rules are noise ──────────────────────────

_NON_SEMANTIC = ("wsp", "SP", "HTAB", "c-nl", "CR", "LF", "DQUOTE")
"""Whitespace, line endings, and the char-val quote delimiter. Dropped from a
structural rule's children and skipped by :data:`~lexic.parsing_2.reduce.YIELD`."""

ABNF_NOISE: IrMap = IrMap(
    *(IrTuple(IrRuleRef(name), DROP) for name in _NON_SEMANTIC),
    IrTuple(IR_DEFAULT, KEEP_REDUCED),
)
"""Child-contribution policy: non-semantic rules drop, every other rule is
reduced and kept. The reduce-side mirror of the emit ``IrMap`` tables."""


# ── Decode helpers: hex code points off args; joined decimal count ────────

_cp0 = IrPipe(IrArg(0), IrUnradix(16, IrChr))
"""First hex digit-run arg → an ``IrChr`` code point."""
_cp1 = IrPipe(IrArg(1), IrUnradix(16, IrChr))
"""Second hex digit-run arg → an ``IrChr`` code point."""
_dec = IrPipe(IrJoin(IrArgs()), IrUnradix(10, IrInt))
"""Joined decimal digit-run args → an ``IrInt`` count."""


# Dyads in an annotated tuple so each value widens to ``IrSelf`` (the invariant
# ``IrTuple`` would otherwise reject the heterogeneous bodies under ``IrMap``).
ABNF_REDUCTIONS: IrMap[IrRuleRef, IrSelf] = IrMap(
    IrTuple(
        IrRuleRef("rulelist"),
        IrBuild(IrAst, IrTuple(IrBuild(IrSeq), IrPipe(IrArg(0), IrField("name")))),
    ),
    IrTuple(IrRuleRef("rule"), IrBuild(IrRule)),
    IrTuple(IrRuleRef("alternation"), IrBuild(IrAlternation)),
    IrTuple(IrRuleRef("altrest"), IrArg(0)),
    IrTuple(IrRuleRef("concatenation"), IrBuild(IrSequence)),
    IrTuple(IrRuleRef("catrest"), IrArg(0)),
    # repetition: repeat-opt is child 0, element is child 1 → IrItem(atom, quant).
    IrTuple(IrRuleRef("repetition"), IrBuild(IrItem, IrTuple(IrArg(1), IrArg(0)))),
    # repeat-opt: present → forward the quantifier; empty → a built default (1,1).
    IrTuple(
        IrRuleRef("repeat-opt"),
        IrCond(
            test=IrArgs(),
            then_op=IrArg(0),
            else_op=IrBuild(IrQuantifier, IrTuple()),
        ),
    ),
    IrTuple(IrRuleRef("repeat"), IrArg(0)),
    IrTuple(
        IrRuleRef("repeat-exact"),
        IrBuild(
            IrQuantifier,
            IrTuple(
                IrPipe(IrArg(0), IrUnradix(10, IrInt)),
                IrPipe(IrArg(0), IrUnradix(10, IrInt)),
            ),
        ),
    ),
    IrTuple(
        IrRuleRef("repeat-range"),
        IrBuild(IrQuantifier, IrTuple(IrArg(0), IrArg(1))),
    ),
    # bounds own their own emptiness: IrArgs() is falsy when the rule matched empty.
    IrTuple(
        IrRuleRef("lo-bound"),
        IrCond(test=IrArgs(), then_op=_dec, else_op=IrInt(0)),
    ),
    IrTuple(
        IrRuleRef("hi-bound"),
        IrCond(test=IrArgs(), then_op=_dec, else_op=IrNone),
    ),
    # digit-run rules: join the scattered single-char args into one string.
    IrTuple(IrRuleRef("decits"), IrJoin(IrArgs())),
    IrTuple(IrRuleRef("hexits"), IrJoin(IrArgs())),
    IrTuple(IrRuleRef("element"), IrArg(0)),
    IrTuple(IrRuleRef("group"), IrArg(0)),
    # Text rules — wrap the subtree text as the leaf type (quotes skipped).
    IrTuple(IrRuleRef("rulename"), IrBuild(IrRuleRef, IrTuple(YIELD))),
    IrTuple(IrRuleRef("char-val"), IrBuild(IrLiteral, IrTuple(YIELD))),
    # num-val → IrCharClass over code points (IrChr endpoints).
    IrTuple(IrRuleRef("num-val"), IrArg(0)),
    IrTuple(IrRuleRef("num-single"), IrBuild(IrCharClass, IrTuple(_cp0))),
    IrTuple(
        IrRuleRef("num-range"),
        IrBuild(IrCharClass, IrTuple(IrBuild(IrRange, IrTuple(_cp0, _cp1)))),
    ),
    IrTuple(IR_DEFAULT, YIELD),
)
"""Per-rule reductions: parse tree → IR. Numeric rules decode their clean digit
runs with :class:`~lexic.ir.action.IrUnradix`; structural rules build from clean
``nc``; every char/terminal rule falls through ``IR_DEFAULT`` to :data:`YIELD`.
Paired with :data:`ABNF_NOISE`."""


ABNF_REDUCER = Reducer(reductions=ABNF_REDUCTIONS, noise=ABNF_NOISE, literal=DROP)
"""The configured ABNF reducer: ``ABNF_REDUCTIONS`` plus the cleaning policy."""
