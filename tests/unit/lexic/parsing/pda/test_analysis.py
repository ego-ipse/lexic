"""Tests for lexic.parsing.pda.analysis — FIRST/hard-FIRST/FOLLOW + taxonomy.

The headline gate pins, per ground-truth grammar, the exact island rule-name
set (and demotion set) :class:`GrammarAnalysis` must produce — asserted equal to
the hybrid-parsing PoC's own milestone-1 output over the same lifted codegen
grammar. The remaining sections exercise the fixpoints and the loop-policy
taxonomy on small hand-authored grammars, and prove an unknown atom type raises
rather than being silently classified.
"""

from __future__ import annotations

import pytest

from lexic.codegen import build_codegen_grammar
from lexic.compile import canonical_grammar
from lexic.exceptions import UnsupportedConstructError
from lexic.grammars import flavour_for_extension, get_flavour
from lexic.ir.base import IrAtom, IrNone, IrSeq
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
from lexic.parsing.fold import lift_optional_nullables
from lexic.parsing.pda import kwindow
from lexic.parsing.pda.analysis import GrammarAnalysis, nullable_names
from lexic.parsing.pda.charsets import CharSet
from tests.paths import GROUND_TRUTH

# ── helpers ───────────────────────────────────────────────────────────────


def _analysis(*rules: IrRule, start: str | None = None) -> GrammarAnalysis:
    """A :class:`GrammarAnalysis` over a hand-authored rule list."""
    resolved = start if start is not None else str(rules[0].name)
    return GrammarAnalysis(IrAst(rules=IrSeq(*rules), start=resolved))


def _rule(name: str, *arms: IrSequence) -> IrRule:
    """A rule from explicit sequence arms."""
    return IrRule(name, IrAlternation(*arms))


def _item(atom: IrAtom, lo: int = 1, hi: int | None = 1) -> IrItem:
    """An item with an explicit quantifier (``hi=None`` means unbounded)."""
    bound = IrNone if hi is None else hi
    return IrItem(atom, IrQuantifier(lo, bound))


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
    "json.gbnf": ["array-item2", "object-item2", "value", "ws"],
    "json_arr.gbnf": ["number"],
    "json_ws.gbnf": ["number"],
    "list.gbnf": [],
    "arithmetic.abnf": [],
    "json.abnf": ["array-item2", "object-item2", "value", "ws"],
}

_PINNED_DEMOTED: dict[str, list[str]] = {
    "arithmetic.gbnf": ["ws"],
    "c.gbnf": ["multilinecomment"],
    "chess.gbnf": ["nonpawn", "pawn"],
    "japanese.gbnf": [],
    "json.gbnf": [],
    "json_arr.gbnf": [],
    "json_ws.gbnf": [],
    "list.gbnf": [],
    "arithmetic.abnf": [],
    "json.abnf": [],
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


def test_p2_demotion_flag_defaults_to_true():
    """The master switch defaults ``True`` — P2 k-window demotion is live
    (Task 6.3 part c landed; ``False`` remains the A/B test seam)."""
    assert kwindow.P2_DEMOTION_ENABLED is True


@pytest.fixture
def _demotion_disabled():
    """Flip ``kwindow.P2_DEMOTION_ENABLED`` off for one test, restoring the
    prior value afterwards — the toggle must never leak between tests."""
    prior = kwindow.P2_DEMOTION_ENABLED
    kwindow.P2_DEMOTION_ENABLED = False
    try:
        yield
    finally:
        kwindow.P2_DEMOTION_ENABLED = prior


@pytest.mark.parametrize(
    ("factory", "pre_p2", "post_p2"),
    [
        (lambda: _self_grammar_analysis("gbnf"), 17, 8),
        (lambda: _self_grammar_analysis("abnf"), 9, 7),
        (lambda: _lifted_analysis("json.gbnf"), 4, 4),
        (lambda: _lifted_analysis("chess.gbnf"), 1, 0),
    ],
    ids=["gbnf-self", "abnf-self", "json.gbnf", "chess.gbnf"],
)
def test_island_set_reverts_to_pre_p2_with_demotion_disabled(
    factory, pre_p2, post_p2, _demotion_disabled
):
    """With ``P2_DEMOTION_ENABLED`` forced off (the A/B seam) the island count
    is the pre-P2 baseline; the default (ON) count is pinned by the same
    factory outside the fixture in
    :func:`test_island_set_default_is_post_p2`."""
    assert kwindow.P2_DEMOTION_ENABLED is False
    assert len(factory().islands) == pre_p2
    assert pre_p2 >= post_p2


@pytest.mark.parametrize(
    ("factory", "expected_count"),
    [
        (lambda: _self_grammar_analysis("gbnf"), 8),
        (lambda: _self_grammar_analysis("abnf"), 7),
        (lambda: _lifted_analysis("json.gbnf"), 4),
        (lambda: _lifted_analysis("chess.gbnf"), 0),
    ],
    ids=["gbnf-self", "abnf-self", "json.gbnf", "chess.gbnf"],
)
def test_island_set_default_is_post_p2(factory, expected_count):
    """Under the live default the island counts moved exactly as the coverage
    map predicts: GBNF-self 17→8 (cc-esc family k2 ×8 + cc-neg k3), ABNF-self
    9→7 (defined/element k2), chess 1→0 (nonpawn k3); json unchanged."""
    assert kwindow.P2_DEMOTION_ENABLED is True
    assert len(factory().islands) == expected_count


def test_demotes_chess_nonpawn_loop():
    """Chess's ``nonpawn`` loop (an island pre-P2) demotes to a k-window gate
    under the live default, and the taxonomy STORES the gate spec (the
    option-(a) channel the clone compiler reads back)."""
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
    demotes under the live default, and the taxonomy STORES the per-arm
    windows aligned to the rule body's arms."""
    analysis = _self_grammar_analysis("gbnf")
    assert "cc-esc" not in analysis.islands
    assert analysis.demoted["cc-esc"] == ["cc-esc: arms k-window separable (demoted)"]

    arms = [_items(arm) for arm in analysis.rules["cc-esc"].body]
    stored = analysis.taxonomy.arm_gates["cc-esc"]
    assert len(stored) == len(arms)
    gate = kwindow.arm_gate(analysis.rules, arms, analysis.follow["cc-esc"])
    assert gate is not None
    assert stored == tuple(kwindow.windows_of(s) for s in gate[1])


def test_group_arm_overlap_stays_an_island():
    """An inline group's arm overlap never demotes (no rule-name store key) —
    the enclosing rule islands even with P2 live, so the clone compiler never
    meets an overlapping group without a spec."""
    assert kwindow.P2_DEMOTION_ENABLED is True
    grp = IrAlternation(
        IrSequence(_item(IrLiteral("ab"))), IrSequence(_item(IrLiteral("ac")))
    )
    root = _rule("root", IrSequence(_item(grp)))
    analysis = _analysis(root, start="root")
    assert "root" in analysis.islands
    assert "root" not in analysis.taxonomy.arm_gates


def test_flag_restored_after_demotion_tests():
    """Sanity: the flag fixtures restored the module flag, so later tests
    (and the rest of the suite) see the live default ``True`` again."""
    assert kwindow.P2_DEMOTION_ENABLED is True


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
def test_fail_islands_empty_for_non_semantic_ws_escape(stem: str):
    """json's ``ws`` fires the F1 stop-set-escape branch but is ``semantic=False``
    (structural-noise, via ``@non-semantic``) — it stays a normal parse-island,
    not a fail-island, so ``fail_islands`` is empty (the perf-preserving
    guarantee of ruling B: a non-semantic F1 escape does not force an engine
    fallback).
    """
    analysis = _lifted_analysis(stem)
    assert "ws" in analysis.islands
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
