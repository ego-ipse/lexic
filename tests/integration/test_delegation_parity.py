"""A/B parity gate for island-interior delegation (Task 6.2, D-c).

Delegation is the one silent-wrong-parse surface in the effort: a conflict-free
island-interior rule runs on its PDA clone instead of the island's Earley
machinery, and a wrong delegability call would corrupt the parse *without*
failing. The corpus-level protection is byte-equality between delegates **on**
and delegates **off** — the off path is the pre-delegation pure-Earley island
parse, itself pinned against the full engine by
:mod:`tests.integration.test_pda_parity`.

Delegation is unconditional in the compiled artifact, so the A/B toggle here
swaps ``pda.program.delegates`` for a no-delegates
:class:`~lexic.parsing.pda.compiler.delegate_compile.DelegateSource` variant
(:class:`~tests.unit.lexic.parsing.pda.test_delegate_compile.NoDelegates`,
built from the real source's own construction ingredients through its
constructor seam) and back; the per-island delegate cache is busted between
runs (:meth:`PdaTables.reset_delegate_cache`) so each recomputes under the
current source. Every sample where the on path
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

from lexic.compile import (
    CompiledGrammar,
    compile_text,
    parse_grammar,
)
from lexic.exceptions import UnsupportedConstructError
from lexic.generate import generate
from lexic.grammars.gbnf import GBNF_FLAVOUR
from lexic.model import GrammarModel
from lexic.parsing.pda.compiler.delegate_compile import DelegateSource
from lexic.parsing.pda.compiler.specs import IslandRef
from lexic.parsing.pda.compiler.tables import PdaTables
from lexic.parsing.pda.runtime.reduce_runtime import pda_model, pda_reduce
from lexic.parsing.pda.runtime.runtime import PdaFail
from lexic.parsing.products import _reduce_product
from tests.integration.test_pda_parity import ALL_STEMS, grammar_for
from tests.unit.lexic.parsing.parsing_helpers import prod
from tests.unit.lexic.parsing.pda.compiler.test_delegate_compile import NoDelegates

# ── the A/B toggle ────────────────────────────────────────────────────────


def no_delegates_variant(source: DelegateSource) -> DelegateSource:
    """A no-delegates :class:`DelegateSource` built from ``source``'s own
    construction ingredients — the off arm of the injection seam, constructed
    through the same constructor as the real (on) source."""
    return NoDelegates(source.lifted, source.name_to_rid, source.target, source.seams)


def with_delegates(pda: PdaTables, on: bool, run: Callable[[], object]) -> object:
    """Run ``run`` with ``pda.program.delegates`` forced on/off, cache busted first.

    ``on`` runs against the real (compiled) source; ``off`` swaps in a
    no-delegates variant (:func:`no_delegates_variant`) for the duration.
    The real source is restored and the (shared, compile-cached) delegate
    cache is dropped afterwards, so the next reader recomputes lazily under
    whichever source is current — no stale cache leaks between tests.
    """
    real = pda.program.delegates
    pda.program.delegates = real if on else no_delegates_variant(real)
    try:
        return run()
    finally:
        pda.program.delegates = real
        pda.reset_delegate_cache()


# ── instance A/B (model path) ─────────────────────────────────────────────


SYNTH_GRAMMAR = """root ::= item+
item ::= a | b
a ::= digits "x"
b ::= digits "y"
digits ::= [0-9]+
"""
"""A minimal delegation payoff grammar: ``item`` is an alternation island (both
arms share FIRST ``[0-9]``), and its interior delegable rule ``digits``
(``[0-9]+``) is an unbounded run — a long predictive span the delegate resolves
on its clone instead of the island's Earley item machinery."""

SYNTH_SAMPLES: tuple[str, ...] = (
    "1x2y3x",
    "12345x",
    ("1" * 80 + "x") + ("2" * 120 + "y") + ("3" * 200 + "x"),
    "0y" * 30,
)


def instance_ab(cg: CompiledGrammar, text: str) -> None:
    """Assert on-vs-off byte parity of the forced PDA parse of ``text``.

    A delegates-on ``PdaFail`` is a legitimate engine fallback only if the
    delegates-off path also fails (same shape); delegation must never turn a
    succeeding PDA parse into a failing one, so an on-fail / off-succeed split is
    an assertion failure.
    """
    pda = prod(cg).pda
    assert pda is not None

    def _parse() -> object:
        try:
            return pda_model(pda, text, cg.fold)
        except PdaFail:
            return None

    on = with_delegates(pda, True, _parse)
    off = with_delegates(pda, False, _parse)
    if off is None:
        assert on is None, f"delegation broke a parse the engine makes: {text!r}"
        return
    assert on is not None, f"delegation failed a parse off-mode makes: {text!r}"
    on_m, off_m = cast(GrammarModel, on), cast(GrammarModel, off)
    assert on_m.semantic_dump() == off_m.semantic_dump()
    assert on_m.to_text() == off_m.to_text() == text


@pytest.mark.parametrize("stem", ALL_STEMS)
def test_delegation_instance_parity(stem: str) -> None:
    """On-vs-off parity across seeded generated samples of every grammar.

    A grammar whose (possibly overridden) start rule is itself an island
    (c.gbnf under the "statement" override — see ``test_pda_parity``)
    compiles to an immediate-``PdaFail`` start: :meth:`PdaKernel.run` raises
    before looking at the delegate source or the input (``runtime.py``'s
    "IslandRef opt-out" branch), so delegation cannot fire either way.
    Rather than skip the stem outright, this pins that invariant directly —
    on and off both fail identically on a real generated sample."""
    cg, specs, start = grammar_for(stem)
    pda = prod(cg).pda
    if isinstance(pda.start_key, IslandRef):
        text = generate(start, specs, rng=random.Random(0), max_depth=4) or "x"
        for flag in (True, False):
            with pytest.raises(PdaFail):
                with_delegates(pda, flag, lambda: pda_model(pda, text, cg.fold))
        return
    checked = 0
    for seed in range(40):
        text = generate(start, specs, rng=random.Random(seed), max_depth=4)
        if not text:
            continue
        try:
            instance_ab(cg, text)
        except UnsupportedConstructError:
            continue  # generator overshoot the engine itself rejects
        checked += 1
    assert checked >= 20, f"{stem}: too few samples actually checked"


def test_delegation_fires_where_expected() -> None:
    """The island set matches the post-6.4 map and delegation is non-vacuous.

    Guards against a silently no-op harness: chess and json are island-free
    now (P2 demoted chess ``nonpawn``; P6+P3 demoted json ``ws``/``value``/
    ``*-item2``), so neither delegates at all — the non-vacuity witness is the
    synthetic long-interior island grammar
    (:func:`test_delegation_synthetic_long_interior` pins that its ``digits``
    interior actually delegates); this test pins that the bench grammars'
    island sets stay where the map put them.
    """
    expected = {"chess.gbnf": 0, "json.gbnf": 0, "json.abnf": 0}
    for stem, count in expected.items():
        cg, _specs, _start = grammar_for(stem)
        assert not isinstance(prod(cg).pda.start_key, IslandRef)
        assert len(prod(cg).pda.islands) == count, f"{stem}: island set changed"


# ── the synthetic long-interior island grammar ────────────────────────────


def test_delegation_synthetic_long_interior() -> None:
    """A long digit run under an alternation island: delegates fire, parity holds."""
    cg = compile_text(SYNTH_GRAMMAR, cache_key="delegation-synth")
    assert not isinstance(prod(cg).pda.start_key, IslandRef)
    assert sorted(prod(cg).pda.islands) == ["item"], "synthetic island set"
    names = {
        prod(cg).instance_grammar.rules[rid].name
        for rid in prod(cg).pda.island_delegates("item")
    }
    assert "digits" in names, "the long-run rule must delegate"
    for text in SYNTH_SAMPLES:
        instance_ab(cg, text)


# ── grammar-text A/B (reduce path) ─────────────────────────────────────────


def reduce_outcome(pda: PdaTables, text: str, flag: bool) -> object:
    """The reduce PDA's observable outcome on ``text`` under delegation ``flag``.

    ``('ok', IrAst)`` on a full parse, or ``('fail', message)`` on a
    :class:`PdaFail` (the position it stops at) — a comparable value for the
    on-vs-off parity assertion.
    """

    def run() -> object:
        try:
            return ("ok", pda_reduce(pda, text))
        except PdaFail as exc:
            return ("fail", str(exc))

    return with_delegates(pda, flag, run)


def test_delegation_reduce_path_is_behaviour_neutral() -> None:
    """GBNF self-emit grammar-text: the reduce PDA behaves identically on vs off.

    The reduce path exercises the delegate splice through the flavour's
    :class:`~lexic.parsing.earley.reduce.Reducer` (payload = reduced IR fragment)
    while the parse advances. The GBNF self-grammar reduce PDA is *wired but not
    routed* today (Task 7 flips ``parse_grammar`` onto it) — it does not complete
    a full grammar-text parse standalone yet — so this pins the achievable
    guarantee: delegation changes nothing observable, the parse reaches the exact
    same point (and, per :func:`reduce_outcome`, the same reduced IR wherever it
    does complete) with delegates on and off, up to and including where the
    un-routed reduce PDA stops. The ABNF reduce PDA opts out whole-grammar
    (``rulelist`` is a start island), so it has no forced-PDA path to A/B yet.
    """
    pda = _reduce_product(GBNF_FLAVOUR.grammar, GBNF_FLAVOUR.reducer).pda
    assert pda is not None, "GBNF self-grammar reduce PDA should exist"
    fresh = with_delegates(pda, True, lambda: pda.island_delegates("charclass"))
    assert fresh, "the reduce path must carry at least one delegating island"
    text = str(GBNF_FLAVOUR.apply(GBNF_FLAVOUR.grammar))
    on = reduce_outcome(pda, text, True)
    off = reduce_outcome(pda, text, False)
    assert on == off, "reduce delegation diverges from the pure-Earley island path"
    if isinstance(on, tuple) and on[0] == "ok":
        assert on[1] == parse_grammar(text, GBNF_FLAVOUR)
