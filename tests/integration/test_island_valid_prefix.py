"""Island valid-prefix regression — window truncation must fail SOFT.

The island sub-parse runs a doubling character window (256 …) whose growth
heuristic is "grow while the best completion touches the window edge". A
language with the *valid-prefix property* (bare identifiers) defeats it: when
the window cuts a token, the truncated text can complete as a VALID island
parse strictly inside the window — no edge touch, no growth — and the spliced
sub-model is wrong. The first thing to notice is the fold (an unknown-symbol
``LexicError``), which must reroute to ``PdaFail`` so the Earley completion
(whole input, same fold) becomes the authority — on the splice path
(``island_value``) and on the island-interior delegate path
(``finish_delegate`` declining).

The fixture is a mini comma-list grammar whose ``list ::= value rest* comma?``
shape is ungateable (the ``rest`` loop and the optional trailing comma share
FIRST = ','), so ``list`` islands — asserted below so the fixture can never
silently stop exercising the island path. The name fold resolves against a
whitelist, exactly like the notation's symbol table: a truncated identifier
is a *valid parse* whose fold refuses.
"""

from __future__ import annotations

from lexic.compile import notation
from lexic.compile.notation import load_ir
from lexic.exceptions import UnsupportedConstructError
from lexic.grammars.gbnf import GBNF_GRAMMAR
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
from lexic.parsing.fold import (
    FieldFold,
    ModelFold,
    RuleFold,
    lift_optional_nullables,
)
from lexic.parsing.pda.analysis.analysis import GrammarAnalysis
from lexic.parsing.products import parse_model

_STAR = IrQuantifier(0, IrNone)
_OPT = IrQuantifier(0, 1)
_LOWER = IrCharClass(IrRange(IrChr("a"), IrChr("z")))
_WS = IrCharClass(IrChr(32), IrChr(9), IrChr(10))

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
                    IrItem(IrRuleRef("rest"), _STAR),
                    IrItem(IrRuleRef("comma"), _OPT),
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
                IrSequence(
                    IrItem(_LOWER), IrItem(_LOWER, _STAR), IrItem(IrRuleRef("ws"))
                )
            ),
        ),
        IrRule(
            "comma",
            IrAlternation(IrSequence(IrItem(IrLiteral(",")), IrItem(IrRuleRef("ws")))),
        ),
        IrRule("ws", IrAlternation(IrSequence(IrItem(_WS, _STAR))), False),
    ),
    "start",
)

# Two long identifiers: the second straddles the 256-char window boundary, so
# the windowed island parse can complete on a truncated (but valid) prefix.
NAME_A = "a" * 200
NAME_B = "b" * 200
WHITELIST = {NAME_A: "A", NAME_B: "B"}


def _name(head: str, tail: str = "") -> str:
    full = head + tail
    if full not in WHITELIST:
        raise UnsupportedConstructError(f"mini-notation: unknown name {full!r}")
    return WHITELIST[full]


def _start(v: object = None) -> object:
    return v


def _list(first: object, rest: list[object] | None = None) -> list[object]:
    return [first, *(rest or [])]


def _rest(v: object) -> object:
    return v


_ALT = RuleFold("alternation", lambda: None, 0, ())
FOLD = ModelFold.from_config(
    {
        "start": RuleFold("sequence", _start, 2, (FieldFold(1, "model", "v", 1),)),
        "list": RuleFold(
            "sequence",
            _list,
            3,
            (FieldFold(0, "model", "first", 1), FieldFold(1, "models", "rest", 0)),
        ),
        "rest": RuleFold("sequence", _rest, 2, (FieldFold(1, "model", "v", 1),)),
        "value": RuleFold(
            "sequence",
            _name,
            3,
            (FieldFold(0, "text", "head", 1), FieldFold(1, "text", "tail", 0)),
        ),
    }
)


def test_the_fixture_list_rule_actually_islands():
    """The trailing-comma shape must stay ungateable — the fixture's licence."""
    analysis = GrammarAnalysis(lift_optional_nullables(GRAMMAR))
    assert "list" in analysis.islands


def test_window_cut_identifier_fails_soft_to_the_completion():
    """An identifier straddling the 256 window parses correctly end-to-end."""
    text = f"{NAME_A}, {NAME_B}"
    assert parse_model(GRAMMAR, text, FOLD) == ["A", "B"]


def test_window_cut_with_trailing_comma_and_noise():
    """Same crossing with the variant's motivating syntax (trailing comma)."""
    text = f"  {NAME_A} ,\n {NAME_B} , "
    assert parse_model(GRAMMAR, text, FOLD) == ["A", "B"]


def test_a_genuine_unknown_name_still_errors():
    """A real fold error reproduces on the Earley completion — never muted."""
    try:
        parse_model(GRAMMAR, "zzz", FOLD)
    except UnsupportedConstructError as exc:
        assert "zzz" in str(exc) or "parse" in str(exc)
    else:
        raise AssertionError("unknown name must surface an error")


# ── the historical repro: the notation grammar with a trailing-comma arglist ──
#
# ``arglist ::= value arg-rest* comma?`` islands, and constructor-call syntax
# makes the windowed best completion back off BELOW the window edge (the
# unclosed call after the cut refuses, so a bare-name prefix wins) — the
# splice-path (`island_value`) variant of the truncation, where a truncated
# ``IrChr`` folds as the unknown symbol ``IrCh``. Built from the PUBLIC
# notation surface: NOTATION_GRAMMAR + NOTATION_FOLD.baked.


def _notation_variant() -> tuple[IrAst, ModelFold]:
    rules = []
    for rule in notation.NOTATION_GRAMMAR.rules:
        if str(rule.name) == "arglist":
            arm = IrSequence(
                IrItem(IrRuleRef("value")),
                IrItem(IrRuleRef("arg-rest"), _STAR),
                IrItem(IrRuleRef("comma"), _OPT),
            )
            rule = IrRule(rule.name, IrAlternation(arm), rule.semantic)
        rules.append(rule)
    grammar = IrAst(IrSeq(*rules), notation.NOTATION_GRAMMAR.start)
    baked = dict(notation.NOTATION_FOLD.baked)
    arglist = baked["arglist"]
    baked["arglist"] = RuleFold(arglist.kind, arglist.ctor, 3, arglist.fields, None)
    return grammar, ModelFold.from_config(baked)


NOTATION_VARIANT_GRAMMAR, NOTATION_VARIANT_FOLD = _notation_variant()

# 280 chars: the 256 window cuts inside the last ``IrChr`` names; the best
# arglist completion ends short of the edge on a bare-name prefix.
WINDOW_CUT_CALL = (
    "IrCharClass(IrRange(IrChr(0), IrChr(9)), IrRange(IrChr(11), IrChr(33)), "
    "IrRange(IrChr(35), IrChr(84)), IrRange(IrChr(86), IrChr(91)), "
    "IrRange(IrChr(93), IrChr(109)), IrRange(IrChr(111), IrChr(113)), "
    "IrChr(115), IrRange(IrChr(118), IrChr(119)), "
    "IrRange(IrChr(121), IrChr(1114111)))"
)


def test_notation_variant_window_cut_call_parses_correctly():
    """The splice-path truncation reroutes; the product returns the truth."""
    got = parse_model(NOTATION_VARIANT_GRAMMAR, WINDOW_CUT_CALL, NOTATION_VARIANT_FOLD)
    assert got == load_ir(WINDOW_CUT_CALL)


def test_notation_variant_full_self_grammar_repr_round_trips():
    """A whole self-grammar repr (many window crossings) round-trips."""
    got = parse_model(
        NOTATION_VARIANT_GRAMMAR, repr(GBNF_GRAMMAR), NOTATION_VARIANT_FOLD
    )
    assert got == GBNF_GRAMMAR
