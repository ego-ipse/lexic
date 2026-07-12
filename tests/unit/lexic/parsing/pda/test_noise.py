"""Tests for lexic.parsing.pda.noise — semantic-FOLLOW attribution (P6).

Pins the decomposition that powers the noise-greedy licence: which chars a
rule can be followed by *as semantic content*. The tests build small
hand-authored grammars (the same idiom as ``test_analysis``) plus the real
json ground truth, whose ``ws`` is the licence's motivating case.
"""

from __future__ import annotations

from typing import NamedTuple

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
from lexic.parsing.pda.analysis import GrammarAnalysis
from lexic.parsing.pda.charsets import CharSet
from lexic.parsing.pda.noise import (
    ResidualFirst,
    _exit_is_noise,
    _probe_candidate,
    _sem_first_table,
    _sem_follow_clear,
    noise_alphabet,
    noise_roots,
    peek_arm_gate,
    peek_loop_gate,
    sem_follow_table,
)
from lexic.parsing.pda.scanner import SG_MATCH, SG_PROBE, SG_SCAN
from tests.unit.lexic.parsing.pda.test_analysis import (
    _lifted_analysis as _ground_truth_analysis,
)
from tests.unit.lexic.parsing.pda.test_analysis import (
    _self_grammar_analysis,
)

_WS = IrCharClass(IrChr(32), IrChr(9))
"""A tiny whitespace class (space + tab) for the hand grammars."""


def _item(atom, lo: int = 1, hi: "int | None" = 1) -> IrItem:
    """An item with explicit bounds (``hi=None`` → unbounded)."""
    return IrItem(atom, IrQuantifier(lo, IrNone if hi is None else hi))


def _analysis(*rules: IrRule, start: str) -> GrammarAnalysis:
    """A :class:`GrammarAnalysis` over hand-authored rules."""
    return GrammarAnalysis(IrAst(IrSeq(*rules), start))


def _noise_rule(name: str, *arms: IrSequence) -> IrRule:
    """A ``semantic=False`` rule over ``arms``."""
    return IrRule(name, IrAlternation(*arms), semantic=False)


# ── semantic-FIRST decomposition ────────────────────────────────────────────


def test_terminal_in_semantic_rule_counts_as_semantic_first():
    """A literal inside a ``semantic=True`` rule contributes its lead char."""
    root = IrRule("root", IrAlternation(IrSequence(_item(IrLiteral("ab")))))
    table = _sem_first_table(_analysis(root, start="root"))
    assert table["root"] == CharSet.from_chars("a")


def test_terminal_in_noise_rule_contributes_nothing():
    """The same literal inside a ``semantic=False`` rule is noise-attributable."""
    root = _noise_rule("root", IrSequence(_item(IrLiteral("ab"))))
    table = _sem_first_table(_analysis(root, start="root"))
    assert table["root"] == CharSet.EMPTY


def test_ref_to_noise_rule_contributes_nothing_even_from_a_semantic_rule():
    """A semantic rule's leading noise ref contributes no semantic FIRST —
    the target's whole subtree is excluded from ``semantic_dump``; the
    semantic chars come from the item after the nullable noise."""
    ws = _noise_rule("ws", IrSequence(_item(_WS, lo=0, hi=None)))
    root = IrRule(
        "root",
        IrAlternation(IrSequence(_item(IrRuleRef("ws")), _item(IrLiteral("q")))),
    )
    table = _sem_first_table(_analysis(root, ws, start="root"))
    assert table["root"] == CharSet.from_chars("q")
    assert table["ws"] == CharSet.EMPTY


def test_ref_to_semantic_rule_contributes_its_own_decomposition_not_raw_first():
    """A ref to a semantic rule whose own lead is a noise ref contributes only
    the target's *semantic* part — raw FIRST would be polluted by the noise."""
    ws = _noise_rule("ws", IrSequence(_item(_WS, lo=0, hi=None)))
    inner = IrRule(
        "inner",
        IrAlternation(IrSequence(_item(IrRuleRef("ws")), _item(IrLiteral("z")))),
    )
    root = IrRule("root", IrAlternation(IrSequence(_item(IrRuleRef("inner")))))
    table = _sem_first_table(_analysis(root, inner, ws, start="root"))
    assert table["root"] == CharSet.from_chars("z")


def test_undefined_ref_is_conservatively_any():
    """An undefined ref decomposes to ANY — unknown content denies the licence."""
    root = IrRule("root", IrAlternation(IrSequence(_item(IrRuleRef("ghost")))))
    table = _sem_first_table(_analysis(root, start="root"))
    assert table["root"] == CharSet.ANY


def test_group_terminals_count_under_the_enclosing_rule_semantics():
    """An inline group's terminals attribute to the ENCLOSING rule: semantic
    inside a semantic rule, noise inside a noise rule."""
    grp = IrAlternation(
        IrSequence(_item(IrLiteral("x"))), IrSequence(_item(IrLiteral("y")))
    )
    root = IrRule("root", IrAlternation(IrSequence(_item(grp))))
    noise = _noise_rule("noise", IrSequence(_item(grp)))
    table = _sem_first_table(_analysis(root, noise, start="root"))
    assert table["root"] == CharSet.from_chars("x", "y")
    assert table["noise"] == CharSet.EMPTY


# ── semantic FOLLOW ─────────────────────────────────────────────────────────


def test_sem_follow_sees_a_semantic_literal_past_a_nullable_noise_run():
    """``root ::= x y "q"`` with ``x``/``y`` nullable noise: ``q`` follows
    ``x`` semantically (through nullable ``y``); the whitespace that also
    follows ``x`` (from ``y``) does NOT — it is noise-attributable."""
    x = _noise_rule("x", IrSequence(_item(_WS, lo=0, hi=None)))
    y = _noise_rule("y", IrSequence(_item(_WS, lo=0, hi=None)))
    root = IrRule(
        "root",
        IrAlternation(
            IrSequence(
                _item(IrRuleRef("x")), _item(IrRuleRef("y")), _item(IrLiteral("q"))
            )
        ),
    )
    follow = sem_follow_table(_analysis(root, x, y, start="root"))
    assert follow["x"] == CharSet.from_chars("q")
    assert follow["y"] == CharSet.from_chars("q")


def test_sem_follow_sees_an_optional_semantic_follower():
    """The licence-denial shape: ``root ::= x "ab"?`` — the optional literal's
    lead ``a`` follows ``x`` as semantic content even though it is soft-only."""
    x = _noise_rule(
        "x", IrSequence(_item(IrCharClass(IrRange(IrChr(97), IrChr(99))), 0, None))
    )
    root = IrRule(
        "root",
        IrAlternation(
            IrSequence(_item(IrRuleRef("x")), _item(IrLiteral("ab"), lo=0, hi=1))
        ),
    )
    follow = sem_follow_table(_analysis(root, x, start="root"))
    assert follow["x"].has("a")


def test_sem_follow_is_seeded_empty_no_eof_sentinel():
    """End-of-input is not semantic content — the start rule's entry never
    carries the EOF sentinel the soft-FOLLOW fixpoint seeds."""
    root = IrRule("root", IrAlternation(IrSequence(_item(IrLiteral("q")))))
    follow = sem_follow_table(_analysis(root, start="root"))
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
    ws = _noise_rule("ws", IrSequence(_item(_WS, lo=0, hi=None)))
    dquote = _noise_rule("dquote", IrSequence(_item(IrLiteral('"'))))
    root = IrRule(
        "root",
        IrAlternation(
            IrSequence(
                _item(IrRuleRef("ws")),
                _item(IrRuleRef("dquote")),
                _item(IrLiteral("q")),
            )
        ),
    )
    w = noise_alphabet(_analysis(root, ws, dquote, start="root"))
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
    assert rf.seq([_item(_WS, lo=0, hi=None), _item(IrLiteral("x"))]) == (
        CharSet.from_chars("x"),
        False,
    )
    mixed = IrCharClass(IrChr(32), IrChr(120))  # {space, x} — mixes W and non-W
    assert rf.seq([_item(mixed)]) is None
    assert rf.seq([_item(IrRuleRef("ghost"))]) is None  # undefined ref poisons


def test_residual_first_open_end_flag():
    """A sequence whose every item is transparent or nullable is end-open —
    its post-noise char could come from the FOLLOW side."""
    analysis = _ground_truth_analysis("json.gbnf")
    rf = ResidualFirst(analysis, CharSet.from_chars(" ", "\t"))
    got = rf.seq([_item(_WS, lo=0, hi=None), _item(IrLiteral("x"), lo=0, hi=1)])
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


# ── structured gates (P3 structured / P5 probe, Task 6.6) ──────────────────


def test_noise_roots_on_gbnf_self_grammar():
    """GBNF's run-forming noise roots are its comment/whitespace rule ``n`` and
    the trailing-comment closure member ``tail-comment``."""
    roots = noise_roots(_self_grammar_analysis("gbnf"))
    assert {"n", "tail-comment"} <= roots


def test_noise_roots_on_abnf_self_grammar():
    """ABNF's run-forming noise roots include ``filler``/``c-wsp``/``c-nl`` —
    the LWS-folding and comment/blank-line closure members."""
    roots = noise_roots(_self_grammar_analysis("abnf"))
    assert {"filler", "c-wsp", "c-nl"} <= roots


def _struct_gate(analysis: GrammarAnalysis, rule_name: str, item_index: int):
    """The stored :class:`ScanGate` for ``rule_name``'s body-arm-0 item at
    ``item_index`` — the taxonomy's identity-keyed struct-gate channel."""
    items = [i for i in analysis.rules[rule_name].body[0] if isinstance(i, IrItem)]
    return analysis.taxonomy.struct_loop_gates[id(items[item_index])]


def test_gbnf_sequence_loop_demotes_to_sg_probe():
    """GBNF ``sequence[1]``'s exit skips ``n`` into the next rule's rulename,
    overlapping the item's own lead — the P5 probe (``rulename n* "::="``)
    breaks the tie, refuting the take reading on a matched header."""
    analysis = _self_grammar_analysis("gbnf")
    gate = _struct_gate(analysis, "sequence", 1)
    assert gate.kind == SG_PROBE
    assert gate.probe is not None
    rev = {v: k for k, v in gate.rec.index.items()}
    name_idx, _noise_idx, lit, take_on_match = gate.probe
    assert rev[name_idx] == "rulename"
    assert lit == "::="
    assert take_on_match is False


def test_gbnf_alternation_loop_demotes_to_sg_scan():
    """GBNF ``alternation[1]``'s bar-arm continuation is a plain post-noise
    take on ``|`` — no header ambiguity, so ``SG_SCAN`` suffices."""
    analysis = _self_grammar_analysis("gbnf")
    gate = _struct_gate(analysis, "alternation", 1)
    assert gate.kind == SG_SCAN
    assert gate.take is not None
    chars, negated = gate.take
    assert chars == frozenset({"|"})
    assert negated is False


def test_abnf_has_two_pure_folding_sg_match_gates():
    """ABNF's ``rulelist``/``rl-cont`` trailing ``c-wsp*`` loops are pure
    folding (noise↔noise exit) — both demote to ``SG_MATCH``."""
    analysis = _self_grammar_analysis("abnf")
    rulelist_gate = _struct_gate(analysis, "rulelist", 3)
    rl_cont_gate = _struct_gate(analysis, "rl-cont", 0)
    assert rulelist_gate.kind == SG_MATCH
    assert rl_cont_gate.kind == SG_MATCH


def test_gbnf_n_loop_demotes_to_sg_match_via_sem_follow_clear():
    """GBNF's own ``n`` rule (``nunit+``) demotes to ``SG_MATCH`` too — not via
    :func:`_exit_is_noise` (its own body has no arm-local exit to inspect),
    but via the P6 precision clause :func:`_sem_follow_clear`: the ``#``
    overlap with the trailing ``tail-comment`` resolves by exact recognition
    (an incomplete ``comment-line`` simply fails to match)."""
    analysis = _self_grammar_analysis("gbnf")
    gate = _struct_gate(analysis, "n", 0)
    assert gate.kind == SG_MATCH


# ── _sem_follow_clear (the P6 precision clause for SG_MATCH) ───────────────


class _Scope(NamedTuple):
    """A minimal duck-typed stand-in for analysis' private ``_Scope`` — only
    the ``rule``/``tail``/``body`` fields :func:`_sem_follow_clear` reads."""

    rule: str
    tail: CharSet
    body: bool = True


def test_sem_follow_clear_true_on_the_gbnf_n_shape():
    """The positive control, at the function level: ``n``'s own ``nunit+``
    loop (empty rest, no semantic follower) clears."""
    analysis = _self_grammar_analysis("gbnf")
    items = [i for i in analysis.rules["n"].body[0] if isinstance(i, IrItem)]
    scope = _Scope("n", analysis.follow["n"])
    assert _sem_follow_clear(analysis, items, 0, scope) is True


def test_sem_follow_clear_denies_on_a_semantic_follower():
    """A semantic ref after the loop denies the clause outright — the
    arm-local check alone cannot see past a real content boundary."""
    nz = _noise_rule("nz", IrSequence(_item(_WS, lo=0, hi=None)))
    z = IrRule("z", IrAlternation(IrSequence(_item(IrLiteral("z")))))
    items = [_item(IrRuleRef("nz"), lo=0, hi=None), _item(IrRuleRef("z"))]
    shaped = IrRule("shaped", IrAlternation(IrSequence(*items)))
    analysis = _analysis(shaped, nz, z, start="shaped")
    scope = _Scope("shaped", analysis.follow["shaped"])
    assert _sem_follow_clear(analysis, items, 0, scope) is False


def test_sem_follow_clear_denies_when_the_overeaten_char_is_semantic():
    """An empty rest, but the loop's own alphabet overlaps a char that CAN
    follow the rule as semantic content (``sem_follow_table``) — denied."""
    cc = IrCharClass(IrRange(IrChr(97), IrChr(99)))  # [a-c]
    nz = IrRule(
        "nz", IrAlternation(IrSequence(_item(cc, lo=0, hi=None))), semantic=False
    )
    items = [_item(IrRuleRef("nz"), lo=0, hi=None)]
    shaped = IrRule("shaped", IrAlternation(IrSequence(*items)))
    top = IrRule(
        "top",
        IrAlternation(IrSequence(_item(IrRuleRef("shaped")), _item(IrLiteral("a")))),
    )
    analysis = _analysis(top, shaped, nz, start="top")
    scope = _Scope("shaped", analysis.follow["shaped"])
    assert _sem_follow_clear(analysis, items, 0, scope) is False


# ── _exit_is_noise (the SG_MATCH licence) ───────────────────────────────────


def test_exit_is_noise_denies_on_nullable_semantic_follower():
    """A nullable but ``semantic=True`` follower after the loop denies the
    licence — the exit could steal semantic content, not just noise."""
    nz = _noise_rule("nz", IrSequence(_item(_WS, lo=0, hi=None)))
    z = IrRule(
        "z",
        IrAlternation(
            IrSequence(_item(IrLiteral(""))), IrSequence(_item(IrLiteral("z")))
        ),
    )
    loop_item = _item(IrRuleRef("nz"), lo=0, hi=None)
    items = [loop_item, _item(IrRuleRef("z"), lo=0, hi=1)]
    root = IrRule("root", IrAlternation(IrSequence(*items)))
    analysis = _analysis(root, nz, z, start="root")
    assert _exit_is_noise(analysis, items, 0) is False


def test_exit_is_noise_denies_on_empty_rest():
    """An empty rest (the loop is the arm's last item) denies the licence —
    the exit is then the rule's FOLLOW, whose noise-ness this arm-local walk
    cannot see."""
    nz = _noise_rule("nz", IrSequence(_item(_WS, lo=0, hi=None)))
    items = [_item(IrRuleRef("nz"), lo=0, hi=None)]
    root = IrRule("root", IrAlternation(IrSequence(*items)))
    analysis = _analysis(root, nz, start="root")
    assert _exit_is_noise(analysis, items, 0) is False


def test_exit_is_noise_licenses_a_required_noise_follower():
    """A required (``lo>=1``) non-semantic follower licenses the take — the
    exit boundary is itself noise."""
    nz = _noise_rule("nz", IrSequence(_item(_WS, lo=0, hi=None)))
    nz2 = _noise_rule("nz2", IrSequence(_item(IrLiteral(";"))))
    items = [_item(IrRuleRef("nz"), lo=0, hi=None), _item(IrRuleRef("nz2"), lo=1, hi=1)]
    root = IrRule("root", IrAlternation(IrSequence(*items)))
    analysis = _analysis(root, nz, nz2, start="root")
    assert _exit_is_noise(analysis, items, 0) is True


def test_exit_is_noise_licenses_an_optional_noise_only_run_to_arm_end():
    """A run of optional non-semantic refs to the arm's end (GBNF ``grammar``'s
    trailing ``n? tail-comment?`` shape) licenses the take."""
    nz = _noise_rule("nz", IrSequence(_item(_WS, lo=0, hi=None)))
    nz2 = _noise_rule("nz2", IrSequence(_item(IrLiteral(";"))))
    items = [_item(IrRuleRef("nz"), lo=0, hi=None), _item(IrRuleRef("nz2"), lo=0, hi=1)]
    root = IrRule("root", IrAlternation(IrSequence(*items)))
    analysis = _analysis(root, nz, nz2, start="root")
    assert _exit_is_noise(analysis, items, 0) is True


# ── _probe_candidate (P5 uniqueness + refutation licence) ──────────────────


def _name_ws_headers(*extra: IrRule, start: str, headers: "tuple[IrRule, ...]"):
    """A hand grammar: ``name`` ([a-z]+), a noise ``ws``, and the given header
    rules, wired to a ``start`` rule that references every header (so each is
    reachable)."""
    name = IrRule(
        "name",
        IrAlternation(IrSequence(_item(IrCharClass(IrRange(IrChr("a"), IrChr("z")))))),
    )
    ws = _noise_rule("ws", IrSequence(_item(_WS, lo=0, hi=None)))
    return _analysis(name, ws, *headers, *extra, start=start)


def test_probe_candidate_none_when_two_distinct_headers_cover_the_overlap():
    """Two distinct header-shaped rules (``name ws+ "::="`` and
    ``name ws+ "="``), both covering the overlap via the same ``R`` — the spec
    is not unique, so no probe is licensed (the decision stays an island)."""
    h1 = IrRule(
        "h1",
        IrAlternation(
            IrSequence(
                _item(IrRuleRef("name")),
                _item(IrRuleRef("ws"), lo=1, hi=None),
                _item(IrLiteral("::="), lo=1, hi=1),
            )
        ),
    )
    h2 = IrRule(
        "h2",
        IrAlternation(
            IrSequence(
                _item(IrRuleRef("name")),
                _item(IrRuleRef("ws"), lo=1, hi=None),
                _item(IrLiteral("="), lo=1, hi=1),
            )
        ),
    )
    root = IrRule(
        "root",
        IrAlternation(IrSequence(_item(IrRuleRef("h1")), _item(IrRuleRef("h2")))),
    )
    analysis = _name_ws_headers(root, start="root", headers=(h1, h2))
    overlap = CharSet.from_chars("a")
    assert _probe_candidate(analysis, frozenset({"ws"}), overlap) is None


def test_probe_candidate_none_when_lead_char_follows_r_elsewhere():
    """A single header (``name ws+ "::="``), but ``name`` is also directly
    followed by ``":"`` (``L``'s lead char) elsewhere in the grammar — the
    refutation licence fails, so no probe is licensed."""
    h1 = IrRule(
        "h1",
        IrAlternation(
            IrSequence(
                _item(IrRuleRef("name")),
                _item(IrRuleRef("ws"), lo=1, hi=None),
                _item(IrLiteral("::="), lo=1, hi=1),
            )
        ),
    )
    other = IrRule(
        "other",
        IrAlternation(
            IrSequence(_item(IrRuleRef("name")), _item(IrLiteral(":"), lo=1, hi=1))
        ),
    )
    root = IrRule(
        "root",
        IrAlternation(IrSequence(_item(IrRuleRef("h1")), _item(IrRuleRef("other")))),
    )
    analysis = _name_ws_headers(root, start="root", headers=(h1, other))
    overlap = CharSet.from_chars("a")
    assert _probe_candidate(analysis, frozenset({"ws"}), overlap) is None


def test_probe_candidate_finds_the_unique_spec_with_no_interference():
    """The positive control: one header, no competing spec, no refutation —
    ``_probe_candidate`` resolves the ``(R, noise root, L)`` triple."""
    h1 = IrRule(
        "h1",
        IrAlternation(
            IrSequence(
                _item(IrRuleRef("name")),
                _item(IrRuleRef("ws"), lo=1, hi=None),
                _item(IrLiteral("::="), lo=1, hi=1),
            )
        ),
    )
    root = IrRule("root", IrAlternation(IrSequence(_item(IrRuleRef("h1")))))
    analysis = _name_ws_headers(root, start="root", headers=(h1,))
    overlap = CharSet.from_chars("a")
    assert _probe_candidate(analysis, frozenset({"ws"}), overlap) == (
        "name",
        "ws",
        "::=",
    )


def test_peek_arm_gate_bails_on_true_post_noise_overlap():
    """Two arms sharing their post-noise lead do not separate — no gate."""
    ws = _noise_rule("ws", IrSequence(_item(_WS, lo=0, hi=None)))
    root = IrRule(
        "root",
        IrAlternation(
            IrSequence(_item(IrRuleRef("ws")), _item(IrLiteral("ab"))),
            IrSequence(_item(IrRuleRef("ws")), _item(IrLiteral("ac"))),
        ),
    )
    analysis = _analysis(root, ws, start="root")
    w = noise_alphabet(analysis)
    arms = [[i for i in arm if isinstance(i, IrItem)] for arm in root.body]
    assert peek_arm_gate(analysis, arms, w) is None
