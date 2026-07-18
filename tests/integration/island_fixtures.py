"""Shared fixture-grammar builders for ``tests/integration/test_island_valid_prefix.py``.

The mini comma-list grammar (an island by construction — ``list``'s
``rest*``/optional-comma FIRST-overlap is ungateable) plus its whitelist-name
fold, and the notation-grammar variant (``arglist`` widened to the same
trailing-comma shape) used to reproduce the windowed island-parse valid-prefix
regression on the splice path.
"""

from __future__ import annotations

from lexic.compile import notation
from lexic.exceptions import UnsupportedConstructError
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
from lexic.parsing.fold import FieldFold, ModelFold, RuleFold

STAR = IrQuantifier(0, IrNone)
OPT = IrQuantifier(0, 1)
LOWER = IrCharClass(IrRange(IrChr("a"), IrChr("z")))
WS = IrCharClass(IrChr(32), IrChr(9), IrChr(10))

GRAMMAR = IrAst(
    IrSeq(
        IrRule(
            "start",
            IrAlternation(
                IrSequence(IrItem(IrRuleRef("ws")), IrItem(IrRuleRef("list")))
            ),
        ),
        IrRule(
            "list",
            IrAlternation(
                IrSequence(
                    IrItem(IrRuleRef("value")),
                    IrItem(IrRuleRef("rest"), STAR),
                    IrItem(IrRuleRef("comma"), OPT),
                )
            ),
        ),
        IrRule(
            "rest",
            IrAlternation(
                IrSequence(IrItem(IrRuleRef("comma")), IrItem(IrRuleRef("value")))
            ),
        ),
        IrRule(
            "value",
            IrAlternation(
                IrSequence(IrItem(LOWER), IrItem(LOWER, STAR), IrItem(IrRuleRef("ws")))
            ),
        ),
        IrRule(
            "comma",
            IrAlternation(IrSequence(IrItem(IrLiteral(",")), IrItem(IrRuleRef("ws")))),
        ),
        IrRule("ws", IrAlternation(IrSequence(IrItem(WS, STAR))), False),
    ),
    "start",
)

# Two long identifiers: the second straddles the 256-char window boundary, so
# the windowed island parse can complete on a truncated (but valid) prefix.
NAME_A = "a" * 200
NAME_B = "b" * 200
WHITELIST = {NAME_A: "A", NAME_B: "B"}


def name(head: str, tail: str = "") -> str:
    """The whitelist-name fold: resolve a possibly-truncated identifier."""
    full = head + tail
    if full not in WHITELIST:
        raise UnsupportedConstructError(f"mini-notation: unknown name {full!r}")
    return WHITELIST[full]


def start(v: object = None) -> object:
    """The ``start`` rule's fold: pass its single child through unchanged."""
    return v


def make_list(first: object, rest: list[object] | None = None) -> list[object]:
    """The ``list`` rule's fold: ``first`` plus every ``rest`` element."""
    return [first, *(rest or [])]


def unwrap_rest(v: object) -> object:
    """The ``rest`` rule's fold: pass its single child through unchanged."""
    return v


ALT = RuleFold("alternation", lambda: None, 0, ())
FOLD = ModelFold.from_config(
    {
        "start": RuleFold("sequence", start, 2, (FieldFold(1, "model", "v", 1),)),
        "list": RuleFold(
            "sequence",
            make_list,
            3,
            (FieldFold(0, "model", "first", 1), FieldFold(1, "models", "rest", 0)),
        ),
        "rest": RuleFold("sequence", unwrap_rest, 2, (FieldFold(1, "model", "v", 1),)),
        "value": RuleFold(
            "sequence",
            name,
            3,
            (FieldFold(0, "text", "head", 1), FieldFold(1, "text", "tail", 0)),
        ),
    }
)


# ── the historical repro: the notation grammar with a trailing-comma arglist ──
#
# ``arglist ::= value arg-rest* comma?`` islands, and constructor-call syntax
# makes the windowed best completion back off BELOW the window edge (the
# unclosed call after the cut refuses, so a bare-name prefix wins) — the
# splice-path (`island_value`) variant of the truncation, where a truncated
# ``IrChr`` folds as the unknown symbol ``IrCh``. Built from the PUBLIC
# notation surface: NOTATION_GRAMMAR + NOTATION_FOLD.baked.


def notation_variant() -> tuple[IrAst, ModelFold]:
    """The notation grammar with ``arglist`` widened to the trailing-comma
    island shape, plus its matching fold — the splice-path repro fixture."""
    rules = []
    for rule in notation.NOTATION_GRAMMAR.rules:
        if str(rule.name) == "arglist":
            arm = IrSequence(
                IrItem(IrRuleRef("value")),
                IrItem(IrRuleRef("arg-rest"), STAR),
                IrItem(IrRuleRef("comma"), OPT),
            )
            rule = IrRule(rule.name, IrAlternation(arm), rule.semantic)
        rules.append(rule)
    grammar = IrAst(IrSeq(*rules), notation.NOTATION_GRAMMAR.start)
    baked = dict(notation.NOTATION_FOLD.baked)
    arglist = baked["arglist"]
    baked["arglist"] = RuleFold(arglist.kind, arglist.ctor, 3, arglist.fields, None)
    return grammar, ModelFold.from_config(baked)


NOTATION_VARIANT_GRAMMAR, NOTATION_VARIANT_FOLD = notation_variant()

# 280 chars: the 256 window cuts inside the last ``IrChr`` names; the best
# arglist completion ends short of the edge on a bare-name prefix.
WINDOW_CUT_CALL = (
    "IrCharClass(IrRange(IrChr(0), IrChr(9)), IrRange(IrChr(11), IrChr(33)), "
    "IrRange(IrChr(35), IrChr(84)), IrRange(IrChr(86), IrChr(91)), "
    "IrRange(IrChr(93), IrChr(109)), IrRange(IrChr(111), IrChr(113)), "
    "IrChr(115), IrRange(IrChr(118), IrChr(119)), "
    "IrRange(IrChr(121), IrChr(1114111)))"
)
