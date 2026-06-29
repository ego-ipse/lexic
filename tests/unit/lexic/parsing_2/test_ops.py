"""Tests for lexic.parsing_2.ops — Predict/Scan/Complete, EARLEY_OPS, and LeoItem.

API changes:

- ``ParseCtx`` is now a mutable per-parse cursor (an ``IrLeaf``), constructed
  ``ParseCtx(chart, rules, nullable)`` with ``col``/``item`` advanced in place by
  the driver — no longer a frozen 6-field tuple.

New symbols tested: ``LeoItem``, ``LEO_ITEM``, ``_LEO_ENABLED``.
"""

from __future__ import annotations

import lexic.parsing_2.ops as ops_mod
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
from lexic.parsing_2 import recognize
from lexic.parsing_2.chart import Chart
from lexic.parsing_2.normalize import normalize
from lexic.parsing_2.ops import (
    _LEO_ENABLED,
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


def test_parse_ctx_has_nullable_field():
    """ParseCtx declares a 'nullable' field for Aycock-Horspool."""
    annotations = getattr(ParseCtx, "__annotations__", {})
    assert "nullable" in annotations


def test_parse_ctx_child_attrs_is_empty():
    """ParseCtx walks no children — context is engine state, not grammar."""
    ctx = ParseCtx(Chart(), IrMap(), IrMultiMap(), IrMultiMap())
    assert not ctx.children()


# ── LeoItem / LEO_ITEM / _LEO_ENABLED ────────────────────────────────


def test_leo_item_singleton_is_leo_item_instance():
    """LEO_ITEM is an instance of LeoItem."""
    assert isinstance(LEO_ITEM, LeoItem)


def test_leo_enabled_is_true_by_default():
    """_LEO_ENABLED is True at module import time."""
    assert _LEO_ENABLED is True


# ── Grammar helpers for behavioral/differential tests ────────────────


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


# ── Differential: Leo on vs off must agree on every input ─────────────


def _recognize_with_leo(enabled: bool, grammar: IrAst, text: str) -> int:
    """Run recognize with _LEO_ENABLED forced to ``enabled``; always restores."""
    original = ops_mod._LEO_ENABLED
    try:
        ops_mod._LEO_ENABLED = enabled
        return int(recognize(grammar, text))
    finally:
        ops_mod._LEO_ENABLED = original


def _check_differential(grammar: IrAst, inputs: list[str]) -> None:
    """Assert Leo on and off produce identical results for every input."""
    for text in inputs:
        on = _recognize_with_leo(True, grammar, text)
        off = _recognize_with_leo(False, grammar, text)
        assert on == off, f"Leo on/off disagree on {text!r}: on={on}, off={off}"


def test_differential_star_grammar():
    """Leo on and off produce identical results for S = 'a'*."""
    g = _star("a")
    _check_differential(g, ["", "a", "aa", "aaaa", "b", "aab"])


def test_differential_plus_grammar():
    """Leo on and off produce identical results for S = 'a'+."""
    g = _plus("a")
    _check_differential(g, ["", "a", "aaaa", "b"])


def test_differential_star_star_sequence():
    """Leo on and off agree for S = 'a'* 'b'*."""
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
    _check_differential(g, ["", "aaa", "bbb", "aabb", "ba", "ab"])


def test_differential_indirect_ruleref_star():
    """Leo on and off agree for S = X*  where  X = 'a' | 'b'."""
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
    _check_differential(g, ["", "a", "b", "ab", "abba", "c", "ac"])


def test_leo_enabled_restored_after_differential():
    """_LEO_ENABLED is restored to True after the differential helper runs."""
    g = _star("a")
    _check_differential(g, ["a"])
    assert ops_mod._LEO_ENABLED is True
