"""Tests for lexic.parsing.pda.runtime.kernel.decisions — the attempt/probe
decision half of ``PdaKernel``.

``Attempting``'s methods read the live kernel cursor's state (``pos``,
``stack``, ``_caches``) and are exercised end to end through real parses in
``tests/unit/lexic/parsing/pda/test_group_attempt.py`` and the parity suite;
this file targets the loop-close bookkeeping, an island iteration's bail, and
what a sub-run writes for the verdict to read. The verdict itself is
:mod:`lexic.parsing.pda.runtime.kernel.verdicts`'s, and its tests beside it.
"""

from __future__ import annotations

from typing import Never

import pytest

from lexic.parsing.pda.compiler.program.flatten import FlatArm, FlatClone
from lexic.parsing.pda.compiler.program.opcodes import (
    OP_ISLAND,
)
from lexic.parsing.pda.compiler.specs import IslandPayload
from lexic.parsing.pda.core.errors import ProbeFork
from lexic.parsing.pda.runtime.admission import KernelCaches
from lexic.parsing.pda.runtime.build import Frame
from lexic.parsing.pda.runtime.kernel.decisions import (
    Attempting,
)
from lexic.parsing.pda.runtime.kernel.kernel import PdaKernel
from tests.unit.lexic.parsing.pda.runtime.flat_support import flat_arm, flat_clone
from tools.benchmark.cases.grammars import BENCHES


def test_close_loop_resets_count_advances_i_and_records_the_end():
    """The frame's loop-close bookkeeping: count reset, ``i`` advanced, end recorded.

    Item ``i``'s end is ``ends[i + 1]``, because ``ends[0]`` is the frame's own
    span start — the layout that removes the first-item test from every reader.
    """
    frame = Frame(flat_arm(3), [], flat_clone(), 0)
    frame.count = 5
    result = frame.close_loop(1, 42)
    assert result == 2
    assert frame.count == 0
    assert frame.i == 2
    ends = frame.ends
    assert ends is not None  # this clone keeps boundaries
    assert ends[2] == 42


class _IslandUndecidable(Attempting[str]):
    """An attempted island iteration whose sub-parse finds two ends, either
    of which could compose: the island raises ``ProbeFork``."""

    __slots__ = ("text", "pos", "stack")

    def __init__(self, text: str) -> None:
        self.text = text
        self.pos = 0
        self.stack = []

    def _stop_viable(self, arm: FlatArm, i: int, pos: int) -> bool:
        return False  # the one-character stop test says nothing here

    def _enter(self, clone: FlatClone[str], out: list[str]) -> bool:
        raise AssertionError("an island iteration pushes no frame")

    def _drive(self, floor: int = 0, limit: int = -1) -> None:
        raise AssertionError("an island iteration drives nothing")

    def _sink_for(self, frame: Frame[str], arm: FlatArm, i: int) -> list[str]:
        return []

    def _island(self, ref: IslandPayload, sink: list[str]) -> None:
        raise ProbeFork("island spans two ends and the shorter could compose", 0)

    def _island_value(self, name: str, tree: object, built: object) -> Never:
        raise AssertionError("an island iteration that bails splices nothing")


def test_an_attempted_island_that_cannot_settle_bails_instead_of_closing() -> None:
    """Read as a failed iteration, the refusal closed the loop at the current
    count and committed a carving the gated engine had been asked to decide."""
    arm = flat_arm(
        1,
        kinds=(OP_ISLAND,),
        los=(0,),
        his=(-1,),
        gate_data=(((frozenset("a"), False), (frozenset(), False)),),
        payloads=(None,),
    )
    frame: Frame[str] = Frame(arm, [], flat_clone(), 0)
    with pytest.raises(ProbeFork):
        _IslandUndecidable("a").attempt_iteration(frame, arm, 0, 0)


def test_a_program_that_cannot_fork_marks_no_sub_run(monkeypatch) -> None:
    """A fork is an attempted loop's boundary, so markdown — attempt entries,
    no item gated ``GATE_ATTEMPT`` — flags no clone ``sub_root``: its
    sub-runs push frames that carry no start, and its audits hold no record."""
    real_drive = next(
        vars(c)["_drive"] for c in PdaKernel.__mro__ if "_drive" in vars(c)
    )
    real_init = KernelCaches.__init__
    seen = {"frames": 0, "marked": 0, "records": 0}

    class Audits(list):
        """The audit stack, counting what is pushed on it."""

        def append(self, record) -> None:
            seen["records"] += 1
            super().append(record)

    def init(self) -> None:
        real_init(self)
        self.audits = Audits()

    def drive(self, floor: int = 0, limit: int = -1) -> None:
        if floor:  # a sub-run's drive: its root frame sits at the floor
            seen["frames"] += 1
            seen["marked"] += hasattr(self.stack[floor], "start")
        return real_drive(self, floor, limit)

    monkeypatch.setattr(KernelCaches, "__init__", init)
    monkeypatch.setattr(PdaKernel, "_drive", drive)
    bench = next(b for b in BENCHES if b.name == "markdown")
    bench.compiled.parse(bench.corpus, cores=1)
    assert seen["frames"] and not seen["marked"] and not seen["records"], seen
