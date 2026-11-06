"""Tests for how a published cell is read from the processes that measured it."""

from __future__ import annotations

import pytest

from tools.benchmark.presentation.artifact import (
    REFUSES,
    UNMEASURED,
    Artifact,
    Provenance,
    Reading,
    Seat,
    assemble,
    cell_of,
    floors,
    median_index,
)


def _record(day: str, note: str | None = None) -> Provenance:
    """A one-process record, told apart by its date."""
    return Provenance(day, 7, None, "corpus", 10, "g", "d", "x", None, note, 1, None)


def _reading(value, day: str) -> Reading:
    """One process's reading of one cell."""
    return Reading(value, _record(day), None)


def test_the_cell_is_the_median_process_copied_whole_not_the_first() -> None:
    """The middle reading by value, with that process's own record."""
    cell = cell_of(
        [_reading(3.0, "p1"), _reading(1.0, "p2"), _reading(2.0, "p3")], None
    )

    assert cell.value == 2.0
    assert cell.record.measured == "p3", "the median process's record, not another's"
    assert cell.record.processes == 3
    assert cell.record.spread_percent == 100.0


def test_a_tie_goes_to_the_earlier_reading() -> None:
    """Equal values name one real process, the first of them."""
    assert median_index([2.0, 2.0, 1.0]) == 0
    assert median_index([1.0, 2.0, 2.0]) == 1


def test_a_refusal_must_be_every_readings_and_answers_as_the_first() -> None:
    """A seat that refuses in some processes only is a harness fault, said aloud."""
    cell = cell_of([_reading(REFUSES, "p1")], None)
    assert (cell.value, cell.record.processes) == (REFUSES, 1)
    with pytest.raises(SystemExit, match="refused in some processes only"):
        cell_of([_reading(REFUSES, "p1"), _reading(1.0, "p2")], None)


def test_an_unsettled_reading_is_replaced_by_the_extra_process() -> None:
    """The extra's reading stands where the unsettled one stood."""
    taken = [_reading(UNMEASURED, "p1"), _reading(1.0, "p2"), _reading(3.0, "p3")]

    cell = cell_of(taken, _reading(2.0, "extra"))

    assert (cell.value, cell.record.measured) == (2.0, "extra")
    assert cell.record.processes == 4


def test_an_extra_that_does_not_settle_either_publishes_no_number() -> None:
    """Still unsettled, the cell is UNMEASURED, and its words name the
    readings that did settle."""
    taken = [_reading(UNMEASURED, "p1"), _reading(1.0, "p2"), _reading(3.0, "p3")]

    cell = cell_of(taken, _reading(UNMEASURED, "extra"))

    assert cell.value == UNMEASURED
    assert cell.record.note is not None
    assert "never settled in 2 of 4 processes" in cell.record.note
    assert "[1.0, 3.0]" in cell.record.note


def test_the_floor_is_the_median_of_the_cells_spreads() -> None:
    """Not their mean, nor the largest: a grammar's floor is its middle cell's spread."""
    records = {
        seat: _record("p")._replace(spread_percent=spread)
        for seat, spread in (("a", 1.0), ("b", 2.0), ("c", 10.0), ("d", None))
    }
    artifact = Artifact({}, {}, {"csv": records}, {}, {})

    assert floors(artifact) == {"csv": 2.0}


def test_a_run_in_passes_assembles_to_its_median_processes() -> None:
    """Three one-process passes and one extra become one table."""

    def one(value, day: str) -> Artifact:
        return Artifact(
            {},
            {"a": Seat("a", "python")},
            {"csv": {"a": _record(day)}},
            {"csv": {"a": value}},
            {"csv": {}},
        )

    passes = [one(5.0, "p1"), one(UNMEASURED, "p2"), one(1.0, "p3")]
    table = assemble(passes, {("csv", "a"): one(4.0, "extra")})

    assert table.values == {"csv": {"a": 4.0}}
    assert table.provenance["csv"]["a"].measured == "extra"
    assert table.noise_floor_percent == {"csv": 100.0}
