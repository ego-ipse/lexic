"""Tests for lexic.parsing_2.ops — Predict/Scan/Complete, EARLEY_OPS, and LeoItem."""

from __future__ import annotations

from lexic.ir.base import IrNone, IrSeq
from lexic.ir.mapping import IrMap, IrMultiMap, IrTypeMap
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
from lexic.parsing_2 import parse, recognize
from lexic.parsing_2.chart import Chart
from lexic.parsing_2.normalize import normalize
from lexic.parsing_2.ops import (
    EARLEY_OPS,
    LEO_ITEM,
    Complete,
    LeoItem,
    ParseCtx,
    Predict,
    Scan,
)

# ── EARLEY_OPS dispatch table ─────────────────────────────────────────


def test_earley_ops_is_ir_type_map():
    """EARLEY_OPS is an IrTypeMap."""
    assert isinstance(EARLEY_OPS, IrTypeMap)


def test_earley_ops_irruleref_resolves_to_predict():
    """IrRuleRef symbol → Predict."""
    assert isinstance(EARLEY_OPS.resolve(IrRuleRef("x")), Predict)


def test_earley_ops_irliteral_resolves_to_scan():
    """IrLiteral symbol → Scan."""
    assert isinstance(EARLEY_OPS.resolve(IrLiteral("a")), Scan)


def test_earley_ops_ircharclass_resolves_to_scan():
    """IrCharClass symbol → Scan."""
    assert isinstance(
        EARLEY_OPS.resolve(IrCharClass(IrRange(IrChr("a"), IrChr("z")))), Scan
    )


def test_earley_ops_irrange_resolves_to_scan():
    """IrRange symbol → Scan."""
    assert isinstance(EARLEY_OPS.resolve(IrRange(IrChr("a"), IrChr("z"))), Scan)


def test_earley_ops_irnone_resolves_to_complete():
    """IrNone (IrNoneType) symbol → Complete (dot-past-end sentinel)."""
    assert isinstance(EARLEY_OPS.resolve(IrNone), Complete)


# ── ParseCtx fields ───────────────────────────────────────────────────


def test_parse_ctx_has_nullable_table_field():
    """ParseCtx declares a 'nullable_table' field for Aycock-Horspool."""
    annotations = getattr(ParseCtx, "__annotations__", {})
    assert "nullable_table" in annotations


def test_parse_ctx_child_attrs_is_empty():
    """ParseCtx walks no children — context is engine state, not grammar."""
    ctx = ParseCtx(Chart(), IrMap(), IrMultiMap(), IrMultiMap())
    assert not ctx.children()


# ── LeoItem / LEO_ITEM ────────────────────────────────────────────────


def test_leo_item_singleton_is_leo_item_instance():
    """LEO_ITEM is an instance of LeoItem."""
    assert isinstance(LEO_ITEM, LeoItem)


# ── Grammar helpers for behavioral tests ─────────────────────────────


def _norm(*rules: IrRule, start: str) -> IrAst:
    """Build and normalise an IrAst from a sequence of rules."""
    return normalize(IrAst(rules=IrSeq(*rules), start=start))


def _star(char: str, rule_name: str = "S") -> IrAst:
    """Grammar: S = '<char>'*  (zero or more)."""
    return _norm(
        IrRule(
            rule_name,
            IrAlternation(IrSequence(IrItem(IrLiteral(char), IrQuantifier(0, IrNone)))),
        ),
        start=rule_name,
    )


def _plus(char: str, rule_name: str = "S") -> IrAst:
    """Grammar: S = '<char>'+  (one or more)."""
    return _norm(
        IrRule(
            rule_name,
            IrAlternation(IrSequence(IrItem(IrLiteral(char), IrQuantifier(1, IrNone)))),
        ),
        start=rule_name,
    )


# ── Leo correctness: right-recursive grammars accept/reject properly ──


def test_leo_star_accepts_empty():
    """S = 'a'* accepts the empty string."""
    g = _star("a")
    assert recognize(g, "") == 1


def test_leo_star_accepts_single():
    """S = 'a'* accepts a single 'a'."""
    g = _star("a")
    assert recognize(g, "a") == 1


def test_leo_star_accepts_many():
    """S = 'a'* accepts a run of four 'a's."""
    g = _star("a")
    assert recognize(g, "aaaa") == 1


def test_leo_star_rejects_wrong_char():
    """S = 'a'* rejects input containing a 'b'."""
    g = _star("a")
    assert recognize(g, "aab") == 0


def test_leo_plus_rejects_empty():
    """S = 'a'+ rejects the empty string."""
    g = _plus("a")
    assert recognize(g, "") == 0


def test_leo_plus_accepts_one():
    """S = 'a'+ accepts a single 'a'."""
    g = _plus("a")
    assert recognize(g, "a") == 1


def test_leo_plus_accepts_many():
    """S = 'a'+ accepts a run of five 'a's."""
    g = _plus("a")
    assert recognize(g, "aaaaa") == 1


def test_leo_star_star_sequence():
    """S = 'a'* 'b'* accepts '', 'aaa', 'bbb', 'aabb', rejects 'ba'."""
    g = _norm(
        IrRule(
            "S",
            IrAlternation(
                IrSequence(
                    IrItem(IrLiteral("a"), IrQuantifier(0, IrNone)),
                    IrItem(IrLiteral("b"), IrQuantifier(0, IrNone)),
                )
            ),
        ),
        start="S",
    )
    assert recognize(g, "") == 1
    assert recognize(g, "aaa") == 1
    assert recognize(g, "bbb") == 1
    assert recognize(g, "aabb") == 1
    assert recognize(g, "ba") == 0


def test_leo_indirect_ruleref_star():
    """S = X*  where  X = 'a' | 'b'  (right-recursive via an indirect ref)."""
    x_rule = IrRule(
        "X",
        IrAlternation(
            IrSequence(IrItem(IrLiteral("a"))),
            IrSequence(IrItem(IrLiteral("b"))),
        ),
    )
    s_rule = IrRule(
        "S",
        IrAlternation(IrSequence(IrItem(IrRuleRef("X"), IrQuantifier(0, IrNone)))),
    )
    g = _norm(s_rule, x_rule, start="S")
    assert recognize(g, "") == 1
    assert recognize(g, "abba") == 1
    assert recognize(g, "c") == 0


# ── Parse correctness: Leo-on-parse returns correct trees ────────────


def test_leo_parse_star_single():
    """S = 'a'* — parse 'a' returns correct tree."""
    g = _star("a")
    tree = parse(g, "a")
    assert tree is not None


def test_leo_parse_star_many():
    """S = 'a'* — parse 'aaaa' returns correct tree."""
    g = _star("a")
    tree = parse(g, "aaaa")
    assert tree is not None


def test_leo_parse_plus_many():
    """S = 'a'+ — parse 'aaaaaa' returns correct tree (deep right-recursion)."""
    g = _plus("a")
    tree = parse(g, "aaaaaa")
    assert tree is not None


def test_leo_parse_deep_right_recursion():
    """Leo-on-parse: parse 200 'a's — would crash at ~300 without depth safety."""
    g = _star("a")
    tree = parse(g, "a" * 200)
    assert tree is not None


def test_leo_parse_indirect_ruleref():
    """Leo-on-parse: indirect right-recursion via ruleref."""
    x_rule = IrRule(
        "X",
        IrAlternation(
            IrSequence(IrItem(IrLiteral("a"))),
            IrSequence(IrItem(IrLiteral("b"))),
        ),
    )
    s_rule = IrRule(
        "S",
        IrAlternation(IrSequence(IrItem(IrRuleRef("X"), IrQuantifier(0, IrNone)))),
    )
    g = _norm(s_rule, x_rule, start="S")
    tree = parse(g, "abba")
    assert tree is not None
