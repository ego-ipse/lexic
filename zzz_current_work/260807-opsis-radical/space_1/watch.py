"""The engines' clocks — what each machine DID, and what it cost to say so.

Lifted from the build before this one, carrying its four corrections rather
than its code:

1. A frame that merely SPANS the window is context, not an event.
2. No sampling. A subset of hypotheses drew a staircase that is not in the
   parse; a picture that invents structure is worse than a dense one.
3. A lane must MEAN something — the rule, not a free packing slot.
4. A clone id must index the table it was measured against, or it lights the
   wrong clone. Where the two tables disagree, say -1 and draw a miss.
"""

from __future__ import annotations

from typing import Any

from time import perf_counter

from lexic.compile import CompiledGrammar
from lexic.exceptions import LexicError
from lexic.parsing.products import earley_model
from track import said
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

__all__ = ["Clock", "column", "hypotheses", "parity", "watch"]

CEILING = 20000


def spell(clones: dict[int, FlatClone]) -> dict[int, str]:
    """Name every clone that ran — numbered only where its rule has kin.

    126 clones from 39 rules is the machine's whole shape: the same rule
    compiled for two hard continuations IS two different machines, and
    naming a frame after its rule collapsed those five into one word
    repeated five times — which reads as duplication and hides the only
    detail that would explain it.

    The census is only known once the run is over, so the naming happens
    there: numbering as you go gave one clone two different names.
    """
    kin: dict[str, list[int]] = {}
    for key, clone in clones.items():
        kin.setdefault(clone.name, []).append(key)
    said: dict[int, str] = {}
    for name, keys in kin.items():
        for at, key in enumerate(keys):
            if not name:
                said[key] = f"«group»#{at}"
            else:
                said[key] = name if len(keys) == 1 else f"{name}#{at}"
    return said


class Clock(PdaKernel[Any]):
    """The predictive kernel, reporting. It decides nothing differently."""

    # the kernel is slotted and carries no __dict__ — a watcher that wants
    # state declares it, and pays the discipline the hot path pays
    __slots__ = ("clones", "frames", "open", "seats")

    def __init__(
        self, tables: PdaTables, text: str, fold: ModelFold[Any] | None = None
    ) -> None:
        super().__init__(tables, text, fold)
        self.frames: list[list[Any]] = []
        self.open: dict[int, list[Any]] = {}
        self.seats: dict[int, int] = {}
        # every clone this run entered, by identity — named once the run is
        # over, when how many kin its rule has is finally known
        self.clones: dict[int, FlatClone] = {}

    def _enter(self, clone: FlatClone, out: list[object]) -> bool:
        """A frame opens where the cursor stands, at the depth of the stack."""
        depth = len(self.stack)
        entered = super()._enter(clone, out)
        if entered and len(self.stack) > depth and len(self.frames) < CEILING:
            seat = self.seats.setdefault(id(clone), len(self.seats))
            self.clones.setdefault(id(clone), clone)
            record = [self.pos, -1, depth, id(clone), 1, seat]
            self.frames.append(record)
            self.open[id(self.stack[-1])] = record
        return entered

    def _complete(self, frame: list[Any]) -> None:
        """A frame closes where the cursor now stands."""
        record = self.open.pop(id(frame), None)
        super()._complete(frame)
        if record is not None:
            record[1] = self.pos

    def close(self) -> None:
        """Whatever is still open was abandoned; say where it died."""
        for record in self.frames:
            if record[1] < 0:
                record[1] = self.pos
                record[4] = 0


def watch(compiled: CompiledGrammar, text: str) -> list[list[Any]]:
    """Run the predictive engine again, watched, and hand back what it did."""
    kernel = Clock(compiled.pda_tables(), text, compiled.fold)
    try:
        kernel.run()
    except PdaFail:
        pass
    kernel.close()
    said = spell(kernel.clones)
    for record in kernel.frames:
        record[3] = said.get(record[3], "·")
    return kernel.frames


_CHART: dict[tuple[int, int], tuple[Kernel, ParserTables]] = {}


def chart(compiled: CompiledGrammar, text: str) -> tuple[Kernel, ParserTables]:
    """The retained recognizer for this reading — built once, asked per cursor."""
    key = (id(compiled), hash(text))
    if key not in _CHART:
        grammar = normalize(lift_optional_nullables(compiled.codegen_grammar))
        tables = compile_tables(grammar)
        _CHART[key] = (Kernel(tables, text, record_links=False).run(), tables)
    kernel, tables = _CHART[key]
    return kernel, tables


def column(compiled: CompiledGrammar, text: str, at: int) -> str:
    """One Earley column, as dotted items — what the chart believed there.

    Fetched per cursor move; whole-document item sets never ship. Items are
    spelled the way the GRAMMAR spells them, because a reader owed an answer
    is not owed ``IrItem(IrRuleRef('quotation-mark'))``.
    """
    kernel, tables = chart(compiled, text)
    if not 0 <= at < len(kernel.cols):
        return f"#COLUMN {at} 0\n#EXPECT 0\n"
    items: list[str] = []
    expect: set[str] = set()
    for packed in kernel.cols[at]:
        rule, seq, dot, origin = decode_item(tables, packed)
        done = " ".join(said(part) for part in seq[:dot])
        todo = " ".join(said(part) for part in seq[dot:])
        role = "complete" if dot >= len(seq) else "active"
        items.append(f"{origin} {role} {rule} ::= {done} ● {todo}".rstrip())
        if dot < len(seq):
            expect.add(said(seq[dot]))
    return "\n".join(
        [
            f"#COLUMN {at} {len(items)}",
            *items,
            f"#EXPECT {len(expect)}",
            *sorted(expect),
            "",
        ]
    )


def hypotheses(compiled: CompiledGrammar, text: str) -> tuple[list[str], list[str]]:
    """Every hypothesis the other engine held, in COLUMN ORDER.

    Two attempts at this were wrong before: a prefix cut left the tail of the
    document looking like nothing was ever hypothesised, and sampling drew a
    regular staircase that is not in the parse. All of them go, in the order
    the chart built them, and the leaf decides what it can draw.
    """
    kernel, tables = chart(compiled, text)
    names: dict[str, int] = {}
    rows: list[str] = []
    for last, column_items in enumerate(kernel.cols):
        for item in column_items:
            rule, seq, dot, origin = decode_item(tables, item)
            at = names.setdefault(str(rule), len(names))
            rows.append(f"{origin} {last} {1 if dot >= len(seq) else 0} {at}")
    return rows, list(names)


def parity(compiled: CompiledGrammar, text: str) -> tuple[float, str, str]:
    """Run the road not taken and compare the VALUES, not the timings.

    One parse, two observations: the product comes from the engine's own
    composition, and the instrument additionally runs the explicit Earley
    route. Agreement is structural equality AND the same re-emission — two
    engines that build different values from one text is the finding, not a
    detail.
    """
    grammar = normalize(lift_optional_nullables(compiled.codegen_grammar))
    clock = perf_counter()
    try:
        other = earley_model(grammar, text, compiled.fold)
    except (LexicError, RecursionError, ValueError) as refusal:
        return perf_counter() - clock, "failed", str(refusal)[:120]
    seconds = perf_counter() - clock
    mine = compiled.parse(text)
    same = other == mine and other.to_text() == mine.to_text()
    return (
        seconds,
        "holds" if same else "fails",
        "both engines built the same value"
        if same
        else "the engines built DIFFERENT values from one text",
    )
