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

**Why some reductions stay procedural.** The action algebra is an *emission* DSL:
its nodes produce strings (:class:`~lexic.ir.base.IrStr`). So every rule that
yields text — the character/terminal rules — reduces with one shared
:data:`_YIELD` (:class:`~lexic.ir.action.IrJoin` over :class:`~lexic.ir.action.IrArgs`),
no procedural bodies at all. But reductions that *construct*
typed structural nodes (:class:`~lexic.ir.nodes.IrItem` / ``IrSequence`` /
``IrAlternation`` / ``IrRule`` / ``IrAst``) or *filter* children by type have no
algebra node to call — construction/filtering is consumer policy the emission
algebra never needed — so those use :class:`~lexic.ir.base.IrLambda`, the
procedural escape hatch.
"""

from __future__ import annotations

from typing import Sequence

from lexic.grammars.abnf import ABNF_FLAVOUR
from lexic.ir.action import IrArg, IrBuild, IrField, IrPipe
from lexic.ir.base import IrAtom, IrLambda, IrNone, IrSelf, IrSeq, IrStr, IrTuple
from lexic.ir.mapping import IR_DEFAULT, IrMap
from lexic.ir.nodes import (
    IrAlternation,
    IrAst,
    IrCharClass,
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
                    IrItem(IrRuleRef("repeat"), IrQuantifier(0, 1)),
                    IrItem(IrRuleRef("element")),
                )
            ),
        ),
        IrRule(
            "repeat",
            IrAlternation(
                IrSequence(IrItem(IrRuleRef("DIGIT"), IrQuantifier(1, IrNone))),
                IrSequence(
                    IrItem(IrRuleRef("DIGIT"), IrQuantifier(0, IrNone)),
                    IrItem(IrLiteral("*")),
                    IrItem(IrRuleRef("DIGIT"), IrQuantifier(0, IrNone)),
                ),
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
                IrSequence(IrItem(IrCharClass(IrRange(chr(0x20), chr(0x21))))),
                IrSequence(IrItem(IrCharClass(IrRange(chr(0x23), chr(0x7E))))),
            ),
        ),
        IrRule(
            "num-val",
            IrAlternation(
                IrSequence(
                    IrItem(IrLiteral("%")),
                    IrItem(IrLiteral("x")),
                    IrItem(IrRuleRef("HEXDIG"), IrQuantifier(1, IrNone)),
                    IrItem(IrRuleRef("rangerest"), IrQuantifier(0, 1)),
                )
            ),
        ),
        IrRule(
            "rangerest",
            IrAlternation(
                IrSequence(
                    IrItem(IrLiteral("-")),
                    IrItem(IrRuleRef("HEXDIG"), IrQuantifier(1, IrNone)),
                )
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
                IrSequence(IrItem(IrCharClass(IrRange("A", "Z")))),
                IrSequence(IrItem(IrCharClass(IrRange("a", "z")))),
            ),
        ),
        IrRule(
            "DIGIT",
            IrAlternation(IrSequence(IrItem(IrCharClass(IrRange("0", "9"))))),
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
        IrRule("CR", IrAlternation(IrSequence(IrItem(IrCharClass(IrStr("\r")))))),
        IrRule("LF", IrAlternation(IrSequence(IrItem(IrCharClass(IrStr("\n")))))),
        IrRule("SP", IrAlternation(IrSequence(IrItem(IrCharClass(IrStr(" ")))))),
        IrRule("HTAB", IrAlternation(IrSequence(IrItem(IrCharClass(IrStr("\t")))))),
        IrRule("DQUOTE", IrAlternation(IrSequence(IrItem(IrCharClass(IrStr('"')))))),
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


# ── Procedural reductions: numeric tokens + the optional/reordered item ────


def _num_val(d: IrSelf, n: IrSelf, _nc: Sequence[IrSelf]) -> IrCharClass:
    """``%x``-token → :class:`IrCharClass`, parsing the subtree's raw text.

    Radix/range parsing is deferred to :meth:`ABNF_FLAVOUR.parse_charclass`
    (Issue 2 — the pure radix algebra is a separate effort).
    """
    pattern, _negated = ABNF_FLAVOUR.parse_charclass(str(YIELD.eval(d, n, ())))
    if "-" in pattern:
        lo, hi = pattern.split("-", 1)
        return IrCharClass(IrRange(lo, hi))
    return IrCharClass(IrStr(pattern))


def _repeat(d: IrSelf, n: IrSelf, _nc: Sequence[IrSelf]) -> IrQuantifier:
    """``1*5`` etc. → :class:`IrQuantifier`, parsing the subtree's raw text."""
    return ABNF_FLAVOUR.parse_quantifier(str(YIELD.eval(d, n, ())))


def _repetition(_d: IrSelf, _n: IrSelf, nc: Sequence[IrSelf]) -> IrItem:
    """``repeat? element`` → :class:`IrItem`. The optional quantifier prefixes
    the atom, so both are picked by type from the clean ``nc`` (an absent
    quantifier defaults)."""
    atom = next(c for c in nc if isinstance(c, IrAtom))
    quant = next((c for c in nc if isinstance(c, IrQuantifier)), IrQuantifier())
    return IrItem(atom, quant)


# ── Reductions: structural rules build from clean nc, text rules yield ─────

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
    IrTuple(IrRuleRef("repetition"), IrLambda(_repetition)),
    IrTuple(IrRuleRef("element"), IrArg(0)),
    IrTuple(IrRuleRef("group"), IrArg(0)),
    # Text rules — wrap the subtree text as the leaf type (quotes skipped).
    IrTuple(IrRuleRef("rulename"), IrBuild(IrRuleRef, IrTuple(YIELD))),
    IrTuple(IrRuleRef("char-val"), IrBuild(IrLiteral, IrTuple(YIELD))),
    # Numeric tokens — parse the raw text (radix algebra deferred, Issue 2).
    IrTuple(IrRuleRef("num-val"), IrLambda(_num_val)),
    IrTuple(IrRuleRef("repeat"), IrLambda(_repeat)),
    IrTuple(IR_DEFAULT, YIELD),
)
"""Per-rule reductions: parse tree → IR. Structural rules build from clean
``nc``; every char/terminal rule falls through ``IR_DEFAULT`` to :data:`YIELD`,
which yields its subtree source. Paired with :data:`ABNF_NOISE`."""


ABNF_REDUCER = Reducer(reductions=ABNF_REDUCTIONS, noise=ABNF_NOISE, literal=DROP)
"""The configured ABNF reducer: ``ABNF_REDUCTIONS`` plus the cleaning policy."""
