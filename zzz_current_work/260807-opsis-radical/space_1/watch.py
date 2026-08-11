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

from lexic.compile import CompiledGrammar
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

__all__ = ["Clock", "column", "hypotheses", "watch"]

CEILING = 20000


class Clock(PdaKernel[Any]):
    """The predictive kernel, reporting. It decides nothing differently."""

    # the kernel is slotted and carries no __dict__ — a watcher that wants
    # state declares it, and pays the discipline the hot path pays
    __slots__ = ("frames", "open", "seats")

    def __init__(
        self, tables: PdaTables, text: str, fold: ModelFold[Any] | None = None
    ) -> None:
        super().__init__(tables, text, fold)
        self.frames: list[list[Any]] = []
        self.open: dict[int, list[Any]] = {}
        self.seats: dict[int, int] = {}

    def _enter(self, clone: FlatClone, out: list[object]) -> bool:
        """A frame opens where the cursor stands, at the depth of the stack."""
        depth = len(self.stack)
        entered = super()._enter(clone, out)
        if entered and len(self.stack) > depth and len(self.frames) < CEILING:
            seat = self.seats.setdefault(id(clone), len(self.seats))
            record = [self.pos, -1, depth, clone.name or "·", 1, seat]
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
