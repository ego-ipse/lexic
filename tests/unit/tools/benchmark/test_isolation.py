"""Tests for the report's process schedule: passes, final rows, extra processes."""

from __future__ import annotations

from pathlib import Path

import pytest

from tools.benchmark.execution import isolation
from tools.benchmark.execution.isolation import ReportRow, RowRequest, report_passes

SETTLED = ReportRow([1.0], None, None, (2400, True), None, 0.0)
MOVING = ReportRow([1.0], None, None, (2400, False), None, 0.0)
PLAIN = ReportRow([1.0], None, None, None, None, 0.0)
REFUSED = ReportRow([], "cannot take it", None, None, None, 0.0)


def _requests(*seats: str) -> list[RowRequest]:
    """One request per seat of one grammar."""
    return [RowRequest("csv", seat, 7, None, False) for seat in seats]


def _scripted(
    monkeypatch: pytest.MonkeyPatch, answers: dict[str, list[ReportRow]]
) -> list[str]:
    """Each seat's process answers in turn; returns the seats in run order."""
    ran: list[str] = []

    def run(request: RowRequest, _root: Path) -> ReportRow:
        ran.append(request.engine)
        return answers[request.engine][ran.count(request.engine) - 1]

    monkeypatch.setattr(isolation, "run_report_row", run)
    return ran


def test_pass_k_runs_process_k_of_every_cell_before_k_plus_one_of_any(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Two processes of one cell have every other cell of the run between them."""
    ran = _scripted(monkeypatch, {s: [PLAIN] * 3 for s in "abc"})

    taken = report_passes(_requests("a", "b", "c"), Path("."), 3)

    assert ran == ["a", "b", "c"] * 3
    assert [len(one) for one in taken.passes] == [3, 3, 3]
    assert taken.extras == {}


def test_a_refusal_answers_from_its_first_process(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A seat that cannot take the language is not asked again."""
    ran = _scripted(monkeypatch, {"a": [REFUSED], "b": [PLAIN] * 3})

    taken = report_passes(_requests("a", "b"), Path("."), 3)

    assert ran.count("a") == 1 and ran.count("b") == 3
    assert [one[0] for one in taken.passes] == [REFUSED, None, None]


def test_an_unsettled_reading_takes_exactly_one_more_process(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """However many of a cell's readings did not settle, it gets ONE extra
    process, run after every pass; a settled JIT and a seat without a warm-up
    get none."""
    ran = _scripted(
        monkeypatch,
        {
            "jit": [MOVING, SETTLED, MOVING, SETTLED],
            "calm": [SETTLED] * 3,
            "plain": [PLAIN] * 3,
        },
    )

    taken = report_passes(_requests("jit", "calm", "plain"), Path("."), 3)

    assert ran.count("jit") == 4 and ran[-1] == "jit"
    assert ran.count("calm") == 3 and ran.count("plain") == 3
    assert taken.extras == {0: SETTLED}
