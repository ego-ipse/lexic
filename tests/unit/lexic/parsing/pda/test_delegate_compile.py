"""Unit tests for the island-interior delegate compile (Task 6.2).

Mirror of :mod:`lexic.parsing.pda.delegate_compile`. The end-to-end on-vs-off
parity + perf payoff live in :mod:`tests.integration.test_delegation_parity`;
here we pin the classifier (island-free + triviality floor) and the
:class:`DelegateSource` cache / no-delegates injection mechanism directly.
"""

from __future__ import annotations

from lexic.compile import compile_text
from lexic.parsing.pda.analysis import GrammarAnalysis
from lexic.parsing.pda.delegate_compile import DelegateSource, _delegable
from lexic.parsing.pda.flatten import FlatClone
from lexic.parsing.products import _model_product


class _NoDelegates(DelegateSource):
    """A :class:`DelegateSource` that compiles nothing — the off arm of the
    A/B injection seam :mod:`tests.integration.test_delegation_parity` uses
    (delegation is otherwise unconditional). Constructed the same way as
    the real source; only ``_compile`` differs."""

    def _compile(self, island_name: str) -> dict[int, object]:
        return {}


# An alternation island (``item``: both arms share FIRST ``[0-9]``) with a long
# island-free interior run (``digits``); ``wrapped`` references the ``item``
# island (an island-referencing rule the floor must exclude); ``short`` is a
# below-floor bounded literal.
_G = """root ::= item wrapped
item ::= a | b
a ::= digits "x"
b ::= digits "y"
digits ::= [0-9]+
wrapped ::= "<" item ">"
short ::= "z"
"""


def _prod(cg):
    """The instance product for a CompiledGrammar (pda / instance_grammar / tables)."""
    return _model_product(cg.codegen_grammar, cg.fold)


def _compiled():
    """Compile ``_G`` and return its (analysis, DelegateSource, CompiledGrammar)."""
    cg = compile_text(_G, cache_key="delegate-compile-unit")
    assert _prod(cg).pda is not None
    source = _prod(cg).pda.program.delegates
    assert isinstance(source, DelegateSource)
    lifted = source.lifted
    return GrammarAnalysis(lifted), source, cg


def test_delegable_accepts_island_free_long_run() -> None:
    """A long island-free run (``digits`` = ``[0-9]+``) clears the floor."""
    analysis, _source, _cg = _compiled()
    assert _delegable(analysis, "digits")


def test_delegable_rejects_island_referencing_interior() -> None:
    """A rule reaching an island (``wrapped`` → ``item``) is not delegated.

    Delegating it would re-enter the Earley island sub-parse for that reference,
    so the PDA-clone wrapper is pure overhead (the json regression the floor
    fixes).
    """
    analysis, _source, _cg = _compiled()
    assert "item" in analysis.islands
    assert not _delegable(analysis, "wrapped")


def test_delegable_rejects_short_interior() -> None:
    """A short bounded interior (``short`` = ``"z"``) sits below the floor."""
    analysis, _source, _cg = _compiled()
    assert not _delegable(analysis, "short")


def test_source_for_island_returns_flat_clones_for_delegables() -> None:
    """``for_island`` yields rule_id → flat clone for the island's delegables."""
    _analysis, source, cg = _compiled()
    delegates = source.for_island("item")
    assert delegates, "the item island should delegate its island-free interior"
    names = {_prod(cg).instance_grammar.rules[rid].name for rid in delegates}
    assert "digits" in names and "wrapped" not in names
    assert all(isinstance(clone, FlatClone) for clone in delegates.values())


def test_no_delegates_variant_yields_no_delegates() -> None:
    """A :class:`_NoDelegates` source, built from the real source's own
    construction ingredients, compiles nothing for any island — the
    injection mechanism the A/B parity harness swaps in for its off arm."""
    _analysis, source, _cg = _compiled()
    off = _NoDelegates(source.lifted, source.name_to_rid, source.target, source.seams)
    assert off.for_island("item") == {}


def test_for_island_is_cached_until_reset() -> None:
    """``for_island`` memoises per island; ``reset`` drops the cache."""
    _analysis, source, _cg = _compiled()
    first = source.for_island("item")
    assert source.for_island("item") is first  # same cached object
    source.reset()
    assert source.for_island("item") is not first  # recomputed after reset
