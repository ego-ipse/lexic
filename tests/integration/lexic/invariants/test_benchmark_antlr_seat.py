"""The ANTLR seat's two-stage prediction must refuse exactly what one stage did.

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
from tools.benchmark.engines.antlr_java import JavaAntlr

pytestmark = pytest.mark.skipif(NO_JAVA, reason="the Java seat needs java and javac")


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
