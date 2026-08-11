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
from lexic.parsing.fold import ModelFold
from lexic.parsing.pda.compiler.flatten import FlatClone
from lexic.parsing.pda.compiler.tables import PdaTables
from lexic.parsing.pda.core.errors import PdaFail
from lexic.parsing.pda.runtime.kernel.kernel import PdaKernel

__all__ = ["Clock", "watch"]

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
