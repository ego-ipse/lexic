"""The two bench rows the live set exists for keep asking it, on the predictive route.

`two-mark` (a loop boundary settled a line later) and `reopening` (an arm
choice whose readings both complete) went to the gated engine whole before the
live set. Each row prices that settlement, so each pins it: on every lexic seat
the corpus asks the live set and never falls back to whole-document Earley. A
change that sent either shape back would leave the row timing a different
route under the same name, and these fail instead.
"""

from __future__ import annotations

import pytest

from lexic.parsing import products
from lexic.parsing.pda.runtime.kernel.verdicts.liveset import LiveSet
from tools.benchmark.bench import lexic_rows
from tools.benchmark.cases.grammars import BENCHES
from tools.benchmark.measurement.language import unfaithful

ROWS = ("two-mark", "reopening")
SEATS = ("lexic-pda", "lexic-lex", "lexic-lex-ns")


def _row(name: str):
    """The roster entry for ``name``."""
    return next(bench for bench in BENCHES if bench.name == name)


@pytest.mark.parametrize("seat", SEATS)
@pytest.mark.parametrize("name", ROWS)
def test_the_row_asks_the_live_set_on_the_predictive_route(
    monkeypatch, name: str, seat: str
) -> None:
    """The corpus asks live sets, and no parse of it reaches the gated engine
    whole — on the plain seat and under the row's declared directives."""
    bench = _row(name)
    engines, _mt = lexic_rows(bench, None, frozenset({seat}))
    sets, fell = [0], [0]
    decide, earley = vars(LiveSet)["_decide"], products.earley_model

    def counting(self, roots, ahead_first):
        sets[0] += 1
        return decide(self, roots, ahead_first)

    def falling(*args, **kwargs):
        fell[0] += 1
        return earley(*args, **kwargs)

    monkeypatch.setattr(LiveSet, "_decide", counting)
    monkeypatch.setattr(products, "earley_model", falling)
    engines[seat](bench.corpus)
    assert sets[0], f"{name}/{seat}: no live set asked — the row prices nothing"
    assert not fell[0], f"{name}/{seat}: the corpus fell back to the gated engine"


@pytest.mark.parametrize("name", ROWS)
def test_the_earley_seat_builds_the_predictive_seats_model(name: str) -> None:
    """The two lexic columns answer with one model: the gated engine keeps the
    decider's carving, and the predictive path keeps the same one."""
    bench = _row(name)
    engines, _mt = lexic_rows(bench, None, frozenset({"lexic-pda", "lexic-earley"}))
    assert engines["lexic-pda"](bench.corpus) == engines["lexic-earley"](bench.corpus)


def test_a_seat_carving_the_ambiguity_its_own_way_is_still_faithful() -> None:
    """The faithfulness gate judges the LANGUAGE — what a seat accepts and
    refuses — never the tree it builds. On the ambiguous `reopening` row a
    seat that accepts exactly lexic's language but returns a tree of its own
    passes: carving `(0),(1)` differently is answering the same question."""
    bench = _row("reopening")
    engines, _mt = lexic_rows(bench, None, frozenset({"lexic-earley"}))

    def own_carving(text: str) -> object:
        engines["lexic-earley"](text)  # accepts and refuses exactly as lexic
        return ("another", "carving")

    assert unfaithful(own_carving, bench) is None
