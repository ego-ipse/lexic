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
from lexic.grammars import flavour_for_extension
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
_PINNED_ISLANDS: dict[str, list[str]] = {
    "arithmetic.gbnf": [],
    "c.gbnf": [
        "factor",
        "forinit",
        "multilinecomment",
        "relationoperator",
        "statement",
        "statement-arm7",
    ],
    "chess.gbnf": ["nonpawn"],
    "japanese.gbnf": [],
    "json.gbnf": ["array-item2", "char", "object-item2", "string", "value", "ws"],
    "json_arr.gbnf": ["number", "string"],
    "json_ws.gbnf": ["number", "string"],
    "list.gbnf": [],
    "arithmetic.abnf": [],
    "json.abnf": ["array-item2", "char", "object-item2", "string", "value", "ws"],
}

_PINNED_DEMOTED: dict[str, list[str]] = {
    "arithmetic.gbnf": ["ws"],
    "c.gbnf": ["singlelinecomment"],
    "chess.gbnf": ["pawn"],
    "japanese.gbnf": [],
    "json.gbnf": [],
    "json_arr.gbnf": [],
    "json_ws.gbnf": [],
    "list.gbnf": ["item"],
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
