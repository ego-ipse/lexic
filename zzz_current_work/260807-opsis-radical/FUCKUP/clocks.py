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
HYPOTHESES = 400000


class ClockKernel(PdaKernel[Any]):
    """The predictive kernel, reporting. It decides nothing differently."""

    # the kernel is slotted and carries no __dict__ — a watcher that wants
    # state declares it, and pays the same discipline the hot path pays
    __slots__ = ("clones", "events", "frames", "open", "seated", "walk")

    def __init__(
        self, tables: PdaTables, text: str, fold: ModelFold[Any] | None = None
    ) -> None:
        super().__init__(tables, text, fold)
        self.frames: list[list[Any]] = []
        self.events: list[tuple[int, str, str]] = []
        self.open: dict[int, list[Any]] = {}
        self.clones: dict[int, tuple[int, FlatClone, int]] = {}
        # parent → child, as the run walked it: a clone entered beneath
        # another IS an edge, and the view cannot lay out nodes without them
        self.walk: set[tuple[int, int]] = set()
        self.seated: list[int] = []

    def _enter(self, clone: FlatClone, out: list[object]) -> bool:
        """A frame opens where the cursor stands, at the depth of the stack."""
        depth = len(self.stack)
        entered = super()._enter(clone, out)
        if entered and len(self.stack) > depth and len(self.frames) < CEILING:
            seat = self.clones.setdefault(id(clone), (len(self.clones), clone, depth))[
                0
            ]
            # a clone entered BENEATH another is an edge, walked not declared
            if self.seated:
                self.walk.add((self.seated[-1], seat))
            self.seated.append(seat)
            record = [self.pos, -1, depth, clone.name or "·", 1, seat]
            self.frames.append(record)
            self.open[id(self.stack[-1])] = record
        return entered

    def _complete(self, frame: list[Any]) -> None:
        """A frame closes where the cursor now stands."""
        record = self.open.pop(id(frame), None)
        if record is not None and self.seated:
            self.seated.pop()
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


_SEATS: dict[tuple[int, int], list[tuple[int, FlatClone, int]]] = {}
_WALKS: dict[tuple[int, int], set[tuple[int, int]]] = {}


def seats(compiled: CompiledGrammar, text: str) -> list[tuple[int, FlatClone, int]]:
    """The clones the kernel entered, in the order it first entered them.

    The compiler's table and the runtime's program are two identities for one
    machine; a frame carries the runtime's. Lighting a clone means indexing
    the SAME table the frames indexed, so the automaton is served from here.
    """
    key = (id(compiled), hash(text))
    if key not in _SEATS:
        pda_clock(compiled, text)
    return _SEATS.get(key, [])


def _distance(edges: set[tuple[int, int]], count: int) -> dict[int, int]:
    """Distance from the start clone along the walked edges — BFS, not entry.

    A clone first entered near the top of a recursive grammar keeps saying
    "depth 0" however deep the machine actually goes; the view then draws
    every node on one line. Distance answers the question the layout asks.
    """
    out: dict[int, list[int]] = {}
    for frm, to in edges:
        out.setdefault(frm, []).append(to)
    depth = {0: 0}
    frontier = [0]
    while frontier:
        onward = []
        for seat in frontier:
            for nxt in out.get(seat, ()):
                if nxt not in depth:
                    depth[nxt] = depth[seat] + 1
                    onward.append(nxt)
        frontier = onward
    return {seat: depth.get(seat, 0) for seat in range(count)}


def walked(compiled: CompiledGrammar, text: str) -> str:
    """The machine as the run met it — clones seated, edges as walked."""
    rows = seats(compiled, text)
    edges = _WALKS.get((id(compiled), hash(text)), set())
    far = _distance(edges, len(rows))
    names = sorted({clone.name or "·" for _seat, clone, _deep in rows})
    at = {name: index for index, name in enumerate(names)}
    drawn = [
        f"{at[clone.name or '·']} {_mode(clone)} {_flags(clone)} {far[seat]}"
        for seat, clone, _deep in rows
    ]
    return "\n".join(
        [
            f"#ACLONES {len(drawn)}",
            *drawn,
            f"#ANAMES {len(names)}",
            *names,
            f"#AEDGES {len(edges)}",
            *(f"{a} {b}" for a, b in sorted(edges)),
            "",
        ]
    )


def _mode(clone: FlatClone) -> str:
    """What the runtime does with this clone — its own build mode, named."""
    if getattr(clone, "leaf", False):
        return "value_str"
    if getattr(clone, "attempt", None) is not None:
        return "alt"
    return "dispatch" if len(getattr(clone, "selectors", ()) or ()) > 1 else "seq"


def _flags(clone: FlatClone) -> str:
    """a attempt · l leaf · s structured-noise — read off the clone itself."""
    out = ""
    out += "a" if getattr(clone, "attempt", None) is not None else ""
    out += "l" if getattr(clone, "leaf", False) else ""
    out += "s" if getattr(clone, "struct_arm", None) is not None else ""
    return out or "-"


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
    _SEATS[(id(compiled), hash(text))] = sorted(kernel.clones.values())
    _WALKS[(id(compiled), hash(text))] = kernel.walk
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
            *(
                # -1 until a runtime clone can be mapped to the compiled
                # table's seat: a wrong id would light the wrong clone
                f"{s} {e} {d} {at[str(n)]} -1 {ok}"
                for s, e, d, n, ok, seat in kernel.frames
            ),
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
    # NO SAMPLING. Three-per-column drew a regular diagonal staircase that
    # is not in the parse — a picture that invents structure is worse than a
    # dense one. Every hypothesis goes, in column order, and the ceiling is
    # high enough that nothing is dropped silently; what a legible Earley
    # chart needs is an AGGREGATE per column, not a subset of items.
    dropped = max(0, len(rows) - HYPOTHESES)
    return rows[:HYPOTHESES], list(names), dropped


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
