"""Tests for lexic.parsing.pda.analysis.gates.kwindow — the FIRST_k fixpoint + gate functions.

Pins the fixed (post-Fable-review) semantics of :class:`KWindowFirst`,
:func:`arm_gate`/:func:`loop_gate`, and their small helpers. Findings 1
(``lo > window budget`` silently emptying an arm's prefix set) and 2
(``loop_gate``'s old two-rep union
under-covering 3-rep windows at k=3) are both fixed on disk; this file pins
the fixed behaviour so it cannot regress.
"""

from __future__ import annotations

import string

import pytest

from lexic.compile import compile_text
from lexic.grammars import get_flavour
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
from lexic.parsing.lift import lift_optional_nullables
from lexic.parsing.pda.analysis.analysis import GrammarAnalysis
from lexic.parsing.pda.analysis.gates.kwindow import (
    FOLLOW_LOOP_K,
    MAX_K,
    arm_gate,
    follow_arm_gate,
    follow_loop_gate,
    loop_gate,
    rule_references,
)
from lexic.parsing.pda.analysis.gates.windows import (
    END,
    MORE,
    UNK,
    FollowWindows,
    KWindowFirst,
    collide,
    extend_follow,
    separable,
    windows_of,
)
from lexic.parsing.pda.core.charsets import CharSet
from tests.gate_grammars import ARM_FINAL_LOOP
from tests.gate_grammars import NULL_ARM as NULL_ARM_GRAMMAR
from tests.unit.lexic.parsing.pda.analysis.test_analysis import arm_items as _rule_items
from tests.unit.lexic.parsing.pda.analysis.test_analysis import (
    lifted_analysis as _ground_truth_analysis,
)

EOF = CharSet.from_chars("")


def digits() -> IrCharClass:
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
    cc = digits()
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


def test_group_prefixes_memoises_a_node_reached_via_multiple_paths(
    monkeypatch: pytest.MonkeyPatch,
):
    """An inline group is a rule without a name — it earns the identical
    ``id``-keyed memo :meth:`rule_prefixes` has under a name. Reached from
    two call sites (the exact shape ``@lexical`` inlining produces when it
    splices one body into several sites), it costs one computation and both
    callers see the SAME result, equal to the unmemoised union of its arms.
    """
    inner = IrAlternation(
        IrSequence(IrItem(IrLiteral("p"))),
        IrSequence(IrItem(IrLiteral("q"))),
    )
    solver = KWindowFirst({}, 3)
    expected: set = set()
    for arm in inner:
        expected |= solver.arm_prefixes(_rule_items(arm), 3)

    calls: list[int] = []
    original = KWindowFirst.arm_prefixes

    def counting(self, items, r):
        calls.append(1)
        return original(self, items, r)

    monkeypatch.setattr(KWindowFirst, "arm_prefixes", counting)

    first_path = solver.group_prefixes(inner, 3)
    second_path = solver.group_prefixes(inner, 3)

    assert first_path == expected
    assert second_path == expected
    assert len(calls) == 2, "the second path must be a memo hit, not a recompute"
    assert (id(inner), 3) in solver.memo


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
            [IrItem(digits(), IrQuantifier(4, IrNone)), IrItem(IrLiteral("x"))],
            id="lo-gt-k-unbounded",
        ),
        pytest.param(
            [IrItem(digits(), IrQuantifier(4, 8)), IrItem(IrLiteral("x"))],
            id="lo-gt-k-bounded",
        ),
        pytest.param(
            [IrItem(digits(), IrQuantifier(9, 9)), IrItem(IrLiteral("x"))],
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
    arm1 = [IrItem(digits(), IrQuantifier(4, IrNone)), IrItem(IrLiteral("x"))]
    arm2 = [IrItem(IrLiteral("12"))]
    assert arm_gate({}, [arm1, arm2], EOF, max_k=2) is None
    got = arm_gate({}, [arm1, arm2], EOF, max_k=3)
    assert got is not None
    assert got[0] == 3


def test_finding1_lo_gt_k_bounded_twin_islands_at_k2():
    """The bounded ``{4,8}`` variant (ABNF's ``4*8DIGIT``) fails identically
    to the unbounded one."""
    arm1 = [IrItem(digits(), IrQuantifier(4, 8)), IrItem(IrLiteral("x"))]
    arm2 = [IrItem(IrLiteral("12"))]
    assert arm_gate({}, [arm1, arm2], EOF, max_k=2) is None
    got = arm_gate({}, [arm1, arm2], EOF, max_k=3)
    assert got is not None
    assert got[0] == 3


def test_finding1_k3_separation_rides_an_eof_carrying_charset():
    """The k=3 separator is EOF-exact: arm2's "12" is extended by the EOF
    sentinel at position 3, not a generic character — the shape the part-(c)
    runtime window matcher must special-case."""
    arm1 = [IrItem(digits(), IrQuantifier(4, IrNone)), IrItem(IrLiteral("x"))]
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


def self_analysis(name: str) -> GrammarAnalysis:
    """Analysis of a flavour's own lifted self-grammar."""
    return GrammarAnalysis(lift_optional_nullables(get_flavour(name).grammar))


def arm_k(analysis: GrammarAnalysis, name: str) -> int | None:
    """``arm_gate``'s separating ``k`` for rule ``name``'s arms, or ``None``."""
    arms = [_rule_items(arm) for arm in analysis.rules[name].body]
    got = arm_gate(analysis.rules, arms, analysis.follow[name])
    return got[0] if got else None


def loop_k(analysis: GrammarAnalysis, name: str, idx: int) -> int | None:
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
    assert arm_k(self_analysis("gbnf"), name) == 2


def test_gbnf_self_cc_neg_arm_gate_separates_at_k3():
    """``cc-neg`` (the negated-charclass arm) needs the wider k=3 window."""
    assert arm_k(self_analysis("gbnf"), "cc-neg") == 3


@pytest.mark.parametrize("name", ["cc-first", "cc-item", "cc-nfirst"])
def test_gbnf_self_cc_family_de_islanded(name):
    """The left-factored ``cc-*`` rules now separate cleanly at k=2 (``cc-unit``
    never leads with ``-``), so the whole class family is off the island path."""
    assert arm_k(self_analysis("gbnf"), name) == 2


def test_gbnf_self_cc_tail_needs_follow_windows():
    """``cc-tail`` (``- cc-hi | ε``) does not separate under the FIRST arm gate —
    the empty arm overlaps FOLLOW through a trailing ``-`` — so it is demoted by
    the deeper FOLLOW-window gate instead, stored under ``arm_gates``."""
    an = self_analysis("gbnf")
    assert arm_k(an, "cc-tail") is None
    assert "cc-tail" in an.taxonomy.arm_gates


def test_follow_windows_cc_tail_separates_take_from_escape():
    """The FOLLOW\\ :sub:`2` fixpoint gives ``cc-tail`` a separable arm gate: the
    ``- cc-hi`` take window (``-`` then a non-``]`` cc-hi lead) never collides
    with the escape (FOLLOW) windows, whose only ``-``-led window is ``- ]``."""
    an = self_analysis("gbnf")
    fw = FollowWindows(an.rules, an.start, 2)
    follow = fw.follow["cc-tail"]
    take = extend_follow(
        fw.solver.arm_prefixes(_rule_items(an.rules["cc-tail"].body[0]), 2), follow, 2
    )
    escape = extend_follow(fw.solver.arm_prefixes([], 2), follow, 2)
    assert separable([take, escape])
    # every take window leads with '-'; the escape's dash-led window is '- ]'.
    dash = CharSet.from_chars("-")
    close = CharSet.from_chars("]")
    take_wins = windows_of(take)
    assert take_wins and all(w[0] == dash for w in take_wins)
    esc_dash = [w for w in windows_of(escape) if w[0] == dash]
    assert esc_dash and all(len(w) >= 2 and w[1] == close for w in esc_dash)


def test_follow_arm_gate_returns_cc_tail_windows():
    """``follow_arm_gate`` returns per-arm windows for ``cc-tail`` in body-arm
    order (the ``- cc-hi`` take arm, then the ε escape arm) where the plain
    FIRST :func:`arm_gate` — with only a single FOLLOW char to reach — cannot."""
    an = self_analysis("gbnf")
    arms = [_rule_items(a) for a in an.rules["cc-tail"].body]
    assert arm_gate(an.rules, arms, an.follow["cc-tail"]) is None
    gate = follow_arm_gate(an.rules, an.start, arms, "cc-tail")
    assert gate is not None
    assert len(gate) == 2  # take arm + escape arm, body order
    dash = CharSet.from_chars("-")
    assert gate[0] and all(w[0] == dash for w in gate[0])


def test_extend_follow_single_charset_is_the_k1_special_case():
    """A single :class:`CharSet` FOLLOW arg behaves exactly as before — append
    one char set to each short END prefix, mark it UNK — i.e. the degenerate
    one-window case of the generalised window extension."""
    a = CharSet.from_chars("a")
    b = CharSet.from_chars("b")
    prefs = {((a,), END), ((a, b), END)}
    out = extend_follow(prefs, b, 2)
    assert ((a, b), UNK) in out  # the short END extended by FOLLOW 'b'
    assert ((a, b), END) in out  # the full-window END rides through unchanged
    # An empty FOLLOW CharSet contributes nothing (short END rides through).
    assert extend_follow({((a,), END)}, CharSet.EMPTY, 2) == {((a,), END)}


def test_follow_windows_pays_only_when_asked():
    """``FollowWindows`` is a standalone fixpoint the analysis builds lazily —
    seeded EOF at the start rule, empty elsewhere before the fixpoint feeds."""
    an = self_analysis("gbnf")
    fw = FollowWindows(an.rules, an.start, 2)
    assert ((), END) in fw.follow[an.start]
    # No window exceeds the window width (which itself never exceeds MAX_K).
    assert fw.k <= MAX_K
    assert all(len(w) <= fw.k for wins in fw.follow.values() for w, _ in wins)


@pytest.mark.parametrize("name", ["defined", "element"])
def test_abnf_self_arm_gate_separates_at_k2(name):
    """The ABNF self-grammar's ``defined``/``element`` rules separate at k=2."""
    assert arm_k(self_analysis("abnf"), name) == 2


def test_chess_nonpawn_loop_separates_at_k3():
    """chess's ``nonpawn`` loop (the file-letter optional item) separates only
    at k=3, via the FOLLOW extension — not rep-depth (Finding 2's re-run)."""
    assert loop_k(_ground_truth_analysis("chess.gbnf"), "nonpawn", 1) == 3


def test_json_value_arm_gate_stays_island():
    """json's ``value`` alternation is genuinely not k-window separable."""
    assert arm_k(_ground_truth_analysis("json.gbnf"), "value") is None


# ── the FOLLOW-window loop gate ────────────────────────────────────────
#
# `loop_gate` takes the enclosing rule's FOLLOW as a bare `CharSet`, which
# becomes exactly ONE length-1 window, and `collide` compares over the shorter
# prefix. So for a loop that is the arm's LAST item the skip side is one
# position wide and separation collapses to the single-character stop-set test —
# every character past the first is compared against nothing, and no `k` can
# change the verdict. `follow_loop_gate` asks the same decision with both sides
# `k` deep.
#
# Each test below takes a grammar satisfying the other preconditions and breaks
# exactly ONE, so a refusal names its reason.


CLASS = ARM_FINAL_LOOP
NULL_ARM = NULL_ARM_GRAMMAR


def _compiled_analysis(source: str, key: str) -> GrammarAnalysis:
    """One grammar's finished analysis."""
    compiled = compile_text(source, cache_key=key)
    analysis = GrammarAnalysis(compiled.codegen_grammar)
    analysis.eval(analysis, compiled.codegen_grammar, ())
    return analysis


def _gate(source: str, rule: str, key: str, idx: int = 0):
    """The windows the gate issues for ``rule``'s loop at ``idx``, or ``None``."""
    analysis = _compiled_analysis(source, key)
    items = list(analysis.rules[rule].body[0])
    return follow_loop_gate(analysis.rules, analysis.start, items, idx, rule)


# ── the licence ────────────────────────────────────────────────────────


def test_the_class_is_licensed_and_its_windows_are_two_deep() -> None:
    """The control: without it every refusal below could be for another reason.

    The gate's product is the ``taken`` window set, and it must be `k` deep —
    a one-position window is exactly the thing this gate exists to replace.
    """
    windows = _gate(CLASS, "run", "flg-class")

    assert windows is not None
    assert all(len(one) == FOLLOW_LOOP_K for one in windows)


def test_the_class_loop_is_no_longer_a_conflict() -> None:
    """End to end: the cascade reaches the gate and the island note goes away."""
    analysis = _compiled_analysis(CLASS, "flg-class")

    assert not analysis.conflicts
    assert analysis.taxonomy.loop_gates, "the gate should have filed its windows"


def test_the_licence_leaves_the_attempt_gate_unused() -> None:
    """The point of the gate is that the loop stops being decided by running it."""
    analysis = _compiled_analysis(CLASS, "flg-class")

    assert not analysis.taxonomy.attempt_loops


# ── the withholds ──────────────────────────────────────────────────────


def test_a_loop_a_stop_set_already_decides_never_reaches_the_gate() -> None:
    """`%` cannot start a word, so k = 1 settles it and no fixpoint is built.

    A gate that fired here would be taxing a decision the cheapest tier already
    makes — which is why it sits at the BOTTOM of the separability tiers.
    """
    analysis = _compiled_analysis(NULL_ARM, "flg-null")

    assert not analysis.conflicts
    assert not analysis.taxonomy.loop_gates
    assert not analysis.taxonomy.attempt_loops


def test_a_rule_referenced_twice_is_refused() -> None:
    """The fixpoint unions every call site, so a two-site rule's FOLLOW is a union.

    A window separating in the union need not separate at the site that runs, and
    the gate is stored per RULE and applied wherever that rule runs. So the
    licence is withheld rather than proved against a continuation that is not
    the one in force.
    """
    source = (
        "root ::= first second\n"
        "first ::= run sep\n"
        "second ::= run other\n"
        "run ::= word+\n"
        "word ::= [a-z]+ sp\n"
        'sep ::= "e." nl\n'
        'other ::= "e:" nl\n'
        'sp ::= " "\n'
        'nl ::= "\\n"\n'
    )
    analysis = _compiled_analysis(source, "flg-two-refs")

    assert rule_references(analysis.rules, "run") == 2
    items = list(analysis.rules["run"].body[0])
    assert follow_loop_gate(analysis.rules, analysis.start, items, 0, "run") is None


def test_a_loop_that_is_not_arm_final_is_refused() -> None:
    """With items after the loop, `loop_gate`'s skip side is ALREADY k deep.

    This gate exists for the one-position skip side; where the arm supplies a
    real continuation there is nothing for it to add, and firing would duplicate
    a cheaper tier's question.
    """
    source = (
        "root ::= run sep\n"
        "run ::= word+ marker\n"
        "word ::= [a-z]+ sp\n"
        'marker ::= "!"\n'
        'sep ::= "e." nl\n'
        'sp ::= " "\n'
        'nl ::= "\\n"\n'
    )
    analysis = _compiled_analysis(source, "flg-not-final")
    items = list(analysis.rules["run"].body[0])

    assert len(items) == 2, "the loop must have a real continuation after it"
    assert items[0].quantifier.hi is IrNone, "item 0 must be the unbounded loop"
    assert follow_loop_gate(analysis.rules, analysis.start, items, 0, "run") is None


def test_a_decision_needing_three_characters_is_refused() -> None:
    """The width is `FOLLOW_LOOP_K`, and it is a cap rather than a budget.

    `sep ::= "ee."` agrees with a word for TWO characters and diverges on the
    third, so a 2-deep window cannot separate it. Measured across the roster,
    nothing is settled by a wider window that a 2-deep one misses, while the
    fixpoint's cost climbs into seconds — so the gate declines instead of
    widening, and this pins that it does.
    """
    source = (
        "root ::= run sep\n"
        "run ::= word+\n"
        "word ::= [a-z]+ sp\n"
        'sep ::= "ee." nl\n'
        'sp ::= " "\n'
        'nl ::= "\\n"\n'
    )

    assert _gate(source, "run", "flg-three") is None


def test_the_width_is_two() -> None:
    """Stated as a constant so a future widening is a deliberate edit, not a drift."""
    assert FOLLOW_LOOP_K == 2


# ── the reference counter ──────────────────────────────────────────────


@pytest.mark.parametrize(
    ("name", "count"),
    [("run", 1), ("word", 1), ("sp", 1), ("nowhere", 0)],
)
def test_the_reference_counter_counts_reference_nodes(name: str, count: int) -> None:
    """It walks each body's own tree and never through a reference, so a
    recursive grammar terminates without a visited set."""
    analysis = _compiled_analysis(CLASS, "flg-class")

    assert rule_references(analysis.rules, name) == count


def test_the_reference_counter_terminates_on_a_recursive_grammar() -> None:
    """A rule referring to itself is counted, not followed."""
    source = 'root ::= list\nlist ::= "(" list ")" | "x"\n'
    analysis = _compiled_analysis(source, "flg-recursive")

    assert rule_references(analysis.rules, "list") >= 1


# ── the shapes the retired 2-char prefix gate used to answer ───────────
#
# A dedicated LL(2) gate compared concrete 2-character prefix STRINGS, and the
# concern when it was removed was that a set of positionwise CharSets is
# coarser — that `{"ab","cd"}` against `{"ad"}` would separate as strings and
# collide as a merged `({a,c},{b,d})` box.
#
# It does not, because `arm_prefixes` keeps one window PER DERIVATION and
# `collide` runs per window pair: the take side is `('a','b')` and `('c','d')`,
# never `({a,c},{b,d})`. These pin that, since the grammars below are exactly
# the ones the retired gate used to claim and nothing else would notice if the
# window quietly started merging them.


@pytest.mark.parametrize(
    "source",
    [
        'root ::= ("ab" | "cd")? "ad"',
        'root ::= ("ab" | "cd")? "cb"',
        'root ::= ("ax" | "by")? "ay"',
        'root ::= ([a-h] "x")? [a-h] [1-8]',  # chess `pawn`
    ],
)
def test_a_two_char_prefix_decision_separates_at_k2(source: str) -> None:
    """Prefix sets disjoint, windows per-derivation — the k-window settles it."""
    analysis = _compiled_analysis(source + "\n", f"kw-pair-{hash(source)}")
    items = list(analysis.rules["root"].body[0])
    gate = loop_gate(analysis.rules, items, 0, analysis.follow["root"])

    assert gate is not None, "the window must settle what the pair gate used to"
    assert gate[0] == 2


@pytest.mark.parametrize(
    "source",
    [
        'root ::= ("ab" | "cd")? "ad"',
        'root ::= ("ax" | "by")? "ay"',
        'root ::= ([a-h] "x")? [a-h] [1-8]',
    ],
)
def test_such_a_grammar_carries_no_island(source: str) -> None:
    """The decision is MADE, not deferred — no island, no attempt."""
    analysis = _compiled_analysis(source + "\n", f"kw-pair-{hash(source)}")

    assert not analysis.islands
    assert not analysis.taxonomy.attempt_loops
