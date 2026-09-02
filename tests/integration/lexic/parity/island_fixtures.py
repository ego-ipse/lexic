"""Shared fixture-grammar builders for ``tests/integration/test_island_valid_prefix.py``.

The mini comma-list grammar (an island by construction — ``list``'s
``rest*``/optional-comma FIRST-overlap is ungateable) plus its whitelist-name
fold, and the notation-grammar variant (``arglist`` widened to the same
trailing-comma shape) used to reproduce the windowed island-parse valid-prefix
regression on the splice path.
"""

from __future__ import annotations

from typing import Callable

from lexic.compile.foldkit import AuthoredRule, product_rules
from lexic.compile.notation import parse as notation
from lexic.compile.product import rules_by_name
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
from lexic.parsing import ModelBinding
from lexic.parsing.fold import FieldFold, ModelFold, RuleFold
from lexic.parsing.product import CaptureMode, CaptureSpec, LoweringOwned

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
                ),
                # A LEFT-RECURSIVE arm — the class no gate licences and no
                # attempt settles (the delegation-parity SYNTH_GRAMMAR
                # idiom), pinning ``list`` an island however sharp the
                # analysis' separators get. Reachable only through a
                # double comma, which no fixture input contains, so the
                # language and folds of every exercised input are
                # unchanged.
                IrSequence(
                    IrItem(IrRuleRef("list")),
                    IrItem(IrRuleRef("comma")),
                    IrItem(IrRuleRef("comma")),
                ),
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

_ONE = int(CaptureMode.ONE)
_MANY = int(CaptureMode.MANY)
_TEXT = int(CaptureMode.TEXT)

MINI_RULES: dict[str, AuthoredRule] = {
    "start": AuthoredRule("start", (CaptureSpec(_ONE, 1),), ("v",), 2),
    "list": AuthoredRule(
        "make_list",
        (CaptureSpec(_ONE, 0), CaptureSpec(_MANY, 1)),
        ("first", "rest"),
        3,
    ),
    "rest": AuthoredRule("unwrap_rest", (CaptureSpec(_ONE, 1),), ("v",), 2),
    "value": AuthoredRule(
        "name",
        (CaptureSpec(_TEXT, 0), CaptureSpec(_TEXT, 1)),
        ("head", "tail"),
        3,
    ),
}
"""The same four rules in the product vocabulary — this fixture is an authored
surface like any other, so it says what its rules do in both halves."""

MINI_SYMBOLS: dict[str, Callable[..., object]] = {
    "start": start,
    "make_list": make_list,
    "unwrap_rest": unwrap_rest,
    "name": name,
}

_MINI_PRODUCT = product_rules(MINI_RULES)
BINDING = ModelBinding(
    rules_by_name(_MINI_PRODUCT.rules, _MINI_PRODUCT.codes),
    LoweringOwned(symbols=_MINI_PRODUCT.symbols, registry=MINI_SYMBOLS),
)


# ── the historical repro: the notation grammar with a trailing-comma arglist ──
#
# ``arglist ::= value arg-rest* comma?`` islands, and constructor-call syntax
# makes the windowed best completion back off BELOW the window edge (the
# unclosed call after the cut refuses, so a bare-name prefix wins) — the
# splice-path (`island_value`) variant of the truncation, where a truncated
# ``IrChr`` completes as the unknown symbol ``IrCh``. Built from the PUBLIC
# notation surface: NOTATION_GRAMMAR + NOTATION_RULES.


def arg_rest_value(v: object) -> object:
    """The authored ``arg-rest`` fold — pass the comma'd value through."""
    return v


def notation_variant() -> tuple[IrAst, ModelBinding]:
    """The notation grammar with ``arglist`` widened to the UNGATEABLE
    trailing-comma island shape (``value arg-rest* comma?`` — loop and
    optional share FIRST=','), plus its matching product — the splice-path
    repro fixture. The STOCK notation now uses the gateable arg-tail shape,
    so this fixture authors its own ``arg-rest`` rule to stay the island
    repro the engine tests need."""
    rules = []
    for rule in notation.NOTATION_GRAMMAR.rules:
        rule_name = str(rule.name)
        if rule_name == "arglist":
            arm = IrSequence(
                IrItem(IrRuleRef("value")),
                IrItem(IrRuleRef("arg-rest"), STAR),
                IrItem(IrRuleRef("comma"), OPT),
            )
            rules.append(IrRule(rule.name, IrAlternation(arm), rule.semantic))
            rules.append(
                IrRule(
                    "arg-rest",
                    IrAlternation(
                        IrSequence(
                            IrItem(IrRuleRef("comma")), IrItem(IrRuleRef("value"))
                        )
                    ),
                )
            )
            continue
        if rule_name in ("arg-tail", "arg-val"):
            continue
        rules.append(rule)
    grammar = IrAst(IrSeq(*rules), notation.NOTATION_GRAMMAR.start)
    rules = dict(notation.NOTATION_RULES)
    rules.pop("arg-tail", None)
    rules.pop("arg-val", None)
    rules["arglist"] = rules["arglist"]._replace(n_items=3)
    rules["arg-rest"] = AuthoredRule(
        "arg_rest_value", (CaptureSpec(_ONE, 1),), ("v",), 2
    )
    product = product_rules(rules)
    registry = notation.NOTATION_SYMBOLS | {"arg_rest_value": arg_rest_value}
    return grammar, ModelBinding(
        rules_by_name(product.rules, product.codes),
        LoweringOwned(symbols=product.symbols, registry=registry),
    )


NOTATION_VARIANT_GRAMMAR, NOTATION_VARIANT_BINDING = notation_variant()

# 280 chars: the 256 window cuts inside the last ``IrChr`` names; the best
# arglist completion ends short of the edge on a bare-name prefix.
WINDOW_CUT_CALL = (
    "IrCharClass(IrRange(IrChr(0), IrChr(9)), IrRange(IrChr(11), IrChr(33)), "
    "IrRange(IrChr(35), IrChr(84)), IrRange(IrChr(86), IrChr(91)), "
    "IrRange(IrChr(93), IrChr(109)), IrRange(IrChr(111), IrChr(113)), "
    "IrChr(115), IrRange(IrChr(118), IrChr(119)), "
    "IrRange(IrChr(121), IrChr(1114111)))"
)
