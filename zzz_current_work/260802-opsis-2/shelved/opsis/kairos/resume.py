"""The resumable parse — a chart that grows, and can be wound back.

A parse is usually one question about one whole text. This is the other
shape: a chart held open while text arrives, marked at points worth
returning to, and rolled back to any of them. That makes marks temporal
rather than spatial — a point in the session's history, not in the
document.

This chart runs on PLAIN tables and says so. A run-collapsed table
cannot be extended — a run has already consumed past where you are —
so the collapsible rules are named beside the chart rather than
silently traded away.
"""

from __future__ import annotations

from typing import NamedTuple

from opsis.opsis.floor.engine import walked
from opsis.praxis.reading import FOREIGN, Reading

from lexic.exceptions import UnsupportedConstructError
from lexic.parsing import compile_tables
from lexic.parsing.earley.kernel.forest.readout import accept_item
from lexic.parsing.earley.lexruns import run_candidates
from lexic.parsing.earley.resume import ResumableKernel

__all__ = ["Mark", "Resume", "Resumes"]


class Mark(NamedTuple):
    """One point worth returning to, and what the text said there."""

    at: int
    text: str
    accepting: bool


class Resume:
    """One reading's growing chart, and the marks taken along it."""

    __slots__ = ("kernel", "marks", "text", "runs")

    def __init__(self, reading: Reading) -> None:
        compiled = reading.compiled
        if compiled is None:
            raise UnsupportedConstructError("resume: nothing compiled here")
        tables = compile_tables(walked(compiled))
        self.runs = sorted(run_candidates(tables))
        # Recognition-only: extend() cannot truncate the parse-global
        # state record_links keeps, so a growing chart answers whether
        # what has arrived is a whole string, not what it means.
        self.kernel = ResumableKernel(tables, "", False)
        self.kernel.run()
        self.text = ""
        self.marks: list[Mark] = []

    @property
    def accepting(self) -> bool:
        """Whether what has arrived so far is already a whole string."""
        return accept_item(self.kernel) >= 0

    def mark(self) -> Mark:
        """Take a point, so this state can be returned to."""
        taken = Mark(self.kernel.mark(), self.text, self.accepting)
        self.marks.append(taken)
        return taken

    def extend(self, chars: str) -> None:
        """More text, onto the chart that is already there.

        :raises UnsupportedConstructError: When the chart refuses to
            grow — which it says in its own words rather than mine.
        """
        try:
            self.kernel.extend(chars)
        except FOREIGN as exc:
            raise UnsupportedConstructError(f"extend refused: {exc}") from exc
        self.text += chars

    def rollback(self, at: int) -> None:
        """Wind the chart back to a mark, and the text with it."""
        if not any(m.at == at for m in self.marks):
            raise UnsupportedConstructError(f"{at} is not a mark that was taken")
        self.kernel.rollback(at)
        self.text = self.text[:at]
        self.marks = [m for m in self.marks if m.at <= at]


class Resumes:
    """Every reading's resumable parse, dropped when the reading re-reads."""

    __slots__ = ("held", "stamp")

    def __init__(self) -> None:
        self.held: dict[str, Resume] = {}
        self.stamp: dict[str, int] = {}

    def of(self, reading: Reading) -> Resume:
        """This reading's chart, fresh if the grammar under it changed."""
        now = id(reading.product)
        if self.stamp.get(reading.ident) != now:
            self.held[reading.ident] = Resume(reading)
            self.stamp[reading.ident] = now
        return self.held[reading.ident]

    def reset(self, reading: Reading) -> Resume:
        """Throw the chart away and start from the empty prefix."""
        self.stamp.pop(reading.ident, None)
        return self.of(reading)
