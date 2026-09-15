"""Tests for tools.benchmark.runs.diff — pairing two performance runs.

What is under test is the conclusion the tool draws, on synthetic artefacts and
with no network: which rows it calls moved, which it calls the same, what it
does with a row only one run judged, and what it does with a job that published
nothing. The last is the reason the tool exists — a row read out of a cancelled
job's log is a number that run never stood behind, and it has been quoted as
evidence here before.
"""

from __future__ import annotations

import pytest

from tools.benchmark.compare import Verdict
from tools.benchmark.runs.diff import Job, Run, compare_runs, render


def _verdict(row: str, ratio: float, half: float = 0.01, envelope: float = 1.02):
    """One judged row, its interval centred on ``ratio``."""
    return Verdict(row, "ok", ratio, ratio - half, ratio + half, envelope, 6, "cpu")


def _run(ref: str, rows: dict[str, float], jobs: tuple[Job, ...] = ()) -> Run:
    """A run judging ``rows``, each name mapped to its ratio."""
    return Run(ref, {name: _verdict(name, ratio) for name, ratio in rows.items()}, jobs)


# ── what moved ─────────────────────────────────────────────────────────


def test_a_row_whose_intervals_are_disjoint_moved() -> None:
    """Two intervals no single value could have produced."""
    report = compare_runs(_run("A", {"g/s": 1.00}), _run("B", {"g/s": 1.20}))

    (row,) = report.paired
    assert row.moved
    assert row.change == pytest.approx(1.20)


def test_a_row_whose_intervals_overlap_is_the_same() -> None:
    """Overlap is consistent with one value, however far the midpoints look.

    This is the judgement the hand-reading got wrong: 0.987 against 1.041 looks
    like a move and is not one when the envelopes are wide enough to overlap.
    """
    wide = Run("A", {"g/s": Verdict("g/s", "ok", 0.99, 0.93, 1.06, 1.07, 6, "cpu")}, ())
    also = Run("B", {"g/s": Verdict("g/s", "ok", 1.04, 0.98, 1.10, 1.06, 6, "cpu")}, ())

    (row,) = compare_runs(wide, also).paired

    assert not row.moved
    assert row.change == pytest.approx(1.0505, abs=1e-4)


def test_rows_are_ordered_by_how_far_they_moved() -> None:
    """Furthest first, in log space, so a 0.5x sorts with a 2x."""
    before = _run("A", {"a/s": 1.00, "b/s": 1.00, "c/s": 1.00})
    after = _run("B", {"a/s": 1.05, "b/s": 0.50, "c/s": 1.01})

    report = compare_runs(before, after)

    assert [row.row for row in report.paired] == ["b/s", "a/s", "c/s"]


def test_a_halving_and_a_doubling_are_the_same_distance() -> None:
    """The ordering is symmetric, which a plain ratio would not be."""
    before = _run("A", {"a/s": 1.00, "b/s": 1.00})
    after = _run("B", {"a/s": 2.00, "b/s": 0.50})

    report = compare_runs(before, after)

    assert report.paired[0].distance == pytest.approx(report.paired[1].distance)


# ── what only one run judged ───────────────────────────────────────────


def test_a_row_judged_in_one_run_only_is_listed_as_such() -> None:
    """Never paired against nothing — the rows that do not publish are real."""
    report = compare_runs(_run("A", {"a/s": 1.0}), _run("B", {"a/s": 1.0, "b/s": 1.0}))

    assert [row for row, _ in report.only] == ["b/s"]
    assert report.only[0][1] == "B"
    assert [row.row for row in report.paired] == ["a/s"]


def test_a_seat_filter_keeps_one_seat_across_both_runs() -> None:
    """The seat is the part after the last slash, so a grammar name never is."""
    before = _run("A", {"g/one": 1.0, "g/two": 1.0})
    after = _run("B", {"g/one": 1.1, "g/two": 1.1})

    report = compare_runs(before, after, seat="two")

    assert [row.row for row in report.paired] == ["g/two"]


# ── what published nothing ─────────────────────────────────────────────


def test_a_job_that_published_nothing_is_reported_not_read() -> None:
    """With its duration, because how long it ran is what a reader asks next."""
    cancelled = Run("B", {}, (Job("x", "cancelled", 30.0),))

    report = compare_runs(_run("A", {}), cancelled)

    assert report.unfinished == (("B", Job("x", "cancelled", 30.0)),)
    assert not report.paired


def test_a_successful_job_is_not_reported_as_unfinished() -> None:
    """Only the ones that failed to publish."""
    report = compare_runs(
        Run("A", {}, (Job("x", "success", 3.0),)),
        Run("B", {}, (Job("x", "success", 3.0),)),
    )

    assert not report.unfinished


# ── the rendering ──────────────────────────────────────────────────────


def test_the_table_names_both_runs_and_every_section_it_has() -> None:
    """A reader must see which run is which and why a row is missing."""
    before = Run("aaa", {"a/s": _verdict("a/s", 1.0)}, ())
    after = Run(
        "bbb",
        {"a/s": _verdict("a/s", 1.3), "b/s": _verdict("b/s", 1.0)},
        (Job("c", "cancelled", 30.0),),
    )

    text = render(before, after, compare_runs(before, after))

    assert "`aaa` → `bbb`" in text
    assert "**moved**" in text
    assert "Judged in one run only" in text
    assert "Jobs that published nothing" in text
    assert "cancelled after 30 min" in text


def test_a_run_with_nothing_missing_prints_no_empty_sections() -> None:
    """A heading with nothing under it is noise in a report read at a glance."""
    before, after = _run("A", {"a/s": 1.0}), _run("B", {"a/s": 1.0})

    text = render(before, after, compare_runs(before, after))

    assert "Judged in one run only" not in text
    assert "Jobs that published nothing" not in text
