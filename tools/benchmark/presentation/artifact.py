"""The committed cross-engine artifact — its records, and how a cell is read
from the processes that measured it.

A cell is its median process: the reading of the process whose value is the
middle of the cell's readings, copied whole, so a cell's number, provenance
and CharStream share stay one process's facts. The per-grammar noise floor is
the median of the grammar's cells' process spreads — measured where a cell
varies, across processes, rather than inside one.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from pathlib import Path
from statistics import median
from typing import NamedTuple

NOTE = (
    "Cross-engine medians of isolated rounds, each cell the median of several "
    "isolated processes (`processes`, with their spread in `spread_percent`), "
    "and each grammar's noise floor the median of its cells' spreads. A run "
    "writes only the cells it "
    "measured and leaves every other one exactly as it found it, so each "
    "(grammar, seat) cell carries its own measurement date, round count, "
    "worker request and input. A cell is a number, `refuses` (the seat cannot "
    "take this language) or `unmeasured` (the seat could, but this run could "
    "not obtain a figure it stands behind); the two are different facts and "
    "`note` says which. `engines` is display metadata only. README rendering "
    "reads this file and never triggers a run."
)
"""The artifact's own account of how it is written."""


SCHEMA = 6
"""The artifact's shape version — per-cell provenance with its processes and
their spread, and the per-grammar noise floor read from those spreads."""

REFUSES = "refuses"
"""A cell whose seat cannot take this row's language — a fact about the SEAT.

Published, and informative: it is the answer to "can this tool express this
grammar", and the harness prefers it to a number for a different language.
"""

UNMEASURED = "unmeasured"
"""A cell this run could not put a trustworthy number in — a fact about the RUN.

Not a capability result and not interchangeable with :data:`REFUSES`. A JIT
whose warm-up never settled can parse the grammar perfectly well; what is
missing is a figure the harness will stand behind. Serialising that as
`refuses` told every reader — the README included — that the tool had failed
at the language, which is a claim about someone else's parser that we would be
making up.
"""

type Cell = float | str
"""One measured median, or :data:`REFUSES` / :data:`UNMEASURED`."""

NOTE_LIMIT = 240
"""How much of a nonnumeric cell's reason one record keeps.

The reason is a sentence a reader acts on, and some tools answer with a dump:
Lark's reduce/reduce verdict on `vyx` runs to 70 KB — most of this artifact
again, for one cell — and every clause after the first restates the same
collision for another terminal. The head IS the reason, so the record keeps
that much and marks where it stopped.
"""


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
    :ivar grammar_digest: Digest of the grammar SOURCE this cell was measured
        under. A length says a fixture was resized; only a digest says it was
        EDITED, and an edited grammar leaves every unrefreshed cell in the file
        reading as a measurement of the current language.
    :ivar document_digest: Digest of the exact input parsed, for the same
        reason: a fixture rewritten to the same length is invisible to
        :attr:`chars`.
    :ivar directive_digest: Digest of the EXACT directive sets this seat was
        built with (:func:`~tools.benchmark.bench.seat_directives`). The
        declarations live in `cases/directives.py`, not in the grammar source,
        so editing them changes what a `-lex` cell measured while leaving
        :attr:`grammar_digest` and :attr:`document_digest` untouched. Per SEAT
        rather than per row, because the marked and unmarked seats of one
        grammar are built with different sets on purpose.
    :ivar warmed: Parses spent bringing a JIT seat to steady state, or ``None``
        for a seat with no warm-up. A published figure standing on 2,400 warm
        parses and one standing on 24 are not the same claim, and the cell used
        to say neither. An UNSETTLED warm-up keeps this field — the budget it
        spent is the evidence — and takes :data:`UNMEASURED` as its value.
    :ivar note: Why a nonnumeric cell holds no number, in the seat's own words,
        bounded by :data:`NOTE_LIMIT`; ``None`` for a measured one. The reason
        used to reach the console and stop there, which is what let a refusal
        and a failed measurement serialise identically.
    :ivar processes: The isolated processes the cell took: one for a refusal,
        which answers from its first, one more where a reading did not settle.
    :ivar spread_percent: How far apart the cell's process readings lie,
        ``(max - min) / median`` in percent; ``None`` without a number or with
        one reading only. The
        noise floor is read from these, at the level a cell varies.
    """

    measured: str
    rounds: int
    cores: int | None
    scale: str
    chars: int
    grammar_digest: str
    document_digest: str
    directive_digest: str
    warmed: int | None
    note: str | None
    processes: int
    spread_percent: float | None


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


def reason(note: str | None) -> str | None:
    """One cell's reason as a record keeps it — bounded, and marked where cut.

    Public because a cell whose reason is re-derived outside a timing run is
    recorded through this same function: two spellings of "the reason this cell
    holds no number" would differ on exactly the cells nobody re-measures.

    :param note: The seat's own words, or ``None`` for a measured cell.
    :returns: The same reason within :data:`NOTE_LIMIT`, ``None`` unchanged.
    """
    if note is None or len(note) <= NOTE_LIMIT:
        return note
    return note[: NOTE_LIMIT - 1] + "…"


def spliced[T](kept: dict[str, T], fresh: dict[str, T]) -> dict[str, T]:
    """``kept`` with ``fresh`` written over it, in the order it already had.

    Insertion order is the artifact's own: a refreshed seat keeps the column
    it had, and a new one is appended rather than reordering the file.
    """
    merged = dict(kept)
    for name, value in fresh.items():
        merged[name] = value
    return merged


def median_index(readings: Sequence[float]) -> int:
    """Which reading is the median — the middle one by value, the earlier on a
    tie — so the cell is a real process's reading, never an average."""
    order = sorted(range(len(readings)), key=lambda k: (readings[k], k))
    return order[len(order) // 2]


def spread_of(readings: Sequence[float]) -> float:
    """How far apart a cell's readings lie, in percent of their median."""
    return round((max(readings) - min(readings)) / median(readings) * 100, 2)


def floors(artifact: Artifact) -> dict[str, float]:
    """Each grammar's noise floor: the median of its cells' process spreads,
    over every cell the file holds a spread for."""
    out: dict[str, float] = {}
    for grammar, cells in artifact.provenance.items():
        spreads = [
            r.spread_percent for r in cells.values() if r.spread_percent is not None
        ]
        if spreads:
            out[grammar] = round(median(spreads), 2)
    return out


class Reading(NamedTuple):
    """One process's answer for one cell: its value, record and share."""

    value: Cell
    record: Provenance
    share: float | None


def readings_of(passes: Sequence[Artifact], grammar: str, seat: str) -> list[Reading]:
    """The cell's readings, one per pass that measured it, in pass order."""
    return [
        Reading(
            one.values[grammar][seat],
            one.provenance[grammar][seat],
            one.charstream_share.get(grammar, {}).get(seat),
        )
        for one in passes
        if seat in one.values.get(grammar, {})
    ]


def cell_of(taken: list[Reading], spare: Reading | None) -> Reading:
    """One cell from its processes' readings, and the extra one an unsettled
    reading took.

    A refusal must be every reading's and answers as the first. An unsettled
    reading is replaced by the extra; still unsettled, the cell is
    :data:`UNMEASURED` with words naming its settled readings. Otherwise the
    cell is the median reading, copied whole.

    :raises SystemExit: If the readings disagree about a refusal.
    """
    values = [one.value for one in taken]
    if REFUSES in values:
        if values.count(REFUSES) != len(values):
            raise SystemExit(f"a seat refused in some processes only: {values}")
        return taken[0]._replace(record=taken[0].record._replace(processes=len(taken)))
    count = len(taken) + (spare is not None)
    lone = values.index(UNMEASURED) if UNMEASURED in values else -1
    if lone >= 0 and spare is not None:
        taken = [*taken[:lone], spare, *taken[lone + 1 :]]
        values = [one.value for one in taken]
    settled = [v for v in values if not isinstance(v, str)]
    if len(settled) != len(values):
        held = taken[values.index(UNMEASURED)]
        moving = len(values) - len(settled) + (lone >= 0 and spare is not None)
        words = reason(
            f"warm-up never settled in {moving} of {count} processes; "
            f"the settled readings were {settled} us/char"
        )
        return held._replace(record=held.record._replace(processes=count, note=words))
    chosen = taken[median_index(settled)]
    spread = spread_of(settled) if len(settled) > 1 else None
    record = chosen.record._replace(processes=count, spread_percent=spread)
    return chosen._replace(record=record)


def assemble(
    passes: Sequence[Artifact], extras: Mapping[tuple[str, str], Artifact]
) -> Artifact:
    """The published cells of a run taken in passes: each the median of its
    processes (:func:`cell_of`), each grammar's floor from their spreads.

    :param passes: Pass k's cells, one process each, as a one-process artifact.
    :param extras: ``(grammar, seat)`` → the extra process an unsettled reading took.
    """
    out = Artifact({}, dict(passes[0].engines), {}, {}, {})
    for grammar, seats in passes[0].values.items():
        values, records, shares = {}, {}, {}
        for seat in seats:
            spare = extras.get((grammar, seat))
            cell = cell_of(
                readings_of(passes, grammar, seat),
                readings_of([spare], grammar, seat)[0] if spare is not None else None,
            )
            values[seat], records[seat] = cell.value, cell.record
            if cell.share is not None:
                shares[seat] = cell.share
        out.values[grammar], out.provenance[grammar] = values, records
        out.charstream_share[grammar] = shares
    out.noise_floor_percent.update(floors(out))
    return out
