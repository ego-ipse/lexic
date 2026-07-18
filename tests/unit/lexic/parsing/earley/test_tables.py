"""Tests for lexic.parsing.earley.tables — CodeTables, DecodeTables, ParserTables,
compile_tables, atom_accepts.

New module (the compiled "codegen moment" for parsing): every dotted
position of every arm gets one int ``code``, laid out dot-dense so advancing
a dot is ``+ 1``. This file covers the coding scheme, the ``next_sym``
discriminator, nullable/accept-code fixpoints, memoisation, per-char scan
caching, the ``UnsupportedConstructError`` guards on unnormalised input, and
(Task 2) the per-arm FIRST seed-gate semantics in ``rule_seed_gates`` /
``_FirstGates``. ``expand_atom``'s charset extraction (moved home from
``lexruns.py``) also lives here now — see that module's test file for a
back-compat re-export smoke test.
"""

from __future__ import annotations

import pytest

from lexic.exceptions import UnsupportedConstructError
from lexic.ir.base import IrNone, IrSeq
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
from lexic.ir.operators import IrNot
from lexic.parsing import recognize
from lexic.parsing.earley.tables import (
    ADVANCE,
    ORIGIN_BITS,
    RUN_STR,
    CodeTables,
    DecodeTables,
    ParserTables,
    RunTerm,
    atom_accepts,
    build_tables,
    compile_tables,
    expand_atom,
)
from tests.unit.lexic.parsing.ir_fixtures import digit_grammar as _digit_grammar
from tests.unit.lexic.parsing.ir_fixtures import sss_grammar as _sss_grammar
from tests.unit.lexic.parsing.ir_fixtures import word_grammar as _word_grammar

# ── atom_accepts ────────────────────────────────────────────────────────


def test_atom_accepts_literal_matches_same_char():
    """A single-char IrLiteral accepts its own char."""
    assert atom_accepts(IrLiteral("x"), "x")


def test_atom_accepts_literal_rejects_other_char():
    """A single-char IrLiteral rejects a different char."""
    assert not atom_accepts(IrLiteral("x"), "y")


def test_atom_accepts_charclass_range_matches():
    """A range char-class accepts a char within bounds."""
    atom = IrCharClass(IrRange(IrChr("a"), IrChr("z")))
    assert atom_accepts(atom, "m")


def test_atom_accepts_charclass_range_rejects_outside():
    """A range char-class rejects a char outside bounds."""
    atom = IrCharClass(IrRange(IrChr("a"), IrChr("z")))
    assert not atom_accepts(atom, "0")


def test_atom_accepts_charclass_single_chr_matches():
    """A char-class with a bare IrChr element accepts that exact char."""
    atom = IrCharClass(IrChr("q"))
    assert atom_accepts(atom, "q")


def test_atom_accepts_charclass_single_chr_rejects_other():
    """A char-class with a bare IrChr element rejects any other char."""
    atom = IrCharClass(IrChr("q"))
    assert not atom_accepts(atom, "r")


def test_atom_accepts_negated_charclass_matches_char_outside_set():
    """A negated char-class accepts a char that is not in the inner set."""
    atom = IrNot(IrCharClass(IrChr('"')))
    assert atom_accepts(atom, "a")


def test_atom_accepts_negated_charclass_rejects_char_in_set():
    """A negated char-class rejects a char that is in the inner set."""
    atom = IrNot(IrCharClass(IrChr('"')))
    assert not atom_accepts(atom, '"')


def test_atom_accepts_negated_range_matches_char_outside_range():
    """A negated range accepts a char outside the inner range."""
    atom = IrNot(IrCharClass(IrRange(IrChr("a"), IrChr("z"))))
    assert atom_accepts(atom, "0")


def test_atom_accepts_negated_range_rejects_char_in_range():
    """A negated range rejects a char inside the inner range."""
    atom = IrNot(IrCharClass(IrRange(IrChr("a"), IrChr("z"))))
    assert not atom_accepts(atom, "m")


def test_atom_accepts_negated_non_charclass_raises():
    """An IrNot over anything but an IrCharClass raises."""
    with pytest.raises(UnsupportedConstructError):
        atom_accepts(IrNot(IrRuleRef("x")), "a")


# ── expand_atom (moved home from lexruns.py — mirror-rule relocation) ──


def test_expand_atom_single_char_literal_returns_its_char():
    """A single-char IrLiteral expands to a one-char frozenset."""
    assert expand_atom(IrLiteral("a")) == frozenset("a")


def test_expand_atom_multichar_literal_returns_none():
    """A literal longer than one char is not a char-unit — poisoned."""
    assert expand_atom(IrLiteral("ab")) is None


def test_expand_atom_charclass_with_ranges_returns_charset():
    """A range char-class expands to every char in the range."""
    atom = IrCharClass(IrRange(IrChr("a"), IrChr("c")))
    assert expand_atom(atom) == frozenset("abc")


def test_expand_atom_charclass_with_bare_chr_returns_charset():
    """A char-class with a bare IrChr element expands to that one char."""
    atom = IrCharClass(IrChr("q"))
    assert expand_atom(atom) == frozenset("q")


def test_expand_atom_over_cap_range_poisons():
    """A range wider than the expansion cap poisons to None."""
    atom = IrCharClass(IrRange(IrChr(chr(0)), IrChr(chr(0x2000))))
    assert expand_atom(atom) is None


def test_expand_atom_ruleref_is_not_a_terminal_atom():
    """An IrRuleRef is never a char-unit — poisoned regardless of shape."""
    assert expand_atom(IrRuleRef("digit")) is None


def test_expand_atom_negated_charclass_poisons():
    """A negated char-class is not a positive char-unit — poisoned to None."""
    assert expand_atom(IrNot(IrCharClass(IrChr('"')))) is None


# ── Grammar builders ─────────────────────────────────────────────────────


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


def undefined_ref_grammar() -> IrAst:
    """top = missing ; 'missing' is referenced but never given an IrRule."""
    return IrAst(
        rules=IrSeq(
            IrRule("top", IrAlternation(IrSequence(IrItem(IrRuleRef("missing")))))
        ),
        start="top",
    )


# ── Coding scheme: dot-density, arm_base, completed code ────────────────


def test_word_grammar_positions_are_dot_dense():
    """word's single 2-item arm gets 3 consecutive codes: dot0, dot1, complete."""
    tables = compile_tables(_word_grammar())
    word_rid = tables.decode.rule_ids["word"]
    (base,) = tables.codes.rule_dot0[word_rid]
    assert tables.codes.code_arm[base] == tables.codes.code_arm[base + 1]
    assert tables.codes.code_arm[base + 1] == tables.codes.code_arm[base + 2]


def test_arm_base_is_dot_zero_code():
    """arm_base[arm_id] equals the arm's dot-0 code (rule_dot0's entry)."""
    tables = compile_tables(_digit_grammar())
    digit_rid = tables.decode.rule_ids["digit"]
    (dot0_code,) = tables.codes.rule_dot0[digit_rid]
    arm_id = tables.codes.code_arm[dot0_code]
    assert tables.codes.arm_base[arm_id] == dot0_code


def test_completed_code_is_arm_base_plus_arm_length():
    """The completed code for an arm is arm_base + len(seq)."""
    tables = compile_tables(_word_grammar())
    word_rid = tables.decode.rule_ids["word"]
    (base,) = tables.codes.rule_dot0[word_rid]
    arm_id = tables.codes.code_arm[base]
    seq = tables.decode.arm_seqs[arm_id]
    completed_code = base + len(seq)
    assert tables.codes.next_sym[completed_code] == 0


# ── next_sym discriminator ───────────────────────────────────────────────


def test_next_sym_positive_for_predict_position():
    """A dot facing a rule-ref gets next_sym == rule_id + 1 (> 0)."""
    tables = compile_tables(_word_grammar())
    word_rid = tables.decode.rule_ids["word"]
    letter_rid = tables.decode.rule_ids["letter"]
    (base,) = tables.codes.rule_dot0[word_rid]
    assert tables.codes.next_sym[base] == letter_rid + 1


def test_next_sym_negative_for_scan_position():
    """A dot facing a terminal atom gets next_sym == -(term_id + 1) (< 0)."""
    tables = compile_tables(_digit_grammar())
    digit_rid = tables.decode.rule_ids["digit"]
    (base,) = tables.codes.rule_dot0[digit_rid]
    assert tables.codes.next_sym[base] < 0


def test_next_sym_zero_for_complete_position():
    """A dot past the arm's end gets next_sym == 0."""
    tables = compile_tables(_digit_grammar())
    digit_rid = tables.decode.rule_ids["digit"]
    (base,) = tables.codes.rule_dot0[digit_rid]
    seq_len = len(tables.decode.arm_seqs[tables.codes.code_arm[base]])
    assert tables.codes.next_sym[base + seq_len] == 0


# ── nullable_completes least-fixpoint ────────────────────────────────────


def test_empty_arm_rule_is_nullable():
    """A rule whose only arm is empty has a non-empty nullable_completes entry."""
    tables = compile_tables(nullable_grammar())
    rid = tables.decode.rule_ids["nullish"]
    assert tables.codes.nullable_completes[rid] != ()


def test_chained_nullable_via_ruleref():
    """A rule referencing only a nullable rule is itself nullable (chained)."""
    tables = compile_tables(chained_nullable_grammar())
    outer_rid = tables.decode.rule_ids["outer"]
    inner_rid = tables.decode.rule_ids["inner"]
    assert tables.codes.nullable_completes[inner_rid] != ()
    assert tables.codes.nullable_completes[outer_rid] != ()


def test_non_nullable_rule_has_empty_tuple():
    """A rule with only non-empty terminal arms is NOT nullable — empty tuple."""
    tables = compile_tables(non_nullable_grammar())
    rid = tables.decode.rule_ids["solid"]
    assert tables.codes.nullable_completes[rid] == ()


# ── accept_codes ──────────────────────────────────────────────────────────


def test_accept_codes_only_contains_start_rule_arms():
    """Every code in accept_codes belongs to an arm of the start rule."""
    tables = compile_tables(_word_grammar())
    start_rid = tables.start_id
    for code in tables.codes.accept_codes:
        arm_id = tables.codes.code_arm[code]
        assert tables.codes.arm_rule[arm_id] == start_rid


def test_accept_codes_nonempty_for_defined_start():
    """accept_codes is non-empty when the start rule is defined with arms."""
    tables = compile_tables(_digit_grammar())
    assert len(tables.codes.accept_codes) > 0


# ── Undefined rule ref ────────────────────────────────────────────────────


def test_undefined_ruleref_gets_empty_rule_dot0():
    """A rule referenced but never defined gets an empty rule_dot0 entry."""
    tables = compile_tables(undefined_ref_grammar())
    missing_rid = tables.decode.rule_ids["missing"]
    assert tables.codes.rule_dot0[missing_rid] == ()


def test_undefined_ruleref_recognizes_nothing():
    """Prediction seeds nothing for an undefined rule — parsing derives no branch."""
    g = undefined_ref_grammar()
    assert recognize(g, "anything") == 0


# ── compile_tables memoisation ────────────────────────────────────────────


def test_compile_tables_memoises_same_object():
    """Passing the SAME grammar object twice returns the identical tables object."""
    g = _digit_grammar()
    t1 = compile_tables(g)
    t2 = compile_tables(g)
    assert t1 is t2


def test_compile_tables_distinct_objects_get_distinct_tables():
    """Two structurally-identical but distinct grammar objects get distinct tables."""
    g1 = _digit_grammar()
    g2 = _digit_grammar()
    t1 = compile_tables(g1)
    t2 = compile_tables(g2)
    assert t1 is not t2


# ── Validation: UnsupportedConstructError on unnormalised input ─────────


def test_compile_tables_rejects_unnormalised_quantifier():
    """A non-(1,1) quantifier on an item raises UnsupportedConstructError."""
    rule = IrRule(
        "s",
        IrAlternation(IrSequence(IrItem(IrLiteral("a"), IrQuantifier(0, IrNone)))),
    )
    g = IrAst(rules=IrSeq(rule), start="s")
    with pytest.raises(UnsupportedConstructError):
        compile_tables(g)


def test_compile_tables_rejects_alternation_atom():
    """A nested IrAlternation used directly as an item's atom (an un-desugared
    group) raises UnsupportedConstructError — only IrRuleRef/IrLiteral/
    IrCharClass are valid normalised atoms."""
    inner = IrAlternation(IrSequence(IrItem(IrLiteral("a"))))
    rule = IrRule("s", IrAlternation(IrSequence(IrItem(inner))))
    g = IrAst(rules=IrSeq(rule), start="s")
    with pytest.raises(UnsupportedConstructError):
        compile_tables(g)


# ── terms_for / char_leaf caching ─────────────────────────────────────────


def test_terms_for_consistent_across_repeat_calls():
    """terms_for(char) called twice with the same char returns the same term ids."""
    tables = compile_tables(_digit_grammar())
    first = tables.terms_for("5")
    second = tables.terms_for("5")
    assert first == second


def test_terms_for_caches_per_distinct_char():
    """Repeated calls with the same char do not grow the term cache."""
    tables = compile_tables(_digit_grammar())
    tables.terms_for("5")
    tables.terms_for("5")
    tables.terms_for("5")
    assert tables.cache_sizes[0] == 1


def test_terms_for_correctness_digit_matches_and_rejects():
    """terms_for finds the digit terminal for a digit char, none for a letter."""
    tables = compile_tables(_digit_grammar())
    assert len(tables.terms_for("7")) == 1
    assert len(tables.terms_for("z")) == 0


def test_char_leaf_returns_interned_literal():
    """char_leaf(char) called twice with the same char returns the same object."""
    tables = compile_tables(_digit_grammar())
    leaf1 = tables.char_leaf("3")
    leaf2 = tables.char_leaf("3")
    assert leaf1 is leaf2
    assert leaf1 == IrLiteral("3")


def test_char_leaf_caches_per_distinct_char():
    """Repeated calls with the same char do not grow the leaf cache."""
    tables = compile_tables(_digit_grammar())
    tables.char_leaf("3")
    tables.char_leaf("3")
    assert tables.cache_sizes[1] == 1


# ── Negated char-class terminals ─────────────────────────────────────────


def negated_grammar() -> IrAst:
    """s = [^"] — one rule with a single negated-char-class terminal."""
    atom = IrNot(IrCharClass(IrChr('"')))
    rule = IrRule("s", IrAlternation(IrSequence(IrItem(atom))))
    return IrAst(rules=IrSeq(rule), start="s")


def test_compile_tables_accepts_negated_charclass_terminal():
    """A normalised IrNot(IrCharClass) compiles without raising."""
    tables = compile_tables(negated_grammar())
    assert isinstance(tables, ParserTables)


def test_negated_charclass_compiles_as_length_one_terminal():
    """A negated char-class scans one column, like a plain char-class."""
    tables = compile_tables(negated_grammar())
    assert tables.terms.lens == (1,)


def test_terms_for_finds_negated_terminal_outside_set():
    """terms_for finds the negated terminal for a char outside its set."""
    tables = compile_tables(negated_grammar())
    assert len(tables.terms_for("a")) == 1
    assert len(tables.terms_for('"')) == 0


# ── Table types ────────────────────────────────────────────────────────


def test_parser_tables_composes_code_and_decode_tables():
    """ParserTables exposes .codes (CodeTables) and .decode (DecodeTables)."""
    tables = compile_tables(_digit_grammar())
    assert isinstance(tables.codes, CodeTables)
    assert isinstance(tables.decode, DecodeTables)
    assert isinstance(tables, ParserTables)


def test_parser_tables_start_id_matches_start_rule():
    """start_id resolves to the rule_id of the grammar's declared start rule."""
    g = _digit_grammar()
    tables = compile_tables(g)
    assert tables.start_id == tables.decode.rule_ids["digit"]


def test_decode_tables_rule_refs_match_rule_names():
    """decode.rule_refs[rid] is an IrRuleRef naming the same rule as rule_names[rid]."""
    tables = compile_tables(_word_grammar())
    for rid, name in enumerate(tables.decode.rule_names):
        assert str(tables.decode.rule_refs[rid]) == name


# ── rule_seeds / rule_dot0 (Task 1: per-arm seed-pair column) ────────────


def test_rule_seeds_has_one_pair_per_arm():
    """s = s s / 'a' has 2 arms — rule_seeds[s] carries exactly 2 pairs."""
    tables = compile_tables(_sss_grammar())
    s_rid = tables.decode.rule_ids["s"]
    assert len(tables.codes.rule_seeds[s_rid]) == 2


def test_rule_seeds_pair_shifted_code_matches_dot0():
    """Each pair's first element is the arm's dot-0 code, pre-shifted."""
    tables = compile_tables(_sss_grammar())
    s_rid = tables.decode.rule_ids["s"]
    for shifted, _sym in tables.codes.rule_seeds[s_rid]:
        dot0_code = shifted >> ORIGIN_BITS
        assert shifted == dot0_code << ORIGIN_BITS


def test_rule_seeds_pair_second_element_matches_next_sym():
    """Each pair's second element is next_sym at that arm's dot-0 code."""
    tables = compile_tables(_sss_grammar())
    s_rid = tables.decode.rule_ids["s"]
    for shifted, sym in tables.codes.rule_seeds[s_rid]:
        dot0_code = shifted >> ORIGIN_BITS
        assert sym == tables.codes.next_sym[dot0_code]


def test_rule_dot0_round_trips_rule_seeds():
    """rule_dot0[rid] recovers exactly the dot-0 codes packed into rule_seeds."""
    tables = compile_tables(_sss_grammar())
    s_rid = tables.decode.rule_ids["s"]
    expected = tuple(
        shifted >> ORIGIN_BITS for shifted, _ in tables.codes.rule_seeds[s_rid]
    )
    assert tables.codes.rule_dot0[s_rid] == expected


def test_rule_seeds_empty_for_undefined_rule():
    """A rule referenced but never defined seeds no pairs — prediction seeds nothing."""
    tables = compile_tables(undefined_ref_grammar())
    missing_rid = tables.decode.rule_ids["missing"]
    assert tables.codes.rule_seeds[missing_rid] == ()


def test_rule_dot0_empty_for_undefined_rule():
    """The derived rule_dot0 view agrees: () for a referenced-but-undefined rule."""
    tables = compile_tables(undefined_ref_grammar())
    missing_rid = tables.decode.rule_ids["missing"]
    assert tables.codes.rule_dot0[missing_rid] == ()


def test_rule_seed_gates_pair_prefix_matches_rule_seeds():
    """Each triple's first two elements are exactly the `rule_seeds` pair view."""
    tables = compile_tables(_sss_grammar())
    s_rid = tables.decode.rule_ids["s"]
    triples = tables.codes.rule_seed_gates[s_rid]
    pairs = tables.codes.rule_seeds[s_rid]
    assert tuple(triple[:2] for triple in triples) == pairs


# ── rule_seed_gates: FIRST gate semantics (Task 2) ───────────────────────


def test_empty_deriving_arm_gate_is_none():
    """nullish = '' — the empty arm's gate is None (always seed)."""
    tables = compile_tables(nullable_grammar())
    rid = tables.decode.rule_ids["nullish"]
    ((_shifted, _sym, gate),) = tables.codes.rule_seed_gates[rid]
    assert gate is None


def test_negated_charclass_arm_gate_is_none():
    """s = [^"] — an IrNot atom poisons the arm's FIRST gate to None."""
    tables = compile_tables(negated_grammar())
    s_rid = tables.decode.rule_ids["s"]
    ((_shifted, _sym, gate),) = tables.codes.rule_seed_gates[s_rid]
    assert gate is None


def test_over_cap_charclass_arm_gate_is_none():
    """A charclass wider than the expansion cap poisons its own arm's gate."""
    wide = IrRule(
        "wide",
        IrAlternation(
            IrSequence(IrItem(IrCharClass(IrRange(IrChr(chr(0)), IrChr(chr(0x2000))))))
        ),
    )
    g = IrAst(rules=IrSeq(wide), start="wide")
    tables = compile_tables(g)
    wide_rid = tables.decode.rule_ids["wide"]
    ((_shifted, _sym, gate),) = tables.codes.rule_seed_gates[wide_rid]
    assert gate is None


def test_over_cap_poison_propagates_transitively_through_ruleref():
    """A rule referencing a poisoned rule is itself poisoned (gate None)."""
    wide = IrRule(
        "wide",
        IrAlternation(
            IrSequence(IrItem(IrCharClass(IrRange(IrChr(chr(0)), IrChr(chr(0x2000))))))
        ),
    )
    outer = IrRule("outer", IrAlternation(IrSequence(IrItem(IrRuleRef("wide")))))
    g = IrAst(rules=IrSeq(outer, wide), start="outer")
    tables = compile_tables(g)
    outer_rid = tables.decode.rule_ids["outer"]
    ((_shifted, _sym, gate),) = tables.codes.rule_seed_gates[outer_rid]
    assert gate is None


def test_plain_charclass_arm_gate_is_its_charset():
    """digit = [0-9] — the arm's gate is exactly the charclass' char set."""
    tables = compile_tables(_digit_grammar())
    rid = tables.decode.rule_ids["digit"]
    ((_shifted, _sym, gate),) = tables.codes.rule_seed_gates[rid]
    assert gate == frozenset("0123456789")


def test_nullable_prefix_continuation_unions_first_of_next_symbol():
    """arm = [a, b] with `a` nullable: gate is FIRST(a) ∪ FIRST(b)."""
    a_rule = IrRule(
        "a",
        IrAlternation(
            IrSequence(IrItem(IrLiteral("x"))),
            IrSequence(),  # empty arm — makes `a` nullable
        ),
    )
    b_rule = IrRule(
        "b",
        IrAlternation(IrSequence(IrItem(IrCharClass(IrRange(IrChr("0"), IrChr("9")))))),
    )
    outer = IrRule(
        "outer",
        IrAlternation(IrSequence(IrItem(IrRuleRef("a")), IrItem(IrRuleRef("b")))),
    )
    g = IrAst(rules=IrSeq(outer, a_rule, b_rule), start="outer")
    tables = compile_tables(g)
    outer_rid = tables.decode.rule_ids["outer"]
    ((_shifted, _sym, gate),) = tables.codes.rule_seed_gates[outer_rid]
    assert gate == frozenset("x0123456789")


def test_multichar_literal_arm_gate_is_first_char_only():
    """s = 'abc' — the arm's gate is just its first char, not the whole literal."""
    rule = IrRule("s", IrAlternation(IrSequence(IrItem(IrLiteral("abc")))))
    g = IrAst(rules=IrSeq(rule), start="s")
    tables = compile_tables(g)
    s_rid = tables.decode.rule_ids["s"]
    ((_shifted, _sym, gate),) = tables.codes.rule_seed_gates[s_rid]
    assert gate == frozenset("a")


def test_run_term_arm_gate_is_the_run_charset():
    """A collapsed run-terminal arm's gate is the run's own charset."""
    run = RunTerm(frozenset("ab"), 1, RUN_STR)
    placeholder = IrRule("s", IrAlternation(IrSequence()))
    g = IrAst(rules=IrSeq(placeholder), start="s")
    tables = build_tables(g, runs={"s": (run, False)})
    s_rid = tables.decode.rule_ids["s"]
    ((_shifted, _sym, gate),) = tables.codes.rule_seed_gates[s_rid]
    assert gate == frozenset("ab")


# ── Sanity on the module constants ────────────────────────────────────────


def test_advance_is_one_shifted_by_origin_bits():
    """ADVANCE == 1 << ORIGIN_BITS, per the packing scheme."""
    assert ADVANCE == 1 << ORIGIN_BITS
