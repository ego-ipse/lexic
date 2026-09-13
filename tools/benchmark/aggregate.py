"""Combine the per-grammar A/B artifacts into one judged summary.

The performance workflow runs one ``compare`` job per grammar and uploads each
job's ``--json`` verdicts. This module reads them back, judges the run the way
``compare.status`` judges one job — ``slower`` rows fail, ``unresolved`` rows
are reported — and renders the result twice: as a plain table on stdout and as
markdown for the job summary, where problems (a grammar whose job never
reported, a row slower than the machine's envelope) come before the bulk.

Standard library only: the aggregate job runs it on a bare checkout without
syncing the development environment.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import NamedTuple, Sequence


class Row(NamedTuple):
    """One judged row, as ``compare`` wrote it."""

    row: str
    status: str
    ratio: float
    low: float
    high: float
    envelope: float
    pairs: int
    clock: str


class Gathered(NamedTuple):
    """Every artifact read, and every grammar whose artifact was not there."""

    rows: tuple[Row, ...]
    missing: tuple[str, ...]


def gather(results: Path, grammars: Sequence[str]) -> Gathered:
    """Read ``results/ab-<grammar>.json`` for every expected grammar.

    :param results: The directory the artifacts were downloaded into.
    :param grammars: The matrix, in matrix order.
    :returns: The rows found, and the grammars with no artifact.
    """
    rows: list[Row] = []
    missing: list[str] = []
    for grammar in grammars:
        file = results / f"ab-{grammar}.json"
        if not file.is_file():
            missing.append(grammar)
            continue
        payload = json.loads(file.read_text(encoding="utf-8"))
        rows.extend(Row(**verdict) for verdict in payload["verdicts"])
    return Gathered(tuple(rows), tuple(missing))


def _cell(value: float) -> str:
    """A ratio to four places."""
    return f"{value:.4f}"


def _markdown_rows(rows: Sequence[Row]) -> list[str]:
    """One markdown table of ``rows``, slowest first."""
    lines = [
        "| row | clock | ratio | ci low | ci high | noise | pairs | status |",
        "|---|---|---:|---:|---:|---:|---:|---|",
    ]
    for row in sorted(rows, key=lambda entry: -entry.ratio):
        lines.append(
            f"| `{row.row}` | {row.clock} | {_cell(row.ratio)} | {_cell(row.low)} "
            f"| {_cell(row.high)} | {_cell(row.envelope)} | {row.pairs} "
            f"| {row.status} |"
        )
    return lines


def _problems(gathered: Gathered) -> list[str]:
    """The section that comes first, or nothing when there is nothing to say."""
    slower = [row for row in gathered.rows if row.status == "slower"]
    if not gathered.missing and not slower:
        return []
    lines = ["## Problems", ""]
    if gathered.missing:
        lines.append(
            "**Matrix jobs that did not report** — the job crashed, timed out or "
            "was cancelled before it wrote its artifact; read that job's log."
        )
        lines.append("")
        lines.extend(f"- `{grammar}`" for grammar in gathered.missing)
        lines.append("")
    if slower:
        lines.append("**Rows slower than this machine's noise envelope**")
        lines.append("")
        lines.extend(_markdown_rows(slower))
        lines.append("")
    return lines


def verdict_line(gathered: Gathered) -> str:
    """The one-line judgement the run's exit code follows."""
    slower = sum(row.status == "slower" for row in gathered.rows)
    unresolved = sum(row.status == "unresolved" for row in gathered.rows)
    tail = f" ({unresolved} unresolved, reported, not blocking)" if unresolved else ""
    if slower or gathered.missing:
        return (
            f"**FAIL** — {slower} row(s) slower than this machine's envelope, "
            f"{len(gathered.missing)} matrix job(s) did not report{tail}"
        )
    return (
        f"**PASS** — no row slower than this machine's envelope across "
        f"{len(gathered.rows)} rows{tail}"
    )


def markdown(gathered: Gathered, grammars: Sequence[str]) -> str:
    """The job summary: verdict, problems first, then every row."""
    lines = [
        "# Same-run Lexic A/B",
        "",
        verdict_line(gathered),
        "",
        *_problems(gathered),
        f"## All rows ({len(grammars) - len(gathered.missing)} of "
        f"{len(grammars)} grammars reported)",
        "",
    ]
    if gathered.rows:
        lines.extend(_markdown_rows(gathered.rows))
    else:
        lines.append("_no artifact reported a row_")
    lines.append("")
    return "\n".join(lines)


def plain(gathered: Gathered) -> str:
    """The stdout rendering — the same columns ``compare.report_table`` prints."""
    lines = [f"MISSING: {grammar} produced no artifact" for grammar in gathered.missing]
    if gathered.rows:
        width = max(len(row.row) for row in gathered.rows)
        lines.append(
            f"{'row':{width}}  {'clock':>5}  {'ratio':>7}  {'ci low':>7}  "
            f"{'ci high':>7}  {'noise':>7}  {'pairs':>5}  status"
        )
        for row in sorted(gathered.rows, key=lambda entry: -entry.ratio):
            lines.append(
                f"{row.row:{width}}  {row.clock:>5}  {row.ratio:7.4f}  "
                f"{row.low:7.4f}  {row.high:7.4f}  {row.envelope:7.4f}  "
                f"{row.pairs:5}  {row.status}"
            )
    lines.append("")
    lines.append(verdict_line(gathered).replace("**", ""))
    return "\n".join(lines)


def status(gathered: Gathered) -> int:
    """1 when a row is slower or a matrix job did not report, else 0."""
    slower = any(row.status == "slower" for row in gathered.rows)
    return 1 if slower or gathered.missing else 0


def main(argv: Sequence[str] | None = None) -> int:
    """Read the artifacts, write both renderings, return the run's exit code."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("results", type=Path, help="directory of ab-<grammar>.json")
    parser.add_argument("--expect", nargs="+", required=True, help="the matrix")
    parser.add_argument("--summary", type=Path, help="markdown target, appended")
    args = parser.parse_args(argv)
    gathered = gather(args.results, args.expect)
    print(plain(gathered))
    if args.summary:
        with args.summary.open("a", encoding="utf-8") as handle:
            handle.write(markdown(gathered, args.expect))
    return status(gathered)


if __name__ == "__main__":
    sys.exit(main())
