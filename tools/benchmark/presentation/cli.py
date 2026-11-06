"""Command-line orchestration for the cross-parser benchmark report."""

from __future__ import annotations

import argparse
import datetime
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
    directive_digest,
)
from tools.benchmark.cases.grammars import BENCHES, Bench
from tools.benchmark.engines.seats import candidates
from tools.benchmark.execution.isolation import (
    ReportRow,
    RowRequest,
    report_passes,
)
from tools.benchmark.measurement.contract import digest
from tools.benchmark.measurement.sampling import medians
from tools.benchmark.presentation.artifact import (
    REFUSES,
    UNMEASURED,
    Artifact,
    Cell,
    Provenance,
    Seat,
    assemble,
    floors,
    reason,
    spliced,
)
from tools.benchmark.presentation.reporting import (
    Block,
    cores_marker,
    legend,
    report_block,
    use_color,
    warmup_values,
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


class Run(NamedTuple):
    """One invocation's measurement settings — the same for every cell it writes.

    Carried as one value because they travel together everywhere: which
    document a seat read, how many rounds stand behind its median and what
    worker count it rode are three answers to "what run was this", and a cell's
    record must not be able to disagree with the roster about any of them.

    :ivar rounds: Timed rounds per row.
    :ivar cores: The mt rows' worker request; ``None`` when there are no mt rows.
    :ivar full: Whether every row reads the case's full document.
    """

    rounds: int
    cores: int | None
    full: bool


def _display(name: str) -> Seat:
    """One seat's display metadata; an unknown seat gets a default, not silence."""
    meta = ENGINE_META.get(name, {"label": name, "runtime": "python"})
    return Seat(meta["label"], meta["runtime"])


def measured_input(bench: Bench, name: str, full: bool) -> tuple[str, str]:
    """Which of the case's documents one seat read, as ``(scale, text)``.

    The mt rows always read the full corpus; ``--full`` puts every other seat
    on it too. Public because the record and the run must not disagree about
    which document a number came from.
    """
    full_input = full or name in MT_ROWS
    return ("full", bench.full) if full_input else ("corpus", bench.corpus)


def _provenance(
    bench: Bench, name: str, run: Run, seen: tuple[int | None, str | None]
) -> Provenance:
    """One cell's record, dated by the run that has just measured it.

    Every digest comes from the same functions the row contract uses, so a cell
    in this file and a contract from a worker name the same grammar, the same
    document and the same declarations by the same values.

    :param bench: The case measured.
    :param name: The seat measured.
    :param run: The settings every cell of this invocation was taken under.
    :param seen: ``(warm-up parses, why this cell holds no number)``, either
        part ``None`` when it does not apply.
    """
    scale, document = measured_input(bench, name, run.full)
    warmed, note = seen
    return Provenance(
        datetime.date.today().isoformat(),
        run.rounds,
        run.cores if name in MT_ROWS else None,
        scale,
        len(document),
        digest(bench.source),
        digest(document),
        directive_digest(bench, name),
        warmed,
        reason(note),
        1,
        None,
    )


def pass_artifact(run: Run, blocks: Sequence[Block]) -> Artifact:
    """One pass's cells as a one-process artifact — what each seat's process
    in this pass measured, refused, or could not put a number to.

    Nothing measured is dropped: a seat the metadata table does not know gets a
    default label rather than silence, so a new seat cannot vanish from the
    record. And a cell that holds no number says WHICH of the two reasons it
    has — :data:`REFUSES` or :data:`UNMEASURED` — with the words in `note`,
    because collapsing both to one word published a measurement failure as a
    claim about someone else's parser.
    """
    artifact = Artifact({}, {}, {}, {}, {})
    for block in blocks:
        grammar = block.bench.name
        cells: dict[str, Cell] = {
            name: round(median, 6) for name, median in medians(block.samples).items()
        }
        cells |= dict.fromkeys(block.refused, REFUSES)
        cells |= dict.fromkeys(block.unmeasured, UNMEASURED)
        reasons = block.refused | block.unmeasured
        artifact.provenance[grammar] = {
            name: _provenance(
                block.bench, name, run, (block.warmed.get(name), reasons.get(name))
            )
            for name in cells
        }
        artifact.engines.update({name: _display(name) for name in cells})
        artifact.values[grammar] = cells
        artifact.charstream_share[grammar] = {
            name: round(share, 4) for name, share in sorted(block.shares.items())
        }
    return artifact


def dump_json(path: Path, measured: Artifact) -> None:
    """Splice this run's assembled cells into the artifact.

    Never a rewrite: a filtered run measures a few seats of a few grammars and
    must leave every other cell byte-identical — its number AND the record of
    what produced it. Provenance is written for exactly the cells this run
    measured, so refreshing one grammar cannot restate an untouched one in the
    same column as a measurement of a different day, length or worker count.
    Each grammar's floor is then read off the file's own cells
    (:func:`~tools.benchmark.presentation.artifact.floors`), so a filtered run
    cannot state a grammar's floor from the few seats it happened to measure.
    """
    artifact = Artifact.load(path)
    artifact.engines.update(measured.engines)
    for grammar in measured.values:
        for field in ("provenance", "values", "charstream_share"):
            held = getattr(artifact, field)
            held[grammar] = spliced(
                held.get(grammar, {}), getattr(measured, field)[grammar]
            )
    artifact.noise_floor_percent.update(floors(artifact))
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


def row_names(
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
    names = lexic + [name for name, _make in candidates(bench)]
    return names if seats is None else [name for name in names if name in seats]


def seat_filter(asked: Sequence[str] | None) -> frozenset[str] | None:
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


PROCESSES = 3
"""Isolated processes behind each report cell; the cell is its median process.

The target is about one slow published median every one to three refreshes. In
three full runs of the README grammars on 2026-10-30, 8 of 216 lexic readings
and 7 of 345 competitor readings lay 10% or more from their cell's median, an
upper 95% rate of 6.6% and 3.8%: at three processes that expects about 0.9 and
0.5 slow published medians per refresh at those bounds, 0.3 and 0.1 at the
point estimates. Five processes would make every refresh about 45 minutes.
"""


def block_of(bench: Bench, run: Run, results: dict[str, ReportRow]) -> Block:
    """One grammar's block from one process per seat."""
    refused = {
        name: result.refusal or "refused without a reason"
        for name, result in results.items()
        if result.refusal is not None
    }
    samples = {
        name: result.samples for name, result in results.items() if result.samples
    }
    unmeasured = unsettled_rows(results, samples)
    samples = {name: runs for name, runs in samples.items() if name not in unmeasured}
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
    # Every seat that WARMED, whether or not it kept its samples: the budget an
    # unsettled row spent is the evidence for why it has no number, so dropping
    # it here is what left that cell recording `warmed=None`.
    warmed = {
        name: result.warmed[0]
        for name, result in results.items()
        if result.warmed is not None and (name in samples or name in unmeasured)
    }
    documents = {name: measured_input(bench, name, run.full)[1] for name in samples}
    return Block(
        bench, samples, refused, documents, mt_notes, shares, warmed, unmeasured
    )


def measure(
    benches: Sequence[Bench], run: Run, seats: frozenset[str] | None, color: bool
) -> Artifact:
    """Every seat of every grammar in :data:`PROCESSES` passes, one process at
    a time, each grammar's seats in its own shuffled order within a pass; then
    each cell its median process (:func:`~...presentation.artifact.assemble`).

    No cohort and no overlap: a worker that is merely "not yet timed" still
    compiles grammars, runs fidelity parses and holds artefacts, and doing that
    beside a timed parse contaminates cache, allocator and thermal state.
    """
    owners = []
    for bench in benches:
        order = row_names(bench, run.cores, seats)
        random.Random(f"lexic-bench:{bench.name}").shuffle(order)
        owners.extend((bench, name) for name in order)
    requests = [
        RowRequest(b.name, n, run.rounds, run.cores, run.full) for b, n in owners
    ]
    taken = report_passes(requests, Path.cwd(), PROCESSES)
    passes = []
    for index, rows in enumerate(taken.passes):
        print(f"\n═══ pass {index + 1} of {PROCESSES}")
        passes.append(pass_artifact(run, _shown(run, owners, rows, color)))
    extras = {
        (owners[k][0].name, owners[k][1]): pass_artifact(
            run, _shown(run, [owners[k]], [row], color)
        )
        for k, row in taken.extras.items()
    }
    return assemble(passes, extras)


def _shown(
    run: Run,
    owners: Sequence[tuple[Bench, str]],
    rows: Sequence[ReportRow | None],
    color: bool,
) -> list[Block]:
    """One pass's blocks, printed as they read, with each JIT's warm-up."""
    grouped: dict[str, tuple[Bench, dict[str, ReportRow]]] = {}
    for (bench, name), row in zip(owners, rows, strict=True):
        if row is not None:
            grouped.setdefault(bench.name, (bench, {}))[1][name] = row
    blocks = []
    for bench, results in grouped.values():
        blocks.append(block_of(bench, run, results))
        report_block(blocks[-1], color)
        for name, result in results.items():
            if result.warmed is not None:
                warmup_values(
                    name,
                    result.warmed,
                    result.cold_us_per_char,
                    result.charstream_share,
                )
    return blocks


def unsettled_rows(
    results: dict[str, ReportRow], samples: dict[str, list[float]]
) -> dict[str, str]:
    """Rows whose warm-up never stopped moving, with the words that say so.

    A JIT seat that has not settled is not measuring the parser: this JVM holds
    a level flat and then steps to roughly half it, and a budget that ran out
    mid-descent published a figure 2.0x to 2.9x above the settled one on five
    of the twelve grammars. That verdict used to reach the console and nowhere
    else, so a `--seats antlr` refresh spliced a soft number into the artifact
    indistinguishably from a settled one.

    The row publishes no number — a figure 2x out is worse than an absent one —
    but it is NOT a refusal. A refusal is a fact about the seat: this tool
    cannot take this language. An unsettled warm-up is a fact about the run:
    the tool parses the grammar perfectly well and we could not get a figure we
    stand behind. Serialising the first for the second told every reader that
    someone else's parser had failed at a language it handles, which is a claim
    we would be making up. So these become :data:`UNMEASURED` cells carrying
    both the reason and the budget spent.

    :param results: Every row's payload, by seat.
    :param samples: The rows that produced timings at all.
    :returns: Seat → why its measurement is not usable.
    """
    return {
        name: (
            f"warm-up never settled after {result.warmed[0]} parses — the "
            f"number would be this JIT mid-descent, not this parser"
        )
        for name, result in results.items()
        if name in samples and result.warmed is not None and not result.warmed[1]
    }


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
    run = Run(args.rounds, cores, args.full)
    color = use_color(args.color)
    seats = seat_filter(args.seats)
    wanted = set(args.only or ())
    benches = [b for b in BENCHES if not wanted or b.name in wanted]
    if not benches:
        raise SystemExit(f"no such grammar: {sorted(wanted)}")
    benches = [b for b in benches if row_names(b, cores, seats)]
    if not benches:
        raise SystemExit(f"no grammar here offers any of: {sorted(seats or ())}")
    print(
        f"rounds={args.rounds}{cores_marker(cores)}  grammars={', '.join(b.name for b in benches)}"
        + (f"  seats={', '.join(sorted(seats))}" if seats else "")
    )
    legend(color)
    assembled = measure(benches, run, seats, color)
    for grammar, floor in assembled.noise_floor_percent.items():
        print(
            f"{grammar}: noise floor {floor:.2f}%, the median of its cells' process spreads"
        )
    if args.json:
        dump_json(args.json, assembled)


if __name__ == "__main__":
    main()
