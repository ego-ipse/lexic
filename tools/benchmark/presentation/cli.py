"""Command-line orchestration for the cross-parser benchmark report."""

from __future__ import annotations

import argparse
import datetime
import json
import random
from collections.abc import Sequence
from pathlib import Path
from typing import NamedTuple

from lexic.parsing.parallel import AUTO, available_workers
from tools.benchmark.bench import (
    DEFAULT_ROUNDS,
    ENGINE,
    MT_ROWS,
    SUMMARY,
    _candidates,
)
from tools.benchmark.cases.grammars import BENCHES, Bench
from tools.benchmark.execution.isolation import (
    ReportRow,
    RowRequest,
    noise_floor,
    run_report_row,
)
from tools.benchmark.presentation.reporting import (
    Block,
    _legend,
    _mark,
    _medians,
    _report,
    _use_color,
    _warmup_values,
)

ENGINE_META = {
    "lexic-mt": {"label": "lexic-mt", "runtime": "python"},
    "lexic-mt-lex-ns": {"label": "lexic-mt-lex-ns", "runtime": "python"},
    "lexic-lex": {"label": "lexic-lex", "runtime": "python"},
    "lexic-lex-ns": {"label": "lexic-lex-ns", "runtime": "python"},
    "lexic-pda": {"label": "lexic-pda", "runtime": "python"},
    "lexic-earley": {"label": "lexic-earley", "runtime": "python"},
    "lark-lalr": {"label": "lark (LALR)", "runtime": "python"},
    "lark-lalr-lex": {"label": "lark (LALR, marked)", "runtime": "python"},
    "lark-earley": {"label": "lark (Earley)", "runtime": "python"},
    "lark-earley-lex": {"label": "lark (Earley, marked)", "runtime": "python"},
    "parsimonious": {"label": "parsimonious", "runtime": "python"},
    "parsimonious-lex": {"label": "parsimonious (marked)", "runtime": "python"},
    "pyparsing": {"label": "pyparsing", "runtime": "python"},
    "antlr-py": {"label": "ANTLR (Python)", "runtime": "python"},
    "antlr-py-lex": {"label": "ANTLR (Python, marked)", "runtime": "python"},
    "antlr": {"label": "ANTLR (Java)", "runtime": "java"},
    "antlr-lex": {"label": "ANTLR (Java, marked)", "runtime": "java"},
    "stdlib-json": {"label": "json.loads (stdlib)", "runtime": "python"},
    "msgspec": {"label": "msgspec", "runtime": "python"},
}
"""Display metadata per row, in the artifact's column order."""


NOTE = (
    "Cross-engine medians of isolated rounds. A run writes only the cells it "
    "measured and leaves every other one exactly as it found it, so each "
    "(grammar, seat) cell carries its own measurement date, round count, "
    "worker request and input. `engines` is display metadata only. README "
    "rendering reads this file and never triggers a run."
)
"""The artifact's own account of how it is written."""


SCHEMA = 3
"""The artifact's shape version — per-cell provenance, per-grammar noise."""

type Cell = float | str
"""One measured median, or the word a refusing seat earned instead."""


class Seat(NamedTuple):
    """One seat's display metadata, and nothing about any run.

    :ivar label: What the README calls this engine.
    :ivar runtime: ``python`` or ``java`` — the README styles java differently.
    """

    label: str
    runtime: str


class Provenance(NamedTuple):
    """The run that measured ONE cell — one grammar, one seat.

    Per cell because that is the granularity a run may update: ``--only`` picks
    grammars and ``--seats`` picks engines, so a column holds cells from
    different days. Stored per column, one refresh restated every untouched
    grammar in that column as though it had been taken with it.

    :ivar measured: The ISO date this cell was taken.
    :ivar rounds: Timed rounds behind it.
    :ivar cores: The worker request an mt row rode; ``None`` for every seat
        that runs on one thread.
    :ivar scale: ``corpus`` or ``full`` — which of the case's two documents the
        seat read. ``--full`` changes the work, so it changes the cell.
    :ivar chars: That document's length, so a resized fixture is visible.
    """

    measured: str
    rounds: int
    cores: int | None
    scale: str
    chars: int


class Artifact(NamedTuple):
    """The committed cross-engine file, as the fields it actually has.

    Named rather than carried as a JSON bag: the schema is fixed, and a
    ``dict[str, Json]`` makes every write to it untypeable and every read a
    narrowing.
    """

    noise_floor_percent: dict[str, float]
    engines: dict[str, Seat]
    provenance: dict[str, dict[str, Provenance]]
    values: dict[str, dict[str, Cell]]
    charstream_share: dict[str, dict[str, float]]

    @classmethod
    def load(cls, path: Path) -> Artifact:
        """Read the artifact, or an empty one when the file is not there yet.

        :param path: The artifact to read.
        :returns: Its typed form.
        :raises SystemExit: If the file states a different schema — a layout
            that records provenance differently, read as this one, leaves the
            cells nobody measured carrying this run's date.
        """
        if not path.exists():
            return cls({}, {}, {}, {}, {})
        raw = json.loads(path.read_text(encoding="utf-8"))
        if raw.get("schema") != SCHEMA:
            raise SystemExit(
                f"{path} states schema {raw.get('schema')!r}; this bench writes "
                f"schema {SCHEMA}. Re-measure the whole roster rather than "
                f"splicing into a layout that records provenance differently."
            )
        return cls(
            dict(raw["noise_floor_percent"]),
            {name: Seat(**meta) for name, meta in raw["engines"].items()},
            {
                grammar: {seat: Provenance(**record) for seat, record in cells.items()}
                for grammar, cells in raw["provenance"].items()
            },
            {grammar: dict(cells) for grammar, cells in raw["values"].items()},
            {
                grammar: dict(shares)
                for grammar, shares in raw["charstream_share"].items()
            },
        )

    def write(self, path: Path) -> None:
        """Write the artifact back, header first and in field order."""
        payload = {
            "schema": SCHEMA,
            "unit": "microseconds_per_character",
            "note": NOTE,
            "noise_floor_percent": self.noise_floor_percent,
            "engines": {name: seat._asdict() for name, seat in self.engines.items()},
            "provenance": {
                grammar: {seat: record._asdict() for seat, record in cells.items()}
                for grammar, cells in self.provenance.items()
            },
            "values": self.values,
            "charstream_share": self.charstream_share,
        }
        path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def _display(name: str) -> Seat:
    """One seat's display metadata; an unknown seat gets a default, not silence."""
    meta = ENGINE_META.get(name, {"label": name, "runtime": "python"})
    return Seat(meta["label"], meta["runtime"])


def measured_input(bench: Bench, name: str, full: bool) -> tuple[str, int]:
    """Which of the case's documents one seat read, as ``(scale, length)``.

    The mt rows always read the full corpus; ``--full`` puts every other seat
    on it too. Public because the record and the run must not disagree about
    which document a number came from.
    """
    full_input = full or name in MT_ROWS
    return ("full", len(bench.full)) if full_input else ("corpus", len(bench.corpus))


def _provenance(
    name: str, rounds: int, cores: int | None, read: tuple[str, int]
) -> Provenance:
    """One cell's record, dated by the run that has just measured it.

    :param name: The seat measured.
    :param rounds: Timed rounds behind the median.
    :param cores: The run's worker request, kept only for a threaded seat.
    :param read: That seat's ``(scale, length)`` from :func:`measured_input`.
    """
    scale, chars = read
    return Provenance(
        datetime.date.today().isoformat(),
        rounds,
        cores if name in MT_ROWS else None,
        scale,
        chars,
    )


def _spliced[T](kept: dict[str, T], fresh: dict[str, T]) -> dict[str, T]:
    """``kept`` with ``fresh`` written over it, in the order it already had.

    Insertion order is the artifact's own: a refreshed seat keeps the column
    it had, and a new one is appended rather than reordering the file.
    """
    merged = dict(kept)
    for name, value in fresh.items():
        merged[name] = value
    return merged


def _dump_json(
    path: Path, rounds: int, cores: int | None, full: bool, blocks: list[Block]
) -> None:
    """Splice this run's measured or refused cells into the cross-engine artifact.

    Never a rewrite: a filtered run measures a few seats of a few grammars and
    must leave every other cell byte-identical — its number AND the record of
    what produced it. Provenance is written for exactly the cells this run
    measured, so refreshing one grammar cannot restate an untouched one in the
    same column as a measurement of a different day, length or worker count.

    Nothing measured is dropped: a seat the metadata table does not know gets a
    default label rather than silence, so a new seat cannot vanish from the
    record.
    """
    artifact = Artifact.load(path)
    for block in blocks:
        grammar = block.bench.name
        cells: dict[str, Cell] = {
            name: round(median, 6) for name, median in _medians(block.samples).items()
        }
        cells |= dict.fromkeys(block.refused, "refuses")
        records = {
            name: _provenance(
                name, rounds, cores, measured_input(block.bench, name, full)
            )
            for name in cells
        }
        for name in cells:
            artifact.engines[name] = _display(name)
        artifact.provenance[grammar] = _spliced(
            artifact.provenance.get(grammar, {}), records
        )
        artifact.values[grammar] = _spliced(artifact.values.get(grammar, {}), cells)
        artifact.charstream_share[grammar] = _spliced(
            artifact.charstream_share.get(grammar, {}),
            {name: round(share, 4) for name, share in sorted(block.shares.items())},
        )
        # Per grammar, for the same reason the dates are per cell: a run that
        # measured four grammars says nothing about the other eight's noise.
        artifact.noise_floor_percent[grammar] = round(block.floor, 2)
    artifact.write(path)
    print(f"wrote {path}")


def _mt_cores(asked: int | None) -> int | None:
    """The lexic-mt thread count — the rows are ON by default when they can be.

    Reads ``cores`` the way lexic does (:mod:`lexic.parsing.parallel.policy`):
    ``--cores N`` is N; bare ``--cores`` and no flag alike are auto. Auto is
    1 on a GIL build, and that is where the rows drop out entirely — a
    "threaded" row running one thread answers a question nobody asked, and
    real threading there measured a net loss.
    """
    workers = available_workers() if asked in (None, AUTO) else asked
    return workers if workers > 1 else None


def _row_names(
    bench: Bench, cores: int | None, seats: frozenset[str] | None = None
) -> list[str]:
    """The isolated worker roster for one grammar, narrowed to ``seats``.

    :param seats: The requested seat names, or ``None`` for every seat this
        grammar admits. A seat the grammar does not offer — a format
        specialist asked of another language — simply does not appear.
    """
    lexic = ["lexic-pda", "lexic-earley", "lexic-lex", "lexic-lex-ns"]
    if cores is not None:
        lexic.extend(("lexic-mt", "lexic-mt-lex-ns"))
    names = lexic + [name for name, _make in _candidates(bench)]
    return names if seats is None else [name for name in names if name in seats]


def _seats(asked: Sequence[str] | None) -> frozenset[str] | None:
    """The requested seat filter, refusing a name no seat answers to.

    A misspelt seat must not read as "that engine measured nothing here": the
    run would write a spliced artifact missing exactly the column it was asked
    to refresh, and every untouched cell would still look freshly measured.
    """
    if not asked:
        return None
    unknown = sorted(frozenset(asked) - frozenset(ENGINE))
    if unknown:
        raise SystemExit(
            f"no such benchmark seat: {', '.join(unknown)}\n"
            f"seats: {', '.join(sorted(ENGINE))}"
        )
    return frozenset(asked)


def _isolated_bench(
    bench: Bench,
    cores: int | None,
    full: bool,
    rounds: int,
    seats: frozenset[str] | None = None,
) -> tuple[Block, dict[str, ReportRow]]:
    """Time every row in its own process, one process at a time.

    No cohort and no overlap: a worker that is merely "not yet timed" still
    compiles grammars, runs fidelity parses and holds artefacts, and doing that
    beside a timed parse contaminates cache, allocator and thermal state.
    """
    names = _row_names(bench, cores, seats)
    order = list(names)
    random.Random(f"lexic-bench:{bench.name}").shuffle(order)
    results = {
        name: run_report_row(
            RowRequest(bench.name, name, rounds, cores, full), Path.cwd()
        )
        for name in order
    }
    samples = {
        name: result.samples for name, result in results.items() if result.samples
    }
    refused = {
        name: result.refusal or "refused without a reason"
        for name, result in results.items()
        if result.refusal is not None
    }
    documents = {
        name: bench.full if full or name in MT_ROWS else bench.corpus
        for name in samples
    }
    mt_notes = {
        name: result.mt_reason
        for name, result in results.items()
        if result.mt_reason is not None
    }
    # Only a seat handed something other than a `str` pays one, so a zero here
    # is the ordinary answer and not a missing reading.
    shares = {
        name: result.charstream_share
        for name, result in results.items()
        if result.charstream_share
    }
    floor = _noise_floor(
        RowRequest(bench.name, "", rounds, cores, full), names, samples
    )
    return Block(bench, samples, refused, floor, documents, mt_notes, shares), results


def _noise_floor(
    request: RowRequest, names: list[str], samples: dict[str, list[float]]
) -> float:
    """This block's same-engine control, run on the first row that measured.

    Zero when nothing in the block did: a floor is a statement about a seat
    that produced numbers, and there is none to make.
    """
    anchor = next((name for name in names if name in samples), None)
    if anchor is None:
        return 0.0
    return noise_floor(request._replace(engine=anchor), Path.cwd())


def main(argv: Sequence[str] | None = None) -> None:
    """Time every engine on every benchmark grammar."""
    parser = argparse.ArgumentParser(description=SUMMARY)
    parser.add_argument(
        "--rounds",
        type=int,
        default=DEFAULT_ROUNDS,
        help=f"timed rounds per engine (default {DEFAULT_ROUNDS}; 1 is a quick pass)",
    )
    parser.add_argument(
        "--cores",
        type=int,
        nargs="?",
        const=0,
        default=None,
        metavar="N",
        help="lexic-mt worker count: the corpus parsed as ONE document "
        "split across N workers (bare --cores = auto, the cpu count; "
        "free-threaded interpreter only — the GIL build measured a net loss)",
    )
    parser.add_argument(
        "--full",
        action="store_true",
        help="time every row on the full corpus (default: only the lexic-mt "
        "rows read it — the slow engines pay seconds per pass there)",
    )
    parser.add_argument(
        "--only", nargs="*", metavar="NAME", help="benchmark only these grammars"
    )
    parser.add_argument(
        "--seats",
        nargs="+",
        metavar="NAME",
        help="benchmark only these seats (--only filters grammars, this "
        "filters engines); an unknown name is refused, and --json then "
        "splices these columns into the artifact and leaves the rest",
    )
    parser.add_argument(
        "--color",
        action="store_true",
        help="force ANSI colour (auto: only on a terminal, honouring NO_COLOR)",
    )
    parser.add_argument(
        "--json",
        type=Path,
        metavar="PATH",
        help="also write the measured medians as the cross-engine artifact "
        "(the file tools/render_readme.py renders the README from)",
    )
    args = parser.parse_args(argv)
    if args.cores and available_workers() == 1:
        raise SystemExit(
            "--cores needs a free-threaded interpreter (python3.14t): "
            "threaded parsing under the GIL measured 0.82-0.92x, a net loss"
        )
    cores = _mt_cores(args.cores)
    color = _use_color(args.color)
    seats = _seats(args.seats)
    wanted = set(args.only or ())
    benches = [b for b in BENCHES if not wanted or b.name in wanted]
    if not benches:
        raise SystemExit(f"no such grammar: {sorted(wanted)}")
    benches = [b for b in benches if _row_names(b, cores, seats)]
    if not benches:
        raise SystemExit(f"no grammar here offers any of: {sorted(seats or ())}")
    print(
        f"rounds={args.rounds}{_mark(cores)}  grammars={', '.join(b.name for b in benches)}"
        + (f"  seats={', '.join(sorted(seats))}" if seats else "")
    )
    _legend(color)
    blocks: list[Block] = []
    for bench in benches:
        block, results = _isolated_bench(bench, cores, args.full, args.rounds, seats)
        blocks.append(block)
        _report(block, color)
        for name in _row_names(bench, cores, seats):
            result = results[name]
            if result.warmed is not None:
                _warmup_values(
                    name,
                    result.warmed,
                    result.cold_us_per_char,
                    result.charstream_share,
                )
    if args.json:
        _dump_json(args.json, args.rounds, cores, args.full, blocks)


if __name__ == "__main__":
    main()
