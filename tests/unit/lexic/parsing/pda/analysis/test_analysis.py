"""Tests for lexic.parsing.pda.analysis.analysis — FIRST/hard-FIRST/FOLLOW + taxonomy.

The headline gate pins, per ground-truth grammar, the exact island rule-name
set (and demotion set) :class:`GrammarAnalysis` must produce — asserted equal to
the hybrid-parsing PoC's own milestone-1 output over the same lifted codegen
grammar. The remaining sections exercise the fixpoints and the loop-policy
taxonomy on small hand-authored grammars, and prove an unknown atom type raises
rather than being silently classified.
"""

from __future__ import annotations

import pytest

from lexic.compile import canonical_grammar
from lexic.compile.passes import build_codegen_grammar
from lexic.exceptions import UnsupportedConstructError
from lexic.grammars import flavour_for_extension, get_flavour
from lexic.ir.base import IrAtom
from lexic.ir.nodes import (
    IrAlternation,
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
from lexic.parsing.fold import lift_optional_nullables
from lexic.parsing.pda.analysis.analysis import GrammarAnalysis, kwindow, nullable_names
from lexic.parsing.pda.core.charsets import CharSet
from lexic.parsing.pda.core.scanner import SG_PROBE, SG_SCAN
from tests._ir_fixtures import analysis_of as _analysis
from tests._ir_fixtures import item_of as _item
from tests._ir_fixtures import rule_of as _rule
from tests.paths import GROUND_TRUTH

# ── helpers ───────────────────────────────────────────────────────────────


def _lifted_analysis(stem: str) -> GrammarAnalysis:
    """Analyse the lifted codegen grammar of a ground-truth grammar file."""
    path = GROUND_TRUTH / stem
    flavour = flavour_for_extension(path)
    canonical = canonical_grammar(path.read_text(encoding="utf-8"), flavour)
    lifted = lift_optional_nullables(build_codegen_grammar(canonical))
    return GrammarAnalysis(lifted)


def _items(arm: IrSequence) -> list[IrItem]:
    """The :class:`IrItem` members of one sequence arm, in order."""
    return [i for i in arm if isinstance(i, IrItem)]


# ── the island / demotion parity gate (pinned to the PoC's M1 output) ──────
#
# Deviation from the PoC: json ``ws`` is islanded, not stop-set-demoted. The
# PoC soft-demoted it, but a top-of-rule ``[ \t\r\n]*`` loop whose soft FOLLOW
# reaches an *optional* whitespace follower (json's ``value ws`` abutting
# ``value-separator ::= ws "," ws``) is not call-site invariant — the per-clone
# hard stop-set greedily over-eats, the same silent-wrong-model latent as the
# ``root ::= x "ab"?`` / ``x ::= [a-c]*`` regression below. arithmetic ``ws``
# stays demoted: its only FIRST∩FOLLOW overlap is ``\n``, a *hard* follower
# (``ws "\n"``), so its stop-set is call-site invariant and sound.
#
# P1 (exact co-finite ``from_charclass``/``from_not``, ``charsets.py``):
# json's ``char``/``string`` islands are gone — their ``[^"\\]`` exclusion no
# longer widens to ANY, so the escape-vs-literal-char split resolves exactly
# (json/json_arr/json_ws/json.abnf all lose their ``string`` entry; json/
# json.abnf also lose ``char``). ``c.gbnf``'s ``singlelinecomment`` and
# ``list.gbnf``'s ``item`` drop out of the demoted set entirely (not just
# un-islanded) — their own ``[^\n]*``-shaped loops now resolve with no
# FIRST∩FOLLOW overlap at all, so no stop-gate is needed.
_PINNED_ISLANDS: dict[str, list[str]] = {
    "arithmetic.gbnf": [],
    "c.gbnf": [
        "factor",
        "forinit",
        "relationoperator",
        "statement",
        "statement-arm7",
    ],
    "chess.gbnf": [],
    "japanese.gbnf": [],
    "json.gbnf": [],
    "json_arr.gbnf": ["number"],
    "json_ws.gbnf": ["number"],
    "list.gbnf": [],
    "arithmetic.abnf": [],
    "json.abnf": [],
}

# Task 6.6 (soft-gap classification): json ``array`` joins the demoted set —
# its item loop's FIRST overlaps only *soft* followers, a class the old
# hard-continuation guard never classified (it silently baked a greedy
# stop-set); the P3 noise-skip gate now carries it.
_PINNED_DEMOTED: dict[str, list[str]] = {
    "arithmetic.gbnf": ["ws"],
    "c.gbnf": ["multilinecomment"],
    "chess.gbnf": ["nonpawn", "pawn"],
    "japanese.gbnf": [],
    "json.gbnf": ["array", "array-item2", "object-item2", "value", "ws"],
    "json_arr.gbnf": [],
    "json_ws.gbnf": [],
    "list.gbnf": [],
    "arithmetic.abnf": [],
    "json.abnf": ["array", "array-item2", "object-item2", "value", "ws"],
}


@pytest.mark.parametrize("stem", sorted(_PINNED_ISLANDS))
def test_island_set_matches_poc(stem: str):
    """The island rule set equals the PoC's milestone-1 output exactly."""
    analysis = _lifted_analysis(stem)
    assert sorted(analysis.islands) == _PINNED_ISLANDS[stem]


@pytest.mark.parametrize("stem", sorted(_PINNED_DEMOTED))
def test_demotion_set_matches_poc(stem: str):
    """The stop-set / LL(2) demotion set equals the PoC's output exactly."""
    analysis = _lifted_analysis(stem)
    assert sorted(analysis.demoted) == _PINNED_DEMOTED[stem]


def test_islands_are_the_conflict_keys():
    """``islands`` is exactly the set of rules carrying an island conflict."""
    analysis = _lifted_analysis("json.gbnf")
    assert analysis.islands == frozenset(analysis.conflicts)


# ── P2 k-window demotion (flag OFF baseline / flag ON gated behavior) ──────


def _self_grammar_analysis(name: str) -> GrammarAnalysis:
    """Analysis of a flavour's own lifted self-grammar (gbnf/abnf)."""
    return GrammarAnalysis(lift_optional_nullables(get_flavour(name).grammar))


@pytest.mark.parametrize(
    ("factory", "expected_count"),
    [
        (lambda: _self_grammar_analysis("gbnf"), 3),
        (lambda: _self_grammar_analysis("abnf"), 0),
        (lambda: _lifted_analysis("json.gbnf"), 0),
        (lambda: _lifted_analysis("chess.gbnf"), 0),
    ],
    ids=["gbnf-self", "abnf-self", "json.gbnf", "chess.gbnf"],
)
def test_island_counts_match_the_coverage_map(factory, expected_count):
    """The island counts after the Task-6.6 P3 *structured* noise-skip and the
    P5 rulename probe land (the folding-aware scanner —
    :mod:`lexic.parsing.pda.core.scanner`).

    GBNF-self 7→**3**: the structured skip demotes ``alternation`` (bar-arm ``n``
    run) and ``quant-opt`` (ws-quant ``n`` run), the P5 probe demotes
    ``sequence`` (its exit skips the inter-rule ``n`` to the next rule's
    rulename, which overlaps the item lead — the ``rulename n* "::="`` header
    probe breaks the tie), and ``n`` itself demotes via the exact-match gate's
    P6 precision clause (:func:`~lexic.parsing.pda.analysis.noise._sem_follow_clear` —
    ``nunit+``'s ``#``-overlap with the trailing ``tail-comment`` is resolved
    by exact recognition, not greed: an incomplete ``comment-line`` simply
    fails to match); ``cc-first``/``cc-item``/``cc-nfirst`` remain islands.
    ABNF-self 4→**0**: the ``rule``/``rulelist`` trailing ``c-wsp*``
    loops demote via the pure-folding match gate, ``alternation``/
    ``concatenation`` via the structured skip, and the ``rulelist``
    boundary-shift left-factor (``filler* rule rl-cont* c-wsp* c-nl?``) turns
    the old unbounded last-rule-vs-more-rules decision into a post-noise
    alpha-vs-EOF scan gate — the ABNF self-grammar PDA exists at all only
    because of it. chess/json stay 0 (their noise is char-set ``ws``, already
    demoted at 6.4)."""
    assert len(factory().islands) == expected_count


def test_demotes_chess_nonpawn_loop():
    """Chess's ``nonpawn`` loop (an island pre-P2) demotes to a k-window gate,
    and the taxonomy STORES the gate spec (the option-(a) channel the clone
    compiler reads back)."""
    analysis = _lifted_analysis("chess.gbnf")
    assert "nonpawn" not in analysis.islands
    assert analysis.demoted["nonpawn"] == ["nonpawn[1]: loop k-window (demoted)"]

    items = _items(analysis.rules["nonpawn"].body[0])
    assert id(items[1]) in analysis.taxonomy.loop_gates
    gate = kwindow.loop_gate(analysis.rules, items, 1, analysis.follow["nonpawn"])
    assert gate is not None
    assert analysis.taxonomy.loop_gates[id(items[1])] == kwindow.windows_of(gate[1])


def test_demotes_gbnf_self_cc_esc_arm():
    """The GBNF self-grammar's ``cc-esc`` arm-selection (an island pre-P2)
    demotes, and the taxonomy STORES the per-arm windows aligned to the rule
    body's arms."""
    analysis = _self_grammar_analysis("gbnf")
    assert "cc-esc" not in analysis.islands
    assert analysis.demoted["cc-esc"] == ["cc-esc: arms k-window separable (demoted)"]

    arms = [_items(arm) for arm in analysis.rules["cc-esc"].body]
    stored = analysis.taxonomy.arm_gates["cc-esc"]
    assert len(stored) == len(arms)
    gate = kwindow.arm_gate(analysis.rules, arms, analysis.follow["cc-esc"])
    assert gate is not None
    assert stored == tuple(kwindow.windows_of(s) for s in gate[1])


@pytest.mark.parametrize("stem", ["json.gbnf", "json.abnf"])
def test_json_p3_demotions_store_their_peek_specs(stem: str):
    """json's remaining ws-led decisions demote via P3 and STORE their specs
    in the taxonomy channels: ``value`` an arm gate (7 post-noise selectors),
    ``array-item2``/``object-item2`` loop gates taking on the separator."""
    analysis = _lifted_analysis(stem)
    assert analysis.demoted["value"] == ["value: arms noise-skip separable (demoted)"]
    w, sets = analysis.taxonomy.pn_arm_gates["value"]
    assert w == CharSet.from_chars(" ", "\t", "\n", "\r")
    assert len(sets) == len(analysis.rules["value"].body)
    for name in ("array-item2", "object-item2"):
        assert analysis.demoted[name] == [f"{name}[1]: loop noise-skip (demoted)"]
        items = _items(analysis.rules[name].body[0])
        stored = analysis.taxonomy.pn_loop_gates[id(items[1])]
        assert stored == (w, CharSet.from_chars(","))


def test_group_arm_overlap_stays_an_island():
    """An inline group's arm overlap never demotes (no rule-name store key) —
    the enclosing rule islands, so the clone compiler never meets an
    overlapping group without a spec."""
    grp = IrAlternation(
        IrSequence(_item(IrLiteral("ab"))), IrSequence(_item(IrLiteral("ac")))
    )
    root = _rule("root", IrSequence(_item(grp)))
    analysis = _analysis(root, start="root")
    assert "root" in analysis.islands
    assert "root" not in analysis.taxonomy.arm_gates


def test_noise_greedy_licence_denied_for_semantic_soft_follower():
    """P6 precision (the plan's risk clause): a NON-semantic rule whose
    over-eatable gap char is reachable via a *semantic* soft-follower keeps
    the island — over-eating would change ``semantic_dump``, not just the
    split between noise fields."""
    x = IrRule(
        "x",
        IrAlternation(
            IrSequence(_item(IrCharClass(IrRange(IrChr(97), IrChr(99))), lo=0, hi=None))
        ),
        semantic=False,
    )
    root = _rule(
        "root", IrSequence(_item(IrRuleRef("x")), _item(IrLiteral("ab"), lo=0, hi=1))
    )
    analysis = _analysis(root, x, start="root")
    assert "x" in analysis.islands
    assert analysis.fail_islands == frozenset()  # non-semantic: island, never fail


def test_noise_greedy_licence_granted_for_noise_only_soft_follower():
    """The json-``ws`` shape in miniature: two adjacent non-semantic noise
    runs share an alphabet, so the escaping stop-set is licensed greedy —
    demoted, not islanded (the split between the two noise fields is the only
    thing that moves)."""
    ws_cc = IrCharClass(IrChr(32), IrChr(9))
    x = IrRule(
        "x",
        IrAlternation(IrSequence(_item(ws_cc, lo=0, hi=None))),
        semantic=False,
    )
    y = IrRule(
        "y",
        IrAlternation(IrSequence(_item(ws_cc, lo=0, hi=None))),
        semantic=False,
    )
    root = _rule(
        "root",
        IrSequence(_item(IrRuleRef("x")), _item(IrRuleRef("y")), _item(IrLiteral("q"))),
    )
    analysis = _analysis(root, x, y, start="root")
    assert "x" not in analysis.islands
    assert analysis.demoted["x"] == ["x[0]: loop stop-set applied (noise-greedy)"]


def test_loop_over_soft_only_follower_islands():
    """A trailing loop whose FOLLOW reaches an *optional* overlapping follower
    islands — the ``x ::= [a-c]*`` / ``root ::= x "ab"?`` F1 shape.

    ``x``'s ``[a-c]*`` loop runs up to ``x``'s FOLLOW; at ``root`` that FOLLOW
    carries the optional ``"ab"?``'s ``'a'`` — a soft-only follower (in FOLLOW,
    absent from the ``{""}`` hard FOLLOW). A non-greedy stop-set would greedily
    eat that ``'a'``, so the stop-set is not call-site invariant and ``x`` must
    island rather than soft-demote.
    """
    x = _rule(
        "x",
        IrSequence(_item(IrCharClass(IrRange(IrChr(97), IrChr(99))), lo=0, hi=None)),
    )
    root = _rule(
        "root", IrSequence(_item(IrRuleRef("x")), _item(IrLiteral("ab"), lo=0, hi=1))
    )
    analysis = _analysis(root, x, start="root")
    assert "x" in analysis.islands
    assert "x" not in analysis.demoted
    assert analysis.follow["x"].has("a")
    assert not analysis.hard_follow["x"].has("a")


def test_loop_over_hard_follower_stays_demoted():
    """A trailing loop whose only FOLLOW overlap is a *hard* follower stays a
    sound stop-set demote — the arithmetic ``ws "\\n"`` shape.

    ``ws``'s FIRST overlaps FOLLOW only on ``'a'``, but ``'a'`` is the mandatory
    literal after ``ws`` — a hard follower present in the hard FOLLOW, so every
    clone's stop-set excludes it and the demote is call-site invariant.
    """
    ws = _rule(
        "ws", IrSequence(_item(IrCharClass(IrChr(10), IrChr(97)), lo=0, hi=None))
    )
    root = _rule("root", IrSequence(_item(IrRuleRef("ws")), _item(IrLiteral("a"))))
    analysis = _analysis(root, ws, start="root")
    assert "ws" not in analysis.islands
    assert "ws" in analysis.demoted
    assert analysis.hard_follow["ws"].has("a")


# ── soft-gap classification (Task 6.6): the un-gatable hard note vs the
# P6-licensed noise-greedy twin ─────────────────────────────────────────────


def _soft_gap_shape(*, noise: bool) -> GrammarAnalysis:
    """The ``root ::= a w* t?`` soft-gap shape: ``w*``'s FIRST overlaps only
    the soft ``t?`` follower (no hard overlap — the rest is nullable, so the
    top-level ``hard_cont_at`` check falls through to EOF and misses this
    class entirely). Both ``w`` and ``t`` share one alphabet (``[a-c]``), so
    no k-window prefix can separate them either — genuinely not gatable.

    :param noise: When ``True``, the shaped rule is wrapped ``semantic=False``
        and referenced from a semantic start rule (the P6 licence applies);
        when ``False`` it IS the (semantic) start rule (the licence is denied).
    """
    cc = IrCharClass(IrRange(IrChr("a"), IrChr("c")))
    shaped = _rule(
        "shaped",
        IrSequence(
            _item(IrLiteral("X")),
            _item(cc, lo=0, hi=None),
            _item(cc, lo=0, hi=1),
        ),
    )
    if not noise:
        return _analysis(shaped, start="shaped")
    shaped = IrRule(shaped.name, shaped.body, semantic=False)
    top = _rule("top", IrSequence(_item(IrRuleRef("shaped"))))
    return _analysis(top, shaped, start="top")


def test_soft_gap_loop_islands_as_not_gatable():
    """The soft-gap shape, un-licensed (the rule itself is semantic and IS the
    start rule): no gate separates ``w*`` from ``t?``, so it islands with the
    exact hard note the soft-gap classification adds."""
    analysis = _soft_gap_shape(noise=False)
    assert analysis.islands == frozenset({"shaped"})
    assert analysis.conflicts["shaped"] == [
        "shaped[1]: loop over-eats soft FOLLOW, not gatable"
    ]
    assert "shaped" not in analysis.demoted


def test_soft_gap_loop_licensed_noise_greedy_when_noise_to_noise():
    """The same shape, wrapped ``semantic=False`` under a semantic start rule:
    the P6 licence grants it (noise↔noise re-split) — demoted, not islanded."""
    analysis = _soft_gap_shape(noise=True)
    assert "shaped" not in analysis.islands
    assert analysis.demoted["shaped"] == [
        "shaped[1]: loop stop-set applied (noise-greedy)"
    ]


# ── structured-noise gate coverage (Task 6.6): GBNF/ABNF self-grammars ─────


@pytest.mark.parametrize(
    ("name", "root_rule", "expected_kinds"),
    [("gbnf", "grammar", [0, 0, 1, 1, 1, 2]), ("abnf", "rulelist", [0, 0, 1, 1, 1])],
)
def test_self_grammar_struct_gate_kinds(name: str, root_rule: str, expected_kinds):
    """The flavour's start rule carries no conflicts (its noise-skip decisions
    all demote via a structured gate — SG_SCAN/SG_MATCH/SG_PROBE), and the
    self-grammar's full struct-gate kind multiset matches exactly. GBNF carries
    a second ``SG_MATCH`` (six gates total) since ``n``'s own ``nunit+`` loop
    now demotes via the exact-match gate's P6 precision clause."""
    analysis = _self_grammar_analysis(name)
    assert root_rule not in analysis.conflicts
    kinds = sorted(gate.kind for gate in analysis.taxonomy.struct_loop_gates.values())
    assert kinds == expected_kinds


# ── struct_arm_gates (Task 4/4b): the empty-arm ARM gate ───────────────────


def test_gbnf_self_arm_struct_gate():
    """GBNF self's ``arm`` (``sequence | empty-seq``) is the only rule
    carrying a stored ``struct_arm_gates`` entry: the escape (the empty
    ``empty-seq`` arm) sits at index 1, and the ambiguity resolves via the P5
    rulename-probe — ``arm``'s exit skips ``n`` into the next rule's
    ``rulename n* "::="`` header, which overlaps the item's own lead."""
    analysis = _self_grammar_analysis("gbnf")
    assert set(analysis.taxonomy.struct_arm_gates) == {"arm"}
    gate = analysis.taxonomy.struct_arm_gates["arm"]
    assert gate.escape == 1
    assert gate.gate.kind == SG_PROBE
    assert analysis.demoted["arm"] == ["arm: empty-arm structured-noise (demoted)"]
    assert "arm" not in analysis.islands
    assert sorted(analysis.islands) == ["cc-first", "cc-item", "cc-nfirst"]


def test_abnf_self_has_no_struct_arm_gates():
    """ABNF's self-grammar has no empty-arm alternation shaped like GBNF's
    ``arm`` — the store stays empty."""
    analysis = _self_grammar_analysis("abnf")
    assert analysis.taxonomy.struct_arm_gates == {}


def sg_scan_arm_fixture_analysis() -> GrammarAnalysis:
    """A hand-authored grammar mirroring GBNF's own ``arm`` shape (a content
    arm plus a trailing empty arm) that demotes to ``SG_SCAN`` — the take/exit
    content leads are disjoint, unlike the GBNF self-grammar's own ``arm``,
    which escalates to ``SG_PROBE`` because its exit overlaps a rulename
    header. Shared with ``test_scanner``'s ``scan_gate_take`` pin."""
    text = (
        "# @non-semantic ws\n"
        'top ::= arm ws "y"\n'
        "arm ::= seq |\n"
        'seq ::= ws? "x"\n'
        'ws ::= " "+\n'
    )
    canonical = canonical_grammar(text, get_flavour("gbnf"))
    lifted = lift_optional_nullables(build_codegen_grammar(canonical))
    return GrammarAnalysis(lifted)


def test_instance_grammar_empty_last_arm_demotes_to_sg_scan():
    """The :func:`sg_scan_arm_fixture_analysis` shape demotes to ``SG_SCAN``."""
    analysis = sg_scan_arm_fixture_analysis()
    gate = analysis.taxonomy.struct_arm_gates["arm"]
    assert gate.gate.kind == SG_SCAN
    assert gate.escape == 1
    assert analysis.demoted["arm"] == ["arm: empty-arm structured-noise (demoted)"]
    assert "arm" not in analysis.islands


def test_inline_group_empty_arm_never_stores_struct_gate():
    """An empty arm inside an inline ``(...)`` group never reaches the
    struct-arm store: its label is a bracketed group tag (``r[0]grp``), never
    a rule name, so ``_demote_struct_arm`` is never even attempted — the
    greedy note stays the plain (non-structured) form."""
    ws = IrRule(
        "ws",
        IrAlternation(IrSequence(_item(IrCharClass(IrChr(32)), lo=1, hi=None))),
        semantic=False,
    )
    seq = _rule(
        "seq",
        IrSequence(_item(IrRuleRef("ws"), lo=0, hi=1), _item(IrLiteral("x"))),
    )
    grp = IrAlternation(IrSequence(_item(IrRuleRef("seq"))), IrSequence())
    root = _rule(
        "r",
        IrSequence(
            _item(grp), _item(IrRuleRef("ws"), lo=0, hi=1), _item(IrLiteral("z"))
        ),
    )
    analysis = _analysis(root, seq, ws, start="r")
    assert analysis.taxonomy.struct_arm_gates == {}
    assert analysis.demoted["r"] == ["r[0]grp: arm 0 FIRST hits FOLLOW (greedy)"]


def test_noise_free_empty_last_arm_denies_structured_demotion():
    """A noise-free grammar's empty-arm greedy overlap can never license a
    structured-noise gate: ``noise_roots`` is empty (no non-semantic rule is
    referenced nullable anywhere), so ``structured_arm_gate`` denies at its
    very first guard and the plain greedy note survives (DENY per the plan)."""
    text = 'top ::= a "x"\na ::= "x" |\n'
    canonical = canonical_grammar(text, get_flavour("gbnf"))
    lifted = lift_optional_nullables(build_codegen_grammar(canonical))
    analysis = GrammarAnalysis(lifted)
    assert analysis.taxonomy.struct_arm_gates == {}
    assert analysis.demoted["a"] == ["a: arm 0 FIRST hits FOLLOW (greedy)"]
    assert "a" not in analysis.islands


def test_empty_middle_arm_licenses_sg_scan_with_escape_at_middle_index():
    """An empty arm in the MIDDLE of a three-arm alternation licenses exactly
    like a trailing one — ``escape`` just tracks whichever index the single
    nullable arm sits at, and the two gated arms' content unions into one
    take-set."""
    text = (
        "# @non-semantic ws\n"
        'top ::= a ws "y"\n'
        "a ::= seq1 | | seq2\n"
        'seq1 ::= ws? "x"\n'
        'seq2 ::= "w"\n'
        'ws ::= " "+\n'
    )
    canonical = canonical_grammar(text, get_flavour("gbnf"))
    lifted = lift_optional_nullables(build_codegen_grammar(canonical))
    analysis = GrammarAnalysis(lifted)
    gate = analysis.taxonomy.struct_arm_gates["a"]
    assert gate.escape == 1
    assert gate.gate.kind == SG_SCAN
    assert gate.gate.take is not None
    chars, negated = gate.gate.take
    assert chars == frozenset({"x", "w"})
    assert negated is False
    assert "a" not in analysis.islands


# ── fail_islands (Option B — F1 semantic guard) ────────────────────────────


def test_fail_islands_pins_the_f1_escape_rule():
    """The F1 shape's island is also a fail-island when its rule is semantic.

    ``root ::= x "ab"?`` / ``x ::= [a-c]*`` (the same grammar as
    :func:`test_loop_over_soft_only_follower_islands`): ``x``'s stop-set escapes
    into the soft-only ``"ab"?`` follower, so a reference to it must raise
    ``PdaFail`` rather than parse via longest-match — ``x`` is a fail-island.
    """
    x = _rule(
        "x",
        IrSequence(_item(IrCharClass(IrRange(IrChr(97), IrChr(99))), lo=0, hi=None)),
    )
    root = _rule(
        "root", IrSequence(_item(IrRuleRef("x")), _item(IrLiteral("ab"), lo=0, hi=1))
    )
    analysis = _analysis(root, x, start="root")
    assert analysis.fail_islands == frozenset({"x"})
    assert analysis.fail_islands <= analysis.islands
    assert analysis.rules["x"].semantic is True


@pytest.mark.parametrize("stem", sorted(_PINNED_ISLANDS))
def test_fail_islands_subset_of_islands_for_every_ground_truth(stem: str):
    """``fail_islands`` is a subset of ``islands`` on every ground-truth grammar."""
    analysis = _lifted_analysis(stem)
    assert analysis.fail_islands <= analysis.islands


@pytest.mark.parametrize("stem", ["json.gbnf", "json.abnf"])
def test_json_ws_escape_is_noise_greedy_licensed(stem: str):
    """json's ``ws`` fires the F1 stop-set-escape branch but is
    ``semantic=False`` and its over-eatable gap is provably noise↔noise (no
    hard follower is whitespace-led; no whitespace can follow ``ws`` as
    semantic content) — the P6 licence demotes it to a plain greedy stop-set:
    not an island, not a fail-island (``semantic_dump``/``to_text`` are
    unchanged, only the split between adjacent noise fields moves).
    """
    analysis = _lifted_analysis(stem)
    assert "ws" not in analysis.islands
    assert analysis.demoted["ws"] == ["ws[0]: loop stop-set applied (noise-greedy)"]
    assert analysis.fail_islands == frozenset()


# ── nullability (ported from test_fold, plus queries) ──────────────────────


def test_nullable_names_empty_literal():
    """A rule whose body is an empty literal is nullable."""
    rule = IrRule("empty", IrAlternation(IrSequence(IrItem(IrLiteral("")))))
    assert "empty" in nullable_names((rule,))


def test_nullable_names_lo_zero_item():
    """A rule whose sole item has quantifier lo=0 is nullable."""
    rule = IrRule(
        "zero_lo", IrAlternation(IrSequence(IrItem(IrLiteral("x"), IrQuantifier(0, 1))))
    )
    assert "zero_lo" in nullable_names((rule,))


def test_nullable_names_alternation_arm():
    """A rule with one empty arm (among others) is nullable."""
    rule = IrRule(
        "alt", IrAlternation(IrSequence(), IrSequence(IrItem(IrLiteral("y"))))
    )
    assert "alt" in nullable_names((rule,))


def test_nullable_names_transitive_ref():
    """A rule that refs a nullable rule is transitively nullable (fixpoint)."""
    empty = IrRule("empty", IrAlternation(IrSequence(IrItem(IrLiteral("")))))
    transitive = IrRule(
        "transitive", IrAlternation(IrSequence(IrItem(IrRuleRef("empty"))))
    )
    assert "transitive" in nullable_names((empty, transitive))


def test_nullable_names_excludes_non_nullable():
    """A rule requiring a non-empty literal is not nullable."""
    rule = IrRule("solid", IrAlternation(IrSequence(IrItem(IrLiteral("z")))))
    assert "solid" not in nullable_names((rule,))


def test_analysis_exposes_nullable_set():
    """``GrammarAnalysis.nullable`` carries the fixpoint result."""
    empty = _rule("empty", IrSequence(IrItem(IrLiteral(""))))
    solid = _rule("solid", IrSequence(IrItem(IrLiteral("z"))))
    analysis = _analysis(empty, solid, start="empty")
    assert analysis.nullable == frozenset({"empty"})


def test_atom_and_item_nullable_queries():
    """A ``(0, 1)`` item is nullable; a mandatory literal atom is not."""
    analysis = _analysis(_rule("s", IrSequence(IrItem(IrLiteral("a")))))
    assert analysis.item_nullable(_item(IrLiteral("a"), lo=0))
    assert not analysis.item_nullable(_item(IrLiteral("a")))
    assert not analysis.atom_nullable(IrLiteral("a"))
    assert analysis.atom_nullable(IrAlternation(IrSequence(), IrSequence()))


# ── FIRST ──────────────────────────────────────────────────────────────────


def test_first_of_literal_is_leading_char():
    """FIRST of a rule reduces to its literal's leading character."""
    analysis = _analysis(_rule("s", IrSequence(IrItem(IrLiteral("xy")))))
    assert analysis.first["s"] == CharSet.from_chars("x")


def test_first_of_charclass_is_members():
    """FIRST of a char-class rule is the class members."""
    digits = IrCharClass(IrRange(IrChr("0"), IrChr("9")))
    analysis = _analysis(_rule("s", IrSequence(IrItem(digits))))
    assert analysis.first["s"] == CharSet.from_charclass(digits)


def test_first_of_irnot_is_complement():
    """FIRST of an ``IrNot`` loop is the exact co-finite complement, not ANY."""
    atom = IrNot(IrCharClass(IrChr('"')))
    analysis = _analysis(_rule("s", IrSequence(_item(atom, lo=0, hi=None))))
    first = analysis.first["s"]
    assert first.negated
    assert first.chars == frozenset({'"'})
    assert first.has("a") and not first.has('"')


def test_first_propagates_through_refs():
    """FIRST of a rule that refs another is that rule's FIRST (fixpoint)."""
    inner = _rule("inner", IrSequence(IrItem(IrLiteral("q"))))
    outer = _rule("outer", IrSequence(IrItem(IrRuleRef("inner"))))
    analysis = _analysis(outer, inner, start="outer")
    assert analysis.first["outer"] == CharSet.from_chars("q")


def test_first_unions_alternation_arms():
    """FIRST of a two-arm rule is the union of both arms' FIRSTs."""
    rule = _rule(
        "s",
        IrSequence(IrItem(IrLiteral("a"))),
        IrSequence(IrItem(IrLiteral("b"))),
    )
    analysis = _analysis(rule)
    assert analysis.first["s"] == CharSet.from_chars("a", "b")


def test_first_of_undefined_ref_is_any():
    """An undefined rule ref conservatively contributes ANY to FIRST."""
    analysis = _analysis(_rule("s", IrSequence(IrItem(IrRuleRef("missing")))))
    assert analysis.first["s"] == CharSet.ANY


# ── hard-FIRST ─────────────────────────────────────────────────────────────


def test_hard_first_skips_leading_nullable_noise():
    """hard-FIRST of ``ws "{" ws`` (nullable ws) requires ``{``, not whitespace.

    The pivot-4 shape: full FIRST includes the leading nullable ``ws``'s space,
    but hard-FIRST — what the construct *requires* — skips it and starts at the
    mandatory ``{``.
    """
    ws = _rule("ws", IrSequence(_item(IrLiteral(" "), lo=0, hi=None)))
    obj = _rule(
        "obj",
        IrSequence(
            IrItem(IrRuleRef("ws")),
            IrItem(IrLiteral("{")),
            IrItem(IrRuleRef("ws")),
        ),
    )
    analysis = _analysis(obj, ws, start="obj")
    assert analysis.hard["obj"] == CharSet.from_chars("{")
    assert analysis.first["obj"].has(" ") and analysis.first["obj"].has("{")


# ── FOLLOW ──────────────────────────────────────────────────────────────────


def test_follow_seeds_eof_at_start_rule():
    """The start rule's FOLLOW carries the end-of-input sentinel ``\"\"``."""
    analysis = _analysis(_rule("s", IrSequence(IrItem(IrLiteral("a")))))
    assert analysis.follow["s"].has("")


def test_follow_is_continuation_first():
    """A ref's FOLLOW is the FIRST of what follows it in the arm."""
    top = _rule("top", IrSequence(IrItem(IrRuleRef("a")), IrItem(IrLiteral("b"))))
    a = _rule("a", IrSequence(IrItem(IrLiteral("x"))))
    analysis = _analysis(top, a, start="top")
    assert analysis.follow["a"].has("b")
    assert not analysis.follow["a"].has("")


def test_follow_repetition_feeds_own_first():
    """A repeated ref's FOLLOW includes its own FIRST (it can follow itself)."""
    top = _rule("top", IrSequence(_item(IrRuleRef("elem"), lo=1, hi=None)))
    elem = _rule("elem", IrSequence(IrItem(IrLiteral("a"))))
    analysis = _analysis(top, elem, start="top")
    assert analysis.follow["elem"].has("a")  # self-follow (repetition)
    assert analysis.follow["elem"].has("")  # inherits the start rule's EOF


# ── loop-policy taxonomy (one case per tier) ───────────────────────────────


def test_loop_policy_ll2_pair_gate():
    """A ``(0, 1)`` item whose 2-char prefix discriminates yields an LL(2) gate.

    The chess ``fxf5`` vs ``f5`` shape: a leading ``fx`` disambiguates from the
    ``f1`` continuation on the second character.
    """
    analysis = _analysis(_rule("s", IrSequence(IrItem(IrLiteral("z")))))
    item = _item(IrLiteral("fx"), lo=0, hi=1)
    rest = [IrItem(IrLiteral("f1"))]
    policy = analysis.loop_policy(item, rest)
    assert policy == ("pairs", frozenset({"fx"}))


def test_loop_policy_stopset_for_unbounded_charclass():
    """An unbounded ``[^"]*`` loop is a stop-set (non-greedy on the overlap)."""
    analysis = _analysis(_rule("s", IrSequence(IrItem(IrLiteral("z")))))
    item = _item(IrNot(IrCharClass(IrChr('"'))), lo=0, hi=None)
    assert analysis.loop_policy(item, []) == "stopset"


def test_loop_policy_island_when_not_gatable():
    """An optional ref with no LL(2) discriminator is a genuine island."""
    inner = _rule("inner", IrSequence(IrItem(IrLiteral("a"))))
    analysis = _analysis(inner)
    item = _item(IrRuleRef("inner"), lo=0, hi=1)
    assert analysis.loop_policy(item, []) == "island"


# ── raising default: an unregistered atom type must not silently classify ──


class _UnknownAtom(IrAtom):
    """An atom type registered in no dispatch table — must trigger the raise."""


def test_unregistered_atom_type_raises_on_first():
    """FIRST of an atom type outside every dispatch table raises, not classifies."""
    analysis = _analysis(_rule("s", IrSequence(IrItem(IrLiteral("a")))))
    with pytest.raises(UnsupportedConstructError):
        analysis.atom_first(_UnknownAtom())


def test_unregistered_atom_type_raises_on_nullable():
    """Nullability of an unregistered atom type raises rather than defaulting."""
    analysis = _analysis(_rule("s", IrSequence(IrItem(IrLiteral("a")))))
    with pytest.raises(UnsupportedConstructError):
        analysis.atom_nullable(_UnknownAtom())
