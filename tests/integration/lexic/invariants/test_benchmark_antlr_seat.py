"""The ANTLR seat must refuse what one stage did, and read reproducibly.

Two independent things are pinned here. The first is the two-stage escalation's
refusal behaviour. The second is the reading protocol: this JVM has no single
steady state, so what the seat publishes is defined by two stated budgets —
a warm-up counted in parses, and a back-to-back burst per reading — and those
budgets must not quietly stop meaning what they say.

The two-stage prediction must refuse exactly what one stage did.

The Java seat parses SLL-first with a bail strategy and re-parses under full LL
only when that stage gives up. That is ANTLR's own fast configuration, and it is
worth a tenth to a sixth of the row — but the escalation is a trap, because the
CharStream is not rewound by anything in the standard wiring. `setInputStream`
nulls the lexer's input before resetting it, so stage two re-lexes from wherever
stage one stopped and answers a question about a *different* input.

It fails in the ACCEPTING direction: `csv` began accepting `'a,,b'` and
`arithmetic` `'1++2'`, because the un-lexed tail happened to parse. A seat that
accepts what lexic refuses is not describing the same language, and nothing is
raised to say so — a suffix that happens NOT to parse hides the bug completely,
which is why it needs a gate of its own rather than the benchmark's differential.

The inputs come from the `ESCALATING` table beside this file, chosen because
they bail out of stage one: that is the only path that touches the rewind.
"""

from __future__ import annotations

import pytest

from tests.integration.lexic.invariants.conftest import NO_JAVA
from tools.benchmark.engines.antlr_java import (
    SETTLE_BURST,
    WARM_BATCH,
    WARM_BUDGET,
    JavaAntlr,
)

pytestmark = pytest.mark.skipif(NO_JAVA, reason="the Java seat needs java and javac")


def _counted(
    parse: JavaAntlr, monkeypatch: pytest.MonkeyPatch, readings: list[float]
) -> list[int]:
    """Replace the seat's single round with a counter serving ``readings``."""
    calls = [0]
    supply = iter(readings)

    def one(_text: str) -> tuple[float, float]:
        """Stand in for one JVM round, returning the next scripted reading."""
        calls[0] += 1
        return next(supply) * 1e3, 0.0

    monkeypatch.setattr(parse, "round", one)
    return calls


def test_an_escalated_parse_still_refuses_what_lexic_refuses(
    seat: tuple[JavaAntlr, str, str],
) -> None:
    """The bug shipped as an ACCEPTANCE, so this asserts the refusal happens."""
    parse, _corpus, bad = seat
    with pytest.raises(SyntaxError):
        parse(bad)


def test_an_escalated_refusal_names_a_position_in_the_whole_input(
    seat: tuple[JavaAntlr, str, str],
) -> None:
    """Stage two must read the input from ITS START, not from stage one's stop.

    Both inputs here go wrong at offset 2, and both are four characters long. A
    stage two handed only the tail cannot report column 2 of the whole input —
    it either accepts, which is the shipped symptom, or it names a position
    inside a suffix. Asserting the column is what distinguishes "refused" from
    "refused for the right reason".
    """
    parse, _corpus, bad = seat
    with pytest.raises(SyntaxError) as refusal:
        parse(bad)
    assert "1:2" in str(refusal.value), (
        f"escalated refusal of {bad!r} named {str(refusal.value)!r}; expected the "
        "error at 1:2, the offset in the WHOLE input"
    )


def test_the_seat_is_usable_after_an_escalation(
    seat: tuple[JavaAntlr, str, str],
) -> None:
    """An escalation must leave the parser in the configuration it started in.

    Stage one swaps in SLL prediction, a bail strategy and no listener; the
    restore is in a `finally`, so a refusal takes the same path a success does.
    If it did not, the FIRST reject in a run would quietly change how every
    later round parses — and the rounds are what the benchmark times.
    """
    parse, corpus, bad = seat
    with pytest.raises(SyntaxError):
        parse(bad)
    parse(corpus)
    with pytest.raises(SyntaxError):
        parse(bad)
    parse(corpus)


def test_one_reading_is_a_whole_settling_burst(
    seat: tuple[JavaAntlr, str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """A reading is a burst, because a lone parse after a pause is resumption.

    The seat used to publish whatever one parse cost after the harness's own
    between-round work, which measured 1.07x to 1.77x apart across processes
    on the same grammar. The burst is the stated budget that replaced it.
    """
    parse, corpus, _bad = seat
    assert SETTLE_BURST > 1, "a burst of one is the lone parse this replaced"
    calls = _counted(parse, monkeypatch, [1.0] * SETTLE_BURST)
    parse(corpus)
    assert calls[0] == SETTLE_BURST


def test_the_reading_is_the_burst_median_not_its_last_parse(
    seat: tuple[JavaAntlr, str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """A single slow parse in the burst must not become the published figure."""
    parse, corpus, _bad = seat
    readings = [10.0] * (SETTLE_BURST - 1) + [900.0]
    _counted(parse, monkeypatch, readings)
    parse(corpus)
    assert parse.measured_us() == pytest.approx(10.0)


def test_a_refusal_costs_one_round_not_a_burst(
    seat: tuple[JavaAntlr, str, str],
) -> None:
    """The burst is a measurement device; a rejected input is not measured."""
    parse, _corpus, bad = seat
    with pytest.raises(SyntaxError):
        parse(bad)


def test_the_warm_budget_is_counted_in_parses(
    seat: tuple[JavaAntlr, str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Warming runs single rounds, so the budget means what it says.

    Warming through the reading burst would multiply the declared budget by
    :data:`SETTLE_BURST` and quietly make the published account wrong.
    """
    parse, corpus, _bad = seat
    total = WARM_BUDGET * WARM_BATCH
    calls = _counted(parse, monkeypatch, [1.0] * total)
    spent, _settled = parse.warm(corpus)
    assert calls[0] == total
    assert spent == total


def test_a_flat_warm_up_reports_settled(
    seat: tuple[JavaAntlr, str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """The tail check must call an unmoving trajectory settled."""
    parse, corpus, _bad = seat
    _counted(parse, monkeypatch, [7.0] * (WARM_BUDGET * WARM_BATCH))
    _spent, settled = parse.warm(corpus)
    assert settled


def test_a_warm_up_still_stepping_reports_unsettled(
    seat: tuple[JavaAntlr, str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """A step inside the tail is reported, never accepted as convergence."""
    parse, corpus, _bad = seat
    total = WARM_BUDGET * WARM_BATCH
    steady = [20.0] * (total - WARM_BATCH * 5)
    _counted(parse, monkeypatch, steady + [5.0] * (WARM_BATCH * 5))
    _spent, settled = parse.warm(corpus)
    assert not settled
