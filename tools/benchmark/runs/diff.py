"""What one commit did to every row — two performance runs, paired.

The matrix judges a run against its own base. Asking whether a COMMIT moved a
row means comparing two of those judgements, and until now that was done by
reading job logs by hand: a number from one log, a number from another, and a
conclusion drawn across them. That is how a row's reading came to be quoted
from a job that had been cancelled mid-print.

So this pairs two runs' artefacts instead, and refuses to read a row that has
none. A cancelled or failed job is reported AS cancelled, with how long it ran
— never as a row with a number, because the number in its log belongs to a
judgement that never finished.

The comparison it prints is the ratio of ratios. Each run's row is already a
ratio against that run's own base, so ``B / A`` is what the commit between them
did, and the verdict beside it is whether the two confidence intervals are
disjoint — "moved" only when no single value could have produced both.

Pure core, one thin fetch: :func:`compare_runs` takes two parsed runs and
returns the table, so what the tool concludes is testable without a network.
"""

from __future__ import annotations

import argparse
import json
import math
import subprocess
import tempfile
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import NamedTuple

from tools.benchmark.aggregate import gather
from tools.benchmark.judging.arithmetic import Verdict

WORKFLOW = "performance regression"
"""The workflow whose runs carry the `ab-*` artefacts."""


class Job(NamedTuple):
    """One matrix job's outcome, for the rows that never published.

    :ivar grammar: The matrix entry.
    :ivar conclusion: What GitHub called it — ``success``, ``cancelled``, …
    :ivar minutes: How long it ran before that.
    """

    grammar: str
    conclusion: str
    minutes: float


class Run(NamedTuple):
    """One performance run: what it judged, and what never finished judging.

    :ivar ref: How the run was named on the command line.
    :ivar verdicts: ``grammar/seat`` → that row's judgement.
    :ivar jobs: Every matrix job, including the ones with no artefact.
    """

    ref: str
    verdicts: Mapping[str, Verdict]
    jobs: tuple[Job, ...]


class Paired(NamedTuple):
    """One row in both runs, and what the commit between them did to it.

    :ivar row: ``grammar/seat``.
    :ivar before: The row's verdict in the first run.
    :ivar after: Its verdict in the second.
    """

    row: str
    before: Verdict
    after: Verdict

    @property
    def change(self) -> float:
        """``after / before`` — the ratio of ratios, 1.0 for no change."""
        return self.after.ratio / self.before.ratio if self.before.ratio else 0.0

    @property
    def moved(self) -> bool:
        """Whether the two intervals are disjoint.

        Overlapping intervals are consistent with one underlying value, so the
        honest word for them is "same" however far apart their midpoints are.
        """
        return self.after.high < self.before.low or self.before.high < self.after.low

    @property
    def distance(self) -> float:
        """How far the row moved, in log space — the ordering."""
        return abs(math.log(self.change)) if self.change > 0 else 0.0


class Report(NamedTuple):
    """Everything the pairing found.

    :ivar paired: Rows judged in both runs, furthest-moved first.
    :ivar only: ``(row, which run)`` for rows judged in one run only.
    :ivar unfinished: Jobs that published nothing, per run.
    """

    paired: tuple[Paired, ...]
    only: tuple[tuple[str, str], ...]
    unfinished: tuple[tuple[str, Job], ...]


def compare_runs(before: Run, after: Run, seat: str = "") -> Report:
    """Pair two runs' rows — the whole comparison, and no I/O.

    :param before: The earlier run.
    :param after: The later one.
    :param seat: Keep only rows whose seat is this, or every row when empty.
    :returns: The paired rows, the one-sided ones, and the jobs that failed.
    """
    kept = {
        name
        for name in set(before.verdicts) | set(after.verdicts)
        if not seat or name.rsplit("/", 1)[-1] == seat
    }
    paired = [
        Paired(name, before.verdicts[name], after.verdicts[name])
        for name in sorted(kept)
        if name in before.verdicts and name in after.verdicts
    ]
    only = tuple(
        (name, before.ref if name in before.verdicts else after.ref)
        for name in sorted(kept)
        if (name in before.verdicts) != (name in after.verdicts)
    )
    unfinished = tuple(
        (run.ref, job)
        for run in (before, after)
        for job in run.jobs
        if job.conclusion != "success"
    )
    return Report(
        tuple(sorted(paired, key=lambda one: -one.distance)), only, unfinished
    )


def render(before: Run, after: Run, report: Report) -> str:
    """The report as markdown."""
    lines = [
        f"# `{before.ref}` → `{after.ref}`",
        "",
        "Each ratio is that run's own judgement against its own base, so "
        "**change** is what the commits between them did. `moved` means the "
        "two confidence intervals are disjoint; overlapping intervals are "
        "consistent with one value and are called `same` however far apart "
        "their midpoints look.",
        "",
        "| row | before | after | change | before ci | after ci | envelopes | verdict |",
        "|---|---:|---:|---:|---|---|---|---|",
    ]
    for one in report.paired:
        lines.append(
            f"| {one.row} | {one.before.ratio:.4f} | {one.after.ratio:.4f} | "
            f"**{one.change:.4f}** | "
            f"{one.before.low:.4f}–{one.before.high:.4f} | "
            f"{one.after.low:.4f}–{one.after.high:.4f} | "
            f"{one.before.envelope:.4f} / {one.after.envelope:.4f} | "
            f"{'**moved**' if one.moved else 'same'} |"
        )
    if report.only:
        lines += ["", "## Judged in one run only", ""]
        lines += [f"- `{row}` — only in `{ref}`" for row, ref in report.only]
    if report.unfinished:
        lines += [
            "",
            "## Jobs that published nothing",
            "",
            "A row from one of these is a row from a judgement that never "
            "finished; its log holds numbers the run never stood behind.",
            "",
        ]
        lines += [
            f"- `{ref}` / {job.grammar} — {job.conclusion} after {job.minutes:.0f} min"
            for ref, job in report.unfinished
        ]
    return "\n".join(lines) + "\n"


def _gh(args: Sequence[str]) -> str:
    """One `gh` call, refusing a failure rather than returning half an answer."""
    done = subprocess.run(["gh", *args], capture_output=True, text=True, check=False)
    if done.returncode:
        raise RuntimeError(f"gh {' '.join(args)}: {done.stderr.strip()}")
    return done.stdout


def _minutes(started: str, ended: str) -> float:
    """Whole minutes between two ISO timestamps, or 0 when either is absent."""
    if not started or not ended:
        return 0.0
    begin, finish = (
        int(stamp[11:13]) * 3600 + int(stamp[14:16]) * 60 + int(stamp[17:19])
        for stamp in (started, ended)
    )
    return ((finish - begin) % 86400) / 60


def fetch(ref: str, into: Path) -> Run:
    """One run's artefacts and job outcomes, by commit sha or run id.

    :param ref: A run id, or any prefix of a commit the workflow ran on.
    :param into: A directory to download the artefacts into.
    :returns: The parsed run.
    """
    if ref.isdigit():
        run_id = ref
    else:
        listing = json.loads(
            _gh(
                [
                    "run",
                    "list",
                    "--workflow",
                    WORKFLOW,
                    "--limit",
                    "60",
                    "--json",
                    "databaseId,headSha",
                ]
            )
        )
        found = [one for one in listing if str(one["headSha"]).startswith(ref)]
        if not found:
            raise RuntimeError(f"no {WORKFLOW!r} run found for {ref!r}")
        run_id = str(found[0]["databaseId"])
    jobs = json.loads(_gh(["run", "view", run_id, "--json", "jobs"]))["jobs"]
    matrix = tuple(
        Job(
            str(job["name"]).rsplit("(", 1)[-1].rstrip(")"),
            str(job["conclusion"]),
            _minutes(str(job.get("startedAt", "")), str(job.get("completedAt", ""))),
        )
        for job in jobs
        if "(" in str(job["name"])
    )
    into.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        ["gh", "run", "download", run_id, "--pattern", "ab-*", "--dir", str(into)],
        capture_output=True,
        text=True,
        check=False,
    )
    names = sorted(one.stem[len("ab-") :] for one in into.rglob("ab-*.json"))
    flat = into / "flat"
    flat.mkdir(exist_ok=True)
    for one in into.rglob("ab-*.json"):
        (flat / one.name).write_bytes(one.read_bytes())
    found_rows = gather(flat, names).rows
    return Run(ref, {row.row: row for row in found_rows}, matrix)


def main(argv: Sequence[str] | None = None) -> int:
    """Pair two performance runs and print what moved."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("before", help="commit sha (any prefix) or run id")
    parser.add_argument("after", help="commit sha (any prefix) or run id")
    parser.add_argument("--seat", default="", help="keep only this seat's rows")
    parser.add_argument("--out", type=Path, help="write the markdown here too")
    args = parser.parse_args(argv)

    with tempfile.TemporaryDirectory() as scratch:
        root = Path(scratch)
        before = fetch(args.before, root / "before")
        after = fetch(args.after, root / "after")
    report = compare_runs(before, after, args.seat)
    text = render(before, after, report)
    print(text)
    if args.out:
        args.out.write_text(text, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
