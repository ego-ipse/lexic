"""Tests for the structured-noise recognizer (:mod:`lexic.parsing.pda.scanner`).

Pins the folding-aware skip semantics against the real GBNF/ABNF noise rules —
the property that makes the P3/P5 spine demotions sound: ``(c-wsp)*`` folds a
``c-nl`` only when a ``wsp`` follows, comments are skipped whole, and the
recogniser opts out (``None``) on any non-simple closure.
"""

from __future__ import annotations

import pytest

from lexic.grammars import get_flavour
from lexic.ir.base import IrNone, IrSeq
from lexic.ir.nodes import (
    IrAlternation,
    IrAst,
    IrItem,
    IrLiteral,
    IrQuantifier,
    IrRule,
    IrRuleRef,
    IrSequence,
)
from lexic.parsing.fold import lift_optional_nullables
from lexic.parsing.pda.scanner import (
    build_recognizer,
    scan_match,
    scan_run,
    scan_run_any,
)


def _rules(name: str) -> dict[str, IrRule]:
    """The lifted self-grammar rule table for flavour ``name``."""
    grammar = lift_optional_nullables(get_flavour(name).grammar)
    return {str(r.name): r for r in grammar.rules}


# ── ABNF c-wsp: LWS folding falls out of arm-in-order matching ──────────────


@pytest.fixture(name="cwsp")
def _cwsp():
    """The ABNF ``c-wsp`` recogniser and its root index."""
    rec = build_recognizer(_rules("abnf"), frozenset({"c-wsp"}))
    assert rec is not None
    return rec, rec.index["c-wsp"]


@pytest.mark.parametrize(
    ("text", "end"),
    [
        ("   x", 3),  # plain whitespace run
        (" \t x", 3),  # sp/htab mix
        ("\n x", 2),  # c-nl + wsp folds (crlf then space)
        ("\n/", 0),  # bare c-nl NOT followed by wsp: no fold, run stops
        (";comment\n x", 10),  # comment (a c-nl) + wsp folds
        (";comment\n/", 0),  # comment then non-wsp: no fold, stops
        ("\r\n a", 3),  # crlf + wsp folds
        ("a", 0),  # no noise
    ],
)
def test_cwsp_scan_run_folds_only_before_wsp(cwsp, text, end):
    """A maximal ``(c-wsp)*`` skip folds a ``c-nl`` iff a ``wsp`` follows it."""
    rec, idx = cwsp
    assert scan_run(text, 0, rec, idx) == end


@pytest.mark.parametrize(
    ("text", "matches"),
    [
        (" x", True),
        ("\n x", True),  # folds
        ("\n/", False),  # bare c-nl, no wsp
        ("x", False),
        (";c\n a", True),  # comment folds
    ],
)
def test_cwsp_scan_match_is_the_folding_gate(cwsp, text, matches):
    """``scan_match`` (ABNF ``rule[5]`` gate): a ``c-wsp`` begins here iff foldable."""
    rec, idx = cwsp
    assert scan_match(text, 0, rec, idx) is matches


# ── GBNF n: comment-line runs ───────────────────────────────────────────────


@pytest.mark.parametrize(
    ("text", "end"),
    [
        ("   x", 3),
        ("# comment\nx", 10),  # one comment-line
        ("# c\n # d\ny", 9),  # comment, space, comment
        ("\t\n x", 3),  # whitespace run
        ("x", 0),
    ],
)
def test_gbnf_n_scan_run_skips_comment_lines(text, end):
    """GBNF ``n = nunit+`` skips whitespace and whole ``#…\\n`` comment lines."""
    rec = build_recognizer(_rules("gbnf"), frozenset({"n"}))
    assert rec is not None
    assert scan_run(text, 0, rec, rec.index["n"]) == end


# ── opt-out paths ───────────────────────────────────────────────────────────


def test_build_opts_out_on_undefined_ref():
    """A ref outside the rule table makes the recogniser opt out (``None``)."""
    rule = IrRule("r", IrAlternation(IrSequence(IrItem(IrRuleRef("missing")))))
    rules = {str(rule.name): rule}
    assert build_recognizer(rules, frozenset({"r"})) is None


def test_build_opts_out_on_cycle():
    """A cyclic closure (a recogniser that could loop without consuming) opts out."""
    a = IrRule("a", IrAlternation(IrSequence(IrItem(IrRuleRef("b")))))
    b = IrRule("b", IrAlternation(IrSequence(IrItem(IrRuleRef("a")))))
    rules = {"a": a, "b": b}
    assert build_recognizer(rules, frozenset({"a"})) is None


def test_build_opts_out_on_inline_group():
    """An inline alternation group is not a simple recogniser construct."""
    grp = IrAlternation(IrSequence(IrItem(IrLiteral("x"))))
    rule = IrRule("r", IrAlternation(IrSequence(IrItem(grp))))
    rules = {str(rule.name): rule}
    assert build_recognizer(rules, frozenset({"r"})) is None


def test_literal_run_is_recognized():
    """A multi-char literal atom matches by prefix, looping on its quantifier."""
    rule = IrRule(
        "r", IrAlternation(IrSequence(IrItem(IrLiteral("ab"), IrQuantifier(0, IrNone))))
    )
    rec = build_recognizer({"r": rule}, frozenset({"r"}))
    assert rec is not None
    assert scan_run("ababX", 0, rec, rec.index["r"]) == 4


def test_scan_run_any_skips_union_of_noise_roots():
    """A run over the union of ABNF ``c-nl``/``filler`` skips whole noise lines.

    The factored ``rl-cont`` leads with ``c-nl filler*``; skipping the union of
    the noise roots lands on the first content char (a rulename alpha) or EOF.
    """
    rec = build_recognizer(_rules("abnf"), frozenset({"c-nl", "filler"}))
    assert rec is not None
    roots = (rec.index["c-nl"], rec.index["filler"])
    # blank line, then a comment line, then a rulename start
    assert scan_run_any("\n;c\nq = x", 0, rec, roots) == 4
    # nothing but noise then EOF
    assert scan_run_any("\n\n", 0, rec, roots) == 2
    # immediate content
    assert scan_run_any("q = x", 0, rec, roots) == 0


def test_single_literal_recognizer():
    """A one-rule, one-literal recogniser matches a single-char run."""
    rule = IrRule("r", IrAlternation(IrSequence(IrItem(IrLiteral(" ")))))
    ast = IrAst(rules=IrSeq(rule), start="r")
    rules = {str(r.name): r for r in ast.rules}
    rec = build_recognizer(rules, frozenset({"r"}))
    assert rec is not None
    assert scan_run("  x", 0, rec, rec.index["r"]) == 2
