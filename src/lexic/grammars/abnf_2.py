"""ABNF grammar as native IR, plus the reduction table that recovers IR from a
parse — the text→IR half of an ABNF flavour, with no Lark.

Two artifacts, mirroring how a flavour pairs structure with per-node rules:

- :data:`ABNF_GRAMMAR` — a subset of the ABNF grammar of ABNF (RFC 5234 §4)
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

**Why some reductions stay procedural.** The action algebra is an *emission* DSL:
its nodes produce strings (:class:`~lexic.ir.base.IrStr`). So every rule that
yields text — the character/terminal rules — reduces with one shared
:data:`_YIELD` (:class:`~lexic.ir.action.IrJoin` over :class:`~lexic.ir.action.IrArgs`),
no :class:`~lexic.ir.base.IrCallable` at all. But reductions that *construct*
typed structural nodes (:class:`~lexic.ir.nodes.IrItem` / ``IrSequence`` /
``IrAlternation`` / ``IrRule`` / ``IrAst``) or *filter* children by type have no
algebra node to call — construction/filtering is consumer policy the emission
algebra never needed — so those use :class:`~lexic.ir.base.IrCallable`, its
documented purpose. (Making them declarative would mean adding construction-
algebra nodes — an ``IrFilter`` / ``IrCollect`` / ``IrMake`` family.)

**Shape status.** ``ABNF_GRAMMAR`` is data, verified by construction (it emits as
well-formed ABNF through ``ABNF_FLAVOUR``). The leaf reductions are exercised on
synthetic trees. Running the full fixpoint additionally needs the
:mod:`lexic.parsing_2.normalize` increments (quantifier/group desugaring) and the
nullable completer; desugaring wraps repetitions in synthetic rules, so the
structural reductions here describe the *conceptual* tree and would gain a
synthetic-node flattening step.
"""

from __future__ import annotations

from typing import Sequence

from lexic.grammars.abnf import ABNF_FLAVOUR
from lexic.ir.action import IrArgs, IrJoin
from lexic.ir.base import IrAtom, IrCallable, IrNone, IrSelf, IrSeq, IrStr, IrTuple
from lexic.ir.mapping import IrMap
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

# ── The ABNF grammar of ABNF (RFC 5234 §4 subset), as IR ──────────────────

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
                    IrItem(IrRuleRef("wsp"), IrQuantifier(0, IrNone)),
                    IrItem(IrRuleRef("rulename")),
                    IrItem(IrRuleRef("wsp"), IrQuantifier(0, IrNone)),
                    IrItem(IrLiteral("=")),
                    IrItem(IrRuleRef("wsp"), IrQuantifier(0, IrNone)),
                    IrItem(IrRuleRef("alternation")),
                    IrItem(IrRuleRef("wsp"), IrQuantifier(0, IrNone)),
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
                IrSequence(IrItem(IrLiteral("*"))),
                IrSequence(IrItem(IrRuleRef("DIGIT"))),
            ),
        ),
        IrRule(
            "element",
            IrAlternation(
                IrSequence(IrItem(IrRuleRef("rulename"))),
                IrSequence(IrItem(IrRuleRef("char_val"))),
                IrSequence(IrItem(IrRuleRef("num_val"))),
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
            "char_val",
            IrAlternation(
                IrSequence(
                    IrItem(IrRuleRef("DQUOTE")),
                    IrItem(IrRuleRef("vchar_nq"), IrQuantifier(0, IrNone)),
                    IrItem(IrRuleRef("DQUOTE")),
                )
            ),
        ),
        IrRule(
            "vchar_nq",
            IrAlternation(
                IrSequence(
                    IrItem(
                        IrCharClass(
                            IrRange(chr(0x20), chr(0x21)),
                            IrRange(chr(0x23), chr(0x7E)),
                        )
                    )
                )
            ),
        ),
        IrRule(
            "num_val",
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
            "wsp",
            IrAlternation(
                IrSequence(IrItem(IrRuleRef("SP"))),
                IrSequence(IrItem(IrRuleRef("HTAB"))),
            ),
        ),
        IrRule(
            "ALPHA",
            IrAlternation(
                IrSequence(IrItem(IrCharClass(IrRange("A", "Z"), IrRange("a", "z"))))
            ),
        ),
        IrRule(
            "DIGIT",
            IrAlternation(IrSequence(IrItem(IrCharClass(IrRange("0", "9"))))),
        ),
        IrRule(
            "HEXDIG",
            IrAlternation(
                IrSequence(
                    IrItem(
                        IrCharClass(
                            IrRange("0", "9"), IrRange("A", "F"), IrRange("a", "f")
                        )
                    )
                )
            ),
        ),
        IrRule("SP", IrAlternation(IrSequence(IrItem(IrLiteral(" "))))),
        IrRule("HTAB", IrAlternation(IrSequence(IrItem(IrLiteral("\t"))))),
        IrRule("DQUOTE", IrAlternation(IrSequence(IrItem(IrLiteral('"'))))),
    ),
    start="rulelist",
)
"""The ABNF grammar of ABNF (RFC 5234 §4 subset) as a canonical :class:`IrAst`."""


# ── String-yield reductions: one shared declarative node, no IrCallable ────

_YIELD = IrJoin(parts=IrArgs(), separator=IrLiteral(""), empty=IrLiteral(""))
"""Yield a rule's matched text: join the reduced children, no separator.

Bound to every character/terminal rule (``ALPHA``, ``DIGIT``, ``HEXDIG``, ``SP``,
``HTAB``, ``DQUOTE``, ``wsp``, ``namechar``, ``vchar_nq``, ``rangerest``). Pure
algebra — :class:`~lexic.ir.action.IrArgs` is the reduced-children channel,
:class:`~lexic.ir.action.IrJoin` concatenates them to an :class:`IrStr`.
"""


# ── Structural reductions: construct typed IR (the algebra cannot) ─────────


def _text(nc: Sequence[IrSelf]) -> str:
    """Concatenate the string forms of already-reduced children."""
    return "".join(str(c) for c in nc)


def _rulename(_d: IrSelf, _n: IrSelf, nc: Sequence[IrSelf], /) -> IrRuleRef:
    """``ALPHA *namechar`` → the rule name as an :class:`IrRuleRef`."""
    return IrRuleRef(_text(nc))


def _char_val(_d: IrSelf, _n: IrSelf, nc: Sequence[IrSelf], /) -> IrLiteral:
    """``DQUOTE *vchar_nq DQUOTE`` → the quoted text (quotes dropped)."""
    return IrLiteral("".join(str(c) for c in nc[1:-1]))


def _num_val(_d: IrSelf, _n: IrSelf, nc: Sequence[IrSelf], /) -> IrCharClass:
    """``%x``-value → an :class:`IrCharClass`, reusing the flavour's parser.

    Rejoins the reduced children into the source token (e.g. ``%x41-5A``) and
    defers radix/range parsing to :meth:`ABNF_FLAVOUR.parse_charclass`.
    """
    pattern, _negated = ABNF_FLAVOUR.parse_charclass(_text(nc))
    if "-" in pattern:
        lo, hi = pattern.split("-", 1)
        return IrCharClass(IrRange(lo, hi))
    return IrCharClass(IrStr(pattern))


def _repeat(_d: IrSelf, _n: IrSelf, nc: Sequence[IrSelf], /) -> IrQuantifier:
    """``*`` / ``DIGIT`` → an :class:`IrQuantifier`, via the flavour's parser."""
    return ABNF_FLAVOUR.parse_quantifier(_text(nc))


def _repetition(_d: IrSelf, _n: IrSelf, nc: Sequence[IrSelf], /) -> IrItem:
    """``[repeat] element`` → an :class:`IrItem` pairing atom and quantifier."""
    quant = next((c for c in nc if isinstance(c, IrQuantifier)), IrQuantifier())
    atom = next(c for c in nc if isinstance(c, IrAtom))
    return IrItem(atom, quant)


def _element(_d: IrSelf, _n: IrSelf, nc: Sequence[IrSelf], /) -> IrAtom:
    """``rulename / char-val / num-val / group`` → the single carried atom."""
    return next(c for c in nc if isinstance(c, IrAtom))


def _catrest(_d: IrSelf, _n: IrSelf, nc: Sequence[IrSelf], /) -> IrItem:
    """``1*wsp repetition`` → the carried :class:`IrItem`."""
    return next(c for c in nc if isinstance(c, IrItem))


def _concatenation(_d: IrSelf, _n: IrSelf, nc: Sequence[IrSelf], /) -> IrSequence:
    """``repetition *catrest`` → an :class:`IrSequence` of items (ws dropped)."""
    return IrSequence(*(c for c in nc if isinstance(c, IrItem)))


def _altrest(_d: IrSelf, _n: IrSelf, nc: Sequence[IrSelf], /) -> IrSequence:
    """``*wsp "/" *wsp concatenation`` → the carried :class:`IrSequence` arm."""
    return next(c for c in nc if isinstance(c, IrSequence))


def _alternation(_d: IrSelf, _n: IrSelf, nc: Sequence[IrSelf], /) -> IrAlternation:
    """``concatenation *altrest`` → an :class:`IrAlternation` of arms."""
    return IrAlternation(*(c for c in nc if isinstance(c, IrSequence)))


def _group(_d: IrSelf, _n: IrSelf, nc: Sequence[IrSelf], /) -> IrAlternation:
    """``"(" *wsp alternation *wsp ")"`` → the inner :class:`IrAlternation` atom."""
    return next(c for c in nc if isinstance(c, IrAlternation))


def _rule_reduce(_d: IrSelf, _n: IrSelf, nc: Sequence[IrSelf], /) -> IrRule:
    """``rulename "=" alternation`` → an :class:`IrRule` (name + body)."""
    name = next(c for c in nc if isinstance(c, IrRuleRef))
    body = next(c for c in nc if isinstance(c, IrAlternation))
    return IrRule(str(name), body)


def _rulelist(_d: IrSelf, _n: IrSelf, nc: Sequence[IrSelf], /) -> IrAst:
    """``1*rule`` → the whole :class:`IrAst`, start = first rule's name."""
    rules = tuple(c for c in nc if isinstance(c, IrRule))
    start = str(rules[0].name) if rules else ""
    return IrAst(rules=IrSeq(*rules), start=start)


ABNF_REDUCTIONS: IrMap[IrRuleRef, IrSelf] = IrMap(
    IrTuple(IrRuleRef("rulelist"), IrCallable(_rulelist)),
    IrTuple(IrRuleRef("rule"), IrCallable(_rule_reduce)),
    IrTuple(IrRuleRef("rulename"), IrCallable(_rulename)),
    IrTuple(IrRuleRef("alternation"), IrCallable(_alternation)),
    IrTuple(IrRuleRef("altrest"), IrCallable(_altrest)),
    IrTuple(IrRuleRef("concatenation"), IrCallable(_concatenation)),
    IrTuple(IrRuleRef("catrest"), IrCallable(_catrest)),
    IrTuple(IrRuleRef("repetition"), IrCallable(_repetition)),
    IrTuple(IrRuleRef("repeat"), IrCallable(_repeat)),
    IrTuple(IrRuleRef("element"), IrCallable(_element)),
    IrTuple(IrRuleRef("group"), IrCallable(_group)),
    IrTuple(IrRuleRef("char_val"), IrCallable(_char_val)),
    IrTuple(IrRuleRef("num_val"), IrCallable(_num_val)),
    # Pure string yields — one shared declarative node, no IrCallable.
    IrTuple(IrRuleRef("namechar"), _YIELD),
    IrTuple(IrRuleRef("vchar_nq"), _YIELD),
    IrTuple(IrRuleRef("rangerest"), _YIELD),
    IrTuple(IrRuleRef("ALPHA"), _YIELD),
    IrTuple(IrRuleRef("DIGIT"), _YIELD),
    IrTuple(IrRuleRef("HEXDIG"), _YIELD),
    IrTuple(IrRuleRef("SP"), _YIELD),
    IrTuple(IrRuleRef("HTAB"), _YIELD),
    IrTuple(IrRuleRef("DQUOTE"), _YIELD),
    IrTuple(IrRuleRef("wsp"), _YIELD),
)
"""Per-rule reductions: parse tree → IR. The text→IR mirror of ``ABNF_ACTIONS``."""
