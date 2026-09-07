"""Tests for the long-lived Java ANTLR benchmark driver."""

from __future__ import annotations

from io import BytesIO
from types import SimpleNamespace
from typing import Any, cast

from tools.benchmark.engines.antlr_java import SETTLE_BURST, JavaAntlr


def _driver(replies: bytes) -> Any:
    """A driver whose JVM is a scripted pipe, with no JVM behind it."""
    parser = cast(Any, object.__new__(JavaAntlr))
    vars(parser).update(
        {
            "_proc": SimpleNamespace(
                stdin=BytesIO(),
                stdout=BytesIO(replies),
                stderr=BytesIO(b""),
            ),
            "_parse_ns": 0.0,
            "_stream_ns": 0.0,
        }
    )
    parser.cold_us_per_char = None
    return parser


def test_the_first_successful_parse_records_cold_cost_per_character() -> None:
    """The cold number is captured once and remains stable after warm parses.

    A reading is the median of a settling burst, so the burst's FIRST round is
    the one and only cold parse — the cold cost may not drift to the median of
    a burst the JVM has already warmed through.
    """
    warm = b"OK 1000 50\n" * (2 * SETTLE_BURST - 1)
    parser = _driver(b"OK 6500 100\n" + warm)

    parser("ab")
    assert parser.cold_us_per_char == 3.25

    parser("ab")
    assert parser.cold_us_per_char == 3.25


def test_a_reading_is_the_median_of_its_settling_burst() -> None:
    """One post-pause parse is a resumption cost, not the settled level: the
    burst is what makes the published figure reproducible across processes."""
    replies = b"OK 9000 900\n" + b"OK 1000 100\n" * (SETTLE_BURST - 1)
    parser = _driver(replies)

    parser("ab")

    assert parser.measured_us() == 1.0
    assert parser.charstream_share() == 0.1
