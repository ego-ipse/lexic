"""Tests for the structured-noise recognizer (:mod:`lexic.parsing.pda.core.scanner`).

Pins the folding-aware skip semantics against the real GBNF/ABNF noise rules —
the property that makes the P3/P5 spine demotions sound: ``(c-wsp)*`` folds a
``c-nl`` only when a ``wsp`` follows, comments are skipped whole, and the
recogniser opts out (``None``) on any non-simple closure.
"""

from __future__ import annotations

import pytest

from lexic.grammars import get_flavour
from lexic.ir.base import IrChr, IrNone, IrSeq
from lexic.ir.nodes import (
    IrAlternation,
    IrAst,
    IrCharClass,
    IrItem,
    IrLiteral,
    IrQuantifier,
    IrRange,
    IrRule,
    IrRuleRef,
    IrSequence,
)
from lexic.parsing.fold import lift_optional_nullables
from lexic.parsing.pda.core.scanner import (
    SG_PROBE,
    SG_SCAN,
    ScanGate,
    build_recognizer,
    scan_gate_take,
    scan_match,
    scan_run,
    scan_run_any,
)
from tests.unit.lexic.parsing.pda.analysis.test_analysis import (
    self_grammar_analysis,
    sg_scan_arm_fixture_analysis,
)


def flavour_rules(name: str) -> dict[str, IrRule]:
    """The lifted self-grammar rule table for flavour ``name``."""
    grammar = lift_optional_nullables(get_flavour(name).grammar)
    return {str(r.name): r for r in grammar.rules}


# ── ABNF c-wsp: LWS folding falls out of arm-in-order matching ──────────────


@pytest.fixture(name="cwsp")
def cwsp_fixture():
    """The ABNF ``c-wsp`` recogniser and its root index."""
    rec = build_recognizer(flavour_rules("abnf"), frozenset({"c-wsp"}))
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
    rec = build_recognizer(flavour_rules("gbnf"), frozenset({"n"}))
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
    rec = build_recognizer(flavour_rules("abnf"), frozenset({"c-nl", "filler"}))
    assert rec is not None
    roots = (rec.index["c-nl"], rec.index["filler"])
    # blank line, then a comment line, then a rulename start
    assert scan_run_any("\n;c\nq = x", 0, rec, roots) == 4
    # nothing but noise then EOF
    assert scan_run_any("\n\n", 0, rec, roots) == 2
    # immediate content
    assert scan_run_any("q = x", 0, rec, roots) == 0


# ── scan_gate_take — SG_PROBE (P5 rulename-probe) coverage ──────────────────


@pytest.fixture(name="probe_gate")
def probe_gate_fixture():
    """A tiny ``name``/``ws`` recognizer + ``ScanGate(SG_PROBE, ...)`` — the
    GBNF ``sequence[1]`` shape in miniature: take on ``{`` directly, else
    probe ``name ws* "::="`` (``take_on_match=False`` — a matched header
    refutes the take reading)."""
    name_rule = IrRule(
        "name",
        IrAlternation(
            IrSequence(
                IrItem(
                    IrCharClass(IrRange(IrChr("a"), IrChr("z"))),
                    IrQuantifier(1, IrNone),
                )
            )
        ),
    )
    ws_rule = IrRule(
        "ws",
        IrAlternation(
            IrSequence(IrItem(IrCharClass(IrChr(" ")), IrQuantifier(0, IrNone)))
        ),
        False,
    )
    rules = {"name": name_rule, "ws": ws_rule}
    rec = build_recognizer(rules, frozenset({"name", "ws"}))
    assert rec is not None
    name_idx, ws_idx = rec.index["name"], rec.index["ws"]
    gate = ScanGate(
        SG_PROBE,
        rec,
        (ws_idx,),
        (frozenset({"{"}), False),
        (name_idx, ws_idx, "::=", False),
    )
    return gate


def test_sg_probe_take_char_admits_without_probing(probe_gate):
    """A char in the take-set admits the loop directly — no probe needed."""
    assert scan_gate_take("{", 0, probe_gate) is True


def test_sg_probe_header_match_is_refuted(probe_gate):
    """A rulename-led overlap char followed by a matching header (``::=``)
    refutes the take reading (``take_on_match=False``) — the loop exits."""
    assert scan_gate_take("abc::=", 0, probe_gate) is False


def test_sg_probe_rulename_led_header_absent_admits(probe_gate):
    """Rulename-led but no ``::=`` header after it — the take reading stands."""
    assert scan_gate_take("abcXYZ", 0, probe_gate) is True


def test_sg_probe_eof_exits(probe_gate):
    """End of input is neither a take char nor rulename-led — the loop exits."""
    assert scan_gate_take("", 0, probe_gate) is False


def test_sg_probe_non_take_non_name_char_exits(probe_gate):
    """A char that is neither in the take-set nor a rulename lead exits."""
    assert scan_gate_take("!!!", 0, probe_gate) is False


def test_sg_scan_with_no_take_set_always_declines(probe_gate):
    """``SG_SCAN`` with ``gate.take is None`` is the defensive always-``False``
    path — it never reaches the probe machinery."""
    rec = probe_gate.rec
    ws_idx = probe_gate.roots[0]
    gate = ScanGate(SG_SCAN, rec, (ws_idx,), None)
    assert scan_gate_take("{", 0, gate) is False


def test_single_literal_recognizer():
    """A one-rule, one-literal recogniser matches a single-char run."""
    rule = IrRule("r", IrAlternation(IrSequence(IrItem(IrLiteral(" ")))))
    ast = IrAst(rules=IrSeq(rule), start="r")
    rules = {str(r.name): r for r in ast.rules}
    rec = build_recognizer(rules, frozenset({"r"}))
    assert rec is not None
    assert scan_run("  x", 0, rec, rec.index["r"]) == 2


# ── scan_gate_take — struct ARM gates (Task 4/4b) ───────────────────────────


@pytest.mark.parametrize(
    ("text", "admits"),
    [
        ("| foo", False),  # bar-arm continuation: escape to the empty arm
        ("  | foo", False),  # noise-led bar-arm continuation: same escape
        ("\nfoo ::= x", False),  # noise then the next rule's header: escape
        ('"x"', True),  # ordinary sequence content: take
        ("foo bar", True),  # a bare rulename sequence: take
    ],
)
def test_gbnf_self_arm_gate_scan_gate_take(text, admits):
    """The GBNF self-grammar's ``arm`` ``SG_PROBE`` gate (``sequence |
    empty-seq``): a rulename-led overlap followed by ``::=`` refutes the take
    reading (escape to the empty arm — the ``bar-arm``/next-rule-header
    shapes), while ordinary sequence content and a bare rulename both take."""
    analysis = self_grammar_analysis("gbnf")
    gate = analysis.taxonomy.struct_arm_gates["arm"]
    assert scan_gate_take(text, 0, gate.gate) is admits


@pytest.fixture(name="sg_scan_arm_gate")
def sg_scan_arm_gate_fixture():
    """The ``SG_SCAN`` gate off :func:`sg_scan_arm_fixture_analysis` (shared
    with ``test_analysis.test_instance_grammar_empty_last_arm_demotes_to_sg_scan``)."""
    analysis = sg_scan_arm_fixture_analysis()
    gate = analysis.taxonomy.struct_arm_gates["arm"]
    assert gate.gate.kind == SG_SCAN
    return gate.gate


@pytest.mark.parametrize(
    ("text", "admits"),
    [
        ("x", True),  # content lead, no noise
        ("  x", True),  # leading noise skipped, then content lead
        ("|", False),  # not the take char (arm content starts with x, not |)
        ("  |", False),  # noise skipped, still not the take char
        ("", False),  # end of input: escape
    ],
)
def test_sg_scan_arm_gate_scan_gate_take(sg_scan_arm_gate, text, admits):
    """The hand-authored ``SG_SCAN`` arm gate: a post-noise ``x`` admits,
    anything else (including EOF) escapes to the empty arm."""
    assert scan_gate_take(text, 0, sg_scan_arm_gate) is admits
