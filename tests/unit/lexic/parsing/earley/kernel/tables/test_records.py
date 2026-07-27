"""Tests for the compiled table records — the parser's read-only artefact."""

from __future__ import annotations

import pytest

from lexic.exceptions import UnsupportedConstructError
from lexic.ir import (
    IrAlternation,
    IrAst,
    IrCharClass,
    IrChr,
    IrItem,
    IrLiteral,
    IrNot,
    IrRule,
    IrRuleRef,
    IrSeq,
    IrSequence,
)
from lexic.parsing import parse_first, recognize
from lexic.parsing.earley.kernel.tables import atoms as tables_mod
from lexic.parsing.earley.kernel.tables.builder import compile_tables
from lexic.parsing.earley.kernel.tables.records import (
    ADVANCE,
    ORIGIN_BITS,
    CodeTables,
    DecodeTables,
    ParserTables,
)
from lexic.parsing.earley.normalize import normalize
from lexic.parsing.fold import lift_optional_nullables
from tests.unit.lexic.parsing.earley.kernel.test_kernel import undefined_ref_grammar
from tests.unit.lexic.parsing.ir_fixtures import digit_grammar as _digit_grammar
from tests.unit.lexic.parsing.ir_fixtures import digits_plus_grammar
from tests.unit.lexic.parsing.ir_fixtures import sss_grammar as _sss_grammar


def nullable_grammar() -> IrAst:
    """nullish = '' ; a single rule whose only arm is empty (nullable)."""
    return IrAst(
        rules=IrSeq(IrRule("nullish", IrAlternation(IrSequence()))),
        start="nullish",
    )


def chained_nullable_grammar() -> IrAst:
    """outer = inner ; inner = '' — nullable transitively via a ruleref."""
    inner = IrRule("inner", IrAlternation(IrSequence()))
    outer = IrRule("outer", IrAlternation(IrSequence(IrItem(IrRuleRef("inner")))))
    return IrAst(rules=IrSeq(outer, inner), start="outer")


def non_nullable_grammar() -> IrAst:
    """solid = 'a' ; a rule with only a non-empty terminal arm."""
    return IrAst(
        rules=IrSeq(IrRule("solid", IrAlternation(IrSequence(IrItem(IrLiteral("a")))))),
        start="solid",
    )


def test_undefined_ruleref_recognizes_nothing():
    """Prediction seeds nothing for an undefined rule — parsing derives no branch."""
    g = undefined_ref_grammar()
    assert recognize(g, "anything") == 0


def negated_grammar() -> IrAst:
    """s = [^"] — one rule with a single negated-char-class terminal."""
    atom = IrNot(IrCharClass(IrChr('"')))
    rule = IrRule("s", IrAlternation(IrSequence(IrItem(atom))))
    return IrAst(rules=IrSeq(rule), start="s")


def test_parser_tables_composes_code_and_decode_tables():
    """ParserTables exposes .codes (CodeTables) and .decode (DecodeTables)."""
    tables = compile_tables(_digit_grammar())
    assert isinstance(tables.codes, CodeTables)
    assert isinstance(tables.decode, DecodeTables)
    assert isinstance(tables, ParserTables)


def test_rule_seeds_pair_shifted_code_matches_dot0():
    """Each pair's first element is the arm's dot-0 code, pre-shifted."""
    tables = compile_tables(_sss_grammar())
    s_rid = tables.decode.rule_ids["s"]
    for shifted, _sym in tables.codes.rule_seeds[s_rid]:
        dot0_code = shifted >> ORIGIN_BITS
        assert shifted == dot0_code << ORIGIN_BITS


def test_advance_is_one_shifted_by_origin_bits():
    """ADVANCE == 1 << ORIGIN_BITS, per the packing scheme."""
    assert ADVANCE == 1 << ORIGIN_BITS


def tiny() -> IrAst:
    """The digit grammar, engine-normalised — the tier tests' substrate."""
    return normalize(lift_optional_nullables(_digit_grammar()))


def test_parse_entries_pick_the_tier_by_input_size(monkeypatch):
    """With TIERS overridden to (8, 28), a 300-char input overflows the
    8-bit tier and routes to the 28-bit one on every parse entry."""
    monkeypatch.setattr(tables_mod, "TIERS", (8, 28))
    grammar = digits_plus_grammar()
    assert recognize(grammar, "7" * 300) == 1
    assert parse_first(grammar, "7" * 300)


def test_parse_entries_capacity_backstop_raises_beyond_the_last_tier(monkeypatch):
    """With only an 8-bit tier available, a 300-char input hits the kernel
    capacity raise — the backstop, never a silent wrap."""
    monkeypatch.setattr(tables_mod, "TIERS", (8,))
    grammar = digits_plus_grammar()
    with pytest.raises(UnsupportedConstructError):
        parse_first(grammar, "7" * 300)
