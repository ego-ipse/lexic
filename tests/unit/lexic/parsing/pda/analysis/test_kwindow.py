"""Tests for lexic.parsing.pda.analysis.kwindow — the FIRST_k fixpoint + gate functions.

Pins the fixed (post-Fable-review) semantics of :class:`KWindowFirst`,
:func:`arm_gate`/:func:`loop_gate`, and their small helpers, against
``zzz_current_work/260706-unified-parse-engine/poc_v4_verify.py`` part 4 and
``FABLE_KWINDOW_REVIEW.md``. Findings 1 (``lo > window budget`` silently
emptying an arm's prefix set) and 2 (``loop_gate``'s old two-rep union
under-covering 3-rep windows at k=3) are both fixed on disk; this file pins
the fixed behaviour so it cannot regress.
"""

from __future__ import annotations

import string

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
from lexic.parsing.pda.analysis.analysis import GrammarAnalysis
from lexic.parsing.pda.analysis.kwindow import (
    END,
    MORE,
    UNK,
    KWindowFirst,
    arm_gate,
    collide,
    extend_follow,
    loop_gate,
    separable,
)
from lexic.parsing.pda.core.charsets import CharSet
from tests.unit.lexic.parsing.pda.analysis.test_analysis import _items as _rule_items
from tests.unit.lexic.parsing.pda.analysis.test_analysis import (
    _lifted_analysis as _ground_truth_analysis,
)

EOF = CharSet.from_chars("")


def _digits() -> IrCharClass:
    """A ``[0-9]`` char class, fresh each call."""
    return IrCharClass(IrRange(IrChr("0"), IrChr("9")))


# ── FIRST_k fixpoint: END/MORE/UNK tagging ─────────────────────────────────


def test_literal_end_tag_when_it_fits_the_window():
    """A literal shorter than or equal to the window is END, char-per-position."""
    solver = KWindowFirst({}, 3)
    prefs = solver.atom_prefixes(IrLiteral("ab"), 3)
    assert prefs == {((CharSet.from_chars("a"), CharSet.from_chars("b")), END)}


def test_literal_more_tag_when_window_is_shorter_than_the_text():
    """A literal longer than the window is truncated and tagged MORE."""
    solver = KWindowFirst({}, 2)
    prefs = solver.atom_prefixes(IrLiteral("abcd"), 2)
    assert prefs == {((CharSet.from_chars("a"), CharSet.from_chars("b")), MORE)}


def test_charclass_contributes_one_position_end_tag():
    """A char class is always exactly one position, tagged END."""
    solver = KWindowFirst({}, 3)
    cc = _digits()
    prefs = solver.atom_prefixes(cc, 3)
    assert prefs == {((CharSet.from_charclass(cc),), END)}


def test_ruleref_delegates_to_rule_prefixes():
    """A rule ref's prefixes are exactly the target rule's FIRST_r."""
    rule = IrRule("r", IrAlternation(IrSequence(IrItem(IrLiteral("z")))))
    solver = KWindowFirst({"r": rule}, 3)
    assert solver.atom_prefixes(IrRuleRef("r"), 3) == {
        ((CharSet.from_chars("z"),), END)
    }


def test_ruleref_cycle_guard_yields_unk_poison_for_the_recursive_arm_only():
    """Left recursion (``a ::= a 'x' | 'y'``) poisons the recursive arm; the
    ``'y'`` branch survives untouched — the poison is retained, not lost."""
    a = IrRule(
        "a",
        IrAlternation(
            IrSequence(IrItem(IrRuleRef("a")), IrItem(IrLiteral("x"))),
            IrSequence(IrItem(IrLiteral("y"))),
        ),
    )
    solver = KWindowFirst({"a": a}, 2)
    prefs = solver.rule_prefixes("a", 2)
    assert ((), UNK) in prefs
    assert ((CharSet.from_chars("y"),), END) in prefs


def test_undefined_ref_yields_unk_poison():
    """A ref to an undefined rule poisons, exactly like a cycle re-entry."""
    solver = KWindowFirst({}, 2)
    assert solver.rule_prefixes("missing", 2) == {((), UNK)}


def test_state_cap_poisons_a_fanned_out_arm():
    """A per-item fan-out past ``_STATE_CAP`` poisons the whole arm to
    ``{((), UNK)}`` rather than enumerating exponentially."""
    chars = (string.ascii_letters + string.digits)[:60]
    many = IrRule(
        "many", IrAlternation(*(IrSequence(IrItem(IrLiteral(c))) for c in chars))
    )
    items = [IrItem(IrRuleRef("many")), IrItem(IrRuleRef("many"))]
    solver = KWindowFirst({"many": many}, 2)
    assert solver.arm_prefixes(items, 2) == {((), UNK)}


def test_unk_state_collides_with_everything():
    """A UNK (poisoned) state's empty tuple collides via the min-window rule —
    there is no nullable oracle to consult; poison collides by construction."""
    poison = ((), UNK)
    other = ((CharSet.from_chars("z"),), END)
    assert collide(poison, other)


# ── extend_follow ───────────────────────────────────────────────────────────


def test_extend_follow_appends_one_follow_char_then_unk():
    """A short END prefix gets exactly one FOLLOW char appended, tagged UNK."""
    prefs = {((CharSet.from_chars("a"),), END)}
    out = extend_follow(prefs, CharSet.from_chars("q"), 2)
    assert out == {((CharSet.from_chars("a"), CharSet.from_chars("q")), UNK)}


def test_extend_follow_leaves_end_at_exactly_k_untouched():
    """A complete (END) prefix already at length ``k`` is never extended."""
    at_k = ((CharSet.from_chars("a"), CharSet.from_chars("b")), END)
    below_k = ((CharSet.from_chars("a"),), END)
    out = extend_follow({at_k, below_k}, CharSet.from_chars("q"), 2)
    assert at_k in out
    assert below_k not in out


def test_extend_follow_empty_follow_is_a_passthrough():
    """An empty FOLLOW set leaves every prefix unchanged."""
    prefs = {((CharSet.from_chars("a"),), END)}
    assert extend_follow(prefs, CharSet.EMPTY, 2) == prefs


# ── collide / separable ─────────────────────────────────────────────────────


def test_collide_positionwise_overlap_over_min_window():
    """A shorter prefix collides with a longer one sharing its lead — only the
    shorter's window positions are compared."""
    short = ((CharSet.from_chars("a"),), END)
    long_ = ((CharSet.from_chars("a"), CharSet.from_chars("b")), END)
    assert collide(short, long_)


def test_collide_false_when_a_shared_position_diverges():
    """Two same-length prefixes that diverge at any position do not collide."""
    a = ((CharSet.from_chars("a"), CharSet.from_chars("x")), END)
    b = ((CharSet.from_chars("a"), CharSet.from_chars("y")), END)
    assert not collide(a, b)


def test_separable_all_or_nothing_any_collision_fails_whole_decision():
    """One colliding pair fails the whole multi-branch decision, even when
    every other pair is clean."""
    set_a = {((CharSet.from_chars("x"),), END)}
    set_b = {((CharSet.from_chars("x"),), END)}  # collides with set_a
    set_c = {((CharSet.from_chars("z"),), END)}  # clean vs both
    assert not separable([set_a, set_b, set_c])
    assert separable([set_a, set_c])
    assert separable([set_b, set_c])


# ── never-empty-prefix-set invariant ────────────────────────────────────────


@pytest.mark.parametrize("k", [2, 3])
@pytest.mark.parametrize(
    "arm",
    [
        pytest.param(
            [IrItem(_digits(), IrQuantifier(4, IrNone)), IrItem(IrLiteral("x"))],
            id="lo-gt-k-unbounded",
        ),
        pytest.param(
            [IrItem(_digits(), IrQuantifier(4, 8)), IrItem(IrLiteral("x"))],
            id="lo-gt-k-bounded",
        ),
        pytest.param(
            [IrItem(_digits(), IrQuantifier(9, 9)), IrItem(IrLiteral("x"))],
            id="lo-gt-k-fixed",
        ),
        pytest.param([IrItem(IrLiteral("12"))], id="short-literal"),
        pytest.param([], id="nullable-empty-arm"),
    ],
)
def test_arm_prefixes_never_yields_the_empty_set(arm, k):
    """A defined-rules arm never yields ``set()`` — a vanishing derivation
    (Finding 1's failure class) would otherwise let ``separable`` pass
    vacuously."""
    solver = KWindowFirst({}, k)
    assert solver.arm_prefixes(arm, k)


# ── Finding 1: lo > window budget no longer empties the arm ─────────────────


def test_finding1_lo_gt_k_unbounded_islands_at_k2_separates_at_k3():
    """``a ::= [0-9]{4,} "x" | "12"``: the false k=2 SEP is gone (island); the
    true separator surfaces only at k=3 (digit-vs-EOF at position 3)."""
    arm1 = [IrItem(_digits(), IrQuantifier(4, IrNone)), IrItem(IrLiteral("x"))]
    arm2 = [IrItem(IrLiteral("12"))]
    assert arm_gate({}, [arm1, arm2], EOF, max_k=2) is None
    got = arm_gate({}, [arm1, arm2], EOF, max_k=3)
    assert got is not None
    assert got[0] == 3


def test_finding1_lo_gt_k_bounded_twin_islands_at_k2():
    """The bounded ``{4,8}`` variant (ABNF's ``4*8DIGIT``) fails identically
    to the unbounded one."""
    arm1 = [IrItem(_digits(), IrQuantifier(4, 8)), IrItem(IrLiteral("x"))]
    arm2 = [IrItem(IrLiteral("12"))]
    assert arm_gate({}, [arm1, arm2], EOF, max_k=2) is None
    got = arm_gate({}, [arm1, arm2], EOF, max_k=3)
    assert got is not None
    assert got[0] == 3


def test_finding1_k3_separation_rides_an_eof_carrying_charset():
    """The k=3 separator is EOF-exact: arm2's "12" is extended by the EOF
    sentinel at position 3, not a generic character — the load-bearing shape
    the part-(c) runtime window matcher must special-case."""
    arm1 = [IrItem(_digits(), IrQuantifier(4, IrNone)), IrItem(IrLiteral("x"))]
    arm2 = [IrItem(IrLiteral("12"))]
    got = arm_gate({}, [arm1, arm2], EOF, max_k=3)
    assert got is not None
    arm1_set, arm2_set = got[1]
    ((arm1_tup, arm1_tag),) = arm1_set
    ((arm2_tup, arm2_tag),) = arm2_set
    assert arm1_tag == MORE
    assert not arm1_tup[2].has("")  # arm1's 3rd position is all-digit, no EOF
    assert arm2_tag == UNK
    assert arm2_tup[2].has("")  # arm2's extended 3rd position IS the EOF sentinel
    assert not arm2_tup[2].has("5")


# ── Finding 2: loop_gate no longer under-covers 3-rep windows at k=3 ────────


def test_finding2_rep_depth_3_loop_stays_island():
    """``s ::= r{1,} "aab"; r ::= "a" | "b"``: the 3-rep window collides
    skip — ``loop_gate`` must refuse (island), not report a false SEPARABLE."""
    r = IrRule(
        "r",
        IrAlternation(
            IrSequence(IrItem(IrLiteral("a"))), IrSequence(IrItem(IrLiteral("b")))
        ),
    )
    items = [IrItem(IrRuleRef("r"), IrQuantifier(1, IrNone)), IrItem(IrLiteral("aab"))]
    assert loop_gate({"r": r}, items, 0, EOF, max_k=3) is None
    assert loop_gate({"r": r}, items, 0, EOF, max_k=2) is None


def test_finding2_k2_loop_separation_still_works():
    """A basic k=2 loop separation (position-0 discriminator) is unaffected
    by the rep-depth-3 fix."""
    items = [IrItem(IrLiteral("x"), IrQuantifier(1, IrNone)), IrItem(IrLiteral("y"))]
    got = loop_gate({}, items, 0, EOF, max_k=3)
    assert got is not None
    assert got[0] == 2


# ── soft-FOLLOW-only contract ────────────────────────────────────────────────


def test_soft_follow_contract_hard_follow_would_be_unsound():
    """The gate must consume soft FOLLOW, never hard FOLLOW: hard FOLLOW
    under-approximates (it skips followers reachable only through a nullable
    continuation), which flips a genuine island into a false SEPARABLE.

    ``b ::= 'z' | ε``; ``q ::= b 'x' | 'xq'``; ``root ::= q 'q'?`` — root's
    optional trailing 'q' makes ``q``'s soft FOLLOW ``{EOF, 'q'}`` but its
    hard FOLLOW (nullable followers skipped) only ``{EOF}``. Feeding the real
    (soft) FOLLOW correctly refuses (b's epsilon arm can produce "x"+"q",
    colliding with the "xq" arm); feeding hard FOLLOW misses that 'q' and
    falsely separates at k=2.
    """
    b = IrRule("b", IrAlternation(IrSequence(IrItem(IrLiteral("z"))), IrSequence()))
    q = IrRule(
        "q",
        IrAlternation(
            IrSequence(IrItem(IrRuleRef("b")), IrItem(IrLiteral("x"))),
            IrSequence(IrItem(IrLiteral("xq"))),
        ),
    )
    root = IrRule(
        "root",
        IrSequence(IrItem(IrRuleRef("q")), IrItem(IrLiteral("q"), IrQuantifier(0, 1))),
    )
    ast = IrAst(rules=IrSeq(root, q, b), start="root")
    analysis = GrammarAnalysis(ast)
    arms = [_rule_items(arm) for arm in analysis.rules["q"].body]

    assert analysis.follow["q"].has("q")
    assert not analysis.hard_follow["q"].has("q")
    assert arm_gate(analysis.rules, arms, analysis.follow["q"], max_k=3) is None
    unsound = arm_gate(analysis.rules, arms, analysis.hard_follow["q"], max_k=3)
    assert unsound is not None, (
        "hard FOLLOW should (wrongly) separate here — exactly why the gate "
        "must never be fed hard FOLLOW"
    )


# ── coverage-map verdict table (real grammars, flag literally False) ───────


def _self_analysis(name: str) -> GrammarAnalysis:
    """Analysis of a flavour's own lifted self-grammar."""
    return GrammarAnalysis(lift_optional_nullables(get_flavour(name).grammar))


def _arm_k(analysis: GrammarAnalysis, name: str) -> int | None:
    """``arm_gate``'s separating ``k`` for rule ``name``'s arms, or ``None``."""
    arms = [_rule_items(arm) for arm in analysis.rules[name].body]
    got = arm_gate(analysis.rules, arms, analysis.follow[name])
    return got[0] if got else None


def _loop_k(analysis: GrammarAnalysis, name: str, idx: int) -> int | None:
    """``loop_gate``'s separating ``k`` for item ``idx`` of rule ``name``'s
    (single-arm) body, or ``None``."""
    items = _rule_items(analysis.rules[name].body[0])
    got = loop_gate(analysis.rules, items, idx, analysis.follow[name])
    return got[0] if got else None


@pytest.mark.parametrize(
    "name",
    [
        "cc-esc",
        "cc-esc-hex",
        "cc-esc-short",
        "cc-pos",
        "charclass",
        "lesc-hex",
        "lesc-short",
        "lunit",
    ],
)
def test_gbnf_self_arm_gate_separates_at_k2(name):
    """The GBNF self-grammar's charclass/literal-escape family separates
    cleanly at k=2."""
    assert _arm_k(_self_analysis("gbnf"), name) == 2


def test_gbnf_self_cc_neg_arm_gate_separates_at_k3():
    """``cc-neg`` (the negated-charclass arm) needs the wider k=3 window."""
    assert _arm_k(_self_analysis("gbnf"), "cc-neg") == 3


@pytest.mark.parametrize("name", ["cc-first", "cc-item", "cc-nfirst"])
def test_gbnf_self_cc_family_stays_island(name):
    """The remaining ``cc-*`` rules are genuinely not k-window separable."""
    assert _arm_k(_self_analysis("gbnf"), name) is None


@pytest.mark.parametrize("name", ["defined", "element"])
def test_abnf_self_arm_gate_separates_at_k2(name):
    """The ABNF self-grammar's ``defined``/``element`` rules separate at k=2."""
    assert _arm_k(_self_analysis("abnf"), name) == 2


def test_chess_nonpawn_loop_separates_at_k3():
    """chess's ``nonpawn`` loop (the file-letter optional item) separates only
    at k=3, via the FOLLOW extension — not rep-depth (Finding 2's re-run)."""
    assert _loop_k(_ground_truth_analysis("chess.gbnf"), "nonpawn", 1) == 3


def test_json_value_arm_gate_stays_island():
    """json's ``value`` alternation is genuinely not k-window separable."""
    assert _arm_k(_ground_truth_analysis("json.gbnf"), "value") is None
