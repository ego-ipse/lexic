"""Tests for lexic.parsing.pda.analysis.noise — semantic-FOLLOW attribution (P6).

Pins the decomposition that powers the noise-greedy licence: which chars a
rule can be followed by *as semantic content*. The tests build small
hand-authored grammars (the same idiom as ``test_analysis``) plus the real
json ground truth, whose ``ws`` is the licence's motivating case.
"""

from __future__ import annotations

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
from lexic.parsing.pda.analysis.analysis import GrammarAnalysis
from lexic.parsing.pda.analysis.noise import (
    ResidualFirst,
    _sem_first_table,
    noise_alphabet,
    peek_arm_gate,
    peek_loop_gate,
    sem_follow_table,
)
from lexic.parsing.pda.core.charsets import CharSet
from tests.unit.lexic.parsing.pda.analysis.test_analysis import (
    lifted_analysis as _ground_truth_analysis,
)

WS = IrCharClass(IrChr(32), IrChr(9))
"""A tiny whitespace class (space + tab) for the hand grammars."""


def item(atom, lo: int = 1, hi: int | None = 1) -> IrItem:
    """An item with explicit bounds (``hi=None`` → unbounded)."""
    return IrItem(atom, IrQuantifier(lo, IrNone if hi is None else hi))


def make_analysis(*rules: IrRule, start: str) -> GrammarAnalysis:
    """A :class:`GrammarAnalysis` over hand-authored rules."""
    return GrammarAnalysis(IrAst(IrSeq(*rules), start))


def noise_rule(name: str, *arms: IrSequence) -> IrRule:
    """A ``semantic=False`` rule over ``arms``."""
    return IrRule(name, IrAlternation(*arms), semantic=False)


# ── semantic-FIRST decomposition ────────────────────────────────────────────


def test_terminal_in_semantic_rule_counts_as_semantic_first():
    """A literal inside a ``semantic=True`` rule contributes its lead char."""
    root = IrRule("root", IrAlternation(IrSequence(item(IrLiteral("ab")))))
    table = _sem_first_table(make_analysis(root, start="root"))
    assert table["root"] == CharSet.from_chars("a")


def test_terminal_in_noise_rule_contributes_nothing():
    """The same literal inside a ``semantic=False`` rule is noise-attributable."""
    root = noise_rule("root", IrSequence(item(IrLiteral("ab"))))
    table = _sem_first_table(make_analysis(root, start="root"))
    assert table["root"] == CharSet.EMPTY


def test_ref_to_noise_rule_contributes_nothing_even_from_a_semantic_rule():
    """A semantic rule's leading noise ref contributes no semantic FIRST —
    the target's whole subtree is excluded from ``semantic_dump``; the
    semantic chars come from the item after the nullable noise."""
    ws = noise_rule("ws", IrSequence(item(WS, lo=0, hi=None)))
    root = IrRule(
        "root",
        IrAlternation(IrSequence(item(IrRuleRef("ws")), item(IrLiteral("q")))),
    )
    table = _sem_first_table(make_analysis(root, ws, start="root"))
    assert table["root"] == CharSet.from_chars("q")
    assert table["ws"] == CharSet.EMPTY


def test_ref_to_semantic_rule_contributes_its_own_decomposition_not_raw_first():
    """A ref to a semantic rule whose own lead is a noise ref contributes only
    the target's *semantic* part — raw FIRST would be polluted by the noise."""
    ws = noise_rule("ws", IrSequence(item(WS, lo=0, hi=None)))
    inner = IrRule(
        "inner",
        IrAlternation(IrSequence(item(IrRuleRef("ws")), item(IrLiteral("z")))),
    )
    root = IrRule("root", IrAlternation(IrSequence(item(IrRuleRef("inner")))))
    table = _sem_first_table(make_analysis(root, inner, ws, start="root"))
    assert table["root"] == CharSet.from_chars("z")


def test_undefined_ref_is_conservatively_any():
    """An undefined ref decomposes to ANY — unknown content denies the licence."""
    root = IrRule("root", IrAlternation(IrSequence(item(IrRuleRef("ghost")))))
    table = _sem_first_table(make_analysis(root, start="root"))
    assert table["root"] == CharSet.ANY


def test_group_terminals_count_under_the_enclosing_rule_semantics():
    """An inline group's terminals attribute to the ENCLOSING rule: semantic
    inside a semantic rule, noise inside a noise rule."""
    grp = IrAlternation(
        IrSequence(item(IrLiteral("x"))), IrSequence(item(IrLiteral("y")))
    )
    root = IrRule("root", IrAlternation(IrSequence(item(grp))))
    noise = noise_rule("noise", IrSequence(item(grp)))
    table = _sem_first_table(make_analysis(root, noise, start="root"))
    assert table["root"] == CharSet.from_chars("x", "y")
    assert table["noise"] == CharSet.EMPTY


# ── semantic FOLLOW ─────────────────────────────────────────────────────────


def test_sem_follow_sees_a_semantic_literal_past_a_nullable_noise_run():
    """``root ::= x y "q"`` with ``x``/``y`` nullable noise: ``q`` follows
    ``x`` semantically (through nullable ``y``); the whitespace that also
    follows ``x`` (from ``y``) does NOT — it is noise-attributable."""
    x = noise_rule("x", IrSequence(item(WS, lo=0, hi=None)))
    y = noise_rule("y", IrSequence(item(WS, lo=0, hi=None)))
    root = IrRule(
        "root",
        IrAlternation(
            IrSequence(item(IrRuleRef("x")), item(IrRuleRef("y")), item(IrLiteral("q")))
        ),
    )
    follow = sem_follow_table(make_analysis(root, x, y, start="root"))
    assert follow["x"] == CharSet.from_chars("q")
    assert follow["y"] == CharSet.from_chars("q")


def test_sem_follow_sees_an_optional_semantic_follower():
    """The licence-denial shape: ``root ::= x "ab"?`` — the optional literal's
    lead ``a`` follows ``x`` as semantic content even though it is soft-only."""
    x = noise_rule(
        "x", IrSequence(item(IrCharClass(IrRange(IrChr(97), IrChr(99))), 0, None))
    )
    root = IrRule(
        "root",
        IrAlternation(
            IrSequence(item(IrRuleRef("x")), item(IrLiteral("ab"), lo=0, hi=1))
        ),
    )
    follow = sem_follow_table(make_analysis(root, x, start="root"))
    assert follow["x"].has("a")


def test_sem_follow_is_seeded_empty_no_eof_sentinel():
    """End-of-input is not semantic content — the start rule's entry never
    carries the EOF sentinel the soft-FOLLOW fixpoint seeds."""
    root = IrRule("root", IrAlternation(IrSequence(item(IrLiteral("q")))))
    follow = sem_follow_table(make_analysis(root, start="root"))
    assert not follow["root"].has("")


def test_json_ws_sem_follow_has_no_whitespace():
    """The motivating case: nothing can follow json's ``ws`` as semantic
    content that is itself whitespace — every whitespace follower comes from
    an adjacent ``ws`` (the sole whitespace-leading rule, ``semantic=False``),
    which is exactly what licenses the greedy stop-set."""
    analysis = _ground_truth_analysis("json.gbnf")
    follow = sem_follow_table(analysis)
    for ch in " \t\n\r":
        assert not follow["ws"].has(ch)
    assert follow["ws"].has(",")  # semantic followers are all still there
    assert follow["ws"].has("}")


# ── P3: noise_alphabet / ResidualFirst / peek gates ─────────────────────────


def test_noise_alphabet_is_the_nullable_noise_first_union():
    """``W`` unions FIRST over nullable non-semantic rules only — a required
    (non-nullable) noise token marker contributes nothing."""
    ws = noise_rule("ws", IrSequence(item(WS, lo=0, hi=None)))
    dquote = noise_rule("dquote", IrSequence(item(IrLiteral('"'))))
    root = IrRule(
        "root",
        IrAlternation(
            IrSequence(
                item(IrRuleRef("ws")),
                item(IrRuleRef("dquote")),
                item(IrLiteral("q")),
            )
        ),
    )
    w = noise_alphabet(make_analysis(root, ws, dquote, start="root"))
    assert w == CharSet.from_chars(" ", "\t")


def test_json_noise_alphabet_is_whitespace():
    """json derives exactly its ``ws`` alphabet — nothing hardcoded."""
    analysis = _ground_truth_analysis("json.gbnf")
    assert noise_alphabet(analysis) == CharSet.from_chars(" ", "\t", "\n", "\r")


def test_residual_first_transparent_opaque_and_poison():
    """Pure-``W`` atoms are transparent, ``W``-free atoms opaque, and a
    terminal mixing both poisons the branch."""
    analysis = _ground_truth_analysis("json.gbnf")
    w = CharSet.from_chars(" ", "\t")
    rf = ResidualFirst(analysis, w)
    assert rf.seq([item(WS, lo=0, hi=None), item(IrLiteral("x"))]) == (
        CharSet.from_chars("x"),
        False,
    )
    mixed = IrCharClass(IrChr(32), IrChr(120))  # {space, x} — mixes W and non-W
    assert rf.seq([item(mixed)]) is None
    assert rf.seq([item(IrRuleRef("ghost"))]) is None  # undefined ref poisons


def test_residual_first_open_end_flag():
    """A sequence whose every item is transparent or nullable is end-open —
    its post-noise char could come from the FOLLOW side."""
    analysis = _ground_truth_analysis("json.gbnf")
    rf = ResidualFirst(analysis, CharSet.from_chars(" ", "\t"))
    got = rf.seq([item(WS, lo=0, hi=None), item(IrLiteral("x"), lo=0, hi=1)])
    assert got is not None
    assert got == (CharSet.from_chars("x"), True)


def test_json_value_peek_arm_gate_separates_post_noise():
    """json ``value``'s seven arms all separate on their first post-noise char
    — the P3 demotion the single-char FIRST (whitespace-polluted) could not
    make."""
    analysis = _ground_truth_analysis("json.gbnf")
    w = noise_alphabet(analysis)
    arms = [
        [i for i in arm if isinstance(i, IrItem)]
        for arm in analysis.rules["value"].body
    ]
    sets = peek_arm_gate(analysis, arms, w)
    assert sets is not None
    assert len(sets) == len(arms)
    lead = {"{": False, "[": False, '"': False}
    for chars in sets:
        for ch in list(lead):
            if chars.has(ch):
                lead[ch] = True
    assert all(lead.values())


def test_json_array_item_peek_loop_gate_takes_on_comma():
    """json ``array-item2``'s item loop takes exactly on a post-noise comma —
    the exit side (``]``) is disjoint."""
    analysis = _ground_truth_analysis("json.gbnf")
    w = noise_alphabet(analysis)
    items = [i for i in analysis.rules["array-item2"].body[0] if isinstance(i, IrItem)]
    take = peek_loop_gate(analysis, items, 1, analysis.follow["array-item2"], w)
    assert take == CharSet.from_chars(",")


def test_peek_arm_gate_bails_on_true_post_noise_overlap():
    """Two arms sharing their post-noise lead do not separate — no gate."""
    ws = noise_rule("ws", IrSequence(item(WS, lo=0, hi=None)))
    root = IrRule(
        "root",
        IrAlternation(
            IrSequence(item(IrRuleRef("ws")), item(IrLiteral("ab"))),
            IrSequence(item(IrRuleRef("ws")), item(IrLiteral("ac"))),
        ),
    )
    analysis = make_analysis(root, ws, start="root")
    w = noise_alphabet(analysis)
    arms = [[i for i in arm if isinstance(i, IrItem)] for arm in root.body]
    assert peek_arm_gate(analysis, arms, w) is None
