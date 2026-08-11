"""The engines' own clocks — what each machine DID, not a histogram of it.

The predictive kernel is subclassed so it reports the frames it pushed and
the decisions it took, in its own seams; a frame still open when the parse
dies closed at the failure position and is drawn as abandoned. Counts were
never the point: a histogram is not a machine.
"""

from __future__ import annotations

from typing import Any

import rails
from lexic.compile import CompiledGrammar
from lexic.parsing.earley.kernel.forest.readout import decode_item
from lexic.parsing.earley.kernel.loop.kernel import Kernel
from lexic.parsing.earley.kernel.tables.builder import compile_tables
from lexic.parsing.earley.kernel.tables.records import ParserTables
from lexic.parsing.earley.normalize import normalize
from lexic.parsing.fold import ModelFold, lift_optional_nullables
from lexic.parsing.pda.compiler.flatten import FlatClone
from lexic.parsing.pda.compiler.tables import PdaTables
from lexic.parsing.pda.core.errors import PdaFail
from lexic.parsing.pda.runtime.kernel.kernel import PdaKernel

__all__ = ["ClockKernel", "column", "earley_clock", "pda_clock"]

CEILING = 20000
HYPOTHESES = 60000


class ClockKernel(PdaKernel[Any]):
    """The predictive kernel, reporting. It decides nothing differently."""

    # the kernel is slotted and carries no __dict__ — a watcher that wants
    # state declares it, and pays the same discipline the hot path pays
    __slots__ = ("events", "frames", "open")

    def __init__(
        self, tables: PdaTables, text: str, fold: ModelFold[Any] | None = None
    ) -> None:
        super().__init__(tables, text, fold)
        self.frames: list[list[Any]] = []
        self.events: list[tuple[int, str, str]] = []
        self.open: dict[int, list[Any]] = {}

    def _enter(self, clone: FlatClone, out: list[object]) -> bool:
        """A frame opens where the cursor stands, at the depth of the stack."""
        depth = len(self.stack)
        entered = super()._enter(clone, out)
        if entered and len(self.stack) > depth and len(self.frames) < CEILING:
            record = [self.pos, -1, depth, clone.name or "·", 1]
            self.frames.append(record)
            self.open[id(self.stack[-1])] = record
        return entered

    def _complete(self, frame: list[Any]) -> None:
        """A frame closes where the cursor now stands."""
        record = self.open.pop(id(frame), None)
        super()._complete(frame)
        if record is not None:
            record[1] = self.pos

    def attempt(self, clone: FlatClone, out: list[object]) -> None:
        """The attempt machinery firing IS the event — where, and on what."""
        if len(self.events) < CEILING:
            self.events.append((self.pos, "attempt", clone.name or "·"))
        super().attempt(clone, out)

    def close(self) -> None:
        """Whatever is still open was abandoned; say where it died."""
        for record in self.frames:
            if record[1] < 0:
                record[1] = self.pos
                record[4] = 0


def pda_clock(compiled: CompiledGrammar, text: str) -> str:
    """Run the predictive engine again, watched, and spell what it did."""
    kernel = ClockKernel(compiled.pda_tables(), text, compiled.fold)
    end = -1
    try:
        kernel.run()
    except PdaFail as stop:
        end = kernel.pos
        kernel.events.append((kernel.pos, "verdict", str(stop)[:80]))
    kernel.close()
    hyps, hnames, dropped = earley_clock(compiled, text)
    names = sorted({str(record[3]) for record in kernel.frames})
    at = {name: index for index, name in enumerate(names)}
    return "\n".join(
        [
            "status done",
            "generation 1",
            f"pda_end {end}",
            f"dropped {dropped}",
            f"#PDAFRAMES {len(kernel.frames)}",
            *(f"{s} {e} {d} {at[str(n)]} -1 {ok}" for s, e, d, n, ok in kernel.frames),
            f"#PDANAMES {len(names)}",
            *names,
            f"#EVENTS {len(kernel.events)}",
            *(f"{pos} {kind} {detail}" for pos, kind, detail in kernel.events),
            f"#EARLEY {len(hyps)}",
            *hyps,
            f"#EARLEYNAMES {len(hnames)}",
            *hnames,
            "",
        ]
    )


def earley_clock(
    compiled: CompiledGrammar, text: str
) -> tuple[list[str], list[str], int]:
    """Every hypothesis the OTHER engine ever held, decoded from its columns.

    The instance-grammar recipe is the pass pair, not a flag: without the
    nullable lift and the normal form the tables refuse, and the parse would
    be measuring something the engine never runs.
    """
    grammar = normalize(lift_optional_nullables(compiled.codegen_grammar))
    tables = compile_tables(grammar)
    kernel = Kernel(tables, text, record_links=False).run()
    names: dict[str, int] = {}
    rows: list[str] = []
    for last, column in enumerate(kernel.cols):
        for item in column:
            rule, seq, dot, origin = decode_item(tables, item)
            name = str(rule)
            at = names.setdefault(name, len(names))
            done = 1 if dot >= len(seq) else 0
            rows.append(f"{origin} {last} {done} {at}")
    dropped = max(0, len(rows) - HYPOTHESES)
    if dropped:
        # keep the longest and the completed: a prefix cut would leave the
        # tail of the document looking like nothing was ever hypothesised
        kept = sorted(rows, key=_worth, reverse=True)[:HYPOTHESES]
        order = {row: at for at, row in enumerate(rows)}
        rows = sorted(kept, key=lambda row: order[row])
    return rows, list(names), dropped


def _worth(row: str) -> tuple[int, int]:
    """A hypothesis is worth keeping if it completed, or if it reached far."""
    origin, last, done, _ = row.split(" ")
    return (int(done), int(last) - int(origin))


def _meant(plain: dict[str, str], item: object) -> str:
    """An item, with synthetic references replaced by what they stand for."""
    said = rails.said(item)
    return plain.get(said, said)


_CHART: dict[tuple[int, int], tuple[Kernel, ParserTables]] = {}


def chart(compiled: CompiledGrammar, text: str) -> tuple[Kernel, ParserTables]:
    """The retained recognizer for this reading — built once, asked many times."""
    key = (id(compiled), hash(text))
    if key not in _CHART:
        grammar = normalize(lift_optional_nullables(compiled.codegen_grammar))
        tables = compile_tables(grammar)
        _CHART[key] = (Kernel(tables, text, record_links=False).run(), tables)
    return _CHART[key]


def _plain(grammar: object) -> dict[str, str]:
    """Synthetic rule name → what it stands for, spelled.

    ``normalize`` cuts ``__rep_N`` helpers out of quantifiers; they are real
    rules of the instance grammar and meaningless to a reader — there is no
    line for them in the text and no room behind their name.
    """
    out: dict[str, str] = {}
    for rule in getattr(grammar, "rules", ()):
        name = str(rule.name)
        if not name.startswith("__"):
            continue
        arms = [" ".join(rails.said(item) for item in arm) or "ε" for arm in rule.body]
        out[name] = arms[0] if len(arms) == 1 else "( " + " | ".join(arms) + " )"
    return out


def column(compiled: CompiledGrammar, text: str, at: int) -> str:
    """One Earley column, as dotted items — what the chart believed there.

    Fetched per cursor move; whole-document item sets never ship.
    """
    kernel, tables = chart(compiled, text)
    plain = _plain(normalize(lift_optional_nullables(compiled.codegen_grammar)))
    if not 0 <= at < len(kernel.cols):
        return f"#COLUMN {at} 0\n#EXPECT 0\n"
    items: list[str] = []
    expect: set[str] = set()
    for packed in kernel.cols[at]:
        rule, seq, dot, origin = decode_item(tables, packed)
        done = " ".join(_meant(plain, part) for part in seq[:dot])
        todo = " ".join(_meant(plain, part) for part in seq[dot:])
        role = "complete" if dot >= len(seq) else "active"
        name = plain.get(str(rule), str(rule))
        items.append(f"{origin} {role} {name} ::= {done} ● {todo}".rstrip())
        if dot < len(seq):
            expect.add(_meant(plain, seq[dot]))
    return "\n".join(
        [
            f"#COLUMN {at} {len(items)}",
            *items,
            f"#EXPECT {len(expect)}",
            *sorted(expect),
            "",
        ]
    )
