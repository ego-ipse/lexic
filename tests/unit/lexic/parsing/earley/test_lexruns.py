"""Tests for lexic.parsing.earley.lexruns — run-terminal detection and collapse.

New module: proves a synthetic star/plus rule's collapse to a single
maximal-munch :class:`~lexic.parsing.earley.tables.RunTerm` (fixed charset,
derivation-uniqueness, follow-disjointness) and reconstructs it as compiled
tables. This file covers ``run_candidates``'s detection and memoisation,
``recognition_tables``'s collapse and result parity with plain tables, and
``unit_leaves``'s transitive charset-rule walk. ``expand_atom``'s own charset
extraction/poisoning behavior moved home to ``tables.py`` (Task 2, alongside
``_MAX_CHARSET``/``Charset``) — see ``test_tables.py``; this module still
imports it for internal use, so a single smoke test below pins that the
back-compat import path keeps working.
"""

from __future__ import annotations

from lexic.grammars.abnf import ABNF_GRAMMAR
from lexic.ir import (
    IrAlternation,
    IrAst,
    IrCharClass,
    IrChr,
    IrItem,
    IrLiteral,
    IrNone,
    IrNot,
    IrQuantifier,
    IrRule,
    IrSeq,
    IrSequence,
)
from lexic.parsing.earley.kernel import Kernel
from lexic.parsing.earley.lexruns import expand_atom as _expand_atom_via_lexruns
from lexic.parsing.earley.lexruns import (
    recognition_tables,
    run_candidates,
    unit_leaves,
)
from lexic.parsing.earley.normalize import SYNTHETIC_PREFIX, normalize
from lexic.parsing.earley.tables import RunTerm, compile_tables
from lexic.parsing.earley.tables import expand_atom as _expand_atom_canonical
from tests.unit.lexic.parsing.ir_fixtures import digit_grammar as _digit_grammar
from tests.unit.lexic.parsing.ir_fixtures import (
    malformed_synthetic_rule,
    nested_synthetic_grammar,
)

# ── expand_atom re-export smoke test (moved home to tables.py) ──────────


def test_expand_atom_still_importable_from_lexruns():
    """``expand_atom`` now lives in ``tables.py``; ``lexruns`` re-imports it
    for its own internal use, so this import path keeps working for anyone
    still written against it — same function object, not a copy."""
    assert _expand_atom_via_lexruns is _expand_atom_canonical


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
    tables = compile_tables(_digit_grammar())
    assert run_candidates(tables) == {}


def test_run_candidates_excludes_negated_class_star():
    """A ``[^"]*`` run is not collapsible — its unit poisons, so it stays per-char."""
    quote = IrItem(IrLiteral('"'))
    body = IrItem(
        IrNot(IrCharClass(IrChr('"'))),
        IrQuantifier(0, IrNone),
    )
    rule = IrRule("s", IrAlternation(IrSequence(quote, body, quote)))
    g = normalize(IrAst(rules=IrSeq(rule), start="s"))
    assert run_candidates(compile_tables(g)) == {}


# ── recognition_tables ────────────────────────────────────────────────


def test_recognition_tables_collapses_when_candidates_exist():
    """recognition_tables introduces RunTerm atoms for a grammar with candidates."""
    g = normalize(ABNF_GRAMMAR)
    tables = recognition_tables(g)
    assert any(isinstance(atom, RunTerm) for atom in tables.terms.atoms)


def test_recognition_tables_returns_plain_when_no_candidates():
    """A grammar with nothing to collapse gets back the plain compiled tables."""
    g = _digit_grammar()
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


ABNF_SAMPLES = (
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
    for text in ABNF_SAMPLES:
        plain_accept = Kernel(plain, text, record_links=False).run().accept >= 0
        collapsed_accept = Kernel(collapsed, text, record_links=False).run().accept >= 0
        assert plain_accept == collapsed_accept, text


# ── unit_leaves ───────────────────────────────────────────────────────


def test_unit_leaves_non_synthetic_rule_is_itself():
    """A non-synthetic rule id resolves to itself, with no bare terminal."""
    tables = compile_tables(_digit_grammar())
    rid = tables.decode.rule_ids["digit"]
    assert unit_leaves(tables, rid) == ({rid}, False)


def test_unit_leaves_synthetic_charset_rule_transitive_leaves_and_bare_flag():
    """A synthetic rule hopping through another synthetic rule collects the
    transitive non-synthetic leaf and sets has_bare from the bare-terminal arm."""
    g = nested_synthetic_grammar()
    tables = compile_tables(g)
    outer_rid = tables.decode.rule_ids[f"{SYNTHETIC_PREFIX}outer"]
    digit_rid = tables.decode.rule_ids["digit"]
    assert unit_leaves(tables, outer_rid) == ({digit_rid}, True)


def test_unit_leaves_malformed_shape_returns_none():
    """A synthetic rule whose arm is not a single item is not a charset shape."""
    bad = malformed_synthetic_rule()
    g = IrAst(rules=IrSeq(bad), start=f"{SYNTHETIC_PREFIX}bad")
    tables = compile_tables(g)
    rid = tables.decode.rule_ids[f"{SYNTHETIC_PREFIX}bad"]
    assert unit_leaves(tables, rid) is None
