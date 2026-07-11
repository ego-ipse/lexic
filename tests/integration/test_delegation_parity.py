"""A/B parity gate for island-interior delegation (Task 6.2, D-c).

Delegation is the one silent-wrong-parse surface in the effort: a conflict-free
island-interior rule runs on its PDA clone instead of the island's Earley
machinery, and a wrong delegability call would corrupt the parse *without*
failing. The corpus-level protection is byte-equality between delegates **on**
and delegates **off** — the off path is the pre-delegation pure-Earley island
parse, itself pinned against the full engine by
:mod:`tests.integration.test_pda_parity`.

The A/B toggle is :data:`lexic.parsing.pda.delegate_compile.DELEGATES_ENABLED`; the
per-island delegate cache (``PdaTables._island_delegates``) is busted between
runs so each recomputes under the current flag. Every sample where the on path
succeeds asserts the off path also succeeds (delegation is fail-soft — it must
never *break* a parse it used to make) and that both yield byte-equal
``semantic_dump()`` + ``to_text()`` (instances) / ``IrAst`` (grammar-text).

Coverage: all ten ground-truth grammars (instances, both flavours) over seeded
generated samples + representative island-dense inputs; the GBNF self-grammar
reduce PDA (grammar-text, both fold paths exercised); and a synthetic
long-interior island grammar — a long digit run under a surviving alternation
island — the delegation payoff case.
"""

from __future__ import annotations

import random
from typing import Callable, cast

import pytest

from lexic.base import GrammarModel
from lexic.compile import (
    CompiledGrammar,
    compile_text,
    parse_grammar,
    self_grammar_pda,
)
from lexic.exceptions import UnsupportedConstructError
from lexic.generate import generate
from lexic.grammars.gbnf import GBNF_FLAVOUR
from lexic.parsing.pda import delegate_compile
from lexic.parsing.pda.clones import PdaTables
from lexic.parsing.pda.reduce_runtime import parse_pda
from lexic.parsing.pda.runtime import PdaFail
from tests.integration.test_pda_parity import _ALL_STEMS, _grammar_for

# ── the A/B toggle ────────────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def _restore_delegates_flag():
    """Restore :data:`DELEGATES_ENABLED` after each test (default on)."""
    saved = delegate_compile.DELEGATES_ENABLED
    yield
    delegate_compile.DELEGATES_ENABLED = True
    assert saved  # the module default must stay on outside the harness


def _with_delegates(pda: PdaTables, flag: bool, run: Callable[[], object]) -> object:
    """Run ``run`` with delegation forced ``flag``, delegate cache busted first.

    The flag is restored and the (shared, compile-cached) delegate cache is
    dropped afterwards, so the next reader recomputes lazily under the
    then-current flag — no stale empty cache leaks between tests.
    """
    saved_flag = delegate_compile.DELEGATES_ENABLED
    delegate_compile.DELEGATES_ENABLED = flag
    pda.reset_delegate_cache()  # recompute under the current flag
    try:
        return run()
    finally:
        delegate_compile.DELEGATES_ENABLED = saved_flag
        pda.reset_delegate_cache()


# ── instance A/B (model path) ─────────────────────────────────────────────


_SYNTH_GRAMMAR = """root ::= item+
item ::= a | b
a ::= digits "x"
b ::= digits "y"
digits ::= [0-9]+
"""
"""A minimal delegation payoff grammar: ``item`` is an alternation island (both
arms share FIRST ``[0-9]``), and its interior delegable rule ``digits``
(``[0-9]+``) is an unbounded run — a long predictive span the delegate resolves
on its clone instead of the island's Earley item machinery."""

_SYNTH_SAMPLES: tuple[str, ...] = (
    "1x2y3x",
    "12345x",
    ("1" * 80 + "x") + ("2" * 120 + "y") + ("3" * 200 + "x"),
    "0y" * 30,
)


def _instance_ab(cg: CompiledGrammar, text: str) -> None:
    """Assert on-vs-off byte parity of the forced PDA parse of ``text``.

    A delegates-on ``PdaFail`` is a legitimate engine fallback only if the
    delegates-off path also fails (same shape); delegation must never turn a
    succeeding PDA parse into a failing one, so an on-fail / off-succeed split is
    an assertion failure.
    """
    pda = cg.pda
    assert pda is not None

    def _parse() -> object:
        try:
            return cast(GrammarModel, parse_pda(pda, text, cg.fold))
        except PdaFail:
            return None

    on = _with_delegates(pda, True, _parse)
    off = _with_delegates(pda, False, _parse)
    if off is None:
        assert on is None, f"delegation broke a parse the engine makes: {text!r}"
        return
    assert on is not None, f"delegation failed a parse off-mode makes: {text!r}"
    on_m, off_m = cast(GrammarModel, on), cast(GrammarModel, off)
    assert on_m.semantic_dump() == off_m.semantic_dump()
    assert on_m.to_text() == off_m.to_text() == text


@pytest.mark.parametrize("stem", _ALL_STEMS)
def test_delegation_instance_parity(stem: str) -> None:
    """On-vs-off parity across seeded generated samples of every grammar."""
    cg, specs, start = _grammar_for(stem)
    if cg.pda is None:
        pytest.skip(f"{stem}: whole-grammar PDA opt-out")
    checked = 0
    for seed in range(40):
        text = generate(start, specs, rng=random.Random(seed), max_depth=4)
        if not text:
            continue
        try:
            _instance_ab(cg, text)
        except UnsupportedConstructError:
            continue  # generator overshoot the engine itself rejects
        checked += 1
    assert checked >= 20, f"{stem}: too few samples actually checked"


def test_delegation_fires_where_expected() -> None:
    """The island set matches the post-P2 map and delegation is non-vacuous.

    Guards against a silently no-op harness: the island counts match the
    post-6.3 (P2-live) baseline — chess ``nonpawn`` left the island set
    entirely (demoted to a pure-PDA k-window gate, so chess no longer
    delegates at all) — and the islands whose interiors carry the payoff runs
    actually delegate (json ``value``; the synthetic grammar below).
    """
    expected = {"chess.gbnf": 0, "json.gbnf": 4, "json.abnf": 4}
    for stem, count in expected.items():
        cg, _specs, _start = _grammar_for(stem)
        assert cg.pda is not None
        assert len(cg.pda.islands) == count, f"{stem}: island set changed"
    js, _s, _t = _grammar_for("json.gbnf")
    assert js.pda is not None
    assert js.pda.island_delegates("value"), "json value should delegate"


# ── the synthetic long-interior island grammar ────────────────────────────


def test_delegation_synthetic_long_interior() -> None:
    """A long digit run under an alternation island: delegates fire, parity holds."""
    cg = compile_text(_SYNTH_GRAMMAR, cache_key="delegation-synth")
    assert cg.pda is not None
    assert sorted(cg.pda.islands) == ["item"], "synthetic island set"
    names = {
        cg.instance_grammar.rules[rid].name for rid in cg.pda.island_delegates("item")
    }
    assert "digits" in names, "the long-run rule must delegate"
    for text in _SYNTH_SAMPLES:
        _instance_ab(cg, text)


# ── grammar-text A/B (reduce path) ─────────────────────────────────────────


def _reduce_outcome(pda: PdaTables, text: str, flag: bool) -> object:
    """The reduce PDA's observable outcome on ``text`` under delegation ``flag``.

    ``('ok', IrAst)`` on a full parse, or ``('fail', message)`` on a
    :class:`PdaFail` (the position it stops at) — a comparable value for the
    on-vs-off parity assertion.
    """

    def run() -> object:
        try:
            return ("ok", parse_pda(pda, text))
        except PdaFail as exc:
            return ("fail", str(exc))

    return _with_delegates(pda, flag, run)


def test_delegation_reduce_path_is_behaviour_neutral() -> None:
    """GBNF self-emit grammar-text: the reduce PDA behaves identically on vs off.

    The reduce path exercises the delegate splice through the flavour's
    :class:`~lexic.parsing.earley.reduce.Reducer` (payload = reduced IR fragment)
    while the parse advances. The GBNF self-grammar reduce PDA is *wired but not
    routed* today (Task 7 flips ``parse_grammar`` onto it) — it does not complete
    a full grammar-text parse standalone yet — so this pins the achievable
    guarantee: delegation changes nothing observable, the parse reaches the exact
    same point (and, per :func:`_reduce_outcome`, the same reduced IR wherever it
    does complete) with delegates on and off, up to and including where the
    un-routed reduce PDA stops. The ABNF reduce PDA opts out whole-grammar
    (``rulelist`` is a start island), so it has no forced-PDA path to A/B yet.
    """
    pda = self_grammar_pda(GBNF_FLAVOUR)
    assert pda is not None, "GBNF self-grammar reduce PDA should exist"
    fresh = _with_delegates(pda, True, lambda: pda.island_delegates("charclass"))
    assert fresh, "the reduce path must carry at least one delegating island"
    text = str(GBNF_FLAVOUR.apply(GBNF_FLAVOUR.grammar))
    on = _reduce_outcome(pda, text, True)
    off = _reduce_outcome(pda, text, False)
    assert on == off, "reduce delegation diverges from the pure-Earley island path"
    if isinstance(on, tuple) and on[0] == "ok":
        assert on[1] == parse_grammar(text, GBNF_FLAVOUR)
