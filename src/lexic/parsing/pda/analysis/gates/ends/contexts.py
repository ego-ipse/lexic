"""Run contexts — the clone compiler's side of a loop decided at its run's end.

The analysis decides which loops read their run's end
(``Taxonomy.loops.run``); the gate
each one compiles to depends on what follows the occurrence it is cloned for.
A clone key therefore carries that context for the rules whose loops can see
it, and this tracks it down the compile: the context at each arm's end, what
it becomes at an item, and the gate a decided loop reads there. A grammar
with no such loop pays one emptiness test per item and keys every clone as
before.
"""

from __future__ import annotations

from typing import NamedTuple, Sequence

from lexic.ir import IrItem, IrLeaf, IrSelf
from lexic.parsing.pda.analysis.analysis import GrammarAnalysis
from lexic.parsing.pda.analysis.gates.ends.leads import (
    EOF_LEAD,
    Lead,
    RunContext,
    compose,
    lead_windows,
)
from lexic.parsing.pda.analysis.gates.ends.sites import RunSites, run_sites
from lexic.parsing.pda.core.charsets import CharSet

__all__ = ["Decided", "Ends", "RunContexts"]

type Ends = dict[CharSet, Lead | None]
"""What follows an arm's end, per run class."""

_NO_ENDS: Ends = {}
"""The shared empty context of a grammar no decided loop reads."""


class Decided(NamedTuple):
    """What a decided loop compiles to under one context.

    :ivar run: The loop's run class.
    :ivar windows: The take windows its run's end is read through — ``None``
        where no follower needs any of the run, so the whole run is the loop's.
    """

    run: CharSet
    windows: tuple[tuple[CharSet, ...], ...] | None


def _class_key(run: CharSet) -> tuple[bool, tuple[str, ...]]:
    """A deterministic order over run classes."""
    return run.negated, tuple(sorted(run.chars))


class RunContexts(IrLeaf[IrSelf, IrSelf]):
    """The run contexts one clone compile threads, and the gates they decide.

    :ivar loops: ``id(item)`` of each decided loop → its run class.
    :ivar sites: Run class → its :class:`~.sites.RunSites`, from the analysis.
    :ivar needs: Run class → the rules a decided loop over it can see the
        context of — the rules whose keys carry it.
    :ivar outer: What follows a clone compiled from outside any body: the
        start rule's end of input, or unknown in an island interior.
    :ivar here: What follows the item being compiled — the context of the
        rule it references, or of the arms of the group it is.
    :ivar ends: The arm-end contexts open, innermost last.
    """

    __slots__ = ("loops", "sites", "needs", "outer", "here", "ends")

    loops: dict[int, CharSet]
    sites: dict[CharSet, RunSites]
    needs: dict[CharSet, set[str]]
    outer: Ends
    here: Ends
    ends: list[Ends]

    def __init__(self, analysis: GrammarAnalysis) -> None:
        """Read the decided loops and their sites off ``analysis``."""
        self.loops = analysis.taxonomy.loops.run
        self.sites = {}
        self.needs = {}
        for run in sorted(set(self.loops.values()), key=_class_key):
            sites = run_sites(analysis, run)
            decided = {
                key: sites.loops[key] for key, of in self.loops.items() if of == run
            }
            self.sites[run] = sites
            self.needs[run] = sites.needs(decided)
        end = None if analysis.taxonomy.delegated else EOF_LEAD
        self.outer = dict.fromkeys(self.sites, end) if self.sites else _NO_ENDS
        self.here = self.outer
        self.ends = [_NO_ENDS]

    def begin(self, runs: RunContext) -> None:
        """Open a clone body whose key carries ``runs``."""
        self.ends = [dict(runs)]

    def at(self, items: Sequence[IrItem], at: int) -> None:
        """Compile item ``at`` of an arm next: what follows it, its own
        further occurrences first, per run class."""
        if not self.sites:
            return
        top = self.ends[-1]
        again = items[at].quantifier.repeats()
        self.here = {
            run: compose(sites.leads.solver.after(items, at, again), top.get(run))
            for run, sites in self.sites.items()
        }

    def push(self) -> None:
        """Open the arms of the group being compiled."""
        self.ends.append(self.here)

    def pop(self) -> None:
        """Close the innermost group."""
        self.ends.pop()

    def key(self, name: str, nested: bool) -> RunContext:
        """The runs part of rule ``name``'s clone key: under the item being
        compiled when ``nested``, else under :attr:`outer`."""
        if not self.sites:
            return ()
        ends = self.here if nested else self.outer
        return tuple((run, ends[run]) for run in self.sites if name in self.needs[run])

    def gate(self, items: Sequence[IrItem], at: int) -> Decided | None:
        """What a decided loop at item ``at`` reads under the open context —
        its run class and take windows, or no windows where no follower needs
        any of the run — or ``None`` for any other item."""
        run = self.loops.get(id(items[at]))
        if run is None:
            return None
        ahead = self.sites[run].leads.solver.after(items, at, False)
        return Decided(run, lead_windows(run, compose(ahead, self.ends[-1].get(run))))
