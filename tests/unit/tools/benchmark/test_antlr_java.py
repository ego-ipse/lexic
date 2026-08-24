"""Tests for the long-lived Java ANTLR benchmark driver."""

from __future__ import annotations

from io import BytesIO
from types import SimpleNamespace
from typing import Any, cast

from tools.benchmark.engines.antlr_java import JavaAntlr


def test_the_first_successful_parse_records_cold_cost_per_character() -> None:
    """The cold number is captured once and remains stable after warm parses."""
    parser = cast(Any, object.__new__(JavaAntlr))
    vars(parser).update(
        {
            "_proc": SimpleNamespace(
                stdin=BytesIO(),
                stdout=BytesIO(b"OK 6500 100\nOK 1000 50\n"),
            ),
            "_parse_ns": 0.0,
            "_stream_ns": 0.0,
        }
    )
    parser.cold_us_per_char = None

    parser("ab")
    assert parser.cold_us_per_char == 3.25

    parser("ab")
    assert parser.cold_us_per_char == 3.25
