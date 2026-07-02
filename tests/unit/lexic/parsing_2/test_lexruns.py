"""Tests for lexic.parsing_2.lexruns — run-terminal detection and collapse.

New module: proves a synthetic star/plus rule's collapse to a single
maximal-munch :class:`~lexic.parsing_2.tables.RunTerm` (fixed charset,
derivation-uniqueness, follow-disjointness) and reconstructs it as compiled
tables. This file covers ``_expand_atom``'s charset extraction and poisoning,
``run_candidates``'s detection and memoisation, ``recognition_tables``'s
collapse and result parity with plain tables, and ``unit_leaves``'s
transitive charset-rule walk.
"""

from __future__ import annotations

from lexic.grammars.abnf_2 import ABNF_GRAMMAR
from lexic.ir.base import IrSeq
from lexic.ir.nodes import (
    IrAlternation,
    IrAst,
    IrCharClass,
    IrChr,
    IrItem,
    IrLiteral,
    IrRange,
    IrRule,
    IrRuleRef,
    IrSequence,
)
from lexic.parsing_2.kernel import Kernel
from lexic.parsing_2.lexruns import (
    _expand_atom,
    recognition_tables,
    run_candidates,
    unit_leaves,
)
from lexic.parsing_2.normalize import SYNTHETIC_PREFIX, normalize
from lexic.parsing_2.tables import RunTerm, compile_tables

# ── _expand_atom ──────────────────────────────────────────────────────


def test_expand_atom_single_char_literal_returns_its_char():
    """A single-char IrLiteral expands to a one-char frozenset."""
    assert _expand_atom(IrLiteral("a")) == frozenset("a")


def test_expand_atom_multichar_literal_returns_none():
    """A literal longer than one char is not a char-unit — poisoned."""
    assert _expand_atom(IrLiteral("ab")) is None


def test_expand_atom_charclass_with_ranges_returns_charset():
    """A range char-class expands to every char in the range."""
    atom = IrCharClass(IrRange(IrChr("a"), IrChr("c")))
    assert _expand_atom(atom) == frozenset("abc")


def test_expand_atom_charclass_with_bare_chr_returns_charset():
    """A char-class with a bare IrChr element expands to that one char."""
    atom = IrCharClass(IrChr("q"))
    assert _expand_atom(atom) == frozenset("q")


def test_expand_atom_over_cap_range_poisons():
    """A range wider than the expansion cap poisons to None."""
    atom = IrCharClass(IrRange(IrChr(chr(0)), IrChr(chr(0x2000))))
    assert _expand_atom(atom) is None


def test_expand_atom_ruleref_is_not_a_terminal_atom():
    """An IrRuleRef is never a char-unit — poisoned regardless of shape."""
    assert _expand_atom(IrRuleRef("digit")) is None


# ── run_candidates ────────────────────────────────────────────────────


def test_run_candidates_detects_collapsible_rules_on_abnf_grammar():
    """run_candidates finds synthetic star/plus rules on the real ABNF grammar."""
    g = normalize(ABNF_GRAMMAR)
    tables = compile_tables(g)
    candidates = run_candidates(tables)
    assert candidates
    for name in candidates:
        assert name.startswith(SYNTHETIC_PREFIX)


def test_run_candidates_memoised_per_tables_object():
    """Calling run_candidates twice on the SAME tables returns the same dict."""
    g = normalize(ABNF_GRAMMAR)
    tables = compile_tables(g)
    first = run_candidates(tables)
    second = run_candidates(tables)
    assert first is second


def test_run_candidates_empty_for_grammar_with_no_synthetic_rules():
    """A plain (non-quantified) grammar has no run candidates."""
    g = IrAst(
        rules=IrSeq(
            IrRule(
                "digit",
                IrAlternation(
                    IrSequence(IrItem(IrCharClass(IrRange(IrChr("0"), IrChr("9")))))
                ),
            ),
        ),
        start="digit",
    )
    tables = compile_tables(g)
    assert run_candidates(tables) == {}


# ── recognition_tables ────────────────────────────────────────────────


def test_recognition_tables_collapses_when_candidates_exist():
    """recognition_tables introduces RunTerm atoms for a grammar with candidates."""
    g = normalize(ABNF_GRAMMAR)
    tables = recognition_tables(g)
    assert any(isinstance(atom, RunTerm) for atom in tables.terms.atoms)


def test_recognition_tables_returns_plain_when_no_candidates():
    """A grammar with nothing to collapse gets back the plain compiled tables."""
    g = IrAst(
        rules=IrSeq(
            IrRule(
                "digit",
                IrAlternation(
                    IrSequence(IrItem(IrCharClass(IrRange(IrChr("0"), IrChr("9")))))
                ),
            ),
        ),
        start="digit",
    )
    assert recognition_tables(g) is compile_tables(g)


def test_recognition_tables_memoised_per_grammar_object():
    """Calling recognition_tables twice on the SAME grammar returns the same tables."""
    g = normalize(ABNF_GRAMMAR)
    first = recognition_tables(g)
    second = recognition_tables(g)
    assert first is second


def test_recognition_tables_distinct_grammar_objects_get_distinct_tables():
    """Two structurally-identical but distinct grammar objects don't share tables."""
    g1 = normalize(ABNF_GRAMMAR)
    g2 = normalize(ABNF_GRAMMAR)
    assert recognition_tables(g1) is not recognition_tables(g2)


_ABNF_SAMPLES = (
    'rule = "a" "b"\r\n',
    "foo = bar / baz\r\n",
    "x = 1*DIGIT\r\n",
    "not a valid abnf line at all !!\r\n",
    "",
)


def test_recognition_tables_matches_plain_recognition_on_samples():
    """The maximally-collapsed tables accept/reject exactly as the plain ones do."""
    g = normalize(ABNF_GRAMMAR)
    plain = compile_tables(g)
    collapsed = recognition_tables(g)
    for text in _ABNF_SAMPLES:
        plain_accept = Kernel(plain, text, record_links=False).run().accept >= 0
        collapsed_accept = Kernel(collapsed, text, record_links=False).run().accept >= 0
        assert plain_accept == collapsed_accept, text


# ── unit_leaves ───────────────────────────────────────────────────────


def test_unit_leaves_non_synthetic_rule_is_itself():
    """A non-synthetic rule id resolves to itself, with no bare terminal."""
    g = IrAst(
        rules=IrSeq(
            IrRule(
                "digit",
                IrAlternation(
                    IrSequence(IrItem(IrCharClass(IrRange(IrChr("0"), IrChr("9")))))
                ),
            ),
        ),
        start="digit",
    )
    tables = compile_tables(g)
    rid = tables.decode.rule_ids["digit"]
    assert unit_leaves(tables, rid) == ({rid}, False)


def test_unit_leaves_synthetic_charset_rule_transitive_leaves_and_bare_flag():
    """A synthetic rule hopping through another synthetic rule collects the
    transitive non-synthetic leaf and sets has_bare from the bare-terminal arm."""
    digit = IrRule(
        "digit",
        IrAlternation(IrSequence(IrItem(IrCharClass(IrRange(IrChr("0"), IrChr("9")))))),
    )
    inner = IrRule(
        f"{SYNTHETIC_PREFIX}inner",
        IrAlternation(
            IrSequence(IrItem(IrLiteral("x"))),
            IrSequence(IrItem(IrRuleRef("digit"))),
        ),
    )
    outer = IrRule(
        f"{SYNTHETIC_PREFIX}outer",
        IrAlternation(IrSequence(IrItem(IrRuleRef(f"{SYNTHETIC_PREFIX}inner")))),
    )
    g = IrAst(rules=IrSeq(outer, inner, digit), start=f"{SYNTHETIC_PREFIX}outer")
    tables = compile_tables(g)
    outer_rid = tables.decode.rule_ids[f"{SYNTHETIC_PREFIX}outer"]
    digit_rid = tables.decode.rule_ids["digit"]
    assert unit_leaves(tables, outer_rid) == ({digit_rid}, True)


def test_unit_leaves_malformed_shape_returns_none():
    """A synthetic rule whose arm is not a single item is not a charset shape."""
    bad = IrRule(
        f"{SYNTHETIC_PREFIX}bad",
        IrAlternation(IrSequence(IrItem(IrLiteral("a")), IrItem(IrLiteral("b")))),
    )
    g = IrAst(rules=IrSeq(bad), start=f"{SYNTHETIC_PREFIX}bad")
    tables = compile_tables(g)
    rid = tables.decode.rule_ids[f"{SYNTHETIC_PREFIX}bad"]
    assert unit_leaves(tables, rid) is None
